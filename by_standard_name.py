import marimo

__generated_with = "0.23.11"
app = marimo.App(
    width="medium",
    app_title="NERACOOS Visualize and Compare - Data Type",
)

with app.setup:
    import altair as alt
    import marimo as mo
    import pandas as pd

    import common
    import monitoring
    import units


@app.cell
def _():
    mo.md(
        r"""
    # Visualize and Compare by Data Type (beta)

    Compare the same type of data for multiple buoys.
    """,
    )


@app.cell
def _(query_params):
    common.set_defaults(page="by_standard_name")
    units_radio = common.units_radio(query_params)
    common.sidebar_menu(units_radio)
    return (units_radio,)


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
            _name = common.platform_display_name(_platform)
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
        label="Data Type",
        value=_standard_name_default,
        on_change=lambda value: query_params.set("standard_name", value),
    )
    return (standard_name_dropdown,)


@app.cell
def _(platform_standards, query_params, standard_name_dropdown):
    try:
        platform_options = platform_standards[standard_name_dropdown.value]
        selected_ts_keys = mo.ui.multiselect(
            sorted(platform_options.keys()),
            label="Platforms",
            max_selections=10,
            value=common.query_param_list_default(
                query_params,
                "platforms",
                platform_options,
                fallback=[],
            ),
            on_change=lambda value: query_params.set("platforms", ",".join(value)),
        )
    except KeyError:
        selected_ts_keys = None
    return platform_options, selected_ts_keys


@app.cell
def _(selected_ts_keys, standard_name_dropdown):
    mo.vstack([i for i in [standard_name_dropdown, selected_ts_keys] if i is not None])


@app.cell
def _(standard_name_dropdown, standards, units_radio):
    try:
        _data_type = standards[standard_name_dropdown.value]
    except KeyError:
        mo.stop(
            True,
            common.admonition(
                "",
                title="Please select a data type to display",
                kind="attention",
            ),
        )

    # Buoy Barn does not guarantee every platform spells this standard name's
    # unit the same way (e.g. air_temperature: "celsius" almost everywhere,
    # bare "F" -- which pint parses as Farad, not Fahrenheit -- on one
    # platform) -- units.display_unit() reads the target straight out of
    # TARGETS instead of validating against whichever platform's data_type
    # happened to land in standards[...], so one bad platform's spelling
    # can't clobber the label, or (via convert() below, per platform) the
    # values, for every other platform on the page.
    target_unit = (
        units.display_unit(standard_name_dropdown.value, units_radio.value)
        or _data_type["units"]
    )
    # ``unit`` names the melted frame's value column, which is also the chart's
    # y encoding and the tooltip's field, so the display label reaches all
    # three by being this one string.
    unit = units.label(target_unit)
    monitoring.tag_context(units=units_radio.value)
    return target_unit, unit


@app.cell
def _(selected_ts_keys):
    try:
        selected_ts_keys.value
    except AttributeError:
        mo.stop(
            True,
            common.admonition("Please select platforms to display", kind="attention"),
        )


@app.cell
def _(
    platform_options,
    selected_ts_keys,
    standard_name_dropdown,
    target_unit,
    unit,
):
    _wide_dfs = []

    if standard_name_dropdown.value:
        monitoring.tag_context(standard_name=standard_name_dropdown.value)
    if selected_ts_keys.value:
        monitoring.tag_context(platforms=",".join(sorted(selected_ts_keys.value)))

    try:
        with mo.status.spinner(title="Loading data from ERDDAP"):
            for _ts_name in selected_ts_keys.value:
                _ts = platform_options[_ts_name]
                try:
                    _df = common.load_ts(_ts, _ts_name)
                except common.ErddapLoadError as error:
                    # Keep going: one unavailable platform should not take the
                    # whole comparison down with it.
                    mo.output.append(
                        common.admonition(
                            str(error),
                            title=f"Unable to load data for {_ts_name}",
                            kind="error",
                            sentry_event_id=error.sentry_event_id,
                        ),
                    )
                    continue
                if not _df.index.is_unique:
                    _df = _df.loc[~_df.index.duplicated(keep="first")]
                # Converted per platform, not once over the whole concatenated
                # frame: Buoy Barn does not guarantee every platform spells
                # this standard name's unit the same way, and convert() safely
                # no-ops a platform whose own spelling doesn't match
                # target_unit rather than mis-converting it under another
                # platform's units.
                _df[_ts_name] = units.convert(
                    _df[_ts_name],
                    _ts["data_type"]["units"],
                    target_unit,
                )
                _wide_dfs.append(_df)

            wide_df = pd.concat(_wide_dfs, axis=1)
            wide_melted = pd.melt(wide_df.reset_index(), id_vars="time (UTC)")
            wide_melted = wide_melted.rename(
                columns={"variable": "Timeseries", "value": unit},
            )
            wide_melted = wide_melted.set_index("time (UTC)")
    except ValueError as error:
        if _wide_dfs:
            # pd.concat([], axis=1) is the "nothing selected yet" case; a
            # ValueError with data present is a genuine bug wearing the same
            # message, and would otherwise never reach Sentry.
            monitoring.report(
                error,
                where="by_standard_name.concat",
                level="error",
            )
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


@app.cell
def _(date_range, wide_melted):
    try:
        time_filtered_df = wide_melted[
            (wide_melted.index >= date_range.value[0].isoformat())
            & (wide_melted.index <= date_range.value[1].isoformat())
        ]
    except AttributeError:
        mo.stop(True)

    filtered_df, _resampled_to = common.resample_to_budget(
        time_filtered_df,
        by="Timeseries",
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
def _(filtered_df, standard_name_dropdown, standards, unit):
    _logo = common.neracoos_logo(
        filtered_df.index.max(),
        standards[standard_name_dropdown.value]["long_name"],
    )
    _chart = (
        alt.Chart(filtered_df.reset_index())
        .mark_line()
        .encode(x="time (UTC):T", y=f"{unit}:Q", color="Timeseries")
    )

    # A wide (one column per platform) frame for the tooltip, so hovering
    # reports every selected buoy's value at that instant in one tooltip box
    # instead of whichever platform's melted-frame row is topmost -- same
    # trick as climatology.py's clim_tooltip/df_plot, and as by_platform.py's
    # per-row _hit_df.
    try:
        # pivot(), not pivot_table(): duplicate (time, Timeseries) pairs
        # should raise so the except branch below can catch them, rather
        # than pivot_table()'s default of silently averaging them together.
        _hit_df = (
            filtered_df.reset_index()  # noqa: PD010
            .pivot(index="time (UTC)", columns="Timeseries", values=unit)
            .reset_index()
        )
        _value_fields = [
            (_col, f"{_col} ({unit})")
            for _col in _hit_df.columns
            if _col != "time (UTC)"
        ]
    except ValueError:
        # Duplicate (time, Timeseries) pairs after resampling -- shouldn't
        # happen given resample_to_budget(..., by="Timeseries")'s groupby,
        # but fall back to one series per tooltip rather than crash.
        _hit_df = filtered_df.reset_index()
        _value_fields = [(unit, unit)]

    _chart, _ = common.linked_hover(_chart, _hit_df, "time (UTC)", _value_fields)
    _chart = _chart.properties(width="container")

    mo.ui.altair_chart(_chart + _logo)


@app.cell
def _(filtered_df, wide_df):
    mo.accordion(
        {
            "Full dataframe and download": wide_df,
            "Filtered dataframe and download": filtered_df,
        },
    )


if __name__ == "__main__":
    app.run()
