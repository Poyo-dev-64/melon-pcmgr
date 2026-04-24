from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path

from .models import PackageMeta, normalize_rel_path
from .repository import collect_payload_files


def parse_recipe(recipe_path: Path) -> PackageMeta:
    raw: dict[str, str] = {}
    for line in recipe_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"invalid recipe line: {line!r}")
        key, value = stripped.split(":", 1)
        raw[key.strip().lower()] = value.strip()

    def split_items(key: str) -> list[str]:
        value = raw.get(key, "")
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    return PackageMeta(
        name=raw["name"],
        version=raw["version"],
        description=raw.get("desc", raw.get("description", "")),
        source_url=raw.get("url", ""),
        dependencies=split_items("deps"),
        sha256=raw.get("sha256", ""),
        build_configure=split_items("config"),
        build_make=split_items("make"),
        install_steps=split_items("install"),
        remove_steps=split_items("remove"),
        patches=split_items("patch"),
    )


def build_package(recipe_path: Path, output_dir: Path) -> Path:
    recipe_path = recipe_path.resolve()
    recipe_dir = recipe_path.parent
    meta = parse_recipe(recipe_path)
    if not meta.package_url:
        meta.package_url = f"packages/{meta.package_filename}"
    files_dir = recipe_dir / "files"
    scripts_dir = recipe_dir / "scripts"

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / meta.package_filename

    with tarfile.open(archive_path, "w:gz") as tar:
        meta_bytes = json.dumps(meta.to_dict(), indent=2).encode("utf-8")
        meta_info = tarfile.TarInfo("meta.json")
        meta_info.size = len(meta_bytes)
        import io

        tar.addfile(meta_info, io.BytesIO(meta_bytes))

        for path in sorted(files_dir.rglob("*")) if files_dir.exists() else []:
            if not path.is_file():
                continue
            arcname = f"payload/{normalize_rel_path(path.relative_to(files_dir))}"
            tar.add(path, arcname=arcname)

        for path in sorted(scripts_dir.rglob("*")) if scripts_dir.exists() else []:
            if not path.is_file():
                continue
            arcname = f"scripts/{normalize_rel_path(path.relative_to(scripts_dir))}"
            tar.add(path, arcname=arcname)

    return archive_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="melon-grow", description="Build a Melon package archive")
    parser.add_argument("recipe", help="path to the .pkg recipe file")
    parser.add_argument("--out", default="dist", help="output directory for package archives")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    archive_path = build_package(Path(args.recipe), Path(args.out))
    print(archive_path)


if __name__ == "__main__":
    main()
