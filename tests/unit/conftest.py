"""Shared configuration for the unit tests.

The HTTP-backed tests use pytest-recording (vcrpy) so that they exercise ERDDAP
request and response shapes including errors.

Re-record with::

    pixi run unit-rerecord    # all cassettes
    pixi run unit-record-new  # only the missing ones
"""

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

import monitoring


@pytest.fixture(scope="module")
def vcr_config():
    """Keep cassettes small and free of anything environment specific."""
    return {
        "filter_headers": ["authorization", "cookie", "user-agent"],
        "decode_compressed_response": True,
    }


class _CaptureTransport(Transport):
    """Collects captured events in-process, with no network call.

    A plain callable would work too, but sentry-sdk 2.x deprecates function
    transports with a warning, and ``filterwarnings = ["error"]`` turns that
    into a test failure.
    """

    def __init__(self):
        super().__init__()
        self.events = []

    def capture_envelope(self, envelope):
        event = envelope.get_event()
        if event is not None:
            self.events.append(event)


@pytest.fixture
def sentry_events(monkeypatch):
    """A list that fills with events captured by a throwaway Sentry client.

    Resets monitoring's per-process init guards so ``init_sentry()`` can be
    exercised fresh in each test, and tears the client back down afterwards so
    tests do not leak a client into one another.
    """
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("SENTRY_RELEASE", raising=False)
    monkeypatch.delenv("SENTRY_TRACES_SAMPLE_RATE", raising=False)
    monkeypatch.setattr(monitoring._state, "initialised_pid", None)
    monkeypatch.setattr(monitoring._state, "hook_installed", False)

    transport = _CaptureTransport()
    options = monitoring.sentry_options(
        monitoring.Settings(dsn="https://public@example.invalid/1", environment="test"),
    )
    options["transport"] = transport
    sentry_sdk.init(**options)
    try:
        yield transport.events
    finally:
        # sentry_sdk.init(dsn="") still constructs a real, "active" client --
        # only clearing the scope's client puts the SDK back into its
        # pre-init, disabled state for the next test.
        sentry_sdk.get_global_scope().set_client(None)
