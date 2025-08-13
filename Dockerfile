# syntax=docker/dockerfile:1.17
FROM ghcr.io/prefix-dev/pixi:0.51.0-noble@sha256:fba64f23c431f2efd911fe7877077af5ad692cbf6945e5ce3b67602f6dd8d070

WORKDIR /app

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
