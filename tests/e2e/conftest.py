"""Shared fixtures for the end-to-end Playwright tests.

The ``app_server`` fixture provides a base URL for the tests. By default it
starts the FastAPI/marimo app (``app:app``) in a subprocess on a free port and
tears it down afterwards. If the ``E2E_BASE_URL`` environment variable is set,
that URL is used as-is and no server is spawned -- handy for pointing the suite
at an already-running server or Docker container (e.g. in CI).

The subprocess runs the ``serve`` task from pyproject.toml, overriding only its
host and port arguments, so a local run serves ``public/`` through granian
exactly like the container does. Restating granian's static options here instead
would let the two drift, and the sidebar logo would 404 in only one of them.

``sentry_app_server`` (see tests/e2e/test_sentry.py) starts a second instance
the same way, but with a dummy ``SENTRY_DSN`` set, so the Sentry-specific tests
do not have to run against a DSN-less server the way the rest of the suite
does.
"""

import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Generator
from pathlib import Path

import pytest

# Repository root (two levels up from tests/e2e/conftest.py) so that the app's
# relative paths (./root.py, ./public/neracoos.png, ...) resolve.
REPO_ROOT = Path(__file__).resolve().parents[2]

# RFC 2606 reserves .invalid, so this DSN is structurally valid enough for the
# SDK to accept and configure the browser widget with, and can never resolve
# -- nothing an end-to-end run does with it can leave the machine.
SENTRY_E2E_DSN = "https://e2e00000000000000000000000000000@o0.ingest.invalid/1"


def _free_port() -> int:
    """Ask the OS for an unused TCP port and return it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_ready(url: str, timeout: float = 60.0) -> None:
    """Poll ``url`` with plain HTTP GETs until it responds or we time out."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                # Any HTTP response (even a 404) means the server is up.
                response.read(1)
                return
        except urllib.error.HTTPError:
            # Server responded with an HTTP status -- it is up.
            return
        except (urllib.error.URLError, ConnectionError, OSError) as error:
            last_error = error
            time.sleep(0.5)
    raise RuntimeError(
        f"App server at {url} did not become ready within {timeout}s"
        + (f" (last error: {last_error})" if last_error else ""),
    )


def _spawn_server(env: dict[str, str] | None = None) -> tuple[subprocess.Popen, str]:
    """Start a fresh ``pixi run serve`` on a free port and wait for it to answer.

    Extra ``env`` is layered on top of the current environment, so a caller can
    add e.g. ``SENTRY_DSN`` without losing ``PATH`` and friends.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    process = subprocess.Popen(
        ["pixi", "run", "serve", "127.0.0.1", str(port)],
        cwd=str(REPO_ROOT),
        # New session/process group so the whole tree can be signalled together.
        start_new_session=True,
        env={**os.environ, **(env or {})},
    )
    _wait_until_ready(base_url + "/", timeout=60.0)
    return process, base_url


@pytest.fixture(scope="session")
def app_server() -> Generator[str]:
    """Yield the base URL of the running app.

    Uses ``E2E_BASE_URL`` if set (no server spawned); otherwise starts granian
    in its own process group and cleans it up on teardown.
    """
    external_url = os.environ.get("E2E_BASE_URL")
    if external_url:
        yield external_url.rstrip("/")
        return

    process, base_url = _spawn_server()
    try:
        yield base_url
    finally:
        _terminate(process)


@pytest.fixture(scope="session")
def sentry_app_server() -> Generator[str | None]:
    """Base URL of a second app instance started with a dummy ``SENTRY_DSN``.

    Honours ``E2E_SENTRY_BASE_URL`` the way ``app_server`` honours
    ``E2E_BASE_URL``. Yields ``None`` (tests using this fixture should skip)
    when the main suite is pointed at an external server via ``E2E_BASE_URL``
    and no ``E2E_SENTRY_BASE_URL`` was given either -- there is then no way to
    start a second, differently configured instance.
    """
    external_url = os.environ.get("E2E_SENTRY_BASE_URL")
    if external_url:
        yield external_url.rstrip("/")
        return

    if os.environ.get("E2E_BASE_URL"):
        yield None
        return

    process, base_url = _spawn_server(
        {
            "SENTRY_DSN": SENTRY_E2E_DSN,
            "SENTRY_ENVIRONMENT": "e2e",
            "SENTRY_RELEASE": "e2e",
        },
    )
    try:
        yield base_url
    finally:
        _terminate(process)


def _terminate(process: subprocess.Popen) -> None:
    """Terminate the server process group cleanly, escalating to SIGKILL."""
    if process.poll() is not None:
        return
    try:
        pgid = os.getpgid(process.pid)
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
        process.wait(timeout=10)


@pytest.fixture(scope="session")
def base_url(app_server: str) -> str:
    """Override pytest-playwright's ``base_url`` so tests can use relative paths."""
    return app_server
