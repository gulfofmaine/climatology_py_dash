import marimo

__generated_with = "0.13.15"
app = marimo.App(
    width="medium",
    app_title="NERACOOS Visualize and Compare - Data Type",
)

with app.setup:
    import pandas as pd
    import altair as alt
    import marimo as mo

    import common


@app.cell
def _():
    mo.md(
        r"""
    # Visualize and Compare by Data Type (beta)

    Compare the same type of data for multiple buoys.
    """,
    )
    return


@app.cell
def _():
    common.set_defaults()
    common.sidebar_menu()
    return


@app.cell
def _():
    platform_json = common.load_platform_json()
    return (platform_json,)


@app.cell
def _(platform_json):
    standards = {}
    platform_standards = {}

    for _platform in platform_json["features"]:
        for _ts in _platform["properties"]["readings"]:
            _standard_name = _ts["data_type"]["standard_name"]
            standards[_standard_name] = _ts["data_type"]
            _name = f"{_platform['id']}"
            if _ts["depth"]:
                _name = _name + f" - {_ts['depth']}"
            platform_standards.setdefault(_standard_name, {})[_name] = _ts
    return platform_standards, standards


@app.cell
def _():
    query_params = mo.query_params()
    return (query_params,)


@app.cell
def _(platform_standards, query_params, standards):
    _dropdown_standards = {}
    for name, data_type in standards.items():
        _dropdown_standards[f"{data_type['long_name']} - {name}"] = name

    _dropdown_standards = {
        key: _dropdown_standards[key] for key in sorted(_dropdown_standards.keys())
    }

    if (
        query_params["standard_name"]
        and query_params["standard_name"] in standards
        and query_params["standard_name"] in platform_standards
    ):
        _standard_name = query_params["standard_name"]
        _standard_name_default = list(_dropdown_standards.keys())[
            list(_dropdown_standards.values()).index(_standard_name)
        ]
    else:
        _standard_name_default = None

    standard_name_dropdown = mo.ui.dropdown(
        options=_dropdown_standards,
        label="Standard Name",
        value=_standard_name_default,
        on_change=lambda value: query_params.set("standard_name", value),
    )
    return (standard_name_dropdown,)


@app.cell
def _(platform_standards, standard_name_dropdown):
    try:
        platform_options = platform_standards[standard_name_dropdown.value]
        selected_ts_keys = mo.ui.multiselect(
            sorted(platform_options.keys()),
            label="Platforms",
            max_selections=10,
        )
    except KeyError:
        selected_ts_keys = None
    return platform_options, selected_ts_keys


@app.cell
def _(selected_ts_keys, standard_name_dropdown):
    mo.vstack([i for i in [standard_name_dropdown, selected_ts_keys] if i is not None])
    return


@app.cell
def _(selected_ts_keys):
    try:
        selected_ts_keys.value
    except AttributeError:
        # if len(selected_ts_keys.value) == 0:
        mo.output.append(
            common.admonition("Please select platforms to display", kind="attention"),
        )
    return


@app.cell
def _(selected_ts_keys):
    try:
        selected_ts_keys.value
    except AttributeError:
        mo.stop(True)
    return


@app.cell
def _(standard_name_dropdown, standards):
    unit = standards[standard_name_dropdown.value]["units"]
    return (unit,)


@app.function
@mo.cache
def load_ts(ts: dict, col_name: str) -> pd.DataFrame:
    df = common.load_ts_from_erddap(ts)
    columns = list(df.columns)
    columns[0] = col_name
    df.columns = columns
    return df


@app.cell
def _(platform_options, selected_ts_keys, unit):
    _wide_dfs = []

    try:
        with mo.status.spinner(title="Loading data from ERDDAP"):
            for _ts_name in selected_ts_keys.value:
                _ts = platform_options[_ts_name]
                _df = load_ts(_ts, _ts_name)
                try:
                    del _df["Timeseries"]
                except KeyError:  # weird caching
                    pass
                # _df = _df.rename(columns={_ts["data_type"]["standard_name"]: _ts_name})
                _wide_dfs.append(_df)

            wide_df = pd.concat(_wide_dfs, axis=1)
            wide_melted = pd.melt(wide_df.reset_index(), id_vars="time (UTC)")
            wide_melted = wide_melted.rename(
                columns={"variable": "Timeseries", "value": unit},
            )
            wide_melted = wide_melted.set_index("time (UTC)")
    except ValueError:
        mo.stop(
            True,
            common.admonition(
                "",
                title="Please select platforms to display",
                kind="attention",
            ),
        )
    return wide_df, wide_melted


@app.cell
def _(wide_df):
    try:
        date_range = mo.ui.date_range(
            label="Date range",
            start=wide_df.index.min().date(),
            stop=wide_df.index.max().date(),
        )
    except AttributeError:
        mo.stop(True)
    date_range
    return (date_range,)


@app.function
def time_grouper(df: pd.DataFrame) -> pd.DataFrame:
    filtered_df = df

    if len(filtered_df) < common.MAX_ROWS:
        print("No aggregation needed")
        return df
    else:
        for time_period, name in common.TIME_GROUPS:
            print(f"Trying to group by {time_period}")
            filtered_df = df.groupby(pd.Grouper(freq=time_period)).apply(
                lambda x: x.groupby("Timeseries").mean(),
            )
            if len(filtered_df) < common.MAX_ROWS:
                mo.output.append(
                    common.admonition(
                        "",
                        title=f"Resampled to {name} means for plotting",
                        kind="attention",
                    ),
                )
                return filtered_df


@app.cell
def _(date_range, wide_melted):
    try:
        time_filtered_df = wide_melted[
            (wide_melted.index >= date_range.value[0].isoformat())
            & (wide_melted.index <= date_range.value[1].isoformat())
        ]
    except AttributeError:
        mo.stop(True)

    filtered_df = time_grouper(time_filtered_df)
    return (filtered_df,)


@app.cell
def _(filtered_df, standard_name_dropdown, standards, unit):
    alt.data_transformers.disable_max_rows()

    _logo = common.neracoos_logo(
        filtered_df.index.max()[0],
        standards[standard_name_dropdown.value]["long_name"],
    )

    _chart = (
        alt.Chart(filtered_df.reset_index())
        .mark_line()
        .encode(x="time (UTC)", y=unit, color="Timeseries")
    )

    mo.ui.altair_chart(_chart + _logo)
    return


@app.cell
def _(filtered_df, wide_df):
    mo.accordion(
        {
            "Full dataframe and download": wide_df,
            "Filtered dataframe and download": filtered_df,
        },
    )
    return


if __name__ == "__main__":
    app.run()
