# syntax=docker/dockerfile:1.13
FROM ghcr.io/prefix-dev/pixi:0.40.3-noble@sha256:2ce403ab03b9882e6aeda6c1f6dce6ce83a82db213202f2708eee9059c973893

WORKDIR /app

COPY --link pixi.lock pixi.toml ./

RUN --mount=type=cache,id=pixi_climatology,target=/root/.cache/rattler/cache \
    pixi install --frozen

COPY --link climatology.py neracoos.png ./

EXPOSE 8080

RUN useradd -m app_user
USER app_user

CMD ["pixi", "run", "--frozen", "serve"]

HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8080/health || exit 1