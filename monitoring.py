"""Sentry wiring: errors, traces, logs, and the browser feedback widget.

Backend monitoring is a no-op when ``SENTRY_DSN`` is unset; the browser widget
additionally needs ``SENTRY_LOADER_URL`` (Sentry's hosted loader script for a
project, from that project's Loader Script settings). Local runs, the
devcontainer, and CI leave both unset, so none of them talk to Sentry or load
a third-party script.

marimo runs each notebook's cells on a kernel that is a *thread* of the server
process in run mode, not a subprocess (``marimo._session.managers.kernel``),
so a single ``init_sentry()`` call in ``app.py`` covers the ASGI server and
every notebook. But marimo never routes a cell's exception through
``logging`` -- ``cell_runner._finalize_run_result`` parks it on
``RunResult.exception`` and writes the traceback straight to the browser --
so no Sentry integration sees a cell failure on its own. ``install_marimo_hook``
below is what makes that visible; see its docstring for how and why.

Kernel-side tracing (``operation``) is deliberately out of scope for anything
beyond a handful of call sites: marimo's own reactive-run and preparation/
on-finish hooks would let a transaction span an entire user interaction, but
that is more private API for uncertain benefit and is left for a follow-up.
marimo's own OpenTelemetry support (``marimo._tracer``) is opt-in and would
double-instrument if enabled alongside this module.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from string import Template
from typing import TYPE_CHECKING, Any

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.threading import ThreadingIntegration

if TYPE_CHECKING:
    from collections.abc import Iterator

LOGGER = logging.getLogger(__name__)

# Paths that carry no signal and would otherwise dominate the trace budget:
# the k8s liveness/readiness/startup probes and the Docker HEALTHCHECK hit
# /health roughly every 10s, granian serves /static itself, and marimo serves
# /assets and /@file.
_UNTRACED_PATHS = frozenset({"/health", "/favicon.ico", "/public-files-sw.js"})
_UNTRACED_PREFIXES = ("/assets/", "/@file/", "/static/")

# marimo's control-flow signals, not failures:
# - MarimoStopError is how every page says "nothing selected yet" (mo.stop).
# - MarimoInterrupt is an alias for KeyboardInterrupt (marimo._runtime.control_flow).
# Both are BaseException-only, so `isinstance(exc, Exception)` already excludes
# them -- kept as a second, explicit check in case a future marimo reparents
# one of them under Exception.
try:
    from marimo._runtime.control_flow import MarimoInterrupt, MarimoStopError

    _CONTROL_FLOW_TYPES: tuple[type[BaseException], ...] = (
        MarimoStopError,
        MarimoInterrupt,
    )
except ImportError:
    _CONTROL_FLOW_TYPES = ()

# A tenth of page loads is enough to see how the app performs without
# spending the whole event quota on a public dashboard. Errors are always
# captured regardless of this setting -- it only governs performance traces.
_DEFAULT_TRACES_SAMPLE_RATE = 0.0


@dataclass
class _State:
    """Mutable process-wide state, kept in one object rather than as
    module-level names rebound with ``global`` (which ruff's PLW0603 flags).
    """

    initialised_pid: int | None = None
    hook_installed: bool = False


_state = _State()

# One kernel thread per notebook session in run mode, so a plain thread-local
# is enough to remember which page it is running -- Sentry's own Scope has no
# public API to read a tag back, only to write one.
_page = threading.local()


@dataclass(frozen=True)
class Settings:
    """Sentry configuration, read from the environment once per call.

    Kept as a plain object (rather than reading os.environ inline everywhere)
    so tests can construct one directly instead of monkeypatching the process
    environment for every case.
    """

    dsn: str = ""
    environment: str | None = None
    release: str | None = None
    traces_sample_rate: float = _DEFAULT_TRACES_SAMPLE_RATE
    # Sentry's hosted loader script for a project (Settings -> Loader Script
    # in the Sentry UI). It is a small, always-current shim: Sentry serves
    # updates behind this URL from their own CDN, so unlike a versioned
    # bundle there is no version or SRI hash to track and bump in this repo
    # -- the trust boundary is Sentry's CDN itself, same as for any other
    # hosted snippet. The DSN is baked into this URL server-side already;
    # Sentry.onLoad() in html_head() is what lets this file pin the
    # integrations and their options explicitly instead of trusting whatever
    # is toggled on the dashboard's Loader Script settings page. Example:
    # SENTRY_LOADER_URL=https://js.sentry-cdn.com/<key>.min.js
    loader_url: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            dsn=os.environ.get("SENTRY_DSN", "").strip(),
            environment=os.environ.get("SENTRY_ENVIRONMENT", "").strip() or None,
            release=os.environ.get("SENTRY_RELEASE", "").strip() or None,
            traces_sample_rate=_float_env(
                "SENTRY_TRACES_SAMPLE_RATE",
                _DEFAULT_TRACES_SAMPLE_RATE,
            ),
            loader_url=_loader_url_env("SENTRY_LOADER_URL"),
        )


def _float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        LOGGER.warning("Ignoring %s: %r is not a number", name, value)
        return default


# Sentry's own dashboard hands this out as a whole <script src="...
# crossorigin="anonymous"></script> tag under the literal heading "Loader
# Script" -- pasting that entire tag as the env var's value, rather than
# picking the URL back out of it, is the natural mistake. Tolerate it rather
# than merely warn about it.
_SCRIPT_SRC_RE = re.compile(r"""src\s*=\s*["']([^"']+)["']""")


def _loader_url_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    match = _SCRIPT_SRC_RE.search(value)
    return match.group(1) if match else value


def _traces_sampler(sampling_context: dict) -> float:
    asgi_scope = sampling_context.get("asgi_scope") or {}
    if asgi_scope:
        # One websocket per open browser tab, held for the tab's whole
        # lifetime -- sampling those produces hours-long transactions with no
        # spans in them.
        if asgi_scope.get("type") != "http":
            return 0.0
        path = asgi_scope.get("path", "")
        if path in _UNTRACED_PATHS or path.startswith(_UNTRACED_PREFIXES):
            return 0.0
    return Settings.from_env().traces_sample_rate


def _before_send_log(log: dict, _hint: dict) -> dict | None:
    # The `serve` pixi task runs granian with --access-log; at INFO that is one
    # access-log line per request, health probes included, and enable_logs
    # would otherwise ship every one of them to Sentry.
    name = (log.get("attributes") or {}).get("logger.name", "")
    if name.startswith(("granian.access", "uvicorn.access")):
        return None
    return log


def sentry_options(settings: Settings | None = None) -> dict:
    """The kwargs ``init_sentry`` passes to ``sentry_sdk.init``.

    Split out so tests can re-init with a fake DSN and a capturing transport
    without a network connection or a real Sentry project.
    """
    settings = settings or Settings.from_env()
    return {
        "dsn": settings.dsn,
        "environment": settings.environment,
        "release": settings.release,
        # Public, unauthenticated dashboard -- no client IPs, cookies, or
        # request bodies. The query string (platform, data type, date range)
        # still comes through on each event and is the real reproduction
        # payload.
        "send_default_pii": False,
        "max_request_body_size": "never",
        "traces_sampler": _traces_sampler,
        "enable_logs": True,
        "before_send_log": _before_send_log,
        "integrations": [
            # Kernel threads live for the whole browser session; with the
            # default (True) every event from a kernel would be permanently
            # stamped with the HTTP request that opened its websocket.
            ThreadingIntegration(propagate_scope=False),
            # Breadcrumbs and Sentry Logs, but no issues manufactured from log
            # records -- marimo's own LOGGER.exception calls still surface as
            # logs rather than duplicate issues.
            LoggingIntegration(
                level=logging.INFO,
                event_level=None,
                sentry_logs_level=logging.WARNING,
            ),
        ],
    }


def init_sentry() -> bool:
    """Start the Sentry SDK. Idempotent per process. False when there is no DSN.

    Skipping init entirely when the DSN is empty (rather than calling
    ``sentry_sdk.init(dsn="")``) means "off" is really off: no client, no
    patched Starlette middleware, no patched threading module.
    """
    settings = Settings.from_env()
    if not settings.dsn:
        return False
    if _state.initialised_pid == os.getpid():
        return True

    sentry_sdk.init(**sentry_options(settings))
    _state.initialised_pid = os.getpid()
    install_marimo_hook()
    return True


def enabled() -> bool:
    """Whether the browser widget is configured and will actually render.

    Used by common.admonition() to decide whether its "tell us what you were
    doing" link has anything to open -- which needs both variables, the same
    as html_head() below.
    """
    settings = Settings.from_env()
    return bool(settings.dsn) and bool(settings.loader_url)


def report(
    error: BaseException,
    *,
    where: str,
    level: str = "error",
    fingerprint: list[str] | None = None,
    **tags: str,
) -> None:
    """Report an exception that was handled and will not propagate.

    Wrapped in a fresh scope so tags never leak onto the next report made from
    the same long-lived kernel thread.
    """
    with sentry_sdk.isolation_scope() as scope:
        scope.set_tag("where", where)
        scope.set_level(level)
        for key, value in tags.items():
            scope.set_tag(key, value)
        if fingerprint:
            scope.fingerprint = fingerprint
        sentry_sdk.capture_exception(error)


def tag_page(page: str) -> None:
    """Tag every event from this kernel thread with the notebook page it came
    from. Call once per notebook (``common.set_defaults(page=...)`` does this).
    """
    _page.name = page
    sentry_sdk.get_isolation_scope().set_tag("marimo.page", page)


def _page_name() -> str:
    tagged = getattr(_page, "name", None)
    if tagged:
        return tagged
    try:
        from marimo._runtime.context.types import safe_get_context

        ctx = safe_get_context()
        if ctx is not None and ctx.filename:
            return ctx.filename
    except ImportError:
        pass
    return "unknown"


@contextlib.contextmanager
def operation(name: str, op: str = "task", **data: Any) -> Iterator[Any]:
    """A child span if a transaction is active, otherwise a new transaction.

    Kernel work runs on a thread with no HTTP request behind it -- there is
    usually nothing to be a child of -- so this opens whichever is needed. A
    fresh scope keeps a span from a previous cell run on the same reused
    kernel thread from becoming this one's parent.
    """
    if not sentry_sdk.get_client().is_active():
        yield None
        return

    active = sentry_sdk.get_current_span()
    with sentry_sdk.new_scope():
        starter = (
            sentry_sdk.start_span
            if active is not None
            else sentry_sdk.start_transaction
        )
        with starter(op=op, name=name) as span:
            for key, value in data.items():
                span.set_data(key, value)
            yield span


def install_marimo_hook() -> bool:
    """Report exceptions raised by notebook cells.

    marimo has no public hook-registration API, and it does not log cell
    exceptions -- ``cell_runner._finalize_run_result`` parks them on
    ``RunResult.exception`` and writes the formatted traceback straight to the
    frontend. Appending to the private list that
    ``marimo._runtime.runner.hooks.create_default_hooks`` copies into every
    kernel's hooks is the only way to see them. Kernels are built per session,
    after this module is imported at app startup, so they all pick this up.

    Returns False (rather than raising) if marimo's internals have moved --
    production then degrades to "no cell errors reported, plus one Sentry
    message saying so" instead of failing to boot. ``tests/unit/test_monitoring.py``
    is the real guard: it walks this same private chain, so a marimo upgrade
    that breaks it fails CI instead of silently disabling reporting.
    """
    if _state.hook_installed:
        return True
    try:
        from marimo._runtime.runner import hooks_post_execution as marimo_hooks

        hooks = marimo_hooks.POST_EXECUTION_HOOKS
        if not isinstance(hooks, list):
            msg = f"expected a list, got {type(hooks)}"
            raise TypeError(msg)
        if _capture_cell_exception not in hooks:
            hooks.append(_capture_cell_exception)
    except Exception:
        sentry_sdk.capture_message(
            "marimo's POST_EXECUTION_HOOKS is not where monitoring.py expects "
            "it; notebook cell errors are NOT being reported",
            level="error",
        )
        return False
    _state.hook_installed = True
    return True


def _capture_cell_exception(cell: Any, _ctx: Any, run_result: Any) -> None:
    try:
        exc = run_result.exception
        # marimo's Error dataclasses (cascade/cycle notices) are not
        # exceptions at all; mo.stop and interrupts are BaseException-only.
        # Either way, isinstance(exc, Exception) already excludes them --
        # _CONTROL_FLOW_TYPES is kept as a belt-and-braces second check.
        if not isinstance(exc, Exception) or isinstance(exc, _CONTROL_FLOW_TYPES):
            return
        with sentry_sdk.isolation_scope() as scope:
            scope.set_tag("marimo.page", _page_name())
            scope.set_tag("marimo.cell_id", str(getattr(cell, "cell_id", "?")))
            sentry_sdk.capture_exception(exc)
    except Exception:
        return  # monitoring must never break a notebook


_HEAD = Template("""
<link rel="preconnect" href="https://js.sentry-cdn.com" crossorigin>
<script src="$loader_url" crossorigin="anonymous"></script>
<script>
  // The loader is a small, synchronous shim: it registers window.Sentry and
  // queues onLoad callbacks immediately, then fetches the full SDK in the
  // background and runs this callback once it lands -- so, like the versioned
  // bundle this replaced, no defer/async is needed for Sentry's handlers to
  // be installed before marimo's own <script type="module"> boots.
  if (window.Sentry) {
    Sentry.onLoad(function () {
      var options = $options;
      options.integrations = [
        Sentry.browserTracingIntegration(),
        // Replays are only kept when something went wrong -- that is the
        // "what were they doing beforehand" the issue asks for, without
        // recording every visitor to a public dashboard.
        Sentry.replayIntegration({ maskAllText: true, blockAllMedia: true }),
        Sentry.feedbackIntegration({
          colorScheme: "system",
          showBranding: false,
          triggerLabel: "Report a problem",
          formTitle: "Report a problem",
          messagePlaceholder: "What were you trying to do?",
          isNameRequired: false,
          isEmailRequired: false
        })
      ];
      Sentry.init(options);
    });

    // marimo re-renders cells continuously, and runs everything it renders
    // through DOMPurify and then html-react-parser, which between them drop
    // inline onclick handlers -- a data attribute survives. Delegation from
    // here needs no element to exist at bind time, unlike Sentry's own
    // attachTo(), so it also covers the error admonitions common.py renders
    // (see common.admonition()).
    document.addEventListener("click", function (event) {
      var target = event.target;
      if (!target || !target.closest) { return; }
      var trigger = target.closest("[data-sentry-report]");
      if (!trigger) { return; }
      event.preventDefault();
      Sentry.onLoad(function () {
        var feedback = Sentry.getFeedback();
        if (!feedback) { return; }
        Promise.resolve(feedback.createForm({
          formTitle: "Report a problem",
          messagePlaceholder: "What were you doing when this happened?"
        })).then(function (form) {
          form.appendToDom();
          form.open();
        });
      });
    });
  }
</script>
""")


def html_head() -> str | None:
    """The <head> snippet for ``marimo.create_asgi_app(html_head=...)``.

    None unless both SENTRY_DSN and SENTRY_LOADER_URL are set, which is what
    keeps local runs, the devcontainer, and the CI end-to-end suite free of
    any third-party script.
    """
    settings = Settings.from_env()
    if not settings.dsn or not settings.loader_url:
        return None
    if not settings.loader_url.startswith("https://"):
        # Unlike the other settings below, this one is written straight into
        # an HTML attribute rather than through json.dumps -- refuse anything
        # that is not shaped like a URL rather than risk a malformed
        # SENTRY_LOADER_URL breaking out of the src="..." attribute.
        LOGGER.warning("Ignoring SENTRY_LOADER_URL: expected an https:// URL")
        return None

    # No "dsn" key: the loader URL already has one baked in server-side (see
    # Settings.loader_url). SENTRY_DSN only toggles whether this snippet is
    # injected at all -- it does not have to name the same Sentry project as
    # the loader, which matters when pointing SENTRY_DSN at a personal
    # project for local testing (see README.md): backend events follow it,
    # browser events still go to the project the loader is configured for.
    options: dict[str, Any] = {
        "tracesSampleRate": settings.traces_sample_rate,
        "replaysSessionSampleRate": 0,
        "replaysOnErrorSampleRate": 1.0,
        "sendDefaultPii": False,
        "ignoreErrors": [
            # Layout-thrash noise from chart resize observers, not a fault.
            # Chromium and Firefox word it differently.
            "ResizeObserver loop limit exceeded",
            "ResizeObserver loop completed with undelivered notifications",
        ],
    }
    if settings.environment:
        options["environment"] = settings.environment
    if settings.release:
        options["release"] = settings.release

    return _HEAD.substitute(
        loader_url=settings.loader_url,
        # json.dumps handles quotes, backslashes and control characters. It
        # leaves "<" alone, so a value containing "</script>" would close the
        # block early -- escaping "<" keeps the literal inert without
        # changing what it evaluates to.
        options=json.dumps(options).replace("<", "\\u003c"),
    )
