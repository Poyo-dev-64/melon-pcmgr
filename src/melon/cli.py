from __future__ import annotations

import argparse
import json
from pathlib import Path

from .service import MelonService
from .storage import MelonPaths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="melon", description="Sandboxed Melon package manager")
    parser.add_argument("--root", default=".", help="install root (e.g. / or /mnt/lfs); workspace root if --layout=workspace")
    parser.add_argument("--layout", choices=["workspace", "system"], default="workspace", help="where Melon stores its state and what install root means")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("hydrate", aliases=["-Hy"], help="sync the repo index from local packages")

    repo = subparsers.add_parser("repo", help="configure or inspect repository settings")
    repo_subparsers = repo.add_subparsers(dest="repo_command", required=True)
    repo_set = repo_subparsers.add_parser("set", help="set the remote repository base URL")
    repo_set.add_argument("url")
    repo_subparsers.add_parser("show", help="show current repository settings")
    repo_index = repo_subparsers.add_parser("index", help="generate index.json for a built package repo folder")
    repo_index.add_argument(
        "--dir",
        default=".melon/repo",
        help="repo directory containing packages/ (writes index.json into this directory)",
    )
    repo_render = repo_subparsers.add_parser("render", help="generate a simple index.html listing for a repo folder")
    repo_render.add_argument(
        "--dir",
        default="docs",
        help="repo directory containing index.json and packages/ (writes index.html into this directory)",
    )

    sniff = subparsers.add_parser("sniff", aliases=["-Sn"], help="search packages in the repo")
    sniff.add_argument("query", nargs="?", default="")

    plant = subparsers.add_parser("plant", aliases=["-P"], help="install a package")
    plant.add_argument("package")

    squeeze = subparsers.add_parser("squeeze", aliases=["-S"], help="remove a package")
    squeeze.add_argument("package")

    preserve = subparsers.add_parser("preserve", help="hold an installed package")
    preserve.add_argument("package")

    thaw = subparsers.add_parser("thaw", help="release a held package")
    thaw.add_argument("package")

    subparsers.add_parser("ripen", aliases=["-R"], help="upgrade installed packages")

    rind = subparsers.add_parser("rind", aliases=["-L"], help="show log files")
    rind.add_argument("package", nargs="?", default="melon")

    nutrition = subparsers.add_parser("nutrition", aliases=["-N"], help="show installed package size")
    nutrition.add_argument("package")

    subparsers.add_parser("wash", help="clean the cache directory")
    subparsers.add_parser("status", help="dump current state as JSON")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()
    paths = MelonPaths.system(root) if args.layout == "system" else MelonPaths.workspace(root)
    service = MelonService(paths)

    try:
        if args.command in {"hydrate", "-Hy"}:
            packages = service.hydrate()
            settings = service.repo_settings()
            if settings.get("url"):
                print(f":: synced {len(packages)} package(s) from {settings['url']}")
            else:
                print(f":: scanned {len(packages)} local package(s)")
            for pkg in packages.values():
                print(f"   {pkg.name} {pkg.version}")
        elif args.command == "repo":
            if args.repo_command == "set":
                config = service.set_repo(args.url)
                print(f":: repository set to {config['url']}")
            elif args.repo_command == "show":
                print(json.dumps(service.repo_settings(), indent=2))
            elif args.repo_command == "index":
                repo_dir = Path(args.dir).resolve()
                count = service.build_repo_index(repo_dir)
                print(f":: wrote {count} package(s) to {repo_dir / 'index.json'}")
            elif args.repo_command == "render":
                repo_dir = Path(args.dir).resolve()
                count = service.render_repo_html(repo_dir)
                print(f":: wrote index.html for {count} package(s) to {repo_dir / 'index.html'}")
        elif args.command in {"sniff", "-Sn"}:
            for pkg in service.sniff(args.query):
                print(f"{pkg.name} {pkg.version} - {pkg.description}")
        elif args.command in {"plant", "-P"}:
            installed = service.plant(args.package, progress=lambda message: print(f":: {message}"))
            print(f":: installed {installed.meta.package_stem} ({len(installed.files)} files)")
        elif args.command in {"squeeze", "-S"}:
            service.squeeze(args.package)
            print(f":: removed {args.package}")
        elif args.command == "preserve":
            service.preserve(args.package)
            print(f":: held {args.package}")
        elif args.command == "thaw":
            service.thaw(args.package)
            print(f":: released {args.package}")
        elif args.command in {"ripen", "-R"}:
            upgrades = service.ripen()
            if upgrades:
                print("\n".join(upgrades))
            else:
                print(":: no upgrades available")
        elif args.command in {"rind", "-L"}:
            for name in service.rind(args.package):
                print(name)
        elif args.command in {"nutrition", "-N"}:
            print(service.nutrition(args.package))
        elif args.command == "wash":
            removed = service.wash()
            print(f":: removed {len(removed)} cache entries")
        elif args.command == "status":
            print(json.dumps(service.status(), indent=2))
    except Exception as exc:  # pragma: no cover - simple CLI surface
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
