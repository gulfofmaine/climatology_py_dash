"""
End-to-end tests for the Climatology page of the application.
"""

from helpers import assert_chart_rendered, download_chart_png
from playwright.sync_api import Page, expect


def test_western_maine_shelf_air(page: Page) -> None:
    page.goto("/")
    page.get_by_role("navigation").get_by_role("link", name="Climatology").click()
    expect(page).to_have_url("/climatology/")
    page.get_by_label("Platform").select_option("Western Maine Shelf")
    page.get_by_label("Data Type").select_option("Air Temperature")
    expect(page).to_have_url(
        "/climatology/?platform=Western+Maine+Shelf&ts=Air+Temperature",
    )

    assert_chart_rendered(page)

    assert download_chart_png(page).suggested_filename.endswith(".png")
