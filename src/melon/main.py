from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .builder import build_from_spec
from .pack import build_package
from .service import MelonService
from .storage import MelonPaths
from .versions import version_key


def _paths_from_args(args) -> MelonPaths:
    root = Path(args.root).resolve()
    if args.layout == "system":
        return MelonPaths.system(root)
    return MelonPaths.workspace(root)


def build_parser() -> argparse.ArgumentParser:
    default_layout = "system" if os.name != "nt" else "workspace"
    default_root = "/" if default_layout == "system" else "."

    parser = argparse.ArgumentParser(prog="melon", description="Melon package manager")
    parser.add_argument("--root", default=default_root, help="install root (system) or workspace root (workspace)")
    parser.add_argument("--layout", choices=["system", "workspace"], default=default_layout)
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Repo management
    repo = sub.add_parser("repo", help="repository configuration and publishing helpers")
    repo_sub = repo.add_subparsers(dest="repo_cmd", required=True)
    repo_set = repo_sub.add_parser("set", help="set a single repo as origin")
    repo_set.add_argument("url")
    repo_add = repo_sub.add_parser("add", help="add a repo")
    repo_add.add_argument("name")
    repo_add.add_argument("url")
    repo_add.add_argument("--priority", type=int, default=0)
    repo_rm = repo_sub.add_parser("rm", help="remove a repo")
    repo_rm.add_argument("name")
    repo_sub.add_parser("ls", help="list repos")
    repo_sub.add_parser("show", help="show raw repo config")
    repo_index = repo_sub.add_parser("index", help="generate index.json from packages/")
    repo_index.add_argument("--dir", default=".", help="repo directory (contains packages/)")
    repo_render = repo_sub.add_parser("render", help="write a dynamic index.html (reads index.json)")
    repo_render.add_argument("--dir", default=".", help="repo directory")

    sub.add_parser("hydrate", help="download and merge repo index")

    sniff = sub.add_parser("sniff", help="search repo index")
    sniff.add_argument("query", nargs="?", default="")

    # Install/remove
    plant = sub.add_parser("plant", help="install a package (with deps)")
    plant.add_argument("package")

    squeeze = sub.add_parser("squeeze", help="remove a package")
    squeeze.add_argument("package")
    squeeze.add_argument("--cascade", action="store_true", help="also remove conservative orphans")

    preserve = sub.add_parser("preserve", help="hold a package (prevent upgrades/removal)")
    preserve.add_argument("package")
    thaw = sub.add_parser("thaw", help="unhold a package")
    thaw.add_argument("package")

    sub.add_parser("ripen", help="upgrade installed packages")

    # Queries
    sub.add_parser("list", help="list installed packages")
    info = sub.add_parser("info", help="show package info (installed and/or repo)")
    info.add_argument("package")
    rdepends = sub.add_parser("rdepends", help="show reverse dependencies for an installed package")
    rdepends.add_argument("package")

    rind = sub.add_parser("rind", help="list log files")
    rind.add_argument("package", nargs="?", default="melon")
    nutrition = sub.add_parser("nutrition", help="show installed size (bytes)")
    nutrition.add_argument("package")
    sub.add_parser("wash", help="clear cache")
    sub.add_parser("status", help="dump state as JSON")

    # Moderator/build tools
    build = sub.add_parser("build", help="build from buildspec and place tarball in a repo")
    build.add_argument("spec")
    build.add_argument("--repo", default=".", help="repo dir (contains packages/)")
    build.add_argument("--work", default="", help="optional work dir (kept)")

    pack = sub.add_parser("pack", help="package already-built files from a .pkg recipe")
    pack.add_argument("recipe")
    pack.add_argument("--out", default="packages", help="output dir for tarballs")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    paths = _paths_from_args(args)
    service = MelonService(paths)

    def locked(fn):
        service.acquire_lock()
        try:
            return fn()
        finally:
            service.release_lock()

    if args.cmd == "repo":
        if args.repo_cmd == "set":
            print(json.dumps(service.set_repo(args.url), indent=2))
        elif args.repo_cmd == "add":
            print(json.dumps(service.add_repo(args.name, args.url, args.priority), indent=2))
        elif args.repo_cmd == "rm":
            print(json.dumps(service.remove_repo(args.name), indent=2))
        elif args.repo_cmd == "ls":
            print(json.dumps(service.repo_settings().get("repos", []), indent=2))
        elif args.repo_cmd == "show":
            print(json.dumps(service.repo_settings(), indent=2))
        elif args.repo_cmd == "index":
            repo_dir = Path(args.dir).resolve()
            print(service.build_repo_index(repo_dir))
        elif args.repo_cmd == "render":
            repo_dir = Path(args.dir).resolve()
            print(service.render_repo_html(repo_dir))
        return

    if args.cmd == "hydrate":
        pkgs = service.hydrate()
        total = sum(len(v) for v in pkgs.values())
        print(total)
        return

    if args.cmd == "sniff":
        for pkg in service.sniff(args.query):
            print(f"{pkg.name} {pkg.version} - {pkg.description}")
        return

    if args.cmd == "plant":
        def op():
            installed = service.plant(args.package, progress=lambda m: print(f":: {m}"))
            print(f":: installed {installed.meta.name} {installed.meta.version}")
        locked(op)
        return

    if args.cmd == "squeeze":
        def op():
            service.squeeze(args.package)
            if args.cascade:
                while True:
                    installed = service.db.load()
                    orphans = []
                    for name, pkg in installed.items():
                        dependents = [o for o, opkg in installed.items() if name in (opkg.meta.dependencies or [])]
                        if not dependents and (pkg.meta.dependencies or []):
                            orphans.append(name)
                    if not orphans:
                        break
                    for orphan in sorted(set(orphans)):
                        try:
                            service.squeeze(orphan)
                        except Exception:
                            continue
            print(f":: removed {args.package}")
        locked(op)
        return

    if args.cmd == "preserve":
        locked(lambda: service.preserve(args.package))
        return
    if args.cmd == "thaw":
        locked(lambda: service.thaw(args.package))
        return
    if args.cmd == "ripen":
        locked(lambda: print("\n".join(service.ripen())))
        return

    if args.cmd == "list":
        installed = service.db.load()
        for name in sorted(installed.keys()):
            meta = installed[name].meta
            print(f"{meta.name} {meta.version}")
        return

    if args.cmd == "info":
        installed = service.db.load()
        repo = service.repo.load()
        name = args.package
        if name in installed:
            print(json.dumps({"installed": installed[name].to_dict()}, indent=2))
            if name in repo:
                versions = sorted((m.version for m in repo[name]), key=version_key, reverse=True)
                print(json.dumps({"available_versions": versions}, indent=2))
        elif name in repo:
            metas = sorted(repo[name], key=lambda m: version_key(m.version), reverse=True)
            print(json.dumps({"available": [m.to_dict() for m in metas]}, indent=2))
        else:
            raise SystemExit(f"{name} not found (run hydrate)")
        return

    if args.cmd == "rdepends":
        installed = service.db.load()
        dependents = sorted(name for name, pkg in installed.items() if args.package in (pkg.meta.dependencies or []))
        print("\n".join(dependents))
        return

    if args.cmd == "rind":
        for name in service.rind(args.package):
            print(name)
        return

    if args.cmd == "nutrition":
        print(service.nutrition(args.package))
        return

    if args.cmd == "wash":
        locked(lambda: service.wash())
        return

    if args.cmd == "status":
        print(json.dumps(service.status(), indent=2))
        return

    if args.cmd == "build":
        repo_dir = Path(args.repo).resolve()
        packages_dir = repo_dir / "packages"
        packages_dir.mkdir(parents=True, exist_ok=True)
        work_dir = Path(args.work).resolve() if args.work else None
        result = build_from_spec(Path(args.spec), out_dir=packages_dir, work_dir=work_dir)
        service.build_repo_index(repo_dir)
        print(result.archive_path)
        return

    if args.cmd == "pack":
        out_dir = Path(args.out).resolve()
        archive = build_package(Path(args.recipe), out_dir)
        print(archive)
        return

