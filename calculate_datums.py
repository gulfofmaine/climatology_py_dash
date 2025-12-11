import marimo

__generated_with = "0.14.0"
app = marimo.App(width="medium")


@app.cell
def _():
    from collections import OrderedDict

    import marimo as mo
    import erddapy
    import tadc
    import pandas as pd

    import common

    return OrderedDict, common, erddapy, mo, pd, tadc


@app.cell
def _(mo):
    mo.md(
        r"""
    # Datum calculator

    Uses CO-OPs [Tidal Analysis Datum Calculator (TADC)](https://github.com/NOAA-CO-OPS/CO-OPS-Tidal-Analysis-Datum-Calculator/) to calculate datums for tidal datasets within our ERDDAP server.

    TADC has some of it's own QC, so QARTOD may not be useful or needed.
    """,
    )
    return


@app.cell
def _(common):
    common.set_defaults()
    common.sidebar_menu()
    return


@app.cell
def _(erddapy, mo, pd):
    with mo.status.spinner("Loading dataset info..."):
        e_search = erddapy.ERDDAP(
            server="https://data.neracoos.org/erddap",
            protocol="tabledap",
        )
        url = e_search.get_search_url(search_for="navd88_meters", response="csv")
        search_df = pd.read_csv(url)
    return (search_df,)


@app.cell
def _(search_df):
    datasets = (
        search_df[["Title", "Dataset ID"]].set_index("Title").to_dict()["Dataset ID"]
    )
    # datasets
    return (datasets,)


@app.cell
def _(OrderedDict, datasets, mo):
    dataset_dropdown = mo.ui.dropdown(options=OrderedDict(sorted(datasets.items())))
    return (dataset_dropdown,)


@app.cell
def _(mo):
    use_qartod = mo.ui.checkbox(label="Apply QARTOD constraints?")
    return (use_qartod,)


@app.cell
def _(dataset_dropdown, mo, use_qartod):
    mo.hstack([dataset_dropdown, use_qartod])
    return


@app.cell
def _(dataset_dropdown):
    dataset_id = dataset_dropdown.value
    return (dataset_id,)


@app.cell
def _(dataset_id, erddapy, mo, use_qartod):
    mo.stop(dataset_id is None)
    e = erddapy.ERDDAP(
        server="https://data.neracoos.org/erddap",
        protocol="tabledap",
        response="csv",
    )
    e.dataset_id = dataset_id
    e.variables = ["time", "latitude", "longitude", "navd88_meters"]
    e.constraints = {"qartod_qc_rollup=": 1} if use_qartod.value else {}
    try:
        with mo.status.spinner("Loading data..."):
            df = e.to_pandas(index_col="time (UTC)", parse_dates=True).dropna()
    except Exception as e:
        mo.output.append(f"Error loading data: {e}")
    # df
    return (df,)


@app.cell
def _(df, mo):
    try:
        latitude = df["latitude (degrees_north)"].mean()
    except NameError:
        mo.stop(True)
    return (latitude,)


@app.cell
def _(df):
    longitude = df["longitude (degrees_east)"].mean()
    return (longitude,)


@app.cell
def _(df):
    df_reset = df.reset_index()[["time (UTC)", "navd88_meters (m)"]]
    return (df_reset,)


@app.cell
def _(common, df_reset, latitude, longitude, mo, tadc):
    try:
        with mo.redirect_stderr(), mo.redirect_stdout():
            out = tadc.run(
                data=df_reset,
                Subordinate_Lat=latitude,
                Subordinate_Lon=longitude,
            )
    except Exception as e:
        mo.output.append(
            common.admonition(
                kind="error",
                title="Error",
                content=f"Error trying to calculate datums: {e}",
            ),
        )
    return (out,)


@app.cell
def _(mo, out):
    mo.ui.table([{"datum": k, "NAVD88 meters": v} for k, v in out.datums.items()])
    return


@app.cell
def _(df, mo, out):
    mo.accordion(
        {
            "Calculation Details": mo.md(
                f"""
    ```
    {out.readme}
    ```
    """,
            ),
            "Source data": df,
        },
    )
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
