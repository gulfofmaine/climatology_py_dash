import marimo

__generated_with = "0.14.0"
app = marimo.App(width="medium", app_title="NERACOOS Climatology")

with app.setup:
    import altair as alt
    import marimo as mo

    import climatology_core as core
    import common


@app.cell
def _():
    common.set_defaults()
    common.sidebar_menu()


@app.cell
def _():
    mo.md(
        r"""
        # Climatology (beta)

        To view different plots, select buoy, data type and the averaging time period from the selections below.""",
    )


@app.cell
def _():
    platform_json = common.load_platform_json(visibility="climatology")
    return (platform_json,)


@app.cell
def _(platform_json):
    platforms = common.platforms_by_name(platform_json)
    return (platforms,)


@app.cell
def _():
    query_params = mo.query_params()
    return (query_params,)


@app.cell
def _(platforms, query_params):
    platform_dropdown = mo.ui.dropdown(
        options=platforms.keys(),
        label="Platform",
        value=common.query_param_default(query_params, "platform", platforms),
        on_change=lambda value: query_params.set("platform", value),
    )
    return (platform_dropdown,)


@app.cell
def _(platform_dropdown, platforms):
    platform = platforms.get(platform_dropdown.value)
    return (platform,)


@app.cell
def _(platform):
    timeseries = common.timeseries_by_name(platform)
    return (timeseries,)


@app.cell
def _(query_params, timeseries):
    timeseries_dropdown = mo.ui.dropdown(
        options=timeseries,
        label="Data Type",
        value=common.query_param_default(query_params, "ts", timeseries),
        # Guarded: clearing the dropdown hands the callback None, and None has
        # no app_name.
        on_change=lambda value: (
            query_params.set("ts", value["app_name"]) if value else None
        ),
    )
    return (timeseries_dropdown,)


@app.cell
def _(platform_dropdown, timeseries_dropdown):
    mo.hstack([platform_dropdown, timeseries_dropdown])


@app.cell
def _(platform):
    if platform is None:
        mo.stop(
            True,
            common.admonition(
                "",
                title="Please select a platform to view climatologies for",
                kind="warning",
            ),
        )


@app.cell
def _(timeseries_dropdown):
    ts = timeseries_dropdown.value
    if ts is None:
        mo.stop(
            True,
            common.admonition(
                "",
                title="Please select a data type to compute climatologies for",
                kind="warning",
            ),
        )
    return (ts,)


@app.cell
def _(ts):
    with mo.status.spinner(title="Loading data from ERDDAP"):
        try:
            df_all = common.load_ts_from_erddap(ts)
        except common.ErddapLoadError as error:
            mo.stop(
                True,
                common.admonition(
                    str(error),
                    title="Data Load Error",
                    kind="error",
                ),
            )
    return (df_all,)


@app.cell
def _(df_all):
    df_no_index = df_all.reset_index()
    df_no_index = df_no_index.rename({"time (UTC)": core.TIME_COLUMN}, axis=1)
    column = df_all.columns[0]
    return column, df_no_index


@app.cell
def _(df_no_index, query_params):
    years = core.available_years(df_no_index)

    year_dropdown = mo.ui.dropdown(
        options=years,
        label="Select a year to display",
        value=common.query_param_default(
            query_params,
            "year",
            years,
            fallback=years[-1],
        ),
        on_change=lambda value: query_params.set("year", value),
    )
    year_dropdown
    return year_dropdown, years


@app.cell
def _(query_params, years):
    start_year_dropdown = mo.ui.dropdown(
        options=years,
        label="Select a year to start generating the climatology",
        value=common.query_param_default(
            query_params,
            "clim_start",
            years,
            fallback=years[0],
        ),
        on_change=lambda value: query_params.set("clim_start", value),
    )
    # start_year_dropdown
    return (start_year_dropdown,)


@app.cell
def _(query_params, start_year_dropdown, years):
    _end_year_options = core.end_year_options(years, start_year_dropdown.value)

    end_year_dropdown = mo.ui.dropdown(
        options=_end_year_options,
        label="Select an end year for the climatology",
        value=common.query_param_default(
            query_params,
            "clim_end",
            _end_year_options,
            fallback=core.default_end_year(_end_year_options),
        ),
        on_change=lambda value: query_params.set("clim_end", value),
    )
    # end_year_dropdown
    return (end_year_dropdown,)


@app.cell
def _(query_params):
    average_period_dropdown = mo.ui.dropdown(
        options=[core.DAILY, core.MONTHLY],
        label="Averaging Time Period",
        value=query_params["avg_period"] or core.DAILY,
        on_change=lambda value: query_params.set("avg_period", value),
    )
    return (average_period_dropdown,)


@app.cell
def _(average_period_dropdown, end_year_dropdown, start_year_dropdown):
    mo.hstack([start_year_dropdown, end_year_dropdown, average_period_dropdown])


