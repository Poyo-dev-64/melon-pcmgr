from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class PackageMeta:
    name: str
    version: str
    description: str = ""
    source_url: str = ""
    package_url: str = ""
    dependencies: list[str] = field(default_factory=list)
    sha256: str = ""
    build_configure: list[str] = field(default_factory=list)
    build_make: list[str] = field(default_factory=list)
    install_steps: list[str] = field(default_factory=list)
    remove_steps: list[str] = field(default_factory=list)
    patches: list[str] = field(default_factory=list)

    @property
    def package_filename(self) -> str:
        return f"{self.name}-{self.version}.tar.gz"

    @property
    def package_stem(self) -> str:
        return f"{self.name}-{self.version}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class InstalledPackage:
    meta: PackageMeta
    files: list[str] = field(default_factory=list)
    held: bool = False

    def to_dict(self) -> dict:
        return {
            "meta": self.meta.to_dict(),
            "files": self.files,
            "held": self.held,
        }


def package_from_dict(data: dict) -> PackageMeta:
    return PackageMeta(
        name=data["name"],
        version=data["version"],
        description=data.get("description", ""),
        source_url=data.get("source_url", ""),
        package_url=data.get("package_url", ""),
        dependencies=list(data.get("dependencies", [])),
        sha256=data.get("sha256", ""),
        build_configure=list(data.get("build_configure", [])),
        build_make=list(data.get("build_make", [])),
        install_steps=list(data.get("install_steps", [])),
        remove_steps=list(data.get("remove_steps", [])),
        patches=list(data.get("patches", [])),
    )


def installed_from_dict(data: dict) -> InstalledPackage:
    return InstalledPackage(
        meta=package_from_dict(data["meta"]),
        files=list(data.get("files", [])),
        held=bool(data.get("held", False)),
    )


def normalize_rel_path(path: Path) -> str:
    return path.as_posix().lstrip("/")
