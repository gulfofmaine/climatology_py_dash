import marimo

__generated_with = "0.10.16"
app = marimo.App(width="medium")


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
def _(mo, platforms):
    platform_dropdown = mo.ui.dropdown(options=platforms, label="Choose a platform")
    platform_dropdown
    return (platform_dropdown,)


@app.cell
def _(mo, platform_dropdown):
    platform = platform_dropdown.value
    if platform == None:
        platform_callout = mo.callout("Please select a platform to view climatologies for", kind="warn")
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
        timeseries[r["data_type"]["long_name"]] = r
    return r, timeseries


@app.cell
def _(mo, timeseries):
    timeseries_dropdown = mo.ui.dropdown(options=timeseries, label="Choose a timeseries")
    timeseries_dropdown
    return (timeseries_dropdown,)


@app.cell
def _(mo, timeseries_dropdown):
    ts = timeseries_dropdown.value
    if ts == None:
        ts_callout = mo.callout("Please select a timeseries to compute climatologies for", kind="warn")
        mo.output.append(ts_callout)
    return ts, ts_callout


@app.cell
def _(mo, ts):
    mo.stop(ts == None)
    return


@app.cell
def _(erddapy, ts):
    e = erddapy.ERDDAP(ts["server"], protocol="tabledap")
    e.dataset_id = ts["dataset"]
    e.variables = ["time", ts["variable"]]
    return (e,)


@app.cell
def _(e, ts):
    e.constraints = ts["constraints"] or {}
    df_all = e.to_pandas(
        index_col="time (UTC)",
        parse_dates=True,
    ).dropna()
    # df_all
    return (df_all,)


@app.cell
def _(df_all):
    df_no_index = df_all.reset_index()
    df_no_index = df_no_index.rename({"time (UTC)": "Date"}, axis=1)
    return (df_no_index,)


@app.cell
def _(df_all, mo):
    years = [str(y) for y in df_all.index.year.unique()]
    year_dropdown = mo.ui.dropdown(options=years, label="Select a year", value=years[-1])
    year_dropdown
    return year_dropdown, years


@app.cell
def _(datetime, year_dropdown):
    year = datetime(int(year_dropdown.value), 1, 1)
    return (year,)


@app.cell
def _(df_all, df_no_index, timedelta, year, years):
    clim_df = df_no_index[df_no_index["Date"] < years[-1]].groupby(df_no_index["Date"].dt.day_of_year)[df_all.columns[0]].agg(
        ["std", "mean", "max", "min"]
    ).reset_index()
    clim_df["Date"] = clim_df["Date"].apply(lambda x: year + timedelta(days=x-1))
    # clim_df
    return (clim_df,)


@app.cell
def _(years):
    f"Climatology calculated from {years[0]} to {years[-2]}"
    return


@app.cell
def _(alt, clim_df):
    area = alt.Chart(clim_df).mark_area(color="yellow", opacity=.5).encode(
        alt.X("Date"),
        alt.Y("min"),
        alt.Y2("max"),
    )

    # area_chart = mo.ui.altair_chart(area)
    # area_chart
    return (area,)


@app.cell
def _(alt, clim_df):
    mean = alt.Chart(clim_df).mark_line().encode(
        alt.X("Date"),
        alt.Y("mean"),
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
def _(df_all, df_no_index, timedelta, year, year_dropdown):
    df_year = df_no_index[(f"{year_dropdown.value}-01-01T00:00" < df_no_index["Date"]) & (df_no_index["Date"] < f"{year_dropdown.value}-12-31T23:59:59")]
    df_year = df_year.groupby(df_year["Date"].dt.day_of_year)[df_all.columns[0]].agg(["mean"])
    df_year = df_year.reset_index()
    df_year["Date"] = df_year["Date"].apply(lambda x: year + timedelta(days=x-1))
    # df_year
    return (df_year,)


@app.cell
def _(alt, df_year, ts):
    title = f"{ts['data_type']['long_name']} ({ts['data_type']['units']})"

    line = alt.Chart(df_year).mark_line().encode(
        alt.X("Date"),
        # alt.Y("mean").title(df_all.columns[0]),
        alt.Y("mean").title(title),
        alt.Color("line:N", scale=alt.Scale(range=["red"]), title="2025")
        # alt.Color("line:N", scale=alt.Scale(range=["red"]), legend=alt.Legend(symbolType="line"), title=year_dropdown.value)
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
def _(clim_df, df_year, mo, pd, year_dropdown):
    df_combined = pd.merge(clim_df, df_year.rename({"mean": year_dropdown.value}, axis=1), on="Date", how="left")
    mo.accordion({"Show data": df_combined})
    return (df_combined,)


@app.cell
def _(mo):
    mo.md(
        """
        <!-- base = alt.Chart(df_combined)
        both = base.mark_line().encode(
            alt.X("Date"),
            alt.Y(alt.repeat("layer")), 
            color=alt.datum(alt.repeat("layer"))
        ).repeat(layer=["mean", "2025"])
        mo.ui.altair_chart(both) -->
        """
    )
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
