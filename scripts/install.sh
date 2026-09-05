#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="$(uname -m)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ "$ARCH" != "x86_64" && "$ARCH" != "amd64" ]]; then
  echo "Fenrys-CAI targets Debian amd64/x86_64; detected $ARCH." >&2
  exit 1
fi
if [[ "${EUID}" -ne 0 ]]; then
  echo "Run Fenrys as root (EUID 0); this deployment does not use a user-local install." >&2
  exit 1
fi
if ! command -v "$PYTHON_BIN" >/dev/null; then
  echo "Python 3.13 is required." >&2
  exit 1
fi
PY_MINOR="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$PY_MINOR" != "3.13" ]]; then
  echo "Python 3.13 is required; detected $PY_MINOR." >&2
  exit 1
fi
if ! command -v uv >/dev/null; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/." >&2
  exit 1
fi

cd "$ROOT"
uv sync --extra dev
mkdir -p "${XDG_CONFIG_HOME:-/root/.config}/fenrys-cai"
mkdir -p "${XDG_DATA_HOME:-/root/.local/share}/fenrys-cai/raw"
echo "Using the existing HexStrike installation; Fenrys will not clone or install it."
echo "Set HEXSTRIKE_HOME if it is not under /root/hexstrike-ai."
echo "Environment ready. Starting Fenrys-CAI setup wizard..."
exec uv run fenrys setup
