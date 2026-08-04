#!/usr/bin/env bash
set -euo pipefail

# Named volumes mount root-owned (as does ~/.cache, created as their parent
# mountpoint); reclaim them for the vscode user.
sudo chown -R vscode:vscode "$PWD/.pixi" /home/vscode/.cache

# The bind-mounted workspace is owned by the host user, which git treats as
# untrusted ownership inside the container.
git config --global --add safe.directory "$PWD"

/usr/local/bin/mise trust
/usr/local/bin/mise install

# Put the mise-managed pixi/prek shims on PATH for the rest of this script.
eval "$(/usr/local/bin/mise activate bash --shims)"

pixi install --frozen -e default -e test
pixi run --frozen -e test playwright install --with-deps chromium
prek install
