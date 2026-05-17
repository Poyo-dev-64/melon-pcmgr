from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import InstalledPackage, PackageMeta, installed_from_dict, package_from_dict


@dataclass(slots=True)
class MelonPaths:
    install_root: Path
    layout: str = "workspace"

    @staticmethod
    def workspace(root: Path) -> "MelonPaths":
        return MelonPaths(install_root=root.resolve(), layout="workspace")

    @staticmethod
    def system(install_root: Path) -> "MelonPaths":
        # install_root can be "/" (live system) or a chroot root like "/mnt/lfs".
        return MelonPaths(install_root=install_root.resolve(), layout="system")

    @property
    def state_dir(self) -> Path:
        if self.layout == "system":
            return self.install_root / "var" / "lib" / "melon"
        return self.install_root / ".melon"

    @property
    def db_dir(self) -> Path:
        return self.state_dir / "db"

    @property
    def installed_db(self) -> Path:
        return self.db_dir / "installed.json"

    @property
    def installed_packages_dir(self) -> Path:
        return self.db_dir / "installed"

    @property
    def repo_dir(self) -> Path:
        return self.state_dir / "repo"

    @property
    def repo_index(self) -> Path:
        return self.repo_dir / "index.json"

    @property
    def repo_config(self) -> Path:
        if self.layout == "system":
            return self.install_root / "etc" / "melon" / "repo.json"
        return self.repo_dir / "config.json"

    @property
    def cache_dir(self) -> Path:
        if self.layout == "system":
            return self.install_root / "var" / "cache" / "melon"
        return self.state_dir / "cache"

    @property
    def package_cache_dir(self) -> Path:
        return self.cache_dir / "packages"

    @property
    def transactions_dir(self) -> Path:
        return self.cache_dir / "transactions"

    @property
    def logs_dir(self) -> Path:
        if self.layout == "system":
            return self.install_root / "var" / "log" / "melon"
        return self.state_dir / "logs"

    @property
    def target_root(self) -> Path:
        # Where package payload files are installed.
        if self.layout == "system":
            return self.install_root
        return self.state_dir / "root"

    @property
    def holds_db(self) -> Path:
        return self.db_dir / "holds.json"

    @property
    def lock_file(self) -> Path:
        return self.state_dir / "melon.lock"

    def ensure(self) -> None:
        for path in (
            self.state_dir,
            self.db_dir,
            self.installed_packages_dir,
            self.repo_dir,
            self.cache_dir,
            self.package_cache_dir,
            self.transactions_dir,
            self.logs_dir,
            self.target_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.repo_index.exists():
            self.repo_index.write_text("{}", encoding="utf-8")
        if not self.repo_config.exists():
            self.repo_config.parent.mkdir(parents=True, exist_ok=True)
            self.repo_config.write_text("{}", encoding="utf-8")
        if not self.holds_db.exists():
            self.holds_db.write_text("[]", encoding="utf-8")


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


class InstalledDB:
    def __init__(self, paths: MelonPaths) -> None:
        self.paths = paths
        self.paths.ensure()

    def load(self) -> dict[str, InstalledPackage]:
        raw = self._load_raw()
        return {name: installed_from_dict(item) for name, item in raw.items()}

    def save(self, packages: dict[str, InstalledPackage]) -> None:
        existing = {path.stem for path in self.paths.installed_packages_dir.glob("*.json")}
        incoming = set(packages)

        for removed in sorted(existing - incoming):
            package_path = self.package_path(removed)
            if package_path.exists():
                package_path.unlink()

        for name, pkg in packages.items():
            write_json(self.package_path(name), pkg.to_dict())

        if self.paths.installed_db.exists():
            self.paths.installed_db.unlink()

    def holds(self) -> set[str]:
        return set(read_json(self.paths.holds_db, []))

    def save_holds(self, holds: set[str]) -> None:
        write_json(self.paths.holds_db, sorted(holds))

    def package_path(self, name: str) -> Path:
        return self.paths.installed_packages_dir / f"{name}.json"

    def _load_raw(self) -> dict[str, dict]:
        package_files = sorted(self.paths.installed_packages_dir.glob("*.json"))
        if package_files:
            return {
                path.stem: read_json(path, {})
                for path in package_files
            }

        legacy = read_json(self.paths.installed_db, {})
        if legacy:
            for name, package_data in legacy.items():
                write_json(self.package_path(name), package_data)
            self.paths.installed_db.unlink(missing_ok=True)
        return legacy


class RepoIndex:
    def __init__(self, paths: MelonPaths) -> None:
        self.paths = paths
        self.paths.ensure()

    def load(self) -> dict[str, PackageMeta]:
        raw = read_json(self.paths.repo_index, {})
        return {name: package_from_dict(item) for name, item in raw.items()}

    def save(self, packages: dict[str, PackageMeta]) -> None:
        write_json(self.paths.repo_index, {name: pkg.to_dict() for name, pkg in packages.items()})


class RepoConfig:
    def __init__(self, paths: MelonPaths) -> None:
        self.paths = paths
        self.paths.ensure()

    def load(self) -> dict:
        raw = read_json(self.paths.repo_config, {})
        # Back-compat: older config stored {"url": "..."}.
        if "repos" not in raw and "url" in raw and isinstance(raw.get("url"), str):
            raw = {"repos": [{"name": "origin", "url": raw["url"], "priority": 0}]}
            self.save(raw)
        if "repos" not in raw:
            raw = {"repos": []}
        return raw

    def save(self, data: dict) -> None:
        write_json(self.paths.repo_config, data)
