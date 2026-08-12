import marimo

__generated_with = "0.23.11"
app = marimo.App(width="medium")


@app.cell
def _():
    from collections import OrderedDict

    import erddapy
    import marimo as mo
    import pandas as pd
    import tadc

    import common
    import monitoring

    return OrderedDict, common, erddapy, mo, monitoring, pd, tadc


@app.cell
def _(mo):
    mo.md(
        r"""
    # Datum calculator

    Uses CO-OPs [Tidal Analysis Datum Calculator (TADC)](https://github.com/NOAA-CO-OPS/CO-OPS-Tidal-Analysis-Datum-Calculator/) to calculate datums for tidal datasets within our ERDDAP server.

    TADC has some of it's own QC, so QARTOD may not be useful or needed.
    """,
    )


@app.cell
def _(common):
    common.set_defaults(page="calculate_datums")
    common.sidebar_menu()


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


@app.cell
def _(dataset_dropdown):
    dataset_id = dataset_dropdown.value
    return (dataset_id,)


@app.cell
def _(common, dataset_id, erddapy, mo, monitoring, use_qartod):
    mo.stop(
        dataset_id is None,
        common.admonition(
            "",
            title="Please select a dataset to calculate datums for",
            kind="warning",
        ),
    )
    monitoring.tag_context(dataset=dataset_id, qartod=str(use_qartod.value))
    e = erddapy.ERDDAP(
        server="https://data.neracoos.org/erddap",
        protocol="tabledap",
        response="csv",
    )
    e.dataset_id = dataset_id
    e.variables = ["time", "latitude", "longitude", "navd88_meters"]
    e.constraints = {"qartod_qc_rollup=": 1} if use_qartod.value else {}
    e.requests_kwargs = {"timeout": common.ERDDAP_TIMEOUT}
    with (
        mo.status.spinner("Loading data..."),
        monitoring.operation(
            "calculate_datums.load",
            op="http.client",
            dataset=dataset_id,
        ),
    ):
        try:
            df = e.to_pandas(index_col="time (UTC)", parse_dates=True).dropna()
        except Exception as error:
            # This is a raw erddapy load with no ErddapLoadError wrapper,
            # unlike common.load_ts_from_erddap -- report it directly, since
            # it otherwise never reaches Sentry. Stop rather than appending:
            # the cell used to fall through to `return (df,)` with df
            # unbound, so a load failure surfaced as a NameError from a cell
            # several steps downstream.
            #
            # Reported from inside the operation() span (not after this
            # `with` exits): capture_exception() only picks up trace context
            # that is still current, and the span's own __exit__ would have
            # already torn that down by the time an outer `except` ran.
            _event_id = monitoring.report(
                error,
                where="calculate_datums.load",
                level="error",
            )
            mo.stop(
                True,
                common.admonition(
                    f"Error loading data: {error}",
                    title="Data Load Error",
                    kind="error",
                    sentry_event_id=_event_id,
                ),
            )
    return (df,)


@app.cell
def _(df):
    latitude = df["latitude (degrees_north)"].mean()
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
def _(common, df_reset, latitude, longitude, mo, monitoring, tadc):
    with (
        mo.redirect_stderr(),
        mo.redirect_stdout(),
        monitoring.operation(
            "tadc.run",
            op="compute",
            rows=len(df_reset),
        ),
    ):
        try:
            out = tadc.run(
                data=df_reset,
                Subordinate_Lat=latitude,
                Subordinate_Lon=longitude,
            )
        except Exception as error:
            # tadc is a third-party numerical library running on
            # user-selected data -- exactly the kind of failure we want
            # visibility into. Reported from inside the operation() span (not
            # after this `with` exits): capture_exception() only picks up
            # trace context that is still current, and the span's own
            # __exit__ would have already torn that down by the time an
            # outer `except` ran.
            _event_id = monitoring.report(
                error,
                where="calculate_datums.tadc_run",
                level="error",
            )
            mo.stop(
                True,
                common.admonition(
                    kind="error",
                    title="Error",
                    content=f"Error trying to calculate datums: {error}",
                    sentry_event_id=_event_id,
                ),
            )
    return (out,)


@app.cell
def _(mo, out):
    mo.ui.table([{"datum": k, "NAVD88 meters": v} for k, v in out.datums.items()])


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


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
