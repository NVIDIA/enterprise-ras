# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Forcing-function test: the per-arch seed inventory must not be
load-bearing.

Goal: the Excel + one shared secrets.yml are the only file inputs;
every invariant fact lives in ONE place (a tool-owned constants module) or is
Excel-derived. A per-arch second copy is a drift hazard — it gets missed on
updates.

This test regenerates each arch's inventory with the seed group_vars policy
files + host_vars REMOVED (against a throwaway copy of the tool tree — never the
live repo) and asserts the generated group_vars are byte-identical (timestamps
ignored) to the committed golden. `all/secrets.yml` is kept — it is the one seed
file that stays.

It is RED until the migration relocates each seeded fact into the
parser/constants. Each migrated category turns part of it green; once green, any
future code that re-reads inventories/<arch>/group_vars/* breaks CI — the durable
anti-drift guarantee.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent  # net-configurator/
ARCHS = ["2-4-3-200", "2-4-5-800", "2-8-9-800"]  # core, csl, dual-plane csl
# Seed group_vars the migration must eliminate. NOT all/secrets.yml (kept).
SEED_POLICY_FILES = ["all.yml", "core.yml", "csl.yml", "cl.yml", "oob.yml",
                     "servers.yml", "switches.yml"]
_COPY_IGNORE = shutil.ignore_patterns(
    "output", "archive", ".git", ".venv*", "__pycache__", "*.pyc",
    ".pytest_cache", ".era-secrets", "topology", "legacy",
)


def _strip_ts(p: Path) -> str:
    return "\n".join(l for l in p.read_text().splitlines() if "Generated" not in l)


def _seedless_tree(tmp: Path, arch: str) -> Path:
    dst = tmp / "nc"
    shutil.copytree(NC, dst, ignore=_COPY_IGNORE)
    gv = dst / "inventories" / arch / "group_vars"
    for f in SEED_POLICY_FILES:
        (gv / f).unlink(missing_ok=True)
    hv = dst / "inventories" / arch / "host_vars"
    if hv.exists():
        shutil.rmtree(hv)
    return dst


@pytest.mark.parametrize("arch", ARCHS)
def test_seedless_inventory_matches_golden(tmp_path, arch):
    golden_gv = NC / "output" / arch / "default" / "inventory" / "group_vars"
    if not golden_gv.exists():
        pytest.skip(f"no committed golden for {arch}")
    dst = _seedless_tree(tmp_path, arch)
    r = subprocess.run(
        [sys.executable, "scripts/excel_parser.py", "--arch", arch,
         "--site", "default", "--skip-validate"],
        cwd=dst, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"parser failed seedless:\n{r.stderr[-2000:]}"
    gen_gv = dst / "output" / arch / "default" / "inventory" / "group_vars"

    diffs = []
    # group_vars coverage. (host_vars are byte-neutrally sourced from the same
    # consolidated defaults, but a strict host_vars comparison is deferred until
    # the 2-4-5-800 vnode-host_vars normalization — its golden carries stale
    # external-conn/external-dhcp/utility that the current tool does not generate.)
    for gf in sorted(golden_gv.rglob("*.yml")):
        rel = gf.relative_to(golden_gv)
        if rel.parts[0] == "all" and rel.name == "secrets.yml":
            continue  # secrets stays; not part of the seed-elimination goal
        ng = gen_gv / rel
        if not ng.exists():
            diffs.append(f"MISSING seedless: {rel}")
        elif _strip_ts(gf) != _strip_ts(ng):
            diffs.append(f"DIFFERS seedless: {rel}")
    assert not diffs, (
        f"[{arch}] seed still load-bearing:\n  "
        + "\n  ".join(diffs)
    )
