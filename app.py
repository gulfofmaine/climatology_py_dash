import marimo
from fastapi import FastAPI

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
    .with_app(path="/whoi_radar", root="./whoi_radar.py")
)

app = FastAPI()

# public/ is served by granian, ahead of this app -- see the `serve` task in
# pyproject.toml. marimo's own public-file convention (a relative
# <img src="public/..."> resolved against a public/ directory beside the
# notebook) does not reach those files once the notebooks are composed with
# create_asgi_app(), so without that static route the sidebar logo 404s on
# every page.
app.mount("/", server.build())
