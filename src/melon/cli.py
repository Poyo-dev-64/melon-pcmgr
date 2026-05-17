from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .service import MelonService
from .storage import MelonPaths
from .versions import version_key


def build_parser() -> argparse.ArgumentParser:
    default_layout = "system" if os.name != "nt" else "workspace"
    default_root = "/" if default_layout == "system" else "."
    parser = argparse.ArgumentParser(prog="melon", description="Melon package manager")
    parser.add_argument(
        "--root",
        default=default_root,
        help="install root (e.g. / or /mnt/lfs); workspace root if --layout=workspace",
    )
    parser.add_argument(
        "--layout",
        choices=["workspace", "system"],
        default=default_layout,
        help="system is the default on Linux; workspace keeps all state local",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("hydrate", aliases=["-Hy"], help="sync the repo index from local packages")

    repo = subparsers.add_parser("repo", help="configure or inspect repository settings")
    repo_subparsers = repo.add_subparsers(dest="repo_command", required=True)
    repo_set = repo_subparsers.add_parser("set", help="set the remote repository base URL")
    repo_set.add_argument("url")
    repo_add = repo_subparsers.add_parser("add", help="add a repository (multi-repo support)")
    repo_add.add_argument("name")
    repo_add.add_argument("url")
    repo_add.add_argument("--priority", type=int, default=0)
    repo_rm = repo_subparsers.add_parser("rm", help="remove a repository by name")
    repo_rm.add_argument("name")
    repo_subparsers.add_parser("ls", help="list configured repositories")
    repo_subparsers.add_parser("show", help="show current repository settings")
    repo_index = repo_subparsers.add_parser("index", help="generate index.json for a built package repo folder")
    repo_index.add_argument(
        "--dir",
        default=".melon/repo",
        help="repo directory containing packages/ (writes index.json into this directory)",
    )
    repo_render = repo_subparsers.add_parser("render", help="(re)write a dynamic index.html for a repo folder (loads index.json)")
    repo_render.add_argument(
        "--dir",
        default=".",
        help="repo directory containing index.json and packages/ (writes index.html into this directory)",
    )

    sniff = subparsers.add_parser("sniff", aliases=["-Sn"], help="search packages in the repo")
    sniff.add_argument("query", nargs="?", default="")

    subparsers.add_parser("list", help="list installed packages")

    info = subparsers.add_parser("info", help="show info for an installed package or repo package")
    info.add_argument("package")

    rdepends = subparsers.add_parser("rdepends", help="show reverse dependencies for an installed package")
    rdepends.add_argument("package")

    plant = subparsers.add_parser("plant", aliases=["-P"], help="install a package")
    plant.add_argument("package")

    squeeze = subparsers.add_parser("squeeze", aliases=["-S"], help="remove a package")
    squeeze.add_argument("package")
    squeeze.add_argument("--cascade", action="store_true", help="also remove unneeded deps (very conservative)")

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
            repos = settings.get("repos", [])
            if repos:
                print(f":: synced {len(packages)} package(s) from {len(repos)} repo(s)")
            else:
                print(f":: scanned {len(packages)} local package(s)")
            for pkg in packages.values():
                print(f"   {pkg.name} {pkg.version}")
        elif args.command == "repo":
            if args.repo_command == "set":
                config = service.set_repo(args.url)
                print(":: repository set")
                print(json.dumps(config, indent=2))
            elif args.repo_command == "add":
                config = service.add_repo(args.name, args.url, args.priority)
                print(":: repository added")
                print(json.dumps(config, indent=2))
            elif args.repo_command == "rm":
                config = service.remove_repo(args.name)
                print(":: repository removed")
                print(json.dumps(config, indent=2))
            elif args.repo_command == "ls":
                print(json.dumps(service.repo_settings().get("repos", []), indent=2))
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
        elif args.command == "list":
            installed = service.db.load()
            for name in sorted(installed.keys()):
                meta = installed[name].meta
                print(f"{meta.name} {meta.version}")
        elif args.command == "info":
            installed = service.db.load()
            repo = service.repo.load()
            name = args.package
            if name in installed:
                meta = installed[name].meta
                print(json.dumps({"installed": installed[name].to_dict()}, indent=2))
                if name in repo:
                    versions = sorted((m.version for m in repo[name]), key=version_key, reverse=True)
                    print(json.dumps({"available_versions": versions}, indent=2))
            elif name in repo:
                metas = sorted(repo[name], key=lambda m: version_key(m.version), reverse=True)
                print(json.dumps({"available": [m.to_dict() for m in metas]}, indent=2))
            else:
                raise SystemExit(f"{name} not found (run hydrate)")
        elif args.command == "rdepends":
            installed = service.db.load()
            dependents = sorted(
                name for name, pkg in installed.items() if args.package in (pkg.meta.dependencies or [])
            )
            if dependents:
                print("\n".join(dependents))
            else:
                print("")
        elif args.command in {"plant", "-P"}:
            service.acquire_lock()
            try:
                installed = service.plant(args.package, progress=lambda message: print(f":: {message}"))
            finally:
                service.release_lock()
            print(f":: installed {installed.meta.package_stem} ({len(installed.files)} files)")
        elif args.command in {"squeeze", "-S"}:
            service.acquire_lock()
            try:
                service.squeeze(args.package)
                if args.cascade:
                    # Remove deps that are now orphaned (no reverse deps).
                    while True:
                        installed = service.db.load()
                        orphans = []
                        for name, pkg in installed.items():
                            if name == args.package:
                                continue
                            dependents = [
                                other for other, opkg in installed.items()
                                if name in (opkg.meta.dependencies or [])
                            ]
                            if not dependents and (pkg.meta.dependencies or []):
                                # Only consider packages that were installed as deps (has deps metadata);
                                # this keeps the behavior conservative.
                                orphans.append(name)
                        if not orphans:
                            break
                        for orphan in sorted(set(orphans)):
                            try:
                                service.squeeze(orphan)
                            except Exception:
                                continue
            finally:
                service.release_lock()
            print(f":: removed {args.package}")
        elif args.command == "preserve":
            service.acquire_lock()
            try:
                service.preserve(args.package)
            finally:
                service.release_lock()
            print(f":: held {args.package}")
        elif args.command == "thaw":
            service.acquire_lock()
            try:
                service.thaw(args.package)
            finally:
                service.release_lock()
            print(f":: released {args.package}")
        elif args.command in {"ripen", "-R"}:
            service.acquire_lock()
            try:
                upgrades = service.ripen()
            finally:
                service.release_lock()
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
            service.acquire_lock()
            try:
                removed = service.wash()
            finally:
                service.release_lock()
            print(f":: removed {len(removed)} cache entries")
        elif args.command == "status":
            print(json.dumps(service.status(), indent=2))
    except Exception as exc:  # pragma: no cover - simple CLI surface
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
