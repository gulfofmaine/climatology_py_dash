import base64
import functools
import re
from pathlib import Path

import altair as alt
import marimo as mo
import pandas as pd

import monitoring

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


def tag_page(page: str) -> None:
    """Tag this kernel's Sentry events with the notebook page it came from.

    ``root.py`` has no other setup to hang this on, so it calls this directly
    rather than through ``set_defaults()``.
    """
    monitoring.tag_page(page)


class ErddapLoadError(Exception):
    """A timeseries could not be loaded from ERDDAP.

    erddapy talks to ERDDAP with ``requests``, so pages catching httpx
    exceptions never caught anything at all. Wrapping the failure in one
    exception type keeps the pages out of that business entirely.

    ``sentry_event_id`` carries the id of the Sentry event this failure was
    already reported under (see ``load_ts_from_erddap``), so a caller
    building an admonition from this exception can offer it back to
    ``common.admonition(..., sentry_event_id=...)`` and let a feedback
    submission be linked to this exact event.
    """

    def __init__(self, message: str, *, sentry_event_id: str | None = None) -> None:
        super().__init__(message)
        self.sentry_event_id = sentry_event_id


def set_defaults(page: str | None = None):
    """Set common defaults for the app.

    ``page`` tags every Sentry event from this notebook's kernel thread with
    the page it came from, so a reported cell error is traceable to the
    notebook the user was on.
    """
    if page:
        tag_page(page)

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

    with monitoring.operation(
        "buoy-barn platforms",
        op="http.client",
        visibility=visibility,
    ) as span:
        platform_res = httpx2.get(
            BUOY_BARN_PLATFORMS,
            params={"visibility": visibility} if visibility else None,
            timeout=HTTP_TIMEOUT,
        )
        if platform_res.status_code != 200:
            msg = f"Failed to load platforms: {platform_res.status_code}"
            raise ValueError(msg)
        platforms = platform_res.json()
        if span is not None:
            span.set_data("feature_count", len(platforms.get("features", ())))
        return platforms


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


def query_param_int(query_params, key, *, fallback, minimum=0, maximum=None):
    """A query parameter as an int, clamped into range, or ``fallback``.

    Widgets like ``mo.ui.number`` reject a value outside their own
    ``start``/``stop`` range, so both a stored value and ``fallback`` are
    clamped here -- a sparse dataset can have a maximum observation count
    below a threshold's usual default.
    """
    value = query_params.get(key)
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = fallback

    result = max(result, minimum)
    if maximum is not None:
        result = min(result, maximum)
    return int(result)


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
    with monitoring.operation(
        f"erddap {ts['dataset']}",
        op="http.client",
        server=ts["server"],
        dataset=ts["dataset"],
        variable=ts["variable"],
    ):
        try:
            df = e.to_pandas(index_col="time (UTC)", parse_dates=True)
        except (requests.exceptions.RequestException, OSError, ValueError) as error:
            # ERDDAP answers a rejected request with a non-CSV body, which
            # reaches us as a pandas parse error rather than as an HTTP
            # failure. Reported here, before wrapping, since every caller of
            # this function handles ErddapLoadError and it would otherwise
            # never reach Sentry. Grouped by server rather than dataset: an
            # ERDDAP outage should be one alertable issue with many events,
            # not one issue per dataset.
            #
            # Reported from inside the span (not after this `with` block
            # exits): capture_exception() only picks up trace context that is
            # still current, and the span's own __exit__ would have already
            # torn that down by the time an outer `except` ran.
            event_id = monitoring.report(
                error,
                where="erddap.load_ts",
                level="warning",
                fingerprint=["erddap-load", ts["server"]],
                dataset=ts["dataset"],
                variable=ts["variable"],
            )
            msg = f"Could not load {ts['dataset']} from {ts['server']}: {error}"
            raise ErddapLoadError(msg, sentry_event_id=event_id) from error
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
    axis=None,
):
    """Render the NERACOOS logo at the top right place on a plot.

    ``max_time`` should be the largest time in the chart being layered onto, so
    that the logo sits at its right edge. Pass the same ``axis`` the other
    layers use: layered charts merge their axes, and leaving this one to its
    defaults gives Vega two different definitions to reconcile.
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
                axis=axis if axis is not None else alt.Undefined,
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
    *,
    report: bool | None = None,
    sentry_event_id: str | None = None,
):
    """Create an admonition.

    kind can be admonition, attention, warning, or error

    ``report`` offers a link that opens the Sentry feedback form. It defaults
    to on for errors when browser monitoring is configured, and is always off
    otherwise so the link is never a dead click. The trigger is a data
    attribute rather than an ``onclick``: marimo runs rendered HTML through
    DOMPurify (which strips event handlers) and then html-react-parser, so the
    click is handled by delegation in the snippet ``monitoring.html_head()``
    injects.

    ``sentry_event_id`` -- the id of a Sentry event this admonition's failure
    was already reported under, e.g. ``ErddapLoadError.sentry_event_id`` --
    lets a feedback submission made from this admonition's link be linked to
    that specific event, via the ``beforeSendFeedback`` hook in
    ``monitoring.html_head()``, rather than floating free of it.
    """
    if report is None:
        report = kind == "error" and monitoring.enabled()

    # Sentry's own event ids are 32 lowercase hex characters; anything else is
    # not a real one, and this is the only guard before it goes straight into
    # an HTML attribute.
    event_attr = ""
    if report and sentry_event_id and re.fullmatch(r"[0-9a-f]{32}", sentry_event_id):
        event_attr = f' data-sentry-event-id="{sentry_event_id}"'

    # No newline before this: mo.md() runs the whole string through
    # inspect.cleandoc(), which dedents by the *smallest* common leading
    # whitespace across all lines. A footer on its own line would start at
    # column 0 while every other line here sits at this function's source
    # indentation, so cleandoc would find a common indent of zero, leave the
    # ///-fenced lines exactly as indented as they are in the source, and the
    # indented /// markers would then fail to parse as a directive at all --
    # rendering as literal text instead of a styled admonition. Keeping the
    # link on the same line as content sidesteps that entirely.
    footer = (
        f' <a href="#" data-sentry-report="admonition"{event_attr}>'
        "Tell us what you were doing</a>"
        if report
        else ""
    )
    return mo.md(
        f"""
        /// {kind} | {title}

        {content}{footer}
        ///
        """,
    )
