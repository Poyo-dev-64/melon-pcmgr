from __future__ import annotations

import argparse
from pathlib import Path

from .builder import build_from_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="melon-build", description="Build and package from a Melon buildspec")
    parser.add_argument("spec", help="path to a Melon buildspec (.ini) file")
    parser.add_argument("--out", default=".melon/repo/packages", help="output directory for package archives")
    parser.add_argument("--work", default="", help="optional work directory (kept; no auto-clean)")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    work_dir = Path(args.work).resolve() if args.work else None
    result = build_from_spec(Path(args.spec), out_dir=Path(args.out), work_dir=work_dir)
    print(result.archive_path)


if __name__ == "__main__":
    main()
