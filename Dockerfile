# syntax=docker/dockerfile:1.16
FROM ghcr.io/prefix-dev/pixi:0.48.0-noble@sha256:f7985e742f92e9870575d1bc416e2945842a5e79701ffaea373c171b9a8eeda9

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
