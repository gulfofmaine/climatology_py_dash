# syntax=docker/dockerfile:1.21
FROM ghcr.io/prefix-dev/pixi:0.59.0-noble@sha256:7a726d5e1f21c9f04fb5d9c850bfe5fd24395d4e4df79bda66ea35c5ed7f4753

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
