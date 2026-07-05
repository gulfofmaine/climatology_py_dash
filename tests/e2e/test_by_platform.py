from playwright.sync_api import Page, expect


def test_western_maine_shelf(page: Page) -> None:
    page.goto("/")
    page.get_by_role("navigation").get_by_role("link", name="By Buoy").click()
    expect(page).to_have_url("/by_platform/")
    page.get_by_test_id("marimo-plugin-dropdown").select_option("Western Maine Shelf")
    page.get_by_text("Select...").click()
    page.get_by_role("option", name="Air Temperature").click()
    page.get_by_role("option", name="Barometric Pressure").click()
    page.get_by_text("Resampled to weekly means for").click()
    page.locator("summary").click()

    with page.expect_download() as download_info:
        page.get_by_role("link", name="Save as PNG").click()
    download = download_info.value
    assert download.suggested_filename.endswith(".png")

    page.get_by_role("button", name="Full dataframe and download").click()
    page.get_by_role("button", name="Download", exact=True).click()
