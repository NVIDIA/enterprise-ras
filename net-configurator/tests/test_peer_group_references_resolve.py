# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Every BGP neighbor must reference a peer-group that is actually defined.

ADR-0043 names this hazard explicitly: "a half-applied rename leaves neighbours
pointing at a peer-group that no longer exists". Nothing asserted it.

It is not hypothetical. Renaming `underlay_esl_external` -> `exit` (ADR-0043)
touched three sources: `excel_parser.py`, `core_nvue_cli.j2` and
`scripts/inventory_defaults.yml`. Renaming only the first two left the fabric
emitting BOTH spellings, and — because `_sync_edge_vrf_neighbors` matches
neighbors *by peer-group name* — silently stopped syncing the EXIT neighbors
against the Excel edge ports, so the generated ports reverted to the hardcoded
defaults. The full 1284-test suite passed in that state.

Two invariants, both cheap:

1. Every `neighbor <if> peer-group <X>` has a matching `peer-group <X> ...`
   definition in the SAME VRF of the SAME file. A dangling reference is a
   config NVUE will reject or, worse, silently treat as an unconfigured peer.
2. No config emits two spellings of one logical peer-group. This is the
   *shape* of a half-applied rename and catches it even when both spellings
   happen to resolve.
"""
import re
from collections import defaultdict
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
CONFIGS = sorted(NC.glob("output/*/*/configs/*-config.sh"))

# A neighbor line and a peer-group definition line, both VRF-scoped. The
# `vrf default` form is spelled the same way, so one pattern covers both.
_NEIGHBOR = re.compile(
    r"^nv set vrf (\S+) router bgp neighbor (\S+) peer-group (\S+)\s*$")
_PEERGROUP = re.compile(
    r"^nv set vrf (\S+) router bgp peer-group (\S+)\s+\S")

# Two spellings of one name differing only by separator — `internal-isl` vs
# `internal_isl` — is the signature ADR-0043 was written to eliminate.
def _canonical(name):
    return name.replace("-", "_").lower()


def _parse(path):
    """-> (defined, referenced) as {(vrf, peer_group)} sets."""
    defined, referenced = set(), set()
    for line in path.read_text().splitlines():
        line = line.strip()
        m = _NEIGHBOR.match(line)
        if m:
            referenced.add((m.group(1), m.group(3)))
            continue
        m = _PEERGROUP.match(line)
        if m:
            defined.add((m.group(1), m.group(2)))
    return defined, referenced


def test_configs_exist():
    """Guard against the whole suite silently passing on an empty glob."""
    assert CONFIGS, "no generated configs found — regenerate before testing"


@pytest.mark.parametrize("cfg", CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
def test_every_neighbor_peer_group_is_defined(cfg):
    defined, referenced = _parse(cfg)
    dangling = referenced - defined
    assert not dangling, (
        f"{cfg.relative_to(NC)}: neighbors reference peer-group(s) that are "
        f"never defined in that VRF: {sorted(dangling)} — this is the "
        f"half-applied-rename failure ADR-0043 warns about")


@pytest.mark.parametrize("cfg", CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
def test_no_two_spellings_of_one_peer_group(cfg):
    defined, referenced = _parse(cfg)
    by_canonical = defaultdict(set)
    for _vrf, pg in defined | referenced:
        by_canonical[_canonical(pg)].add(pg)
    split = {k: sorted(v) for k, v in by_canonical.items() if len(v) > 1}
    assert not split, (
        f"{cfg.relative_to(NC)}: one logical peer-group emitted under multiple "
        f"spellings {split} — a rename reached some sources but not others")
