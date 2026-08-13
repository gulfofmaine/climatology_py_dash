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

    _assert_chart_fits_wrapper(chart)


def _assert_chart_fits_wrapper(chart: Locator) -> None:
    """Assert the settled canvas is no wider than the wrapper that scrolls it.

    "Fills its container" has to mean *fills*, not *overflows*. Vega-Lite only
    compiles width="container" into an autosize: fit-x for single and layered
    views, so a vconcat sized that way makes each row's plotting area the full
    container width and lets the axes, legend and padding spill ~190px past it
    -- cropping the chart's right edge (#162). Nothing else here catches that:
    the min_width check above only gets wider when the canvas overflows.

    Measure against div.chart-wrapper, the overflow-x: auto element vega-embed
    wraps the canvas in, since that is what does the cropping. scrollWidth
    exceeding clientWidth is the direct statement of "this wrapper is scrolling
    because its content does not fit".
    """
    # The canvas lives in a shadow root, so document.querySelector() inside the
    # page never finds it -- hand the element Playwright already pierced to
    # evaluate() as an argument instead of re-querying from document.
    measured = chart.evaluate(
        """(canvas) => {
            const wrapper = canvas.closest(".chart-wrapper");
            if (!wrapper) return null;
            return {
                canvas: canvas.getBoundingClientRect().width,
                clientWidth: wrapper.clientWidth,
                scrollWidth: wrapper.scrollWidth,
            };
        }""",
    )
    assert measured is not None, (
        "chart canvas has no .chart-wrapper ancestor; vega-embed's DOM shape "
        "changed and this assertion needs updating"
    )

    # A pixel of slack: widths are fractional and clientWidth is rounded.
    slack = 2
    assert measured["canvas"] <= measured["clientWidth"] + slack, (
        f"chart canvas is {measured['canvas']}px wide but its .chart-wrapper is "
        f"only {measured['clientWidth']}px; the chart is overflowing and its "
        f"right edge is cropped"
    )
    assert measured["scrollWidth"] <= measured["clientWidth"] + slack, (
        f".chart-wrapper scrollWidth {measured['scrollWidth']}px exceeds its "
        f"clientWidth {measured['clientWidth']}px; chart content overflows it"
    )


def assert_hover_tooltip_appears(page: Page) -> None:
    """Move the mouse over the settled chart and confirm a tooltip shows.

    by_platform.py stacks one subplot per unit in a single canvas, so the
    exact vertical center can land in the gap between rows rather than on
    either plot -- try a few y positions rather than only the center.
    """
    chart = wait_for_chart_settled(page)
    box = chart.bounding_box()
    assert box is not None, "chart canvas reported no bounding box once settled"

    tooltip = page.locator("#vg-tooltip-element")
    for y_fraction in (0.5, 0.25, 0.75, 0.15, 0.85):
        page.mouse.move(0, 0)
        page.mouse.move(
            box["x"] + box["width"] / 2,
            box["y"] + box["height"] * y_fraction,
            steps=5,
        )
        page.wait_for_timeout(300)
        if tooltip.is_visible():
            return

    expect(tooltip).to_be_visible()


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
