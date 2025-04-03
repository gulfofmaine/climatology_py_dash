# syntax=docker/dockerfile:1.14
FROM ghcr.io/prefix-dev/pixi:0.44.0-noble@sha256:5539f80aefab47f0c2e6a6e08df1631db13a2e2e46d0653bf0d8347f9a33e09b

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
