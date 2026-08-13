"""
End-to-end tests for the Climatology page of the application.
"""

import re

from helpers import assert_chart_rendered, download_chart_png
from playwright.sync_api import Page, expect

# The data table only appears once the climatology has been computed from a
# full ERDDAP load, which is slower than Playwright's default assertion wait.
RENDER_TIMEOUT = 60000


def test_western_maine_shelf_air(page: Page) -> None:
    page.goto("/")
    page.get_by_role("navigation").get_by_role("link", name="Climatology").click()
    expect(page).to_have_url("/climatology/")
    page.get_by_label("Platform").select_option("B01 - Western Maine Shelf")
    page.get_by_label("Data Type").select_option("Air Temperature")
    expect(page).to_have_url(
        "/climatology/?platform=B01+-+Western+Maine+Shelf&ts=Air+Temperature",
    )

    assert_chart_rendered(page)

    assert download_chart_png(page).suggested_filename.endswith(".png")


def test_unit_toggle_switches_the_displayed_unit(page: Page) -> None:
    """English by default, and the toggle reaches the data table as well as the
    chart -- the chart is a canvas, so its axis is not assertable from the DOM,
    but the table's column headers carry the same unit the axis does."""
    page.goto("/climatology/?platform=B01+-+Western+Maine+Shelf&ts=Air+Temperature")
    page.get_by_role("button", name="Show data").click()

    expect(
        page.get_by_role("columnheader").filter(has_text="(°F)").first,
    ).to_be_visible(
        timeout=RENDER_TIMEOUT,
    )

    page.get_by_role("radio", name="Metric").click()

    expect(page).to_have_url(re.compile(r"units=Metric"))
    expect(
        page.get_by_role("columnheader").filter(has_text="(°C)").first,
    ).to_be_visible(
        timeout=RENDER_TIMEOUT,
    )


def test_monthly_averaging_period(page: Page) -> None:
    """Monthly used to die on `clim_df["Date"]` after that column was renamed
    to "Month", so the whole averaging period was unreachable."""
    page.goto("/climatology/?platform=B01+-+Western+Maine+Shelf&ts=Air+Temperature")
    page.get_by_label("Averaging Time Period").select_option("Monthly")

    assert_chart_rendered(page)
