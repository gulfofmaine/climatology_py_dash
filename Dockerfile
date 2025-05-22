# syntax=docker/dockerfile:1.16
FROM ghcr.io/prefix-dev/pixi:0.45.0-noble@sha256:be6128891dcd58009d18e45f41375d0e518f6d59727d6c729b74ae9884ce5da4

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
