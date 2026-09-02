# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""The EXIT VRF's BGP neighbors must be the Excel-declared edge ports.

ADR-0035: the workbook is the only source of operator intent. `edge_interfaces`
is derived from the Edge Uplink port profile, but the EXIT VRF's peer-group and
routing policy are *inherited* from `scripts/inventory_defaults.yml`, whose
neighbor list is tied to the reference workbook. `_sync_edge_vrf_neighbors()`
is what reconciles the two — it overwrites the inherited interface list with
the Excel-derived one.

That reconciliation matches neighbors **by peer-group name**, which makes it
quietly fragile: anything that changes the name on one side and not the other
turns the sync into a no-op, and the fabric silently peers on whatever ports
the defaults happened to hardcode.

This is not hypothetical. Renaming `underlay_esl_external` -> `exit` (ADR-0043)
had to touch three files; doing two of them left this sync dead, and the EXIT
neighbors reverted from the workbook's `swp64s0-3` to the defaults' `swp61s0`,
`swp61s1`, `swp63s0`, `swp63s1`. The full 1284-test suite passed in that state,
and so did a peer-group-reference check — each config was internally
consistent, just peering on the wrong physical ports.

Peering on ports the workbook did not declare is an operator-visible fault:
the cables are where the workbook says they are.
"""
import re
from pathlib import Path

import pytest
import yaml

NC = Path(__file__).resolve().parent.parent
# Roles that terminate the EXIT VRF — the N/S switches, single- and two-tier.
_ROLES = ("core", "csl", "cl")
# Matches ANY peer-group name on purpose. The bug this guards is a *name*
# mismatch, so a name-matched filter would skip the broken state and pass
# vacuously — which is exactly what the first draft of this test did.
_NEIGHBOR = re.compile(
    r"^nv set vrf EXIT router bgp neighbor (\S+) peer-group \S+\s*$")


def _expand(edge):
    """Expand {ports:[64], breakout:4} -> {swp64s0..swp64s3}.

    Mirrors `_expand_subport_names`; kept independent on purpose so a bug in
    that helper cannot make this test agree with the code it is checking.
    """
    out = set()
    for p in edge.get("ports") or []:
        b = edge.get("breakout") or 1
        if b and b > 1:
            out.update(f"swp{p}s{i}" for i in range(b))
        else:
            out.add(f"swp{p}")
    return out


# Only the two sites that ship as reference output. `output/` also collects
# throwaway sites from local Air runs, which are not regenerated and would make
# this test fail on someone else's leftovers rather than on a real defect.
_SHIPPED_SITES = ("default", "largescale")


def _cases():
    for gv in sorted(NC.glob("output/*/*/inventory/group_vars/*.yml")):
        if gv.stem not in _ROLES:
            continue
        arch, site = gv.parts[-5], gv.parts[-4]
        if site not in _SHIPPED_SITES:
            continue
        yield pytest.param(gv, arch, site, gv.stem,
                           id=f"{arch}/{site}/{gv.stem}")


CASES = list(_cases())


def test_cases_exist():
    """An empty glob would make every parametrised test vacuously pass."""
    assert CASES, "no N/S group_vars found — regenerate output before testing"


@pytest.mark.parametrize("gv,arch,site,role", CASES)
def test_exit_neighbors_match_declared_edge_ports(gv, arch, site, role):
    data = yaml.safe_load(gv.read_text()) or {}
    edge = data.get("edge_interfaces")
    if not edge or not edge.get("ports"):
        pytest.skip(f"{arch}/{site}/{role}: no edge uplink declared")

    expected = _expand(edge)
    assert expected, f"{gv}: edge_interfaces expanded to nothing"

    exit_vrfs = [v for v in (data.get("vrf_config") or [])
                 if isinstance(v, dict) and v.get("id") == "EXIT"]
    if not exit_vrfs:
        pytest.skip(f"{arch}/{site}/{role}: no EXIT VRF")

    for vrf in exit_vrfs:
        for nb in (vrf.get("bgp") or {}).get("neighbors") or []:
            # No peer-group filter — see _NEIGHBOR above.
            got = set(nb.get("interfaces") or [])
            assert got, f"{arch}/{site}/{role}: EXIT peer-group has no neighbors"
            # Subset, not equality. `_expand` above is deliberately naive — it
            # expands every sub-port of every declared parent — while the real
            # allocator honours partial cabling, so a declared-but-uncabled
            # sub-port legitimately never appears. Requiring equality fails on
            # correct output for five of the six archs.
            #
            # The direction that matters is this one: a port the workbook never
            # declared must never be peered on. When the sync goes dead the
            # neighbors keep `inventory_defaults.yml`'s hardcoded list, which
            # contains `swp61s0`/`swp61s1` — ports no workbook declares as edge
            # uplinks — so this catches exactly that failure.
            undeclared = got - expected
            assert not undeclared, (
                f"{arch}/{site}/{role}: EXIT peers on {sorted(undeclared)}, "
                f"which the workbook never declares as edge ports (declared: "
                f"{sorted(expected)}) — _sync_edge_vrf_neighbors did not "
                f"apply, so the fabric peers where the Excel never asked")


@pytest.mark.parametrize("gv,arch,site,role", CASES)
def test_rendered_config_never_peers_on_undeclared_ports(gv, arch, site, role):
    """Asserted on the artifact that actually ships.

    Deliberately a SUBSET check, not equality. The template emits only the
    sub-ports that are actually wired (ADR-0042), so a declared-but-uncabled
    sub-port legitimately never reaches the config — on 2-8-5-200 core-01 the
    workbook declares `swp62s0-s3` while only `s0`/`s1` are cabled. Equality
    here would fail on correct output.

    What must never happen is the reverse: peering on a port the workbook did
    not declare. That is the direction that indicates the Excel-derived list
    was ignored.
    """
    data = yaml.safe_load(gv.read_text()) or {}
    edge = data.get("edge_interfaces")
    if not edge or not edge.get("ports"):
        pytest.skip(f"{arch}/{site}/{role}: no edge uplink declared")
    expected = _expand(edge)

    cfgdir = NC / "output" / arch / site / "configs"
    configs = sorted(cfgdir.glob(f"{role}-*-config.sh"))
    if not configs:
        pytest.skip(f"{arch}/{site}/{role}: no rendered configs")

    for cfg in configs:
        got = {m.group(1) for m in
               (_NEIGHBOR.match(l.strip()) for l in cfg.read_text().splitlines())
               if m}
        if not got:
            continue  # this switch has no edge uplink; covered above
        undeclared = got - expected
        assert not undeclared, (
            f"{cfg.relative_to(NC)}: EXIT peers on {sorted(undeclared)}, which "
            f"the workbook never declares as edge ports (declared: "
            f"{sorted(expected)}) — the Excel-derived edge list was ignored")
