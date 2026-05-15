from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import configparser


@dataclass(slots=True)
class BuildSpec:
    name: str
    version: str
    base_dir: Path
    description: str = ""
    depends: list[str] = field(default_factory=list)

    source: str = ""
    source_sha256: str = ""
    subdir: str = ""
    patches: list[str] = field(default_factory=list)

    build_commands: list[str] = field(default_factory=list)
    install_commands: list[str] = field(default_factory=list)

    # Where files should land inside the target system (clients install into this layout under .melon/root)
    prefix: str = "/usr"


def _split_list(value: str) -> list[str]:
    value = (value or "").strip()
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def load_buildspec(path: Path) -> BuildSpec:
    path = path.resolve()
    config = configparser.ConfigParser(interpolation=None)
    config.read(path, encoding="utf-8")

    if "package" not in config:
        raise ValueError("buildspec is missing [package] section")

    package = config["package"]
    name = package.get("name", "").strip()
    version = package.get("version", "").strip()
    if not name or not version:
        raise ValueError("[package] requires name and version")

    source = config["source"] if "source" in config else {}
    build = config["build"] if "build" in config else {}

    def lines(section, key: str) -> list[str]:
        raw = (section.get(key, "") if hasattr(section, "get") else "") or ""
        items = [line.strip() for line in raw.splitlines() if line.strip()]
        return [line for line in items if not line.startswith("#")]

    return BuildSpec(
        name=name,
        version=version,
        base_dir=path.parent,
        description=package.get("desc", package.get("description", "")).strip(),
        depends=_split_list(package.get("depends", package.get("deps", ""))),
        source=str(source.get("url", "")).strip(),
        source_sha256=str(source.get("sha256", "")).strip(),
        subdir=str(source.get("subdir", "")).strip(),
        patches=_split_list(source.get("patches", "")),
        build_commands=lines(build, "commands"),
        install_commands=lines(build, "install"),
        prefix=str(build.get("prefix", "/usr")).strip() or "/usr",
    )
