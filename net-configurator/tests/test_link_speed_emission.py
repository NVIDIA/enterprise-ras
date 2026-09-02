# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-55: the Port Profiles `Speed` column must reach the rendered config.

The column has always been documented and populated in every shipped default,
and nothing emitted it. The only `link speed` we produced was hardcoded — 1G in
the OOB template, 100G in spine. Measured against four reproductions of
production fabrics that was ~90-142 missing stanzas per deployment, the largest
Excel-addressable gap, found independently by all four investigations.

The value is PER LANE: `lanes x speed` equals the NIC's port speed. The
July-2026 production captures emit exactly that — `link speed 400G` on 2x/4-lane
parents, `200G` on 4x/2-lane, `100G` on 1-lane children — so these assertions
hold the generator to the captured shape, not to a preference.
"""
import re
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
ARCHS = ["2-4-3-200", "2-4-5-800", "2-8-5-200",
         "2-8-9-400", "2-8-9-400-SP", "2-8-9-800"]

BREAKOUT_RE = re.compile(r"nv set interface (\S+) link breakout (\d)x lanes-per-port (\d)")
SPEED_RE = re.compile(r"nv set interface (\S+) link speed (\d+)G")
SUBPORT_RE = re.compile(r"(swp\d+)s\d+$")


def _core_configs(arch):
    d = NC / "output" / arch / "default" / "configs"
    if not d.is_dir():
        return []
    return [p for p in sorted(d.glob("*-config.sh"))
            if re.match(r"^(core|csl|cl)-\d+-config\.sh$", p.name)]


@pytest.mark.parametrize("arch", ARCHS)
def test_broken_out_ports_declare_a_link_speed(arch):
    """Every broken-out parent must have its children's speed emitted."""
    configs = _core_configs(arch)
    if not configs:
        pytest.skip(f"no generated core configs for {arch}")
    for cfg in configs:
        txt = cfg.read_text()
        parents = set()
        for m in BREAKOUT_RE.finditer(txt):
            parents.update(m.group(1).split(","))
        if not parents:
            continue
        speeded = set()
        for m in SPEED_RE.finditer(txt):
            for iface in m.group(1).split(","):
                sm = SUBPORT_RE.match(iface)
                if sm:
                    speeded.add(sm.group(1))
        missing = sorted(parents - speeded)
        assert not missing, (
            f"{arch}/{cfg.name}: broken out but no link speed emitted for "
            f"{missing} — the Speed column is not reaching the config")


@pytest.mark.parametrize("arch", ARCHS)
def test_emitted_speed_equals_lanes_times_100g(arch):
    """`speed == lanes x 100G` on every sub-port, per the production captures."""
    configs = _core_configs(arch)
    if not configs:
        pytest.skip(f"no generated core configs for {arch}")
    for cfg in configs:
        txt = cfg.read_text()
        lanes_by_parent = {}
        for m in BREAKOUT_RE.finditer(txt):
            for p in m.group(1).split(","):
                lanes_by_parent[p] = int(m.group(3))
        bad = []
        for m in SPEED_RE.finditer(txt):
            speed = int(m.group(2))
            for iface in m.group(1).split(","):
                sm = SUBPORT_RE.match(iface)
                if sm and sm.group(1) in lanes_by_parent:
                    lanes = lanes_by_parent[sm.group(1)]
                    if lanes * 100 != speed:
                        bad.append((iface, speed, lanes))
        assert not bad, (
            f"{arch}/{cfg.name}: speed disagrees with lanes x 100G "
            f"(iface, speed, lanes) = {bad}")


@pytest.mark.parametrize("arch", ARCHS)
def test_only_wired_subports_get_a_speed(arch):
    """An 8x parent with two wired children emits two sub-ports, not eight.

    The reference config does exactly this (`swp59s0-1 link speed 100G` on an
    8x parent). Emitting all eight would name children that are not cabled and
    would drift from the running config.
    """
    configs = _core_configs(arch)
    if not configs:
        pytest.skip(f"no generated core configs for {arch}")
    for cfg in configs:
        txt = cfg.read_text()
        breakout_of = {}
        for m in BREAKOUT_RE.finditer(txt):
            for p in m.group(1).split(","):
                breakout_of[p] = int(m.group(2))
        counts = {}
        for m in SPEED_RE.finditer(txt):
            for iface in m.group(1).split(","):
                sm = SUBPORT_RE.match(iface)
                if sm:
                    counts[sm.group(1)] = counts.get(sm.group(1), 0) + 1
        over = {p: (n, breakout_of[p]) for p, n in counts.items()
                if p in breakout_of and n > breakout_of[p]}
        assert not over, (
            f"{arch}/{cfg.name}: more sub-ports given a speed than the breakout "
            f"creates {over}")
