"""Shared helpers for the end-to-end Playwright tests."""

import time

from playwright.sync_api import Page, expect

# A full-width chart is ~750px on the 1280px test viewport; the narrow-chart
# regression (Vega's default when width isn't set to "container") is ~400px.
# 600 cleanly separates the two.
MIN_CHART_WIDTH = 600


def assert_chart_rendered(page: Page, *, min_width: int = MIN_CHART_WIDTH) -> None:
    """Assert the first vega chart rendered without errors and fills its container.

    Vega renders once at a default width and then re-renders at the container
    width via a resize observer, detaching and replacing the ``<canvas>`` in the
    process. ``bounding_box()`` therefore transiently returns ``None`` (or a
    pre-resize width) right after the canvas becomes visible, which is flaky on
    slower CI runners. Poll until the width settles instead of sampling once.
    """
    expect(page.get_by_text("Duplicate signal name")).to_have_count(0)

    chart = page.locator("canvas").first
    expect(chart).to_be_visible(timeout=60000)

    deadline = time.monotonic() + 60
    stable_width = None
    last_width = None
    while time.monotonic() < deadline:
        box = chart.bounding_box()
        width = box["width"] if box else None
        if width and width == last_width:
            stable_width = width
            break
        last_width = width
        page.wait_for_timeout(250)

    assert stable_width is not None, "chart canvas never reported a stable width"
    assert stable_width > min_width, (
        f"chart width {stable_width} <= {min_width}; expected a full-width chart"
    )
