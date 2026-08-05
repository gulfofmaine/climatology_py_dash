import base64
import functools
from pathlib import Path

import altair as alt
import marimo as mo
import pandas as pd

# Maximum number of rows that Altair will render
MAX_ROWS = 10_000

# Time groups to use for resampling
TIME_GROUPS = [
    # "1h",
    # "6h",
    # "12h",
    ("1D", "daily"),
    ("1W", "weekly"),
    ("MS", "monthly"),
]

BUOY_BARN_PLATFORMS = "https://buoybarn.neracoos.org/api/platforms/"

# Resolved against this file rather than the process working directory, so the
# logo is found however the app was launched.
LOGO_PATH = Path(__file__).parent / "public" / "neracoos.png"

# (connect, read) timeouts for ERDDAP, in seconds. Without them a slow or
# oversized dataset pins the kernel indefinitely with nothing shown to the user.
ERDDAP_TIMEOUT = (10, 180)

HTTP_TIMEOUT = 30


class ErddapLoadError(Exception):
    """A timeseries could not be loaded from ERDDAP.

    erddapy talks to ERDDAP with ``requests``, so pages catching httpx
    exceptions never caught anything at all. Wrapping the failure in one
    exception type keeps the pages out of that business entirely.
    """


def set_defaults():
    """Set common defaults for the app."""
    pd.set_option("display.precision", 2)

    # Inline chart data in the vega spec rather than marimo's default of
    # serving it as virtual files. Virtual files are flushed whenever a cell
    # re-runs, which races the browser's in-flight fetches and leaves charts
    # stuck retrying dead URLs (marimo-team/marimo#9127).
    from marimo._plugins.ui._impl.charts.altair_transformer import (
        register_transformers,
    )

    register_transformers()
    alt.data_transformers.enable("marimo_inline_csv")


@mo.cache
def load_platform_json(visibility: str | None = None):
    """Load the platform JSON from the NERACOOS API.

    ``visibility`` filters server side, e.g. ``"climatology"`` for the platforms
    Buoy Barn flags as suitable for climatologies.
    """
    import httpx2

    platform_res = httpx2.get(
        BUOY_BARN_PLATFORMS,
        params={"visibility": visibility} if visibility else None,
        timeout=HTTP_TIMEOUT,
    )
    if platform_res.status_code != 200:
        msg = f"Failed to load platforms: {platform_res.status_code}"
        raise ValueError(msg)
    return platform_res.json()


def platforms_by_name(platform_json: dict) -> dict:
    """Platform features keyed by station name, falling back to id, sorted."""
    platforms = {
        feature["properties"]["station_name"] or feature["id"]: feature
        for feature in platform_json["features"]
    }
    return dict(sorted(platforms.items()))


def name_for_ts(ts: dict) -> str:
    """Label for a timeseries: its long name, plus the depth when it has one."""
    name = ts["data_type"]["long_name"]
    if ts["depth"]:
        name = f"{name} @ {ts['depth']}m"
    return name


def timeseries_by_name(platform: dict | None) -> dict:
    """A platform's readings keyed by label, sorted, with ``app_name`` set."""
    timeseries = {}
    if not platform:
        return timeseries

    for reading in platform["properties"]["readings"]:
        name = name_for_ts(reading)
        reading["app_name"] = name
        timeseries[name] = reading

    return dict(sorted(timeseries.items()))


def query_param_default(query_params, key: str, options, fallback=None):
    """A query parameter's value if it is one of ``options``, else ``fallback``.

    Every dropdown that round-trips through the URL needs this check: a
    parameter left over from another platform or dataset is not a valid value
    for the dropdown being built.
    """
    value = query_params.get(key)
    if value and value in options:
        return value
    return fallback


def erddap_client(ts: dict):
    """A configured erddapy client for a Buoy Barn timeseries."""
    import erddapy

    e = erddapy.ERDDAP(ts["server"], protocol="tabledap")
    e.dataset_id = ts["dataset"]
    e.variables = ["time", ts["variable"]]
    e.constraints = ts["constraints"] or {}
    e.requests_kwargs = {"timeout": ERDDAP_TIMEOUT}
    return e


def erddap_download_url(ts: dict) -> str:
    """The ERDDAP URL a timeseries' data was requested from."""
    return erddap_client(ts).get_download_url()


def load_ts_from_erddap(ts: dict) -> pd.DataFrame:
    """Load a timeseries from ERDDAP, or raise ``ErddapLoadError``."""
    import requests

    e = erddap_client(ts)
    try:
        df = e.to_pandas(index_col="time (UTC)", parse_dates=True)
    except (requests.exceptions.RequestException, OSError, ValueError) as error:
        # ERDDAP answers a rejected request with a non-CSV body, which reaches
        # us as a pandas parse error rather than as an HTTP failure.
        msg = f"Could not load {ts['dataset']} from {ts['server']}: {error}"
        raise ErddapLoadError(msg) from error
    return df.dropna()


