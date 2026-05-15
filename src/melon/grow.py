from __future__ import annotations

import argparse
from pathlib import Path

from .service import MelonService
from .storage import MelonPaths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="melon-grow",
        description="Fetch, verify, and install a prebuilt package from a Melon repository",
    )
    parser.add_argument("package", help="package name to install")
    parser.add_argument("--root", default=".", help="workspace root for Melon state")
    parser.add_argument(
        "--hydrate",
        action="store_true",
        help="refresh repo index before installing",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service = MelonService(MelonPaths(Path(args.root).resolve()))

    # If user requested, or if we don't have an index yet, refresh it.
    if args.hydrate:
        service.hydrate()
    else:
        repo = service.repo.load()
        if not repo:
            service.hydrate()

    installed = service.plant(args.package, progress=lambda msg: print(f":: {msg}"))
    print(f":: installed {installed.meta.package_stem} ({len(installed.files)} files)")


if __name__ == "__main__":
    main()

