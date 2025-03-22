# syntax=docker/dockerfile:1.14
FROM ghcr.io/prefix-dev/pixi:0.43.0-noble@sha256:0070b959110d91b9c8d52c4e30af0c9b6cd9a8e62e80ac4a58892de28c9e8505

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