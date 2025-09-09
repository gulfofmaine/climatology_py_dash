# syntax=docker/dockerfile:1.18
FROM ghcr.io/prefix-dev/pixi:0.54.2-noble@sha256:5642b666f269ec0c34a466d2e8e091b76b9346b441c9b05349d72a79befc03c2

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
