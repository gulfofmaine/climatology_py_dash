import marimo

__generated_with = "0.23.11"
app = marimo.App(
    width="medium",
    app_title="NERACOOS Visualize and Compare - By Buoy",
)

with app.setup:
    import altair as alt
    import marimo as mo
    import pandas as pd

    import common
    import monitoring


@app.cell
def _():
    common.set_defaults(page="by_platform")
    common.sidebar_menu()


@app.cell
def _():
    mo.md(
        """
    # Visualize and Compare by Buoy (beta)

    Compare multiple types of data for a single buoy.
    """,
    )


@app.cell
def _():
    platform_json = common.load_platform_json()
    return (platform_json,)


@app.cell
def _(platform_json):
    platforms = common.platforms_by_name(platform_json)
    return (platforms,)


@app.cell
def _(platforms):
    platform_selector = mo.ui.dropdown(
        platforms,
        label="Select platform",
    )
    return (platform_selector,)


@app.cell
def _(platform_selector):
    platform_time_series = common.timeseries_by_name(platform_selector.value)
    return (platform_time_series,)


@app.cell
def _(platform_time_series):
    time_series_selector = mo.ui.multiselect(
        platform_time_series,
        label="Select time series",
    )
    return (time_series_selector,)


@app.cell
def _(platform_selector, time_series_selector):
    mo.hstack([platform_selector, time_series_selector])


@app.cell
def _(time_series_selector):
    loaded_ts = {}
    unit_ts = {}

    with mo.status.spinner(title="Loading data from ERDDAP"):
        for _ts in time_series_selector.value:
            _col_name = common.name_for_ts(_ts)
            _unit = _ts["data_type"]["units"]
            _key = (_col_name, _unit)
            try:
                _df = common.load_ts(_ts, _col_name)
                loaded_ts[_key] = _df
                unit_ts.setdefault(_unit, []).append(_col_name)
            except common.ErddapLoadError as error:
                mo.output.append(
                    common.admonition(
                        str(error),
                        title=f"Unable to load data for {_col_name}",
                        kind="error",
                    ),
                )
    return loaded_ts, unit_ts


@app.cell
def _(loaded_ts):
    try:
        _dfs = []
        for _df in loaded_ts.values():
            if not _df.index.is_unique:
                _df = _df.loc[~_df.index.duplicated(keep="first")]
            _dfs.append(_df)
        df = pd.concat(_dfs, axis=1)
    except ValueError as error:
        if _dfs:
            # pd.concat([], axis=1) is the "nothing selected yet" case; a
            # ValueError with data present is a genuine bug wearing the same
            # message, and would otherwise never reach Sentry.
            monitoring.report(error, where="by_platform.concat", level="error")
        mo.stop(
            True,
            common.admonition(
                "",
                title="Please select a platform and timeseries",
                kind="attention",
            ),
        )
    return (df,)


@app.cell
def _(df):
    try:
        date_range = mo.ui.date_range(
            label="Date range",
            start=df.index.min().date(),
            stop=df.index.max().date(),
        )
        date_range
    except NameError:
        mo.stop(True)
    return (date_range,)


@app.cell
def _(date_range, df, unit_ts):
    try:
        time_filtered_df = df[
            (df.index >= date_range.value[0].isoformat())
            & (df.index <= date_range.value[1].isoformat())
        ]
    except NameError:
        mo.stop(True)

    # The subplots share one budget, so comparing four units does not inline
    # four times as much data into the vega spec as comparing one.
    _max_rows = common.MAX_ROWS // max(len(unit_ts), 1)

    filtered_df, _resampled_to = common.resample_to_budget(
        time_filtered_df,
        _max_rows,
    )

    if _resampled_to:
        mo.output.append(
            common.admonition(
                "",
                title=f"Resampled to {_resampled_to} means for plotting",
                kind="attention",
            ),
        )
    return (filtered_df,)


@app.cell
def _(filtered_df, platform_selector, unit_ts):
    _row_dfs = []
    for _unit, _ts_keys in unit_ts.items():
        _row_df = pd.melt(filtered_df[_ts_keys].reset_index(), id_vars="time (UTC)")
        _row_df = _row_df.rename(columns={"value": _unit})
        _row_dfs.append(_row_df)

    melted_df = pd.concat(_row_dfs)

    _base = alt.Chart(melted_df).mark_line().properties(height=300)

    stack = alt.vconcat()
    for i, (_unit, _ts_keys) in enumerate(unit_ts.items()):
        # Every subplot draws from the one melted frame, so without the filter
        # each takes its colour domain from all of the series -- listing the
        # other units' series in its legend and drawing them as nulls.
        _row = _base.encode(
            x="time (UTC):T",
            y=f"{_unit}:Q",
            color="variable",
        ).transform_filter(alt.FieldOneOfPredicate(field="variable", oneOf=_ts_keys))
        if i == 0:
            _row = _row + common.neracoos_logo(
                filtered_df.index.max(),
                platform_selector.value["id"],
            )
        stack &= _row.properties(width="container")

    mo.ui.altair_chart(
        stack.properties(width="container"),
        chart_selection=False,
        legend_selection=False,
    )


@app.cell(hide_code=True)
def _(df, filtered_df):
    mo.accordion(
        {
            "Full dataframe and download": df,
            "Filtered dataframe and download": filtered_df,
        },
    )


if __name__ == "__main__":
    app.run()
