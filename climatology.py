import marimo

__generated_with = "0.13.15"
app = marimo.App(width="medium", app_title="NERACOOS Climatology")

with app.setup:
    from datetime import datetime, timedelta

    import httpx
    import erddapy
    import pandas as pd
    import marimo as mo
    import altair as alt

    import common


@app.cell
def _():
    common.set_defaults()
    common.sidebar_menu()
    return


@app.cell
def _():
    mo.md(
        r"""To view different plots, select buoy, data type and the averaging time period from the selections below.""",
    )
    return


@app.cell
def _():
    platform_res = httpx.get(
        "https://buoybarn.neracoos.org/api/platforms/?visibility=climatology",
    )
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
    return (platforms,)


@app.cell
def _():
    query_params = mo.query_params()
    return (query_params,)


@app.cell
def _(platforms, query_params):
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
    return (platform_dropdown,)


@app.cell
def _(platform_dropdown):
    platform = platform_dropdown.value
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
        # mo.stop(True)
        pass
    timeseries = dict(sorted(timeseries.items()))
    return platform, timeseries


@app.cell
def _(query_params, timeseries):
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
    return (timeseries_dropdown,)


@app.cell
def _(platform_dropdown, timeseries_dropdown):
    mo.hstack([platform_dropdown, timeseries_dropdown])
    return


@app.cell
def _(platform):
    if platform is None:
        mo.output.append(
            common.admonition(
                "",
                title="Please select a platform to view climatologies for",
                kind="warning",
            ),
        )
    return


@app.cell
def _(platform):
    if platform is None:
        mo.stop(True)
    return


@app.cell
def _(timeseries_dropdown):
    ts = timeseries_dropdown.value
    if ts is None:
        mo.output.append(
            common.admonition(
                "",
                title="Please select a data type to compute climatologies for",
                kind="warning",
            ),
        )
    return (ts,)


@app.cell
def _(ts):
    mo.stop(ts is None)
    return


@app.cell
def _(ts):
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
def _(df_all, query_params):
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
    return year_dropdown, years


@app.cell
def _(year_dropdown):
    year = datetime(int(year_dropdown.value), 1, 1)
    return (year,)


@app.cell
def _(query_params, years):
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
    return (start_year_dropdown,)


@app.cell
def _(query_params, start_year_dropdown, years):
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
    return (end_year_dropdown,)


@app.cell
def _(query_params):
    DAILY = "Daily"
    MONTHLY = "Monthly"
    average_period_dropdown = mo.ui.dropdown(
        options=[DAILY, MONTHLY],
        label="Averaging Time Period",
        value=query_params["avg_period"] or DAILY,
        on_change=lambda value: query_params.set("avg_period", value),
    )
    return DAILY, average_period_dropdown


@app.cell
def _(average_period_dropdown, end_year_dropdown, start_year_dropdown):
    mo.hstack([start_year_dropdown, end_year_dropdown, average_period_dropdown])
    return


@app.cell
def _(DAILY, average_period_dropdown, column, df_no_index):
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
                alt.X("count", bin=True, title="Values per month"),
                y="count()",
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
                With the data being dynamic and the rate of observations possibly changing over time, we are only able to set reasonable defaults for a minimum number of observations to be included in a day/month to be eligible to generate climatology from.

                - The default daily threshold is 18 considering a minimum of 3/4 hourly obsevations
                - The default monthly threshold is 20 for 2/3rds of daily observations
                """),
                        ],
                    ),
                    _threshold_chart,
                ],
            ),
        },
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
    start_year_dropdown,
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
            lambda x: year + timedelta(days=x - 1),
        )
        clim_df = clim_df.rename(
            columns={"idxmin": "Min date", "idxmax": "Max date"},
        )
    else:
        clim_df["Date"] = pd.to_datetime(
            clim_df["Date"].apply(lambda x: f"{year.year}-{x}"),
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
        },
    )
    return clim_df, max_range_name, mean_range_name, min_range_name


@app.cell
def _(average_period_dropdown, clim_df, max_range_name, min_range_name):
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
def _(average_period_dropdown, clim_df, mean_range_name):
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
def _(average_period_dropdown, column, df_no_index, year, year_dropdown):
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
            lambda x: year + timedelta(days=x - 1),
        )
    else:
        df_year["Date"] = pd.to_datetime(
            df_year["Date"].apply(lambda x: f"{year.year}-{x}"),
        )
        df_year = df_year.rename({"Date": "Month"}, axis=1)
    return (df_year,)


@app.cell
def _(average_period_dropdown, df_year, ts):
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
    average_period_dropdown,
    clim_df,
    end_year_dropdown,
    platform,
    start_year_dropdown,
    ts,
    year_dropdown,
):
    logo = common.neracoos_logo(
        clim_df["Date"].max(),
        f"{ts['app_name']} at {platform['id']} for {start_year_dropdown.value} thru {max([end_year_dropdown.value, year_dropdown.value])}",
        time_col="Date" if average_period_dropdown.value == "Daily" else "Month",
    )
    return (logo,)


@app.cell
def _(area, line, logo, mean, ts):
    if "direction" in ts["data_type"]["standard_name"].lower():
        combined_chart = mo.ui.altair_chart(logo + mean + line)
    else:
        combined_chart = mo.ui.altair_chart(logo + area + mean + line)
    combined_chart
    return


@app.cell
def _(e, end_year_dropdown, platform, start_year_dropdown):
    mo.hstack(
        [
            mo.md(
                f"[Platform on Mariners Dashboard](https://mariners.neracoos.org/platform/{platform['id']})",
            ),
            mo.md(f"[Dataset on ERDDAP]({e.get_download_url()})"),
            mo.md(
                f"Climatology calculated from {start_year_dropdown.value} to {end_year_dropdown.value}",
            ),
        ],
    )
    return


@app.cell
def _(
    DAILY,
    average_period_dropdown,
    clim_df,
    df_year,
    end_year_dropdown,
    start_year_dropdown,
    year_dropdown,
):
    _range = f"({start_year_dropdown.value} - {end_year_dropdown.value})"
    df_combined = pd.merge(
        clim_df,
        df_year.rename(
            {
                "mean": f"{'Daily' if average_period_dropdown.value == DAILY else 'Monthly'} means for {year_dropdown.value}",
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
    return


if __name__ == "__main__":
    app.run()
