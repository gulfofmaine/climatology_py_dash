# syntax=docker/dockerfile:1.20
FROM ghcr.io/prefix-dev/pixi:0.63.2-noble@sha256:034c9032401f39bbc65d4cb533ac4f834df9d994085558cec75ed800e76a9424

WORKDIR /app

RUN pixi global install git

COPY --link pixi.lock pyproject.toml ./

RUN --mount=type=cache,id=pixi_climatology,target=/root/.cache/rattler/cache \
    pixi install --frozen -e default

COPY --link *.py style.css ./
COPY --link public/neracoos.png ./public/

RUN mkdir __marimo__ && \
    chmod -R 777 __marimo__

EXPOSE 8080

RUN useradd -m app_user
USER app_user

ENV MARIMO_SKIP_UPDATE_CHECK=1

CMD ["pixi", "run", "--frozen", "serve"]

HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8080/health || exit 1
