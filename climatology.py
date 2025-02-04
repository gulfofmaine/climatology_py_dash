import marimo

__generated_with = "0.10.16"
app = marimo.App(width="medium", app_title="NERACOOS Climatology")


@app.cell
def _():
    from datetime import datetime, timedelta
    return datetime, timedelta


@app.cell
def _():
    import httpx
    import erddapy
    import pandas as pd
    import xarray as xr
    import marimo as mo
    import altair as alt
    import numpy as np
    return alt, erddapy, httpx, mo, np, pd, xr


@app.cell
def _(httpx):
    platform_res = httpx.get("https://buoybarn.neracoos.org/api/platforms/")
    return (platform_res,)


@app.cell
def _(platform_res):
    platforms = {}
    for feature in platform_res.json()["features"]:
        if feature["properties"]["station_name"]:
            platforms[feature["properties"]["station_name"]] = feature
        else:
            platforms[feature["id"]] = feature
    return feature, platforms


@app.cell
def _(mo):
    query_params = mo.query_params()
    return (query_params,)


@app.cell
def _(mo, platforms, query_params):
    if query_params["platform"] and query_params["platform"] in platforms:
        platform_default = query_params["platform"]
    else:
        platform_default = None

    platform_dropdown = mo.ui.dropdown(
        options=platforms,
        label="Platform",
        value=platform_default,
        on_change=lambda value: query_params.set("platform", value["id"]),
    )
    platform_dropdown
    return platform_default, platform_dropdown


@app.cell
def _(mo, platform_dropdown):
    platform = platform_dropdown.value
    if platform == None:
        platform_callout = mo.callout(
            "Please select a platform to view climatologies for", kind="warn"
        )
        mo.output.append(platform_callout)
    return platform, platform_callout


@app.cell
def _(mo, platform):
    mo.stop(platform == None)
    return


@app.cell
def _(platform):
    timeseries = {}
    for r in platform["properties"]["readings"]:
        if r["depth"]:
            name = f"{r['data_type']['long_name']} @ {r['depth']}m"

        else:
            name = r["data_type"]["long_name"]
        r["app_name"] = name
        timeseries[name] = r
    return name, r, timeseries


@app.cell
def _(mo, query_params, timeseries):
    if query_params["ts"] and query_params["ts"] in timeseries:
        timeseries_default = query_params["ts"]
    else:
        timeseries_default = None

    timeseries_dropdown = mo.ui.dropdown(
        options=timeseries,
        label="Data Type",
        value=timeseries_default,
        on_change=lambda value: query_params.set("ts", value["app_name"]),
    )
    timeseries_dropdown
    return timeseries_default, timeseries_dropdown


@app.cell
def _(mo, timeseries_dropdown):
    ts = timeseries_dropdown.value
    if ts == None:
        ts_callout = mo.callout(
            "Please select a data type to compute climatologies for", kind="warn"
        )
        mo.output.append(ts_callout)
    return ts, ts_callout


@app.cell
def _(mo, ts):
    mo.stop(ts == None)
    return


@app.cell
def _(erddapy, mo, ts):
    with mo.status.spinner(title="Loading data from ERDDAP"):
        e = erddapy.ERDDAP(ts["server"], protocol="tabledap")
        e.dataset_id = ts["dataset"]
        e.variables = ["time", ts["variable"]]
        e.constraints = ts["constraints"] or {}
        df_all = e.to_pandas(
            index_col="time (UTC)",
            parse_dates=True,
        ).dropna()
    return df_all, e


@app.cell
def _(df_all):
    df_no_index = df_all.reset_index()
    df_no_index = df_no_index.rename({"time (UTC)": "Date"}, axis=1)
    return (df_no_index,)


