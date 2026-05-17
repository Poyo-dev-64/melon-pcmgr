#!/usr/bin/env sh
set -eu

# Builds a single-file Linux binary using PyInstaller.
# Usage:
#   python3 -m venv .venv
#   . .venv/bin/activate
#   pip install -U pip
#   pip install pyinstaller
#   ./scripts/build-linux-binary.sh

rm -rf dist build
pyinstaller -F -n melon -m melon.main --paths src
echo "Built dist/melon"

