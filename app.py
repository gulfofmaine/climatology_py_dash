import marimo
from fastapi import FastAPI

server = (
    marimo.create_asgi_app()
    .with_app(path="/", root="./root.py")
    .with_app(path="/by_platform", root="./by_platform.py")
    .with_app(path="/by_standard_name", root="./by_standard_name.py")
    .with_app(path="/climatology", root="./climatology.py")
    .with_app(path="/calculate_datums", root="./calculate_datums.py")
)

app = FastAPI()

# public/ is served by granian, ahead of this app -- see the `serve` task in
# pyproject.toml. marimo's own public-file convention (a relative
# <img src="public/..."> resolved against a public/ directory beside the
# notebook) does not reach those files once the notebooks are composed with
# create_asgi_app(), so without that static route the sidebar logo 404s on
# every page.
app.mount("/", server.build())
