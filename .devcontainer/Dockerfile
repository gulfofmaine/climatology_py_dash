FROM mcr.microsoft.com/devcontainers/base:noble

# mise is not baked into the base image; it provisions pixi and prek at
# postCreate time from the repo-root mise.toml.
RUN curl -fsSL https://mise.run | MISE_INSTALL_PATH=/usr/local/bin/mise sh

# Activate mise for the vscode user's interactive shells so pixi/prek are
# on PATH once postCreateCommand has installed them.
RUN echo 'eval "$(/usr/local/bin/mise activate bash)"' >> /home/vscode/.bashrc \
  && echo 'eval "$(/usr/local/bin/mise activate zsh)"' >> /home/vscode/.zshrc

ENV MARIMO_SKIP_UPDATE_CHECK=1
