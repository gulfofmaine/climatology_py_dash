import base64
from io import BytesIO

from PIL import Image
import altair as alt
import pandas as pd
import marimo as mo

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


def set_defaults():
    """Set common defaults for the app."""
    pd.set_option("display.precision", 2)


@mo.cache
def load_platform_json():
    """Load the platform JSON from the NERACOOS API."""
    import httpx

    platform_res = httpx.get("https://buoybarn.neracoos.org/api/platforms/")
    if platform_res.status_code != 200:
        raise ValueError(f"Failed to load platforms: {platform_res.status_code}")
    return platform_res.json()


def load_ts_from_erddap(ts: dict) -> pd.DataFrame:
    """Load a timeseries from ERDDAP."""
    import erddapy

    e = erddapy.ERDDAP(ts["server"], protocol="tabledap")
    e.dataset_id = ts["dataset"]
    e.variables = ["time", ts["variable"]]
    e.constraints = ts["constraints"] or {}
    df = e.to_pandas(index_col="time (UTC)", parse_dates=True)
    df = df.dropna()
    return df


def neracoos_logo(max_time, title: str, time_col: str = "time (UTC)"):
    """Render the NERACOOS logo at the top right place on a plot.

    max_value should be the"""
    _pil_image = Image.open("./public/neracoos.png")
    _output = BytesIO()
    _pil_image.save(_output, format="PNG")
    _base64_images = [
        "data:image/png;base64," + base64.b64encode(_output.getvalue()).decode(),
    ]
    try:
        _image_df = pd.DataFrame(
            {
                time_col: max_time,
                "image": _base64_images,
            },
        )
    except ValueError as e:
        raise ValueError(f"Error creating dataframe from {max_time=}") from e

    logo = (
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
            x=time_col,
            y=alt.value(0),
            url="image",
        )
    )
    return logo


def sidebar_menu():
    """Build a sidebar menu"""
    return mo.sidebar(
        [
            mo.md("""
            <a href="https://neracoos.org">
    <img src="public/neracoos.png" />
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
