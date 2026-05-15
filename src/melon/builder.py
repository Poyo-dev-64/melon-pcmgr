from __future__ import annotations

import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .buildspec import BuildSpec, load_buildspec
from .models import PackageMeta
from .repository import download_file, file_sha256


@dataclass(slots=True)
class BuildResult:
    archive_path: Path
    meta: PackageMeta


def build_from_spec(
    spec_path: Path,
    *,
    out_dir: Path,
    work_dir: Path | None = None,
) -> BuildResult:
    spec_path = spec_path.resolve()
    spec = load_buildspec(spec_path)

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Work directory holds sources, build artifacts, and a staged install root.
    if work_dir is None:
        temp_root = Path(tempfile.mkdtemp(prefix=f"melon-build-{spec.name}-"))
        cleanup = True
    else:
        temp_root = work_dir.resolve()
        temp_root.mkdir(parents=True, exist_ok=True)
        cleanup = False

    try:
        sources_dir = temp_root / "sources"
        build_dir = temp_root / "build"
        stage_dir = temp_root / "stage"
        sources_dir.mkdir(parents=True, exist_ok=True)
        build_dir.mkdir(parents=True, exist_ok=True)
        stage_dir.mkdir(parents=True, exist_ok=True)

        source_root = _prepare_source(spec, sources_dir, build_dir)
        env = _base_env(spec, stage_dir)
        _run_commands(spec.configure_commands, cwd=source_root, env=env)
        _run_commands(spec.build_commands, cwd=source_root, env=env)
        _run_commands(spec.check_commands, cwd=source_root, env=env)
        _run_commands(spec.install_commands, cwd=source_root, env=env)

        meta = PackageMeta(
            name=spec.name,
            version=spec.version,
            description=spec.description,
            source_url=spec.source,
            package_url=f"packages/{spec.name}-{spec.version}.tar.gz",
            dependencies=list(spec.depends),
            sha256="",
        )
        archive_path = _package_stage(meta, stage_dir, out_dir)
        meta.sha256 = file_sha256(archive_path)
        # Re-write meta.json inside tarball with final sha? We keep sha256 in index.json, not inside package.
        return BuildResult(archive_path=archive_path, meta=meta)
    finally:
        if cleanup:
            shutil.rmtree(temp_root, ignore_errors=True)


def _prepare_source(spec: BuildSpec, sources_dir: Path, build_dir: Path) -> Path:
    if not spec.source:
        # Allow "no source" packages that only stage files via install commands.
        return build_dir

    # Download source into sources_dir. We support http(s) and file:// via urllib, delegated to download_file.
    filename = spec.source.split("/")[-1] or "source.tar"
    source_path = sources_dir / filename
    download_file(spec.source, source_path)

    if spec.source_sha256:
        actual = file_sha256(source_path)
        if actual != spec.source_sha256:
            raise RuntimeError(f"source sha256 mismatch: expected {spec.source_sha256}, got {actual}")

    # Extract tar archives; if not a tar, just return the downloaded file location.
    extracted_root = build_dir
    if tarfile.is_tarfile(source_path):
        with tarfile.open(source_path) as tar:
            _safe_extract_tar(tar, build_dir)
        extracted_root = _guess_extracted_root(build_dir)

    if spec.subdir:
        extracted_root = extracted_root / spec.subdir

    # Apply patches (relative to spec file directory).
    for patch_name in spec.patches:
        patch_path = (spec.base_dir / patch_name).resolve()
        _apply_patch(extracted_root, patch_path)

    return extracted_root


def _safe_extract_tar(tar: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in tar.getmembers():
        member_path = (destination / member.name).resolve()
        if not str(member_path).startswith(str(destination)):
            raise RuntimeError(f"unsafe tar entry: {member.name}")
    tar.extractall(destination)


def _apply_patch(cwd: Path, patch_path: Path) -> None:
    if not patch_path.exists():
        raise FileNotFoundError(patch_path)
    patch = shutil.which("patch")
    if patch is None:
        raise RuntimeError("cannot apply patches: `patch` executable not found on PATH")
    subprocess.run([patch, "-p1", "-i", str(patch_path)], cwd=cwd, check=True)


def _guess_extracted_root(build_dir: Path) -> Path:
    children = [p for p in build_dir.iterdir() if p.is_dir()]
    if len(children) == 1:
        return children[0]
    return build_dir


def _base_env(spec: BuildSpec, stage_dir: Path) -> dict[str, str]:
    env = {
        "DESTDIR": str(stage_dir),
        "PREFIX": spec.prefix,
        "MELON_SPEC_DIR": str(spec.base_dir),
    }
    return env


def _run_commands(commands: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    if not commands:
        return
    merged_env = dict(**{**_host_env(), **env})
    for cmd in commands:
        subprocess.run(cmd, cwd=cwd, env=merged_env, shell=True, check=True)


def _host_env() -> dict[str, str]:
    # subprocess inherits by default, but we explicitly copy to allow adding vars cleanly.
    import os

    return os.environ.copy()


def _package_stage(meta: PackageMeta, stage_dir: Path, out_dir: Path) -> Path:
    archive_path = out_dir / meta.package_filename
    # Package layout: meta.json + payload/** + scripts/** (scripts are not part of buildspec yet).
    import io
    import json

    with tarfile.open(archive_path, "w:gz") as tar:
        meta_bytes = json.dumps(meta.to_dict(), indent=2).encode("utf-8")
        meta_info = tarfile.TarInfo("meta.json")
        meta_info.size = len(meta_bytes)
        tar.addfile(meta_info, io.BytesIO(meta_bytes))

        payload_root = stage_dir
        for path in sorted(payload_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(payload_root).as_posix()
            tar.add(path, arcname=f"payload/{rel}")

    return archive_path
