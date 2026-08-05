"""Shared configuration for the unit tests.

The HTTP-backed tests use pytest-recording (vcrpy) so that they exercise ERDDAP
request and response shapes including errors.

Re-record with::

    pixi run unit-rerecord    # all cassettes
    pixi run unit-record-new  # only the missing ones
"""

import pytest


@pytest.fixture(scope="module")
def vcr_config():
    """Keep cassettes small and free of anything environment specific."""
    return {
        "filter_headers": ["authorization", "cookie", "user-agent"],
        "decode_compressed_response": True,
    }
