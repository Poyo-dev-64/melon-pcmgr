from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from .models import PackageMeta, normalize_rel_path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_packages(repo_dir: Path) -> dict[str, list[PackageMeta]]:
    packages_dir = repo_dir / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, list[PackageMeta]] = {}
    for archive in sorted(packages_dir.glob("*.tar.gz")):
        with tarfile.open(archive, "r:gz") as tar:
            member = tar.extractfile("meta.json")
            if member is None:
                raise ValueError(f"{archive} is missing meta.json")
            data = json.loads(member.read().decode("utf-8"))
        meta = PackageMeta(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            source_url=data.get("source_url", ""),
            package_url=data.get("package_url", f"packages/{archive.name}"),
            repo_url=data.get("repo_url", ""),
            dependencies=list(data.get("dependencies", [])),
            sha256=file_sha256(archive),
            build_configure=list(data.get("build_configure", [])),
            build_make=list(data.get("build_make", [])),
            install_steps=list(data.get("install_steps", [])),
            remove_steps=list(data.get("remove_steps", [])),
            patches=list(data.get("patches", [])),
        )
        result.setdefault(meta.name, []).append(meta)
    return result


def collect_payload_files(files_dir: Path) -> list[str]:
    if not files_dir.exists():
        return []
    return [
        normalize_rel_path(path.relative_to(files_dir))
        for path in sorted(files_dir.rglob("*"))
        if path.is_file()
    ]


def fetch_json(url: str) -> dict:
    with urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def download_file(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    return destination


def resolve_url(base_url: str, target: str) -> str:
    if not target:
        return base_url
    parsed = urlparse(target)
    if parsed.scheme:
        return target
    base = base_url if base_url.endswith("/") else f"{base_url}/"
    return urljoin(base, target)
