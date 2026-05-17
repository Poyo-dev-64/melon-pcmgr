from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DepSpec:
    name: str
    op: str = ""
    version: str = ""


_DEP_RE = re.compile(r"^\s*([A-Za-z0-9_.+-]+)\s*(==|=|>=|<=|>|<)?\s*([A-Za-z0-9_.+-]+)?\s*$")


def parse_dep_spec(text: str) -> DepSpec:
    match = _DEP_RE.match(text or "")
    if not match:
        raise ValueError(f"invalid dependency spec: {text!r}")
    name, op, version = match.group(1), match.group(2) or "", match.group(3) or ""
    if op == "=":
        op = "=="
    if op and not version:
        raise ValueError(f"invalid dependency spec (missing version): {text!r}")
    return DepSpec(name=name, op=op, version=version)


def version_key(version: str) -> tuple:
    # Lightweight comparator: split into numeric and non-numeric parts.
    parts = re.split(r"([0-9]+)", version or "")
    key: list[tuple[int, object]] = []
    for part in parts:
        if part == "":
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return tuple(key)


def satisfies(version: str, op: str, required: str) -> bool:
    if not op:
        return True
    a = version_key(version)
    b = version_key(required)
    if op == "==":
        return a == b
    if op == ">=":
        return a >= b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == "<":
        return a < b
    raise ValueError(f"unsupported operator: {op}")

