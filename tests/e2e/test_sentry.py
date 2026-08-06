"""End-to-end checks that the Sentry browser SDK is wired up correctly.

These run against a second app instance started with a dummy ``SENTRY_DSN``
(``sentry_app_server`` in conftest.py), so they do not interfere with the main
suite's DSN-less assertions in test_pages.py -- and so a broken Sentry
injection cannot make the primary pages fail to render.
"""

import os
from collections.abc import Generator

import pytest
from conftest import SENTRY_E2E_LOADER_URL
from playwright.sync_api import APIRequestContext, Playwright, expect


@pytest.fixture
def sentry_api_request_context(
    playwright: Playwright,
    sentry_app_server: str | None,
) -> Generator[APIRequestContext]:
    if sentry_app_server is None:
        pytest.skip(
            "no sentry_app_server available -- E2E_BASE_URL is set with no "
            "matching E2E_SENTRY_BASE_URL",
        )
    context = playwright.request.new_context(base_url=sentry_app_server)
    yield context
    context.dispose()


def test_sentry_script_is_injected(
    sentry_api_request_context: APIRequestContext,
) -> None:
    """With SENTRY_DSN and SENTRY_LOADER_URL set, the loader script is on the page.

    The loader's own URL has a DSN baked in server-side -- it is unrelated
    to, and does not have to match, the dummy SENTRY_DSN this app instance
    was started with.
    """
    body = sentry_api_request_context.get("/").text()
    assert SENTRY_E2E_LOADER_URL in body


@pytest.mark.skipif(
    os.environ.get("E2E_SENTRY_WIDGET") != "1",
    reason="loads the real Sentry SDK from its CDN -- opt in with E2E_SENTRY_WIDGET=1",
)
def test_feedback_widget_button_appears(
    playwright: Playwright,
    sentry_app_server: str | None,
) -> None:
    if sentry_app_server is None:
        pytest.skip("no sentry_app_server available")

    browser = playwright.chromium.launch()
    context = browser.new_context(base_url=sentry_app_server)
    page = context.new_page()
    try:
        page.goto("/")
        # Sentry's feedback widget renders into an open shadow root; the role
        # locator pierces it. Fall back to page.locator("#sentry-feedback")
        # if this ever misses on a real SDK version.
        expect(page.get_by_role("button", name="Report a problem")).to_be_visible(
            timeout=30_000,
        )
    finally:
        context.close()
        browser.close()
