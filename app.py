from pathlib import Path

import marimo
from fastapi import FastAPI
from fastapi.responses import FileResponse

import monitoring
import units

# Before create_asgi_app()/FastAPI(): Sentry instruments Starlette by patching
# middleware construction, so apps built before init are not traced. Run-mode
# marimo kernels are threads of this process (marimo._session.managers.kernel),
# so this one call also covers every notebook's cells. A no-op when
# SENTRY_DSN is unset.
monitoring.init_sentry()

server = (
    # Injected before </head> of every notebook page. The Sentry half is None
    # unless SENTRY_DSN is set, so nothing third-party loads outside a
    # configured deployment; the units half is always present and reaches for
    # nothing but localStorage.
    marimo.create_asgi_app(
        html_head="".join(
            part for part in (monitoring.html_head(), units.head_script()) if part
        ),
    )
    .with_app(path="/", root="./root.py")
    .with_app(path="/by_platform", root="./by_platform.py")
    .with_app(path="/by_standard_name", root="./by_standard_name.py")
    .with_app(path="/climatology", root="./climatology.py")
    .with_app(path="/calculate_datums", root="./calculate_datums.py")
)

app = FastAPI()

PUBLIC_DIR = Path(__file__).parent / "public"

# marimo's page template links its icons relatively ("./favicon.ico"), so each
# mounted notebook asks for its own copy (/by_platform/favicon.ico, ...) and
# gets marimo's. Answer those requests with NERACOOS's icons instead, ahead of
# the marimo mount below, rather than adding a second <link rel="icon"> that
# browsers may or may not prefer over marimo's.
_ICONS = {
    "favicon.ico": PUBLIC_DIR / "favicon.ico",
    "apple-touch-icon.png": PUBLIC_DIR / "neracoos_favicon.png",
}


def _add_icon_routes(name: str, source: Path) -> None:
    def icon() -> FileResponse:
        return FileResponse(source)

    app.get(f"/{name}", include_in_schema=False)(icon)
    app.get(f"/{{notebook}}/{name}", include_in_schema=False)(icon)


for _name, _source in _ICONS.items():
    _add_icon_routes(_name, _source)

# public/ is served by granian, ahead of this app -- see the `serve` task in
# pyproject.toml. marimo's own public-file convention (a relative
# <img src="public/..."> resolved against a public/ directory beside the
# notebook) does not reach those files once the notebooks are composed with
# create_asgi_app(), so without that static route the sidebar logo 404s on
# every page.
app.mount("/", server.build())
