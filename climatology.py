import marimo

__generated_with = "0.10.19"
app = marimo.App(width="medium", app_title="NERACOOS Climatology")


@app.cell
def _():
    import base64
    from datetime import datetime, timedelta
    from io import BytesIO
    return BytesIO, base64, datetime, timedelta


@app.cell
def _():
    import httpx
    import erddapy
    import pandas as pd
    from PIL import Image
    import xarray as xr
    import marimo as mo
    import altair as alt
    import numpy as np
    return Image, alt, erddapy, httpx, mo, np, pd, xr


@app.cell
def _(pd):
    pd.set_option("display.precision", 2)
    return


@app.cell
def _(httpx):
    platform_res = httpx.get("https://buoybarn.neracoos.org/api/platforms/?visibility=climatology")
    return (platform_res,)


@app.cell
def _(platform_res):
    platforms = {}
    for feature in platform_res.json()["features"]:
        if feature["properties"]["station_name"]:
            platforms[feature["properties"]["station_name"]] = feature
        else:
            platforms[feature["id"]] = feature
    platforms = dict(sorted(platforms.items()))
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
def _(mo, platform):
    timeseries = {}
    try:
        for r in platform["properties"]["readings"]:
            if r["depth"]:
                name = f"{r['data_type']['long_name']} @ {r['depth']}m"

            else:
                name = r["data_type"]["long_name"]
            r["app_name"] = name
            timeseries[name] = r
    except TypeError:
        mo.stop(True)
    timeseries = dict(sorted(timeseries.items()))
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
        try:
            e = erddapy.ERDDAP(ts["server"], protocol="tabledap")
            e.dataset_id = ts["dataset"]
            e.variables = ["time", ts["variable"]]
            e.constraints = ts["constraints"] or {}
            df_all = e.to_pandas(
                index_col="time (UTC)",
                parse_dates=True,
            ).dropna()
        except TypeError:
            mo.stop(True)
    return df_all, e


@app.cell
def _(df_all):
    df_no_index = df_all.reset_index()
    df_no_index = df_no_index.rename({"time (UTC)": "Date"}, axis=1)
    column = df_all.columns[0]
    return column, df_no_index


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
    DAILY = "Daily"
    MONTHLY = "Monthly"
    average_period_dropdown = mo.ui.dropdown(
        options=[DAILY, MONTHLY],
        label="Averaging Time Period",
        value=query_params["avg_period"] or DAILY,
        on_change=lambda value: query_params.set("avg_period", value),
    )
    return DAILY, MONTHLY, average_period_dropdown


@app.cell
def _(average_period_dropdown, end_year_dropdown, mo, start_year_dropdown):
    mo.hstack([start_year_dropdown, end_year_dropdown, average_period_dropdown])
    return


@app.cell
def _(DAILY, alt, average_period_dropdown, column, df_no_index, mo, pd):
    if average_period_dropdown.value == DAILY:
        means = (
            df_no_index[column]
            .groupby(df_no_index["Date"].dt.date)
            .agg(["mean", "count"])
        )
        # _over_time_chart = alt.Chart(means.reset_index()).mark_line().encode(alt.Y("count"), alt.X("Date"))
        _threshold_chart = (
            alt.Chart(means)
            .mark_bar()
            .encode(alt.X("count", bin=True, title="Values per day"), y="count()")
        )
        threshold = mo.ui.number(
            start=0,
            stop=int(means["count"].max()),
            step=1,
            value=18,
            label="Minimum number of daily values",
        )
    else:
        means = (
            df_no_index[column]
            .groupby(df_no_index["Date"].dt.strftime("%Y-%m"))
            .agg(["mean", "count"])
        )
        _threshold_chart = (
            alt.Chart(means)
            .mark_bar()
            .encode(
                alt.X("count", bin=True, title="Values per month"), y="count()"
            )
        )
        threshold = mo.ui.number(
            start=0,
            stop=int(means["count"].max()),
            step=1,
            value=20,
            label="Minimum number of monthly values",
        )

    means.index = pd.to_datetime(means.index)

    mo.accordion(
        {
            "Threshold configuration": mo.hstack(
                [
                    mo.vstack(
                        [
                            threshold,
                            mo.md("""
                With the data being dynamic and the rate of observations possibly changing over time, we are only able to set reasonable defaults for a minimum number of observations to be included in a day/month to be elgible to generate climatology from.

                - The default daily threshold is 18 considering a minimum of 3/4 hourly obsevations
                - The default monthly threshold is 20 for 2/3rds of daily observations
                """),
                        ]
                    ),
                    _threshold_chart,
                ]
            ),
        }
    )
    return means, threshold


@app.cell
def _(end_year_dropdown, means, start_year_dropdown, threshold):
    means_filtered = means[
        (means["count"] > threshold.value)
        & (start_year_dropdown.value <= means.index)
        & (means.index < str(int(end_year_dropdown.value) + 1))
    ]
    # means_filtered
    return (means_filtered,)


