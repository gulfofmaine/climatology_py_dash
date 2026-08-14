import re

from helpers import (
    assert_chart_rendered,
    assert_hover_tooltip_appears,
    download_chart_png,
    hover_for_tooltip,
)
from playwright.sync_api import Page, expect


def test_western_maine_shelf(page: Page) -> None:
    page.goto("/")
    page.get_by_role("navigation").get_by_role("link", name="By Buoy").click()
    expect(page).to_have_url("/by_platform/")
    page.get_by_test_id("marimo-plugin-dropdown").select_option(
        "B01 - Western Maine Shelf",
    )
    page.get_by_text("Select...").click()
    page.get_by_role("option", name="Air Temperature").click()
    page.get_by_role("option", name="Barometric Pressure").click()
    page.get_by_text("Resampled to weekly means for").click()

    assert_chart_rendered(page)
    assert_hover_tooltip_appears(page)

    assert download_chart_png(page).suggested_filename.endswith(".png")

    page.get_by_role("button", name="Full dataframe and download").click()
    page.get_by_role("button", name="Export").click()
    with page.expect_download() as csv_download_info:
        page.get_by_role("menuitem", name="CSV").first.click()
    assert csv_download_info.value.suggested_filename.endswith(".csv")


def test_unit_toggle_switches_the_displayed_unit(page: Page) -> None:
    """English by default. Barometric pressure is mb either way, so the pair
    also shows that only the family that has an English unit moves."""
    page.goto(
        "/by_platform/?platform=B01&ts=Air+Temperature%2CBarometric+Pressure",
    )

    tooltip = hover_for_tooltip(page)
    expect(tooltip).to_contain_text("(°F)")
    expect(tooltip).to_contain_text("(mb)")

    page.get_by_role("radio", name="Metric").click()
    expect(page).to_have_url(re.compile(r"units=Metric"))

    tooltip = hover_for_tooltip(page)
    expect(tooltip).to_contain_text("(°C)")
    expect(tooltip).to_contain_text("(mb)")
