import marimo

__generated_with = "0.14.0"
app = marimo.App(
    width="medium",
    app_title="NERACOOS Visualize and Compare - By Buoy",
)

with app.setup:
    import httpx
    import pandas as pd
    import altair as alt
    import marimo as mo

    import common


@app.cell
def _():
    common.set_defaults()
    common.sidebar_menu()
    return


@app.cell
def _():
    mo.md(
        """
    # Visualize and Compare by Buoy (beta)

    Compare multiple types of data for a single buoy.
    """,
    )
    return


@app.cell
def _():
    platform_json = common.load_platform_json()
    return (platform_json,)


@app.cell
def _(platform_json):
    platforms = {
        p["properties"]["station_name"] or p["id"]: p for p in platform_json["features"]
    }
    return (platforms,)


@app.cell
def _(platforms):
    platform_selector = mo.ui.dropdown(
        dict(sorted(platforms.items())),
        label="Select platform",
    )
    return (platform_selector,)


@app.function
def name_for_ts(ts: dict):
    name = ts["data_type"]["long_name"]
    if ts["depth"]:
        name = f"{name} @ {ts['depth']} meters"

    return name


@app.cell
def _(platform_selector):
    platform_time_series = {}

    if platform_selector.value:
        for _ts in platform_selector.value["properties"]["readings"]:
            _name = name_for_ts(_ts)

            platform_time_series[_name] = _ts
    return (platform_time_series,)


@app.cell
def _(platform_time_series):
    time_series_selector = mo.ui.multiselect(
        dict(sorted(platform_time_series.items())),
        label="Select time series",
    )
    return (time_series_selector,)


@app.cell
def _(platform_selector, time_series_selector):
    mo.hstack([platform_selector, time_series_selector])
    return


@app.function
@mo.cache
def load_ts(ts: dict, col_name: str | None = None) -> pd.DataFrame:
    df = common.load_ts_from_erddap(ts)

    if not col_name:
        col_name = ts["data_type"]["standard_name"]

    columns = list(df.columns)
    columns[0] = col_name
    df.columns = columns
    return df


@app.cell
def _(time_series_selector):
    loaded_ts = {}
    unit_ts = {}

    with mo.status.spinner(title="Loading data from ERDDAP"):
        for _ts in time_series_selector.value:
            _col_name = name_for_ts(_ts)
            _unit = _ts["data_type"]["units"]
            _key = (_col_name, _unit)
            try:
                _df = load_ts(_ts, col_name=_col_name)
                loaded_ts[_key] = _df
                unit_ts.setdefault(_unit, []).append(_col_name)
            except httpx.HTTPError as e:
                mo.output.append(
                    common.admonition(
                        "",
                        title=f"Unable to load data for {_col_name}",
                        kind="error",
                    ),
                )
                print(f"Error loading {_col_name}: \n{e}")
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
    except ValueError:
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

    MAX_ROWS = 10_000 / len(list(unit_ts.keys()))

    def time_grouper(df: pd.DataFrame) -> pd.DataFrame:
        filtered_df = df

        if len(filtered_df) < MAX_ROWS:
            mo.output.append(mo.callout("No filtering needed"))
            return df[0]
        else:
            for time_period, name in common.TIME_GROUPS:
                filtered_df = df.resample(time_period).mean()
                if len(filtered_df) < MAX_ROWS:
                    mo.output.append(
                        common.admonition(
                            "",
                            title=f"Resampled to {name} means for plotting",
                            kind="attention",
                        ),
                    )
                    return filtered_df

    filtered_df = time_grouper(time_filtered_df)
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
        # _row_df = pd.melt(filtered_df[_ts_keys].reset_index(), id_vars="time (UTC)").dropna()
        # _row_df = _row_df.rename(columns={"value": _unit})
        # _row = alt.Chart(_row_df).mark_line().encode(x="time (UTC)", y=_unit, color="variable").properties(height=300)
        _row = _base.encode(x="time (UTC):T", y=f"{_unit}:Q", color="variable")
        if i == 0:
            _row = _row + common.neracoos_logo(
                filtered_df.index.max(),
                platform_selector.value["id"],
            )
        stack &= _row

    mo.ui.altair_chart(stack)
    return


@app.cell(hide_code=True)
def _(df, filtered_df):
    mo.accordion(
        {
            "Full dataframe and download": df,
            "Filtered dataframe and download": filtered_df,
        },
    )
    return


if __name__ == "__main__":
    app.run()
