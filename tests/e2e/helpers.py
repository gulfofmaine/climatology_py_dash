"""Shared helpers for the end-to-end Playwright tests."""

import time

from playwright.sync_api import Download, Locator, Page, expect

# A full-width chart is ~750px on the 1280px test viewport; the narrow-chart
# regression (Vega's default when width isn't set to "container") is ~400px.
# 600 cleanly separates the two.
MIN_CHART_WIDTH = 600

# How many identical bounding boxes in a row mean the chart has stopped moving.
# Two was not enough on CI: the canvas can report the same width twice while
# still sliding down the page as the surrounding cell grows.
SETTLED_SAMPLES = 3
SAMPLE_INTERVAL_MS = 300
SETTLE_TIMEOUT_S = 60


def wait_for_chart_settled(page: Page) -> Locator:
    """Return the first vega chart canvas once its geometry has stopped changing.

    Vega renders once at a default width and then re-renders at the container
    width via a resize observer, detaching and replacing the ``<canvas>`` in the
    process. ``bounding_box()`` therefore transiently returns ``None`` (or a
    pre-resize box) right after the canvas becomes visible, which is flaky on
    slower CI runners.

    Compare the *whole* box rather than just the width: a steady width tells us
    nothing about position, and overlays anchored to the chart -- notably the
    Vega actions menu -- keep moving while it settles, which is what defeats
    Playwright's click stability check.
    """
    chart = page.locator("canvas").first
    expect(chart).to_be_visible(timeout=60000)

    deadline = time.monotonic() + SETTLE_TIMEOUT_S
    last_box = None
    repeats = 1
    while time.monotonic() < deadline:
        box = chart.bounding_box()
        if box is not None and box == last_box:
            repeats += 1
            if repeats >= SETTLED_SAMPLES:
                return chart
        else:
            repeats = 1
        last_box = box
        page.wait_for_timeout(SAMPLE_INTERVAL_MS)

    msg = (
        f"chart canvas never reported {SETTLED_SAMPLES} identical bounding boxes "
        f"within {SETTLE_TIMEOUT_S}s (last box: {last_box})"
    )
    raise AssertionError(msg)


def assert_chart_rendered(page: Page, *, min_width: int = MIN_CHART_WIDTH) -> None:
    """Assert the first vega chart rendered without errors and fills its container."""
    expect(page.get_by_text("Duplicate signal name")).to_have_count(0)

    chart = wait_for_chart_settled(page)

    box = chart.bounding_box()
    assert box is not None, "chart canvas reported no bounding box once settled"
    assert box["width"] > min_width, (
        f"chart width {box['width']} <= {min_width}; expected a full-width chart"
    )


def download_chart_png(page: Page) -> Download:
    """Open the Vega actions menu and download the chart as a PNG.

    The menu is anchored to the chart, so it keeps moving while Vega re-renders
    and Playwright's stability check never settles -- the click then times out
    after 30s. Wait for the chart to settle, assert the menu actually opened,
    then click past the stability wait. ``expect_download`` still fails if no
    download starts, so nothing is weakened by forcing the click.
    """
    wait_for_chart_settled(page)

    page.get_by_role("group", name="Click to view actions").get_by_role("img").click()

    save_as_png = page.get_by_role("link", name="Save as PNG")
    expect(save_as_png).to_be_visible()

    with page.expect_download() as download_info:
        save_as_png.click(force=True)

    return download_info.value