@app.cell
def _(df_all, mo, query_params):
    years = [str(y) for y in df_all.index.year.unique()]

    if query_params["year"] and query_params["year"] in years:
        years_default = query_params["year"]
    else:
        years_default = years[-1]

    year_dropdown = mo.ui.dropdown(
        options=years,
        label="Select a year to display",
        value=years_default,
        on_change=lambda value: query_params.set("year", value),
    )
    year_dropdown
    return year_dropdown, years, years_default


@app.cell
def _(datetime, year_dropdown):
    year = datetime(int(year_dropdown.value), 1, 1)
    return (year,)


@app.cell
def _(mo, query_params, years):
    if query_params["clim_start"] and query_params["clim_start"] in years:
        start_year_default = query_params["clim_start"]
    else:
        start_year_default = years[0]

    start_year_dropdown = mo.ui.dropdown(
        options=years,
        label="Select a year to start generating the climatology",
        value=start_year_default,
        on_change=lambda value: query_params.set("clim_start", value),
    )
    # start_year_dropdown
    return start_year_default, start_year_dropdown


@app.cell
def _(mo, query_params, start_year_dropdown, years):
    years_greater_than_start = [
        y for y in years if int(start_year_dropdown.value) < int(y)
    ]

    if (
        query_params["clim_end"]
        and query_params["clim_end"] in years_greater_than_start
    ):
        end_year_default = query_params["clim_end"]
    else:
        try:
            end_year_default = years_greater_than_start[-2]
        except IndexError:
            end_year_default = years_greater_than_start[-1]

    end_year_dropdown = mo.ui.dropdown(
        options=years_greater_than_start,
        label="Select an end year for the climatology",
        value=end_year_default,
        on_change=lambda value: query_params.set("clim_end", value),
    )
    # end_year_dropdown
    return end_year_default, end_year_dropdown, years_greater_than_start


@app.cell
def _(mo, query_params):
    average_period_dropdown = mo.ui.dropdown(
        options=["Daily", "Monthly"],
        label="Averaging Time Period",
        value=query_params["avg_period"] or "Daily",
        on_change=lambda value: query_params.set("avg_period", value),
    )
    return (average_period_dropdown,)


@app.cell
def _(average_period_dropdown, end_year_dropdown, mo, start_year_dropdown):
    mo.hstack(
        [start_year_dropdown, end_year_dropdown, average_period_dropdown]
    )
    return


@app.cell
def _(
    average_period_dropdown,
    df_all,
    df_no_index,
    end_year_dropdown,
    start_year_dropdown,
    timedelta,
    year,
):
    if average_period_dropdown.value == "Daily":
        clim_group_by = df_no_index["Date"].dt.day_of_year
    else:
        clim_group_by = df_no_index["Date"].dt.month

    clim_df = (
        df_no_index[
            (start_year_dropdown.value <= df_no_index["Date"])
            & (df_no_index["Date"] <= end_year_dropdown.value)
        ]
        .groupby(clim_group_by)[df_all.columns[0]]
        .agg(["mean", "max", "min"])
        .reset_index()
    )

    if average_period_dropdown.value == "Daily":
        clim_df["Date"] = clim_df["Date"].apply(
            lambda x: year + timedelta(days=x - 1)
        )
    else:
        clim_df = clim_df.rename({"Date": "Month"}, axis=1)

    # clim_df
    return clim_df, clim_group_by


@app.cell
def _(alt, average_period_dropdown, clim_df):
    area = (
        alt.Chart(clim_df)
        .mark_area(color="yellow", opacity=0.5)
        .encode(
            alt.X("Date")
            if average_period_dropdown.value == "Daily"
            else alt.X("Month"),
            alt.Y("min"),
            alt.Y2("max"),
        )
    )

    # area_chart = mo.ui.altair_chart(area)
    # area_chart
    return (area,)


@app.cell
def _(alt, average_period_dropdown, clim_df):
    mean = (
        alt.Chart(clim_df)
        .mark_line()
        .encode(
            alt.X("Date")
            if average_period_dropdown.value == "Daily"
            else alt.X("Month"),
            alt.Y("mean"),
        )
    )
    return (mean,)