@app.cell
def _(average_period_dropdown, column, df_no_index, query_params):
    _period = average_period_dropdown.value
    means = core.period_means(df_no_index, column, _period)

    _per = "day" if _period == core.DAILY else "month"
    _threshold_chart = (
        alt.Chart(means)
        .mark_bar()
        .encode(
            alt.X("count", bin=True, title=f"Values per {_per}"),
            y="count()",
        )
    )
    _stop = int(means["count"].max())
    _key = f"threshold_{_period.lower()}"
    threshold = mo.ui.number(
        start=0,
        stop=_stop,
        step=1,
        value=common.query_param_int(
            query_params,
            _key,
            fallback=core.threshold_default(_period),
            maximum=_stop,
        ),
        label=f"Minimum number of {'daily' if _period == core.DAILY else 'monthly'} values",
        # Guarded like the dropdowns: emptying the field hands the callback
        # None, and int(None) is a TypeError.
        on_change=lambda value: (
            query_params.set(_key, str(int(value))) if value is not None else None
        ),
    )

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
    means_filtered = core.filter_means(
        means,
        threshold=threshold.value,
        start_year=start_year_dropdown.value,
        end_year=end_year_dropdown.value,
    )
    # means_filtered
    return (means_filtered,)


@app.cell
def _(
    average_period_dropdown,
    end_year_dropdown,
    means_filtered,
    start_year_dropdown,
    year_dropdown,
):
    _period = average_period_dropdown.value
    time_col = core.time_column(_period)

    clim_df = core.climatology(means_filtered, _period, year_dropdown.value)

    _range = f"({start_year_dropdown.value} - {end_year_dropdown.value})"
    mean_range_name = f"Mean {_range}"
    min_range_name = f"Min {_range}"
    max_range_name = f"Max {_range}"

    _when = "date" if _period == core.DAILY else "month"
    min_date_name = f"Min {_when}"
    max_date_name = f"Max {_when}"

    # Rounded by name rather than frame-wide: pandas warns that round() has no
    # effect on the date columns sitting alongside these.
    clim_df = clim_df.round({"mean": 2, "min": 2, "max": 2}).rename(
        columns={
            "mean": mean_range_name,
            "min": min_range_name,
            "max": max_range_name,
            "min_date": min_date_name,
            "max_date": max_date_name,
        },
    )
    return clim_df, max_range_name, mean_range_name, min_range_name, time_col


@app.cell
def _(clim_df, max_range_name, min_range_name, time_col):
    area = (
        alt.Chart(clim_df)
        .mark_area(color="yellow", opacity=0.5)
        .encode(
            alt.X(time_col, type="temporal"),
            alt.Y(min_range_name),
            alt.Y2(max_range_name),
        )
    )
    return (area,)


@app.cell
def _(clim_df, mean_range_name, time_col):
    mean = (
        alt.Chart(clim_df)
        .mark_line()
        .encode(
            alt.X(time_col, type="temporal"),
            alt.Y(mean_range_name),
        )
    )
    return (mean,)


@app.cell
def _(average_period_dropdown, column, df_no_index, year_dropdown):
    df_year = core.year_series(
        df_no_index,
        column,
        average_period_dropdown.value,
        year_dropdown.value,
    )
    return (df_year,)


@app.cell
def _(df_year, time_col, ts):
    _y_title = f"{ts['data_type']['long_name']} ({ts['data_type']['units']})"

    line = (
        alt.Chart(df_year)
        .mark_point(color="red")
        .encode(
            alt.X(time_col, type="temporal"),
            alt.Y("mean").title(_y_title),
        )
    )
    return (line,)


@app.cell
def _(
    clim_df,
    end_year_dropdown,
    platform,
    start_year_dropdown,
    time_col,
    ts,
    year_dropdown,
):
    logo = common.neracoos_logo(
        clim_df[time_col].max(),
        f"{ts['app_name']} at {platform['id']} for {start_year_dropdown.value} thru {max([end_year_dropdown.value, year_dropdown.value])}",
        time_col=time_col,
    )
    return (logo,)


@app.cell
def _(area, line, logo, mean, ts):
    if "direction" in ts["data_type"]["standard_name"].lower():
        _layered = logo + mean + line
    else:
        _layered = logo + area + mean + line
    combined_chart = mo.ui.altair_chart(_layered.properties(width="container"))
    combined_chart


@app.cell
def _(end_year_dropdown, platform, start_year_dropdown, ts):
    mo.hstack(
        [
            mo.md(
                f"[Platform on Mariners Dashboard](https://mariners.neracoos.org/platform/{platform['id']})",
            ),
            mo.md(f"[Dataset on ERDDAP]({common.erddap_download_url(ts)})"),
            mo.md(
                f"Climatology calculated from {start_year_dropdown.value} to {end_year_dropdown.value}",
            ),
        ],
    )


@app.cell
def _(average_period_dropdown, clim_df, df_year, time_col, year_dropdown):
    _period = average_period_dropdown.value
    _year_column = (
        f"{'Daily' if _period == core.DAILY else 'Monthly'} means"
        f" for {year_dropdown.value}"
    )

    df_combined = clim_df.merge(
        df_year.rename({"mean": _year_column}, axis=1),
        on=time_col,
        how="left",
    )

    if _period == core.DAILY:
        df_combined[time_col] = df_combined[time_col].dt.date

    # Named rather than sliced by position: the slicing this replaces dropped
    # the mean column outright from the monthly table.
    _columns = [
        time_col,
        _year_column,
        *(c for c in df_combined.columns if c not in (time_col, _year_column)),
    ]
    df_combined = df_combined[_columns]
    df_combined = df_combined.round(
        dict.fromkeys(df_combined.select_dtypes("number").columns, 2),
    )

    mo.accordion({"Show data": df_combined})


if __name__ == "__main__":
    app.run()