def resample_to_budget(
    df: pd.DataFrame,
    max_rows: int = MAX_ROWS,
    *,
    by: str | None = None,
) -> tuple[pd.DataFrame, str | None]:
    """Resample ``df`` coarsely enough to fit ``max_rows`` rows in the vega spec.

    Returns the frame along with the name of the period it was resampled to, or
    the frame unchanged and ``None`` when it already fits. Both paths return the
    same index shape, which the two hand-rolled versions this replaces did not:
    each was written for one path and broke on the other.

    ``by`` names the column identifying each series in a long frame; leave it
    unset for a wide frame with one column per series.
    """
    if len(df) < max_rows:
        return df, None

    index_name = df.index.name
    resampled = df
    label = None

    for freq, name in TIME_GROUPS:
        if by:
            resampled = (
                df.groupby([by, pd.Grouper(level=index_name, freq=freq)])
                .mean()
                .reset_index()
                .set_index(index_name)
            )
        else:
            resampled = df.resample(freq).mean()
        label = name

        if len(resampled) < max_rows:
            break

    return resampled, label


@mo.cache
def _load_ts_cached(ts: dict, col_name: str) -> pd.DataFrame:
    df = load_ts_from_erddap(ts)
    df.columns = [col_name, *df.columns[1:]]
    return df


def load_ts(ts: dict, col_name: str) -> pd.DataFrame:
    """Load a timeseries with its value column named ``col_name``.

    Returns a fresh frame every call. Callers used to mutate what the cache
    handed back -- dropping a column from it -- which poisoned every later read.
    """
    return _load_ts_cached(ts, col_name).copy()


@functools.cache
def _logo_data_uri() -> str:
    """The logo as a data URI, read and encoded once per process."""
    return "data:image/png;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode()


def neracoos_logo(
    max_time,
    title: str,
    time_col: str = "time (UTC)",
    axis_format: str | None = None,
):
    """Render the NERACOOS logo at the top right place on a plot.

    ``max_time`` should be the largest time in the chart being layered onto, so
    that the logo sits at its right edge. ``axis_format`` has to match whatever
    the other layers use: layered charts merge their axes, so leaving it unset
    here would let this layer's default formatting win.
    """
    try:
        _image_df = pd.DataFrame(
            {
                time_col: max_time,
                "image": [_logo_data_uri()],
                "tooltip": "NERACOOS Logo",
            },
        )
    except ValueError as e:
        msg = f"Error creating dataframe from {max_time=}"
        raise ValueError(msg) from e

    return (
        alt.Chart(
            _image_df,
            title=alt.Title(
                title,
                baseline="bottom",
                anchor="start",
                dx=40,
                offset=-46,
            ),
        )
        .mark_image(
            width=219,
            height=46,
            align="right",
            baseline="bottom",
            clip=False,
        )
        .encode(
            x=alt.X(
                time_col,
                type="temporal",
                axis=alt.Axis(format=axis_format) if axis_format else alt.Undefined,
            ),
            y=alt.value(0),
            url="image",
            tooltip="tooltip",
        )
    )


def sidebar_menu():
    """Build a sidebar menu"""
    return mo.sidebar(
        [
            mo.Html("""
            <a href="https://neracoos.org">
    <img src="/static/neracoos.png" />
    </a>
    """),
            mo.nav_menu(
                {
                    "/": "NERACOOS Data Products",
                    "https://mariners.neracoos.org": f"{mo.icon('game-icons:fishing-boat')} Mariners' Dashboard",
                    f"{mo.icon('streamline-ultimate:server-share')} Data services": {
                        "https://data.neracoos.org/erddap/": {
                            "label": "ERDDAP",
                        },
                        "https://data.neracoos.org/thredds/": {"label": "THREDDS"},
                    },
                    f"{mo.icon('streamline-ultimate:analytics-graph-lines-2')} Visualize and Compare": {
                        "/by_platform": {
                            "label": "By Buoy",
                            "description": "Graph and download multiple data types for a buoy",
                        },
                        "/by_standard_name": {
                            "label": "By Data Type",
                            "description": "Compare the same type of data across multiple buoys",
                        },
                        "/climatology": {
                            "label": "Climatology",
                            "description": "View climatology for buoys",
                        },
                    },
                },
                orientation="vertical",
            ),
        ],
    )


def admonition(
    content: str,
    title: str = "Attention",
    kind: str = "admonition",
):
    """Create an admonition.

    kind can be admonition, attention, warning, or error"""
    return mo.md(
        f"""
        /// {kind} | {title}

        {content}
        ///
        """,
    )
