#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""The one place the supported-architecture set is read from (ERA-88).

``scripts/valid_archs.yml`` is generated from ``data-models/models/*.yaml`` and
committed inside the public boundary. Every script that used to restate the
list imports ``VALID_ARCHS`` from here instead::

    from _valid_archs import VALID_ARCHS

``VALID_ARCHS`` is an ordered tuple; wrap it in ``set()`` for membership sets.
A missing or malformed registry is a hard error — an empty arch set would make
every ``ARCH`` invalid and every arch-keyed guard vacuous.

Usage (prints one arch per line, for shell/make consumers)::

    python3 scripts/_valid_archs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent / "valid_archs.yml"
_ARCH_RE = re.compile(r"^\d+-\d+-\d+-\d+(?:-SP)?$")


def load_valid_archs(path: Path = REGISTRY) -> tuple[str, ...]:
    """Read the registry. Deliberately dependency-free (no PyYAML) so the
    Makefile-adjacent helpers keep working on a bare interpreter."""
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise RuntimeError(f"supported-arch registry missing: {path} ({exc})") from exc

    archs: list[str] = []
    in_list = False
    for raw in lines:
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line == "archs:":
            in_list = True
            continue
        if in_list and line.startswith("  - "):
            arch = line[4:].strip().strip("'\"")
            if not _ARCH_RE.match(arch):
                raise RuntimeError(f"{path}: malformed arch entry {arch!r}")
            archs.append(arch)
            continue
        if in_list:
            raise RuntimeError(f"{path}: unexpected line inside archs list: {raw!r}")
    if not archs:
        raise RuntimeError(f"{path}: no archs listed")
    if len(set(archs)) != len(archs):
        raise RuntimeError(f"{path}: duplicate arch entries")
    return tuple(archs)


VALID_ARCHS: tuple[str, ...] = load_valid_archs()


if __name__ == "__main__":
    sys.stdout.write("\n".join(VALID_ARCHS) + "\n")
