"""Unit tests for the Sentry wiring.

No test here needs a network connection or a real Sentry project: the
``sentry_events`` fixture (see conftest.py) installs a throwaway client backed
by an in-process transport, and everything else is a pure function of
environment variables or of objects built by hand.
"""

import inspect
import json
import re

import pytest
import sentry_sdk
from marimo._messaging.errors import MarimoAncestorStoppedError
from marimo._runtime.control_flow import MarimoInterrupt, MarimoStopError
from marimo._runtime.runner import hooks_post_execution
from marimo._runtime.runner.hooks import create_default_hooks

import monitoring


class FakeCell:
    def __init__(self, cell_id="abc"):
        self.cell_id = cell_id


class FakeRunResult:
    def __init__(self, exception):
        self.exception = exception


# --- init_sentry ------------------------------------------------------------


def test_init_sentry_is_a_noop_without_a_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    sentry_sdk.get_global_scope().set_client(None)

    assert monitoring.init_sentry() is False
    assert sentry_sdk.get_client().is_active() is False


def test_init_sentry_is_idempotent_per_process(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setattr(monitoring._state, "initialised_pid", None)
    monkeypatch.setattr(monitoring._state, "hook_installed", False)

    try:
        assert monitoring.init_sentry() is True
        client = sentry_sdk.get_client()
        assert monitoring.init_sentry() is True
        assert sentry_sdk.get_client() is client
    finally:
        sentry_sdk.get_global_scope().set_client(None)


# --- sentry_options -----------------------------------------------------


def test_sentry_options_disables_pii_and_request_bodies():
    options = monitoring.sentry_options(
        monitoring.Settings(dsn="https://public@example.invalid/1"),
    )

    assert options["send_default_pii"] is False
    assert options["max_request_body_size"] == "never"


def test_sentry_options_carries_environment_and_release():
    options = monitoring.sentry_options(
        monitoring.Settings(
            dsn="https://public@example.invalid/1",
            environment="staging",
            release="abc123",
        ),
    )

    assert options["environment"] == "staging"
    assert options["release"] == "abc123"


# --- _traces_sampler ------------------------------------------------------


def test_traces_sampler_drops_health_checks():
    rate = monitoring._traces_sampler(
        {"asgi_scope": {"type": "http", "path": "/health"}},
    )
    assert rate == 0.0


def test_traces_sampler_drops_static_assets():
    rate = monitoring._traces_sampler(
        {"asgi_scope": {"type": "http", "path": "/assets/index.js"}},
    )
    assert rate == 0.0


def test_traces_sampler_drops_websockets():
    """One websocket per open browser tab, held for the tab's whole life --
    sampling those would produce hours-long, span-less transactions."""
    rate = monitoring._traces_sampler(
        {"asgi_scope": {"type": "websocket", "path": "/ws"}},
    )
    assert rate == 0.0


def test_traces_sampler_uses_the_configured_rate_for_everything_else(monkeypatch):
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.4")
    rate = monitoring._traces_sampler(
        {"asgi_scope": {"type": "http", "path": "/climatology"}},
    )
    assert rate == 0.4


# --- _capture_cell_exception ----------------------------------------------


def test_mo_stop_is_not_reported(sentry_events):
    monitoring._capture_cell_exception(
        FakeCell(),
        None,
        FakeRunResult(MarimoStopError(None)),
    )
    sentry_sdk.flush()
    assert sentry_events == []


def test_an_interrupt_is_not_reported(sentry_events):
    """MarimoInterrupt is an alias for KeyboardInterrupt."""
    monitoring._capture_cell_exception(
        FakeCell(),
        None,
        FakeRunResult(MarimoInterrupt()),
    )
    sentry_sdk.flush()
    assert sentry_events == []


def test_a_marimo_error_dataclass_is_not_reported(sentry_events):
    """Cascade notices ("an ancestor raised...") are dataclasses, not
    exceptions, so they are excluded before the control-flow check even runs."""
    cascade = MarimoAncestorStoppedError(msg="stopped", raising_cell="cell-1")
    monitoring._capture_cell_exception(FakeCell(), None, FakeRunResult(cascade))
    sentry_sdk.flush()
    assert sentry_events == []


def test_a_real_cell_exception_is_reported(sentry_events):
    try:
        msg = "boom"
        raise ValueError(msg)
    except ValueError as error:
        monitoring._capture_cell_exception(
            FakeCell(cell_id="cell-42"),
            None,
            FakeRunResult(error),
        )
    sentry_sdk.flush()

    assert len(sentry_events) == 1
    event = sentry_events[0]
    assert event["exception"]["values"][0]["type"] == "ValueError"
    assert event["tags"]["marimo.cell_id"] == "cell-42"
    assert "marimo.page" in event["tags"]


def test_the_hook_never_raises_on_a_malformed_run_result(sentry_events):
    class Weird:
        pass

    monitoring._capture_cell_exception(FakeCell(), None, Weird())
    sentry_sdk.flush()
    assert sentry_events == []


# --- report() ---------------------------------------------------------------


def test_report_sets_level_fingerprint_and_tags(sentry_events):
    try:
        msg = "erddap is down"
        raise RuntimeError(msg)
    except RuntimeError as error:
        monitoring.report(
            error,
            where="erddap.load_ts",
            level="warning",
            fingerprint=["erddap-load", "https://data.neracoos.org/erddap"],
            dataset="A01_met_all",
        )
    sentry_sdk.flush()

    assert len(sentry_events) == 1
    event = sentry_events[0]
    assert event["level"] == "warning"
    assert event["fingerprint"] == ["erddap-load", "https://data.neracoos.org/erddap"]
    assert event["tags"]["where"] == "erddap.load_ts"
    assert event["tags"]["dataset"] == "A01_met_all"


def test_report_defaults_to_error_level(sentry_events):
    try:
        msg = "tadc blew up"
        raise RuntimeError(msg)
    except RuntimeError as error:
        monitoring.report(error, where="calculate_datums.tadc_run")
    sentry_sdk.flush()

    assert sentry_events[0]["level"] == "error"


# --- marimo upgrade canaries ------------------------------------------------
#
# These walk the same private chain install_marimo_hook() depends on. If a
# marimo upgrade moves any of it, these fail loudly in CI instead of
# notebook cell errors silently going unreported in production.


def test_marimo_still_exposes_the_post_execution_hook_list():
    assert isinstance(hooks_post_execution.POST_EXECUTION_HOOKS, list)


def test_our_hook_reaches_the_hooks_new_kernels_are_built_from(monkeypatch):
    monkeypatch.setattr(monitoring._state, "hook_installed", False)
    assert monitoring.install_marimo_hook() is True
    assert (
        monitoring._capture_cell_exception
        in create_default_hooks().post_execution_hooks
    )


def test_the_post_execution_hook_signature_is_still_three_arguments():
    hook = hooks_post_execution.POST_EXECUTION_HOOKS[0]
    assert len(inspect.signature(hook).parameters) == 3


# --- html_head ---------------------------------------------------------

FAKE_DSN = "https://public@example.invalid/1"
FAKE_LOADER_URL = "https://js.sentry-cdn.com/testtesttesttesttesttesttest0000.min.js"


def _configure(monkeypatch, *, dsn=FAKE_DSN, loader_url=FAKE_LOADER_URL):
    """Set (or, with None, unset) SENTRY_DSN and SENTRY_LOADER_URL together --
    html_head() and enabled() both require both."""
    for name, value in (("SENTRY_DSN", dsn), ("SENTRY_LOADER_URL", loader_url)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


@pytest.mark.parametrize("value", ["", "   ", None])
def test_html_head_is_none_without_a_dsn(monkeypatch, value):
    _configure(monkeypatch, dsn=value)

    assert monitoring.html_head() is None


@pytest.mark.parametrize("value", ["", "   ", None])
def test_html_head_is_none_without_a_loader_url(monkeypatch, value):
    _configure(monkeypatch, loader_url=value)

    assert monitoring.html_head() is None


def test_html_head_rejects_a_non_https_loader_url(monkeypatch, caplog):
    _configure(monkeypatch, loader_url="not-a-url")

    assert monitoring.html_head() is None
    assert "SENTRY_LOADER_URL" in caplog.text


def test_loader_url_env_accepts_the_whole_script_tag(monkeypatch):
    """Sentry's dashboard hands this out as a whole <script src="...">
    tag under the literal heading "Loader Script" -- pasting that as-is into
    SENTRY_LOADER_URL, rather than picking the URL back out of it, is the
    natural mistake to make. This is a real production incident: see the
    conversation this test was added from."""
    monkeypatch.setenv(
        "SENTRY_LOADER_URL",
        '<script src="https://js.sentry-cdn.com/abc123.min.js" '
        'crossorigin="anonymous"></script>',
    )

    assert (
        monitoring.Settings.from_env().loader_url
        == "https://js.sentry-cdn.com/abc123.min.js"
    )


def test_html_head_contains_the_loader_script_and_no_defer_or_async(monkeypatch):
    _configure(monkeypatch)

    head = monitoring.html_head()

    assert FAKE_LOADER_URL in head
    script_tag = re.search(r"<script src=.*?</script>", head).group()
    assert "defer" not in script_tag
    assert "async" not in script_tag


def test_html_head_does_not_embed_the_dsn(monkeypatch):
    """The loader URL has a DSN baked in server-side already; SENTRY_DSN here
    only toggles whether the snippet is injected at all, and may even name a
    different Sentry project (see README.md's local-testing note)."""
    _configure(monkeypatch)

    head = monitoring.html_head()

    assert FAKE_DSN not in head


def test_html_head_options_round_trip(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "test")
    monkeypatch.setenv("SENTRY_RELEASE", "abc123")

    head = monitoring.html_head()
    options = json.loads(re.search(r"var options = (\{.*?\});", head, re.S).group(1))

    assert options["environment"] == "test"
    assert options["release"] == "abc123"
    assert options["sendDefaultPii"] is False
    assert options["replaysSessionSampleRate"] == 0
    assert options["replaysOnErrorSampleRate"] == 1.0


def test_html_head_omits_environment_and_release_when_unset(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("SENTRY_RELEASE", raising=False)

    head = monitoring.html_head()
    options = json.loads(re.search(r"var options = (\{.*?\});", head, re.S).group(1))

    assert "environment" not in options
    assert "release" not in options


def test_html_head_neutralises_an_environment_containing_a_closing_script_tag(
    monkeypatch,
):
    """SENTRY_DSN no longer reaches the page (see test_html_head_does_not_embed_the_dsn),
    but SENTRY_ENVIRONMENT still does, so it is what exercises the escaping."""
    _configure(monkeypatch)
    monkeypatch.setenv("SENTRY_ENVIRONMENT", '"; </script><script>alert(1)//')

    head = monitoring.html_head()

    options_blob = head.split("var options = ", 1)[1].split(";\n", 1)[0]
    assert "</script>" not in options_blob


def test_enabled_agrees_with_html_head(monkeypatch):
    _configure(monkeypatch, dsn=None, loader_url=None)
    assert monitoring.enabled() is False
    assert monitoring.html_head() is None

    _configure(monkeypatch, dsn=FAKE_DSN, loader_url=None)
    assert monitoring.enabled() is False
    assert monitoring.html_head() is None

    _configure(monkeypatch)
    assert monitoring.enabled() is True
    assert monitoring.html_head() is not None
