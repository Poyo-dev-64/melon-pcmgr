from __future__ import annotations

import os
import json
import subprocess
import shutil
import sys
import tarfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .models import InstalledPackage, PackageMeta, normalize_rel_path
from .repository import discover_packages, download_file, fetch_json, file_sha256, resolve_url
from .storage import InstalledDB, MelonPaths, RepoConfig, RepoIndex, write_json


@dataclass(slots=True)
class MelonService:
    paths: MelonPaths
    db: InstalledDB | None = None
    repo: RepoIndex | None = None
    repo_config: RepoConfig | None = None

    def __post_init__(self) -> None:
        self.paths.ensure()
        self.db = InstalledDB(self.paths)
        self.repo = RepoIndex(self.paths)
        self.repo_config = RepoConfig(self.paths)

    def log(self, message: str, package: str = "melon") -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%d")
        log_path = self.paths.logs_dir / f"{package}-{stamp}.log"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(UTC).isoformat()} {message}\n")

    def repo_settings(self) -> dict:
        return self.repo_config.load()

    def set_repo(self, url: str) -> dict:
        config = self.repo_config.load()
        config["url"] = url
        self.repo_config.save(config)
        self.log(f"configured repo {url}")
        return config

    def hydrate(self) -> dict[str, PackageMeta]:
        config = self.repo_config.load()
        remote_url = config.get("url", "").strip()
        if remote_url:
            index_url = resolve_url(remote_url, "index.json")
            payload = fetch_json(index_url)
            packages = {}
            for name, data in payload.items():
                packages[name] = PackageMeta(
                    name=data["name"],
                    version=data["version"],
                    description=data.get("description", ""),
                    source_url=data.get("source_url", ""),
                    package_url=data.get("package_url", f"packages/{data['name']}-{data['version']}.tar.gz"),
                    dependencies=list(data.get("dependencies", [])),
                    sha256=data.get("sha256", ""),
                    build_configure=list(data.get("build_configure", [])),
                    build_make=list(data.get("build_make", [])),
                    install_steps=list(data.get("install_steps", [])),
                    remove_steps=list(data.get("remove_steps", [])),
                    patches=list(data.get("patches", [])),
                )
            self.log(f"hydrated repository from {index_url} with {len(packages)} packages")
        else:
            packages = discover_packages(self.paths.repo_dir)
            self.log(f"hydrated repository with {len(packages)} local packages")
        self.repo.save(packages)
        return packages

    def build_repo_index(self, repo_dir: Path) -> int:
        packages = discover_packages(repo_dir)
        (repo_dir / "index.json").write_text(
            json.dumps({name: meta.to_dict() for name, meta in packages.items()}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self.log(f"generated repo index at {repo_dir / 'index.json'} with {len(packages)} package(s)")
        return len(packages)

    def render_repo_html(self, repo_dir: Path) -> int:
        index_path = repo_dir / "index.json"
        if not index_path.exists():
            raise FileNotFoundError(f"missing {index_path}; run `melon repo index --dir {repo_dir}` first")
        data = json.loads(index_path.read_text(encoding="utf-8"))
        packages: list[dict] = [data[name] for name in sorted(data.keys())]

        html_path = repo_dir / "index.html"
        template = html_path.read_text(encoding="utf-8") if html_path.exists() else _default_repo_html()

        rows: list[str] = []
        for pkg in packages:
            name = pkg.get("name", "")
            ver = pkg.get("version", "")
            desc = pkg.get("description", "")
            pkg_url = pkg.get("package_url", f"packages/{name}-{ver}.tar.gz")
            sha = pkg.get("sha256", "")
            rows.append(
                "<tr>"
                f"<td><code>{_html_escape(name)}</code></td>"
                f"<td><code>{_html_escape(ver)}</code></td>"
                f"<td>{_html_escape(desc)}</td>"
                f"<td><a href=\"./{_html_escape(pkg_url)}\">{_html_escape(Path(pkg_url).name)}</a></td>"
                f"<td><code>{_html_escape(sha)}</code></td>"
                "</tr>"
            )

        marker = "<!-- melon-repo:packages -->"
        if marker not in template:
            raise ValueError(f"{html_path} is missing marker {marker}")
        out = template.replace(marker, marker + "\n        " + "\n        ".join(rows))
        html_path.write_text(out, encoding="utf-8")
        self.log(f"rendered repo index html at {html_path} with {len(packages)} package(s)")
        return len(packages)


def _html_escape(value: str) -> str:
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _default_repo_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Melon Repo</title>
  </head>
  <body>
    <h1>Melon Repository</h1>
    <p>Repo index: <a href="./index.json"><code>index.json</code></a></p>
    <table>
      <thead>
        <tr>
          <th>Package</th>
          <th>Version</th>
          <th>Description</th>
          <th>Download</th>
          <th>SHA256</th>
        </tr>
      </thead>
      <tbody>
        <!-- melon-repo:packages -->
      </tbody>
    </table>
  </body>
</html>
"""

    def sniff(self, query: str = "") -> list[PackageMeta]:
        packages = self.repo.load()
        values = list(packages.values())
        if not query:
            return values
        query_lower = query.lower()
        return [
            pkg
            for pkg in values
            if query_lower in pkg.name.lower() or query_lower in pkg.description.lower()
        ]

    def plant(
        self,
        package_name: str,
        *,
        progress: Callable[[str], None] | None = None,
        _installing: set[str] | None = None,
    ) -> InstalledPackage:
        report = progress or (lambda _message: None)
        installed = self.db.load()
        repo_packages = self.repo.load()
        if package_name in installed:
            raise ValueError(f"{package_name} is already installed")
        if package_name not in repo_packages:
            raise ValueError(f"{package_name} is not present in the repo index; run hydrate first")

        package = repo_packages[package_name]
        installing = _installing or set()
        if package_name in installing:
            raise ValueError(f"detected dependency cycle while installing {package_name}")
        installing.add(package_name)
        try:
            for dependency in package.dependencies:
                if dependency in installed:
                    continue
                if dependency not in repo_packages:
                    raise ValueError(f"{package_name} depends on {dependency}, which is missing from the repo")
                report(f"resolving dependency {dependency} for {package_name}")
                self.plant(dependency, progress=progress, _installing=installing)
                installed = self.db.load()

            report(f"fetching {package.package_stem}")
            archive_path = self._ensure_package_archive(package, report)
            report(f"verifying {package.package_stem}")
            self._verify_archive(package, archive_path)
            report(f"installing {package.package_stem}")

            installed_files: list[str] = []
            staged_files: list[Path] = []
            temp_dir = self._new_transaction_dir(package.name)
            script_dir = temp_dir / "scripts"
            try:
                with tarfile.open(archive_path, "r:gz") as tar:
                    self._extract_scripts(tar, script_dir)
                    self._run_hook(script_dir, "pre-install", package, report)
                    staged_files = self._extract_payload_to_stage(tar, temp_dir / "payload")
                    installed_files = self._commit_staged_files(staged_files, temp_dir / "payload")
                installed[package_name] = InstalledPackage(meta=package, files=installed_files)
                self.db.save(installed)
                self._run_hook(script_dir, "post-install", package, report)
            except Exception:
                installed.pop(package_name, None)
                self.db.save(installed)
                self._rollback_installed_files(installed_files)
                raise
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

            self.log(f"installed {package.package_stem}", package_name)
            return installed[package_name]
        finally:
            installing.discard(package_name)

    def squeeze(self, package_name: str) -> None:
        installed = self.db.load()
        if package_name not in installed:
            raise ValueError(f"{package_name} is not installed")

        holds = self.db.holds()
        if package_name in holds:
            raise ValueError(f"{package_name} is held; thaw it before removal")

        package = installed[package_name]
        archive_path = self._ensure_package_archive(package.meta, lambda _message: None)
        self._verify_archive(package.meta, archive_path)

        temp_dir = self._new_transaction_dir(package_name)
        script_dir = temp_dir / "scripts"
        backup_dir = temp_dir / "backup"
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                self._extract_scripts(tar, script_dir)
            self._run_hook(script_dir, "pre-remove", package.meta)
            moved_files = self._stage_removed_files(package.files, backup_dir)
            installed.pop(package_name)
            self.db.save(installed)
            self._run_hook(script_dir, "post-remove", package.meta)
            for rel_path in moved_files:
                self._remove_empty_parents((self.paths.target_root / rel_path).parent)
        except Exception:
            installed[package_name] = package
            self.db.save(installed)
            self._restore_removed_files(backup_dir)
            raise
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.log(f"removed {package.meta.package_stem}", package_name)

    def preserve(self, package_name: str) -> None:
        installed = self.db.load()
        if package_name not in installed:
            raise ValueError(f"{package_name} is not installed")
        holds = self.db.holds()
        holds.add(package_name)
        installed[package_name].held = True
        self.db.save(installed)
        self.db.save_holds(holds)
        self.log(f"held package {package_name}", package_name)

    def thaw(self, package_name: str) -> None:
        installed = self.db.load()
        holds = self.db.holds()
        if package_name not in holds:
            raise ValueError(f"{package_name} is not held")
        holds.remove(package_name)
        if package_name in installed:
            installed[package_name].held = False
            self.db.save(installed)
        self.db.save_holds(holds)
        self.log(f"released hold on {package_name}", package_name)

    def ripen(self) -> list[str]:
        installed = self.db.load()
        repo_packages = self.repo.load()
        holds = self.db.holds()
        upgraded: list[str] = []
        for name, current in list(installed.items()):
            if name in holds or name not in repo_packages:
                continue
            target = repo_packages[name]
            if target.version == current.meta.version:
                continue
            self.squeeze(name)
            self.plant(name)
            upgraded.append(f"{name}: {current.meta.version} -> {target.version}")
        self.log(f"upgraded {len(upgraded)} package(s)")
        return upgraded

    def rind(self, package_name: str = "melon") -> list[str]:
        return sorted(path.name for path in self.paths.logs_dir.glob(f"{package_name}-*.log"))

    def nutrition(self, package_name: str) -> int:
        installed = self.db.load()
        if package_name not in installed:
            raise ValueError(f"{package_name} is not installed")
        total = 0
        for rel_path in installed[package_name].files:
            target = self.paths.install_root / rel_path
            if target.exists():
                total += target.stat().st_size
        return total

    def wash(self) -> list[str]:
        removed: list[str] = []
        for child in self.paths.cache_dir.iterdir():
            if child.is_file():
                child.unlink()
                removed.append(child.name)
            elif child.is_dir():
                shutil.rmtree(child)
                removed.append(child.name)
        self.log(f"washed cache ({len(removed)} entries)")
        return removed

    def status(self) -> dict:
        installed = self.db.load()
        holds = self.db.holds()
        for name, pkg in installed.items():
            pkg.held = name in holds
        repo = self.repo.load()
        data = {
            "installed": {name: pkg.to_dict() for name, pkg in installed.items()},
            "repo": {name: pkg.to_dict() for name, pkg in repo.items()},
            "holds": sorted(holds),
            "repo_config": self.repo_config.load(),
        }
        write_json(self.paths.state_dir / "status.json", data)
        return data

    def _remove_empty_parents(self, start: Path) -> None:
        current = start
        while current != self.paths.target_root and current.exists():
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def _ensure_package_archive(
        self,
        package: PackageMeta,
        progress: Callable[[str], None],
    ) -> Path:
        local_archive = self.paths.repo_dir / "packages" / package.package_filename
        if local_archive.exists() and self._archive_matches(package, local_archive):
            return local_archive

        config = self.repo_config.load()
        remote_url = config.get("url", "").strip()
        if not remote_url:
            if local_archive.exists():
                raise ValueError(
                    f"sha256 mismatch for cached archive {local_archive.name}; no remote repo configured for repair"
                )
            raise FileNotFoundError(f"missing archive: {local_archive}")

        package_target = package.package_url or f"packages/{package.package_filename}"
        package_url = resolve_url(remote_url, package_target)
        cached_archive = self.paths.package_cache_dir / package.package_filename
        if cached_archive.exists() and self._archive_matches(package, cached_archive):
            return cached_archive
        progress(f"downloading {package_url}")
        download_file(package_url, cached_archive)
        return cached_archive

    def _verify_archive(self, package: PackageMeta, archive_path: Path) -> None:
        if not package.sha256:
            raise ValueError(f"{package.name} is missing a sha256 checksum in the repo index")
        actual_sha = file_sha256(archive_path)
        if actual_sha != package.sha256:
            raise ValueError(
                f"sha256 mismatch for {package.package_stem}: expected {package.sha256}, got {actual_sha}"
            )

    def _archive_matches(self, package: PackageMeta, archive_path: Path) -> bool:
        if not archive_path.exists():
            return False
        if not package.sha256:
            return True
        return file_sha256(archive_path) == package.sha256

    def _extract_payload_to_stage(self, tar: tarfile.TarFile, staging_dir: Path) -> list[Path]:
        staged_paths: list[Path] = []
        for member in tar.getmembers():
            if not member.name.startswith("payload/"):
                continue
            relative = Path(member.name).relative_to("payload")
            self._safe_extract_payload_member(tar, member, staging_dir, relative)
            staged_paths.append(relative)
        return staged_paths

    def _commit_staged_files(self, staged_paths: list[Path], staging_dir: Path) -> list[str]:
        installed_files: list[str] = []
        for relative in staged_paths:
            staged_path = staging_dir / relative
            destination = self.paths.target_root / relative

            if staged_path.is_symlink():
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists() or destination.is_symlink():
                    destination.unlink()
                destination.symlink_to(os.readlink(staged_path))
                installed_files.append(normalize_rel_path(relative))
                continue

            if staged_path.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                installed_files.append(normalize_rel_path(relative))
                continue

            if staged_path.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged_path, destination)
                installed_files.append(normalize_rel_path(relative))
        return installed_files

    def _rollback_installed_files(self, installed_files: list[str]) -> None:
        for rel_path in reversed(installed_files):
            target = self.paths.target_root / rel_path
            if target.is_symlink() or target.is_file():
                target.unlink()
                self._remove_empty_parents(target.parent)
            elif target.is_dir():
                try:
                    target.rmdir()
                except OSError:
                    pass

    def _extract_scripts(self, tar: tarfile.TarFile, script_dir: Path) -> None:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.startswith("scripts/"):
                continue
            relative = Path(member.name).relative_to("scripts")
            destination = script_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            with extracted:
                destination.write_bytes(extracted.read())

    def _run_hook(
        self,
        script_dir: Path,
        hook_name: str,
        package: PackageMeta,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        script_path = self._find_hook_script(script_dir, hook_name)
        if script_path is None:
            return
        if progress is not None:
            progress(f"running {hook_name} hook for {package.package_stem}")
        env = os.environ.copy()
        env["MELON_PACKAGE_NAME"] = package.name
        env["MELON_PACKAGE_VERSION"] = package.version
        env["MELON_INSTALL_ROOT"] = str(self.paths.target_root)
        env["MELON_STATE_DIR"] = str(self.paths.state_dir)
        command = self._script_command(script_path)
        completed = subprocess.run(
            command,
            cwd=script_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.stdout.strip():
            self.log(f"{hook_name} stdout: {completed.stdout.strip()}", package.name)
        if completed.stderr.strip():
            self.log(f"{hook_name} stderr: {completed.stderr.strip()}", package.name)
        if completed.returncode != 0:
            raise RuntimeError(
                f"{hook_name} hook failed for {package.package_stem} with exit code {completed.returncode}"
            )

    def _find_hook_script(self, script_dir: Path, hook_name: str) -> Path | None:
        if not script_dir.exists():
            return None
        matches = sorted(path for path in script_dir.iterdir() if path.is_file() and path.stem == hook_name)
        if matches:
            return matches[0]
        for suffix in (".sh", ".ps1", ".py", ".cmd", ".bat"):
            candidate = script_dir / f"{hook_name}{suffix}"
            if candidate.exists():
                return candidate
        return None

    def _script_command(self, script_path: Path) -> list[str]:
        suffix = script_path.suffix.lower()
        if suffix == ".py":
            return [sys.executable, str(script_path)]
        if suffix == ".ps1":
            return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
        if suffix in {".cmd", ".bat"}:
            return [str(script_path)]
        if suffix == ".sh":
            shell = shutil.which("bash") or shutil.which("sh")
            if shell is None:
                raise RuntimeError(f"cannot run shell hook {script_path.name}: no sh/bash available")
            return [shell, str(script_path)]
        if os.name == "nt":
            return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
        return [str(script_path)]

    def _stage_removed_files(self, files: list[str], backup_dir: Path) -> list[Path]:
        moved_files: list[Path] = []
        for rel_path_str in files:
            relative = Path(rel_path_str)
            source = self.paths.target_root / relative
            if not source.exists():
                continue
            backup = backup_dir / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(backup))
            moved_files.append(relative)
        return moved_files

    def _restore_removed_files(self, backup_dir: Path) -> None:
        if not backup_dir.exists():
            return
        for source in sorted(backup_dir.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(backup_dir)
            destination = self.paths.target_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))

    def _new_transaction_dir(self, package_name: str) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        path = self.paths.transactions_dir / f"{package_name}-{stamp}"
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _safe_extract_payload_member(
        self,
        tar: tarfile.TarFile,
        member: tarfile.TarInfo,
        staging_root: Path,
        relative: Path,
    ) -> None:
        staging_root = staging_root.resolve()
        out_path = (staging_root / relative).resolve()
        if not str(out_path).startswith(str(staging_root)):
            raise RuntimeError(f"unsafe path in package payload: {member.name}")

        if member.isdir():
            out_path.mkdir(parents=True, exist_ok=True)
            return

        if member.issym():
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if out_path.exists() or out_path.is_symlink():
                out_path.unlink()
            out_path.symlink_to(member.linkname)
            return

        if member.isfile():
            out_path.parent.mkdir(parents=True, exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted is None:
                return
            with extracted, out_path.open("wb") as handle:
                shutil.copyfileobj(extracted, handle)
            try:
                os.chmod(out_path, member.mode)
            except PermissionError:
                pass
