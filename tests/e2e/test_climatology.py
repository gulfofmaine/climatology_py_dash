"""
End-to-end tests for the Climatology page of the application.
"""

from helpers import assert_chart_rendered
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

    page.get_by_role("group", name="Click to view actions").get_by_role("img").click()
    with page.expect_download() as download_info:
        page.get_by_role("link", name="Save as PNG").click()
    download = download_info.value
    assert download.suggested_filename.endswith(".png")
