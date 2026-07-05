"""End-to-end smoke tests for the marimo multi-page app.

These drive a real browser against the running app (see ``conftest.py``) and
assert on the structural headings that render regardless of whether the live
external data (buoybarn / ERDDAP) has loaded. Generous timeouts are used
because marimo renders client-side over a websocket.
"""

import re
from collections.abc import Generator

import pytest
from playwright.sync_api import APIRequestContext, Page, Playwright, expect

# marimo renders asynchronously over a websocket, and the first visit to a
# page spins up a kernel and imports heavy libraries (matplotlib builds its
# font cache on first use, ...), so wait generously.
RENDER_TIMEOUT = 60_000

# (route, expected h1 heading text) for each mounted marimo app.
PAGES = [
    ("/", "NERACOOS Data Products"),
    ("/by_platform/", "Visualize and Compare by Buoy (beta)"),
    ("/by_standard_name/", "Visualize and Compare by Data Type (beta)"),
    ("/climatology/", "Climatology (beta)"),
    ("/calculate_datums/", "Datum calculator"),
]


@pytest.mark.parametrize(
    "route,heading",
    PAGES,
    ids=[route for route, _ in PAGES],
)
def test_page_heading_visible(page: Page, route: str, heading: str) -> None:
    """Each page renders its expected top-level heading."""
    page.goto(route)
    expect(page.get_by_role("heading", name=heading)).to_be_visible(
        timeout=RENDER_TIMEOUT,
    )


def test_sidebar_navigates_to_by_platform(page: Page) -> None:
    """The sidebar nav on / links to /by_platform and clicking it navigates."""
    page.goto("/")

    # Wait for the page to render before hunting for the nav link.
    expect(page.get_by_role("heading", name="NERACOOS Data Products")).to_be_visible(
        timeout=RENDER_TIMEOUT,
    )

    # The sidebar_menu()'s nav_menu renders a "By Buoy" link pointing at
    # /by_platform. Prefer the accessible-name locator over CSS classes.
    by_buoy_link = page.get_by_role("link", name="By Buoy")
    expect(by_buoy_link.first).to_be_visible(timeout=RENDER_TIMEOUT)

    by_buoy_link.first.click()

    # marimo may append a trailing slash / query params, so match flexibly.
    expect(page).to_have_url(re.compile(r"/by_platform/?"), timeout=RENDER_TIMEOUT)


@pytest.fixture
def api_request_context(
    playwright: Playwright,
    base_url: str,
) -> Generator[APIRequestContext, None, None]:
    """An APIRequestContext bound to the app's base URL.

    pytest-playwright does not ship one (and pytest's built-in ``request``
    fixture shadows the name Playwright's docs use), so build it explicitly.
    """
    context = playwright.request.new_context(base_url=base_url)
    yield context
    context.dispose()


def test_health_endpoint_returns_200(api_request_context: APIRequestContext) -> None:
    """The /health endpoint used by the Docker HEALTHCHECK returns 200."""
    response = api_request_context.get("/health")
    assert response.status == 200
