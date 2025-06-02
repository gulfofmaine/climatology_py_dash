import base64
from io import BytesIO

from PIL import Image
import altair as alt
import pandas as pd

def neracoos_logo(max_time, title: str, time_col: str = "time (UTC)"):
    """Render the NERACOOS logo at the top right place on a plot.
    
    max_value should be the """
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
        raise ValueError(
            f"Error creating dataframe from {max_time=}"
        ) from e
    
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