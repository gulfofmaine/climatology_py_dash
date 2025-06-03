import marimo

__generated_with = "0.13.15"
app = marimo.App(width="medium")


@app.cell
def _():
    import httpx
    import erddapy
    import pandas as pd
    import marimo as mo

    return erddapy, httpx, mo, pd


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
    platforms = {
        p["properties"]["station_name"] or p["id"]: p for p in platform_json["features"]
    }
    return (platforms,)


@app.cell
def _(mo, platforms):
    platform_selector = mo.ui.dropdown(platforms)
    return (platform_selector,)


@app.cell
def _(platform_selector):
    platform_selector
    return


@app.cell
def _(platform_selector):
    platform_selector.value
    return


@app.function
def name_for_ts(ts: dict):
    name = ts["data_type"]["long_name"]
    if ts["depth"]:
        name = f"{name} - {ts['depth']}"

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
    platform_time_series
    return


@app.cell
def _(mo, platform_time_series):
    time_series_selector = mo.ui.multiselect(platform_time_series)
    return (time_series_selector,)


@app.cell
def _(time_series_selector):
    time_series_selector
    return


@app.cell
def _(erddapy, mo, pd):
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

    return (load_ts,)


@app.cell
def _(load_ts, mo, time_series_selector):
    loaded_ts = {}

    with mo.status.spinner(title="Loading data from ERDDAP"):
        for _ts in time_series_selector.value:
            _key = (name_for_ts(_ts), _ts["data_type"]["units"])
            _df = load_ts(_ts)
            loaded_ts[_key] = _df

    loaded_ts
    return (loaded_ts,)


@app.cell
def _(loaded_ts, pd):
    pd.concat(loaded_ts.values())
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
