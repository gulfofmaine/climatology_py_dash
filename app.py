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

app.mount("/", server.build())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)  # nosec B104
