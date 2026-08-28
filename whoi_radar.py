import marimo

__generated_with = "0.23.11"
app = marimo.App(width="medium", app_title="NERACOOS WHOI HF Radar")


@app.cell
def _():
    import marimo as mo

    import common
    import radar

    return common, mo, radar


@app.cell
def _(common):
    common.set_defaults(page="whoi_radar")
    common.sidebar_menu()


@app.cell
def _(mo):
    mo.md(
        r"""
    # WHOI HF Radar

    Daily surface current images from the Woods Hole Oceanographic Institution's
    high frequency radar.
    """,
    )


@app.cell
def _(mo, radar):
    with mo.status.spinner("Loading radar images..."):
        images = radar.latest_images(radar.LISTING_URL)
    return (images,)


@app.cell
def _(mo):
    # Which image the carousel is showing, starting on the newest. Held as
    # state rather than in a single widget so that every control on the page
    # moves the same carousel.
    #
    # allow_self_loops lets the thumbnail strip below update itself: marimo
    # normally skips re-running the cell that set the state, which left the
    # clicked thumbnail unhighlighted while the image above it did change.
    get_index, set_index = mo.state(0, allow_self_loops=True)
    return get_index, set_index


@app.cell
def _(images, mo, set_index):
    def _step(by):
        # Stops at either end rather than wrapping around, so it is always
        # obvious that you have reached the newest or oldest image.
        set_index(lambda index: max(0, min(index + by, len(images) - 1)))

    prev_button = mo.ui.button(label="◀ Previous", on_click=lambda _: _step(-1))
    next_button = mo.ui.button(label="Next ▶", on_click=lambda _: _step(1))
    mo.hstack([prev_button, next_button], justify="center")


@app.cell
def _(common, get_index, images, mo, radar):
    # Guards the lookup below: an empty folder is a normal answer for a radar
    # that does not run every day, not an error.
    mo.stop(
        not images,
        common.admonition(
            "There are no images in the folder this page reads from.",
            title="No images to show",
            kind="warning",
        ),
    )

    index = get_index()
    image = images[index]
    mo.vstack(
        [
            mo.image(src=image, width=700, caption=radar.filename(image)),
            mo.md(f"Image {index + 1} of {len(images)}"),
        ],
        align="center",
    )


@app.cell
def _(get_index, images, mo, radar, set_index):
    current = get_index()
    thumbnails = []
    for position, url in enumerate(images):
        # The browser loads each image once and scales it down here, rather
        # than the app fetching and resizing them, so the page never sits
        # between the image folder and the reader.
        thumbnails.append(
            mo.vstack(
                [
                    mo.image(src=url, width=88, alt=radar.filename(url)),
                    mo.ui.button(
                        label=str(position + 1),
                        kind="success" if position == current else "neutral",
                        tooltip=radar.filename(url),
                        # position is bound as a default argument so each
                        # button keeps its own; a bare `position` would leave
                        # every button pointing at the last image.
                        on_click=lambda _, position=position: set_index(position),
                    ),
                ],
                align="center",
                gap=0.25,
            ),
        )

    # Wrapped, since a fortnight of thumbnails does not fit one row.
    mo.hstack(thumbnails, justify="center", gap=0.5, wrap=True)


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
