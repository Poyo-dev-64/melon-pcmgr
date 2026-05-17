#!/usr/bin/env sh
set -eu

# Builds a single-file Linux binary using PyInstaller.
# Usage:
#   python3 -m venv .venv
#   . .venv/bin/activate
#   pip install -U pip
#   pip install pyinstaller
#   ./scripts/build-linux-binary.sh

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SRC_DIR="$SCRIPT_DIR/../src"

rm -rf "$SCRIPT_DIR/../dist" "$SCRIPT_DIR/../build"

# Static, predictable layout (repo root):
#   scripts/build-linux-binary.sh
#   src/melon/main.py
ENTRYPOINT="$SCRIPT_DIR/src/melon/main.py"
if [ ! -f "$ENTRYPOINT" ]; then
  echo "ERROR: missing entrypoint: $ENTRYPOINT" 1>&2
  echo "Run from the repo checkout that contains src/melon/main.py" 1>&2
  exit 1
fi

python -m PyInstaller -F -n melon --paths "$SCRIPT_DIR/../src" "$ENTRYPOINT"
echo "Built $SCRIPT_DIR/../dist/melon"
