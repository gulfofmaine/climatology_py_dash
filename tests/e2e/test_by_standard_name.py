import re

from helpers import (
    assert_chart_rendered,
    assert_hover_tooltip_appears,
    download_chart_png,
    hover_for_tooltip,
)
from playwright.sync_api import Page, expect


def test_air_temp(page: Page) -> None:
    page.goto("/")
    page.get_by_role("navigation").get_by_role("link", name="By Data Type").click()
    expect(
        page.get_by_role("heading", name="Visualize and Compare by Data"),
    ).to_be_visible()

    page.get_by_test_id("marimo-plugin-dropdown").select_option(
        "Air Temperature - air_temperature",
    )
    expect(page).to_have_url("/by_standard_name/?standard_name=air_temperature")

    page.get_by_text("Select...").click()
    page.get_by_role("option", name="44007").click()
    page.get_by_role("option", name="44008").click()
    page.get_by_role("listbox", name="Suggestions").press("Escape")

    expect(page.get_by_text("Resampled to daily means for")).to_be_visible()

    assert_chart_rendered(page)
    assert_hover_tooltip_appears(page)

    assert download_chart_png(page).suggested_filename.endswith(".png")

    page.get_by_role("button", name="Full dataframe and download").click()
    page.get_by_role("button", name="Export").click()
    with page.expect_download() as csv_download_info:
        page.get_by_role("menuitem", name="CSV").first.click()
    assert csv_download_info.value.suggested_filename.endswith(".csv")


def test_unit_toggle_switches_the_displayed_unit(page: Page) -> None:
    """The unit names the melted frame's value column, so it reaches the chart
    and the tooltip through the one string -- and the tooltip is the only place
    the DOM can see it, the chart being a canvas."""
    page.goto("/by_standard_name/?standard_name=air_temperature")

    page.get_by_text("Select...").click()
    page.get_by_role("option", name="44007").click()
    page.get_by_role("listbox", name="Suggestions").press("Escape")

    expect(hover_for_tooltip(page)).to_contain_text("(°F)")

    page.get_by_role("radio", name="Metric").click()
    expect(page).to_have_url(re.compile(r"units=Metric"))

    expect(hover_for_tooltip(page)).to_contain_text("(°C)")
