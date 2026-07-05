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

    chart = page.locator("canvas").first
    expect(chart).to_be_visible(timeout=60000)
    box = chart.bounding_box()
    assert box is not None
    assert box["width"] > 700

    page.get_by_role("group", name="Click to view actions").get_by_role("img").click()
    with page.expect_download() as download_info:
        page.get_by_role("link", name="Save as PNG").click()
    download = download_info.value
    assert download.suggested_filename.endswith(".png")

    page.get_by_role("button", name="Full dataframe and download").click()
    page.get_by_role("button", name="Export").click()
    with page.expect_download() as csv_download_info:
        page.get_by_role("menuitem", name="CSV").first.click()
    assert csv_download_info.value.suggested_filename.endswith(".csv")
