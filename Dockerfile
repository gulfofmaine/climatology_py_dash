# syntax=docker/dockerfile:1.14
FROM ghcr.io/prefix-dev/pixi:0.46.0-noble@sha256:c12bcbe8ba5dfd71867495d3471b95a6993b79cc7de7eafec016f8f59e4e4961

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