@app.cell
def _(
    DAILY,
    average_period_dropdown,
    end_year_dropdown,
    means_filtered,
    pd,
    start_year_dropdown,
    timedelta,
    year,
):
    if average_period_dropdown.value == DAILY:
        clim_group_by = means_filtered.index.day_of_year
    else:
        clim_group_by = means_filtered.index.month

    clim_df = (
        means_filtered.groupby(clim_group_by)["mean"]
        .agg(["mean", "max", "min", "idxmin", "idxmax"])
        .reset_index()
    )

    clim_df["idxmin"] = clim_df["idxmin"].dt.date
    clim_df["idxmax"] = clim_df["idxmax"].dt.date

    if average_period_dropdown.value == DAILY:
        clim_df["Date"] = clim_df["Date"].apply(
            lambda x: year + timedelta(days=x - 1)
        )
        clim_df = clim_df.rename(
            columns={"idxmin": "Min date", "idxmax": "Max date"}
        )
    else:
        clim_df["Date"] = pd.to_datetime(
            clim_df["Date"].apply(lambda x: f"{year.year}-{x}")
        )
        clim_df = clim_df.rename(
            {
                "Date": "Month",
                "idxmin": "Min month",
                "idxmax": "Max month",
            },
            axis=1,
        )

    _range = f"({start_year_dropdown.value} - {end_year_dropdown.value})"

    mean_range_name = f"Mean {_range}"
    min_range_name = f"Min {_range}"
    max_range_name = f"Max {_range}"
    clim_df = clim_df.round(2).rename(
        columns={
            "mean": mean_range_name,
            "min": min_range_name,
            "max": max_range_name,
        }
    )
    return (
        clim_df,
        clim_group_by,
        max_range_name,
        mean_range_name,
        min_range_name,
    )


@app.cell
def _(
    alt,
    average_period_dropdown,
    clim_df,
    max_range_name,
    min_range_name,
):
    area = (
        alt.Chart(clim_df)
        .mark_area(color="yellow", opacity=0.5)
        .encode(
            alt.X("Date")
            if average_period_dropdown.value == "Daily"
            else alt.X("Month"),
            alt.Y(min_range_name),
            alt.Y2(max_range_name),
        )
    )
    return (area,)


@app.cell
def _(alt, average_period_dropdown, clim_df, mean_range_name):
    mean = (
        alt.Chart(clim_df)
        .mark_line()
        .encode(
            alt.X("Date")
            if average_period_dropdown.value == "Daily"
            else alt.X("Month"),
            alt.Y(mean_range_name),
        )
    )
    return (mean,)


@app.cell
def _(
    average_period_dropdown,
    column,
    df_no_index,
    pd,
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

    df_year = df_year.groupby(year_group_by)[column].agg(["mean"])
    df_year = df_year.reset_index()

    if average_period_dropdown.value == "Daily":
        df_year["Date"] = df_year["Date"].apply(
            lambda x: year + timedelta(days=x - 1)
        )
    else:
        df_year["Date"] = pd.to_datetime(
            df_year["Date"].apply(lambda x: f"{year.year}-{x}")
        )
        df_year = df_year.rename({"Date": "Month"}, axis=1)
    return df_year, year_group_by


@app.cell
def _(alt, average_period_dropdown, df_year, ts):
    _y_title = f"{ts['data_type']['long_name']} ({ts['data_type']['units']})"

    line = (
        alt.Chart(df_year)
        .mark_point(color="red")
        .encode(
            alt.X("Date")
            if average_period_dropdown.value == "Daily"
            else alt.X("Month"),
            alt.Y("mean").title(_y_title),
        )
    )
    return (line,)


@app.cell
def _(
    BytesIO,
    Image,
    alt,
    average_period_dropdown,
    base64,
    clim_df,
    df_year,
    end_year_dropdown,
    max_range_name,
    np,
    pd,
    platform,
    start_year_dropdown,
    ts,
    year_dropdown,
):
    _pil_image = Image.open("./public/neracoos.png")
    _output = BytesIO()
    _pil_image.save(_output, format="PNG")
    _base64_images = [
        "data:image/png;base64," + base64.b64encode(_output.getvalue()).decode()
    ]
    _data_max = np.ceil(
        max([df_year["mean"].max(), clim_df[max_range_name].max()])
    )
    _image_df = pd.DataFrame(
        {
            "Date"
            if average_period_dropdown.value == "Daily"
            else "Month": clim_df["Date"].max(),
            "y": _data_max,
            "image": _base64_images,
        }
    )

    image = (
        alt.Chart(
            _image_df,
            title=alt.Title(
                f"{ts['app_name']} at {platform['id']} for {start_year_dropdown.value} thru {max([end_year_dropdown.value, year_dropdown.value])}",
                baseline="bottom",
                # align="right",
                anchor="start",
                dx=40,
                offset=-46,
            ),
        )
        .mark_image(
            width=219, height=46, align="right", baseline="bottom", clip=False
        )
        .encode(
            x="Date" if average_period_dropdown.value == "Daily" else "Month",
            y="y",
            url="image",
        )
    )
    return (image,)


@app.cell
def _(area, image, line, mean, mo, ts):
    if "direction" in ts["data_type"]["standard_name"].lower():
        combined_chart = mo.ui.altair_chart(image + mean + line)
    else:
        combined_chart = mo.ui.altair_chart(image + area + mean + line)
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
    DAILY,
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
        clim_df,
        df_year.rename(
            {
                "mean": f"{'Daily' if average_period_dropdown.value == DAILY else 'Monthly'} means for {year_dropdown.value}"
            },
            axis=1,
        ),
        on=("Date" if average_period_dropdown.value == DAILY else "Month"),
        how="left",
    )

    if average_period_dropdown.value == DAILY:
        df_combined["Date"] = df_combined["Date"].dt.date

        _cols = (
            [df_combined.columns.to_list()[0]]
            + df_combined.columns.to_list()[-1:]
            + df_combined.columns.to_list()[1:-1]
        )
        df_combined = df_combined[_cols]
    else:
        _cols = (
            [df_combined.columns.to_list()[0]]
            + df_combined.columns.to_list()[-1:]
            + df_combined.columns.to_list()[2:-1]
        )
        df_combined = df_combined[_cols]

    df_combined = df_combined.round(2)

    mo.accordion({"Show data": df_combined})
    return (df_combined,)


if __name__ == "__main__":
    app.run()