@app.cell
def _():
    # clim_df
    return


@app.cell
def _():
    # df_all
    return


@app.cell
def _(
    average_period_dropdown,
    df_all,
    df_no_index,
    timedelta,
    year,
    year_dropdown,
):
    df_year = df_no_index[
        (f"{year_dropdown.value}-01-01T00:00" < df_no_index["Date"])
        & (df_no_index["Date"] < f"{year_dropdown.value}-12-31T23:59:59")
    ]

    if average_period_dropdown.value == "Daily":
        year_group_by = df_year["Date"].dt.day_of_year
    else:
        year_group_by = df_year["Date"].dt.month

    df_year = df_year.groupby(year_group_by)[df_all.columns[0]].agg(["mean"])
    df_year = df_year.reset_index()

    if average_period_dropdown.value == "Daily":
        df_year["Date"] = df_year["Date"].apply(
            lambda x: year + timedelta(days=x - 1)
        )
    else:
        df_year = df_year.rename({"Date": "Month"}, axis=1)
    # df_year
    return df_year, year_group_by


@app.cell
def _(alt, average_period_dropdown, df_year, ts):
    title = f"{ts['data_type']['long_name']} ({ts['data_type']['units']})"

    line = (
        alt.Chart(df_year)
        .mark_line(color="red")
        .encode(
            alt.X("Date")
            if average_period_dropdown.value == "Daily"
            else alt.X("Month"),
            # alt.Y("mean").title(df_all.columns[0]),
            alt.Y("mean").title(title),
            # alt.Color("line:N", scale=alt.Scale(range=["red"]), title="2025")
            # alt.Color("line:N", scale=alt.Scale(range=["red"]), legend=alt.Legend(symbolType="line"), title=year_dropdown.value)
        )
    )
    # line_chart = mo.ui.altair_chart(line)
    # line_chart
    return line, title


@app.cell
def _(area, line, mean, mo):
    combined_chart = mo.ui.altair_chart(area + mean + line)
    combined_chart
    return (combined_chart,)


@app.cell
def _(e, end_year_dropdown, mo, platform, start_year_dropdown):
    mo.hstack(
        [
            mo.md(
                f"[Platform on Mariners Dashboard](https://mariners.neracoos.org/platform/{platform['id']})"
            ),
            mo.md(f"[Dataset on ERDDAP]({e.get_download_url()})"),
            mo.md(
                f"Climatology calculated from {start_year_dropdown.value} to {end_year_dropdown.value}"
            ),
        ]
    )
    return


@app.cell
def _(
    average_period_dropdown,
    clim_df,
    df_year,
    end_year_dropdown,
    mo,
    pd,
    start_year_dropdown,
    year_dropdown,
):
    _range = f"({start_year_dropdown.value} - {end_year_dropdown.value})"
    df_combined = pd.merge(
        clim_df.rename(
        {
            "mean": f"Mean {_range}",
            "min": f"Min {_range}",
            "max": f"Max {_range}",
        },
        axis=1,
    ),
        df_year.rename(
            {
                "mean": f"{'Daily' if average_period_dropdown.value == 'Daily' else 'Monthly'} means for {year_dropdown.value}"
            },
            axis=1,
        ),
        on=("Date" if average_period_dropdown.value == "Daily" else "Month"),
        how="left",
    )

    if average_period_dropdown.value == "Daily":
        df_combined["Month"] = df_combined["Date"].dt.month
        df_combined["Day"] = df_combined["Date"].dt.day
        df_combined = df_combined.drop(columns=["Date"])

        _cols = df_combined.columns.to_list()[-2:] + df_combined.columns.to_list()[:-2]
        df_combined = df_combined[_cols]

    mo.accordion({"Show data": df_combined})
    return (df_combined,)


if __name__ == "__main__":
    app.run()
