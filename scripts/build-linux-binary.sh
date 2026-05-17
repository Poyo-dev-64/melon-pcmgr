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

ENTRYPOINT=""
if [ -f "src/melon/main.py" ]; then
  ENTRYPOINT="src/melon/main.py"
elif [ -f "src/melon/cli.py" ]; then
  ENTRYPOINT="src/melon/cli.py"
elif [ -f "src/melon/__main__.py" ]; then
  ENTRYPOINT="src/melon/__main__.py"
else
  echo "ERROR: could not find an entrypoint (expected src/melon/main.py or src/melon/cli.py)" 1>&2
  exit 1
fi

python -m PyInstaller -F -n melon --paths src "$ENTRYPOINT"
echo "Built dist/melon"
