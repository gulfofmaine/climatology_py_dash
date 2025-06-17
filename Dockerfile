# syntax=docker/dockerfile:1.17
FROM ghcr.io/prefix-dev/pixi:0.47.0-noble@sha256:f9f4331c11fe8ecec4b0bda19c3863af1f372dc988b024ddec1a512f4f6b0068

WORKDIR /app

COPY --link pixi.lock pixi.toml ./

RUN --mount=type=cache,id=pixi_climatology,target=/root/.cache/rattler/cache \
    pixi install --frozen

COPY --link climatology.py ./
COPY --link public/neracoos.png ./public/

EXPOSE 8080

RUN useradd -m app_user
USER app_user

CMD ["pixi", "run", "--frozen", "serve"]

HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8080/health || exit 1
