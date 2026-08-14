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
    import units


@app.cell
def _(query_params):
    common.set_defaults(page="by_platform")
    units_radio = common.units_radio(query_params)
    common.sidebar_menu(units_radio)
    return (units_radio,)


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
    platforms = common.platforms_with_readings(common.platforms_by_name(platform_json))
    return (platforms,)


@app.cell
def _():
    query_params = mo.query_params()
    return (query_params,)


@app.cell
def _(platforms, query_params):
    _ids_to_names = {feature["id"]: name for name, feature in platforms.items()}
    _default_name = _ids_to_names.get(query_params.get("platform"))

    platform_selector = mo.ui.dropdown(
        platforms,
        label="Select platform",
        value=_default_name,
        on_change=lambda value: query_params.set(
            "platform",
            value["id"] if value else None,
        ),
    )
    return (platform_selector,)


@app.cell
def _(platform_selector):
    platform_time_series = common.timeseries_by_name(platform_selector.value)
    return (platform_time_series,)


@app.cell
def _(platform_time_series, query_params):
    time_series_selector = mo.ui.multiselect(
        platform_time_series,
        label="Select time series",
        value=common.query_param_list_default(
            query_params,
            "ts",
            platform_time_series,
            fallback=[],
        ),
        on_change=lambda value: query_params.set(
            "ts",
            ",".join(v["app_name"] for v in value),
        ),
    )
    return (time_series_selector,)


@app.cell
def _(platform_selector, time_series_selector):
    mo.hstack([platform_selector, time_series_selector])


@app.cell
def _(platform_selector, time_series_selector, units_radio):
    loaded_ts = {}
    unit_ts = {}

    if platform_selector.value:
        monitoring.tag_context(platform=platform_selector.value["id"])
    if time_series_selector.value:
        monitoring.tag_context(
            timeseries=",".join(
                sorted(common.name_for_ts(_ts) for _ts in time_series_selector.value),
            ),
        )
    monitoring.tag_context(units=units_radio.value)

    with mo.status.spinner(title="Loading data from ERDDAP"):
        for _ts in time_series_selector.value:
            _col_name = common.name_for_ts(_ts)
            _source = _ts["data_type"]["units"]
            _target = units.target_unit(
                _ts["data_type"]["standard_name"],
                _source,
                units_radio.value,
            )
            # Keyed by the display label, not the source unit, because that key
            # is what the subplots are grouped by: a buoy reporting
            # barometric_pressure in millibars and air_pressure in mbar used to
            # get two pressure rows, and now gets one.
            _unit = units.label(_target)
            _key = (_col_name, _unit)
            try:
                _df = common.load_ts(_ts, _col_name)
                # load_ts hands back a fresh frame every call, so converting in
                # place cannot poison the cache behind it.
                _df[_col_name] = units.convert(_df[_col_name], _source, _target)
                loaded_ts[_key] = _df
                unit_ts.setdefault(_unit, []).append(_col_name)
            except common.ErddapLoadError as error:
                mo.output.append(
                    common.admonition(
                        str(error),
                        title=f"Unable to load data for {_col_name}",
                        kind="error",
                        sentry_event_id=error.sentry_event_id,
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

    # One wide (one column per series, every unit included) hit frame shared
    # by every row, so hovering any single row's crosshair reports every
    # selected series' value at that instant -- not just the values for the
    # unit being hovered. filtered_df is already this shape: one column per
    # loaded timeseries, whatever its unit.
    _unit_for_key = {
        _ts_key: _unit for _unit, _ts_keys in unit_ts.items() for _ts_key in _ts_keys
    }
    _all_ts_keys = list(_unit_for_key)
    _hit_df = filtered_df[_all_ts_keys].reset_index()
    _value_fields = [(_col, f"{_col} ({_unit_for_key[_col]})") for _col in _all_ts_keys]

    stack = alt.vconcat()
    _nearest_time = None
    for i, (_unit, _ts_keys) in enumerate(unit_ts.items()):
        # Every subplot draws from the one melted frame, so without the filter
        # each takes its colour domain from all of the series -- listing the
        # other units' series in its legend and drawing them as nulls.
        _row = _base.encode(
            x="time (UTC):T",
            y=f"{_unit}:Q",
            color="variable",
        ).transform_filter(alt.FieldOneOfPredicate(field="variable", oneOf=_ts_keys))

        # Threading _nearest_time through every row links them: the same
        # Vega-Lite selection reused across multiple views resolves to one
        # shared instance, so hovering any row moves the crosshair -- and
        # shows every series' value at that instant, not just this row's
        # own -- in every row at once. See common.linked_hover()'s docstring
        # for why calling .add_params() again in every row is required (each
        # vconcat row is a separate view) and safe (Altair deduplicates the
        # repeated registration rather than emitting a second Vega param).
        _row, _nearest_time = common.linked_hover(
            _row,
            _hit_df,
            "time (UTC)",
            _value_fields,
            hover=_nearest_time,
        )

        if i == 0:
            # Logo goes *under* the hover layers (added first, not last): its
            # mark_image uses clip=False, and as the topmost layer it was
            # intercepting pointerover events across the whole row, silently
            # breaking the invisible hit target underneath it.
            _row = (
                common.neracoos_logo(
                    filtered_df.index.max(),
                    platform_selector.value["id"],
                )
                + _row
            )
        stack &= _row.properties(width="container")

    # The rows' width="container" is only half of responsive sizing, and the
    # autosize below is the other half. Vega-Lite derives an
    # autosize: fit-x from width="container" for single and layered views, but
    # never for a vconcat -- it warns "Width 'container' only works for single
    # views and layered views" and compiles no autosize at all. Without it,
    # width="container" sizes each row's *plotting area* to the full container
    # width and the y-axis labels, legend and padding then push the canvas
    # ~190px past it: the canvas overflows div.chart-wrapper (overflow-x:
    # auto), which crops the logo and hides the colour legend entirely (#162).
    #
    # fit-x, not fit: Vega-Lite silently downgrades autosize fit to pad for
    # concat views, which puts the overflow straight back.
    #
    # The width="container" here is *not* redundant with the rows', and not
    # dead weight either, despite being schema-invalid on a VConcatChart
    # ("VConcatChart has no parameter named 'width'") and surviving only
    # because mo.ui.altair_chart serializes with to_dict(validate=False).
    # marimo's frontend attaches its container ResizeObserver only when the
    # *top-level* spec width is "container"; that observer is what dispatches
    # the window:resize the compiled width signal listens for when the
    # container changes width without the window doing so -- collapsing the
    # sidebar being the case that happens. Drop it and the canvas stays frozen
    # at its old width in a wider wrapper (measured: 752px canvas, 972px
    # wrapper) until an actual window resize comes along.
    mo.ui.altair_chart(
        stack.properties(
            width="container",
            autosize=alt.AutoSizeParams(type="fit-x", contains="padding"),
        ),
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
