from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import build_from_spec
from .repository import discover_packages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="melon-grow",
        description="Moderator tool: build a package from a buildspec and regenerate the repo index",
    )
    parser.add_argument("spec", help="path to a buildspec (.build.ini)")
    parser.add_argument("--repo", default=".", help="repo directory containing packages/ and index.json")
    parser.add_argument("--work", default="", help="optional build work directory (kept; no auto-clean)")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    repo_dir = Path(args.repo).resolve()
    packages_dir = repo_dir / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work).resolve() if args.work else None

    result = build_from_spec(Path(args.spec), out_dir=packages_dir, work_dir=work_dir)
    print(f":: built {result.archive_path.name}")

    packages = discover_packages(repo_dir)
    (repo_dir / "index.json").write_text(
        json.dumps({name: meta.to_dict() for name, meta in packages.items()}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f":: wrote {len(packages)} package(s) to {repo_dir / 'index.json'}")


if __name__ == "__main__":
    main()
