"""Shared fixtures for the end-to-end Playwright tests.

The ``app_server`` fixture provides a base URL for the tests. By default it
starts the FastAPI/marimo app (``app:app``) in a subprocess on a free port and
tears it down afterwards. If the ``E2E_BASE_URL`` environment variable is set,
that URL is used as-is and no server is spawned -- handy for pointing the suite
at an already-running server or Docker container (e.g. in CI).
"""

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# Repository root (two levels up from tests/e2e/conftest.py) so that the app's
# relative paths (./root.py, ./public/neracoos.png, ...) resolve.
REPO_ROOT = Path(__file__).resolve().parents[2]


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


@pytest.fixture(scope="session")
def app_server() -> str:
    """Yield the base URL of the running app.

    Uses ``E2E_BASE_URL`` if set (no server spawned); otherwise starts uvicorn
    in its own process group and cleans it up on teardown.
    """
    external_url = os.environ.get("E2E_BASE_URL")
    if external_url:
        yield external_url.rstrip("/")
        return

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(REPO_ROOT),
        # New session/process group so the whole tree can be signalled together.
        start_new_session=True,
    )

    try:
        _wait_until_ready(base_url + "/", timeout=60.0)
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
