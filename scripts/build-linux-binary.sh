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

ENTRYPOINT=""
if [ -f "$SRC_DIR/melon/main.py" ]; then
  ENTRYPOINT="$SRC_DIR/melon/main.py"
elif [ -f "$SRC_DIR/melon/cli.py" ]; then
  ENTRYPOINT="$SRC_DIR/melon/cli.py"
elif [ -f "$SRC_DIR/melon/__main__.py" ]; then
  ENTRYPOINT="$SRC_DIR/melon/__main__.py"
else
  echo "ERROR: could not find an entrypoint (expected ../src/melon/main.py or ../src/melon/cli.py)" 1>&2
  exit 1
fi

python -m PyInstaller -F -n melon --paths "$SRC_DIR" "$ENTRYPOINT"
echo "Built $SCRIPT_DIR/../dist/melon"
