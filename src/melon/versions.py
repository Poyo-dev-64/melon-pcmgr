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


_EPOCH_RE = re.compile(r"^(?:(\d+):)?(.+)$")


def version_key(version: str) -> tuple:
    """
    Comparable key for versions in the form:
      [epoch:]version[-release]

    - epoch: integer, defaults to 0
    - version: may contain digits/letters/separators
    - release: distro packaging release (often an int); compared after version
    """
    version = (version or "").strip()
    match = _EPOCH_RE.match(version)
    if not match:
        return (0, (), ())
    epoch = int(match.group(1) or 0)
    rest = match.group(2) or ""

    if "-" in rest:
        base, rel = rest.rsplit("-", 1)
    else:
        base, rel = rest, ""

    return (epoch, _split_version_parts(base), _split_version_parts(rel))


def _split_version_parts(text: str) -> tuple:
    # Split into alternating numeric and alpha chunks; treat separators as boundaries.
    # Special-case "~" as the smallest possible chunk for pre-releases.
    text = (text or "").strip()
    if not text:
        return ()
    chunks: list[tuple[int, object]] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "~":
            chunks.append((-1, ""))  # always sorts before everything else
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            chunks.append((0, int(text[i:j])))
            i = j
            continue
        if ch.isalpha():
            j = i
            while j < len(text) and text[j].isalpha():
                j += 1
            chunks.append((1, text[i:j]))
            i = j
            continue
        # separator/punctuation: skip but create a boundary
        i += 1
    return tuple(chunks)


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
