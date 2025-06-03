import marimo

__generated_with = "0.13.15"
app = marimo.App(
    width="medium",
    app_title="Graph and Download by Standard Name",
)


@app.cell
def _():
    import httpx
    import erddapy
    import pandas as pd
    import altair as alt
    import marimo as mo

    return alt, erddapy, httpx, mo, pd


@app.cell
def _(pd):
    pd.set_option("display.precision", 2)
    return


@app.cell
def _(httpx):
    platform_res = httpx.get(
        "https://buoybarn.neracoos.org/api/platforms/",
        # "https://buoybarn.neracoos.org/api/platforms/?visibility=climatology",
    )
    return (platform_res,)


@app.cell
def _(platform_res):
    platform_json = platform_res.json()
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

    # standards
    return platform_standards, standards


@app.cell
def _(mo):
    query_params = mo.query_params()
    return (query_params,)


@app.cell
def _(mo, platform_standards, query_params, standards):
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
    # standard_name_dropdown
    return (standard_name_dropdown,)


@app.cell
def _(mo, platform_standards, standard_name_dropdown):
    platform_options = platform_standards[standard_name_dropdown.value]
    platform_options

    if standard_name_dropdown.value:
        selected_ts_keys = mo.ui.multiselect(
            sorted(platform_options.keys()),
            label="Platforms",
            max_selections=10,
        )
    else:
        selected_ts_keys = None
    return platform_options, selected_ts_keys


@app.cell
def _(mo, selected_ts_keys, standard_name_dropdown):
    mo.vstack([i for i in [standard_name_dropdown, selected_ts_keys] if i is not None])
    return


@app.cell
def _(mo, selected_ts_keys):
    if len(selected_ts_keys.value) == 0:
        mo.output.append(mo.callout("Please select platforms to display", kind="warn"))
    return


@app.cell
def _(mo, selected_ts_keys):
    mo.stop(len(selected_ts_keys.value) == 0)
    return


@app.cell
def _(erddapy, mo, pd, platform_options, selected_ts_keys):
    @mo.cache
    def load_ts(ts: dict) -> pd.DataFrame:
        e = erddapy.ERDDAP(ts["server"], protocol="tabledap")
        e.dataset_id = ts["dataset"]
        e.variables = ["time", ts["variable"]]
        e.constraints = ts["constraints"] or {}
        df = e.to_pandas(index_col="time (UTC)", parse_dates=True)
        df = df.dropna()
        columns = list(df.columns)
        columns[0] = ts["data_type"]["standard_name"]
        df.columns = columns
        return df

    combined_df = None

    with mo.status.spinner(title="Loading data from ERDDAP"):
        for _ts_name in selected_ts_keys.value:
            _ts = platform_options[_ts_name]
            _df = load_ts(_ts)
            _df["Timeseries"] = _ts_name

            if combined_df is None:
                combined_df = _df
            else:
                combined_df = pd.concat([combined_df, _df])

    # combined_df = combined_df.reset_index()
    # combined_df = combined_df.sort_values("time (UTC)")
    return (combined_df,)


@app.cell
def _(combined_df, mo):
    date_range = mo.ui.date_range(
        label="Date range",
        start=combined_df.index.min().date(),
        stop=combined_df.index.max().date(),
    )
    date_range
    return (date_range,)


@app.cell
def _(combined_df, date_range, mo, pd):
    time_filtered_df = combined_df[
        (combined_df.index >= date_range.value[0].isoformat())
        & (combined_df.index <= date_range.value[1].isoformat())
    ]

    MAX_ROWS = 10_000

    def time_grouper(df: pd.DataFrame) -> pd.DataFrame:
        filtered_df = time_filtered_df

        TIME_GROUPS = [
            # "1h",
            # "6h",
            # "12h",
            ("1D", "Daily"),
            ("1W", "Weekly"),
            ("MS", "Monthly"),
        ]

        if len(filtered_df) < MAX_ROWS:
            print("No filtering needed")
            return df
        else:
            for time_period, name in TIME_GROUPS:
                print(f"Trying to group by {time_period}")
                filtered_df = df.groupby(pd.Grouper(freq=time_period)).apply(
                    lambda x: x.groupby("Timeseries").mean(),
                )
                if len(filtered_df) < MAX_ROWS:
                    mo.output.append(mo.callout(f"Grouped by {name}", kind="warn"))
                    return filtered_df

    filtered_df = time_grouper(time_filtered_df)
    return (filtered_df,)


@app.cell
def _(filtered_df):
    len(filtered_df)
    return


@app.cell
def _(alt, filtered_df, mo, standard_name_dropdown):
    alt.data_transformers.disable_max_rows()

    _chart = (
        alt.Chart(filtered_df.reset_index())
        .mark_line()
        .encode(x="time (UTC)", y=standard_name_dropdown.value, color="Timeseries")
    )

    mo.ui.altair_chart(_chart)
    return


@app.cell
def _(combined_df, filtered_df, mo):
    mo.accordion(
        {
            "Full dataframe and download": combined_df,
            "Filtered dataframe and download": filtered_df,
        },
    )
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
