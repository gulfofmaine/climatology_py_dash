import marimo

__generated_with = "0.13.15"
app = marimo.App(
    width="medium",
    app_title="NERACOOS Data Products",
    css_file="",
)


@app.cell
def _():
    import marimo as mo

    import common

    return common, mo


@app.cell
def _(common):
    common.sidebar_menu()
    return


@app.cell
def _():
    button_style = "display: inline-block; background-color: rgb(23, 133, 150); border-radius: 3px; padding: .5rem; text-align: center; color: white"
    column_style = "margin: 1rem; min-width: 200px"
    return button_style, column_style


@app.cell
def _(button_style, column_style, mo):
    mo.md(
        f"""
    # NERACOOS Data Products

    <div style="display: flex">
        <div style="{column_style}">
            <a href="https://mariners.neracoos.org/">
                <h3>Mariner's Dashboard</h3>
            </a>
            <p>Real-time buoy map with integrated 12-hour histories, wind & wave forecasts.</p>
            <a href="https://mariners.neracoos.org/">
                <button style="{button_style}">
                    View
                </button>
            </a>
        </div>
        <div style="{column_style}">
            <a href="https://data.neracoos.org/erddap/">
                <h3>ERDDAP</h3>
            </a>
            <p>Access and visualize historical NERACOOS data in various file formats.</p>
            <a href="https://data.neracoos.org/erddap/">
                <button style="{button_style}">
                    View
                </button>
            </a>
        </div>
        <div style="{column_style}">
            <a href="https://data.neracoos.org/thredds/">
                <h3>THREDDS</h3>
            </a>
            <p>Best for programmatic access to gridded datasets.</p>
            <a href="https://data.neracoos.org/thredds/">
                <button style="{button_style}">
                    View
                </button>
            </a>
        </div>
    </div>

    ## Visualize and compare (beta)

    <div style="display: flex">
        <div style="{column_style}">
            <a href="/by_platform/">
                <h3>By Buoy</h3>
            </a>
            <p>Visualize, compare, and download multiple data types by buoy.</p>
            <a href="/by_platform/">
                <button style="{button_style}">
                    View
                </button>
            </a>
        </div>
        <div style="{column_style}">
            <a href="/by_data_type/">
                <h3>By Data Type</h3>
            </a>
            <p>Visualize, compare, and download the same data type across multiple buoys.</p>
            <a href="/by_data_type/">
                <button style="{button_style}">
                    View
                </button>
            </a>
        </div>
        <div style="{column_style}">
            <a href="/climatology/">
                <h3>By Data Type</h3>
            </a>
            <p>Compare recent conditions to historical norms at buoy locations.</p>
            <a href="/climatology/">
                <button style="{button_style}">
                    View
                </button>
            </a>
        </div>
    </div>
    """,
    )
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
