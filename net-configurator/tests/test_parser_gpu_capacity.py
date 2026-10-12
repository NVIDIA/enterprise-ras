# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Behavioural tests for the parser's four GPU host-addressing paths.

`excel_parser.build_devices` addresses GPU NICs at four sites — one per
`gpu_vlan_mode` shape: `per_rail_per_plane`, `per_rail`, dual plane, and
`single`. Each used to compute its own offset (`201 + idx`) and, when that
offset overflowed the subnet, `continue` — dropping the interface and carrying
on. `2-4-3-200/largescale` shipped that way: 27 of 32 compute nodes addressed,
5 silently unaddressed, and no error reported anywhere.

The companion tests in `test_gpu_ip_allocation.py` assert the deleted
identifiers are absent from the source. That is a cheap tripwire, not a
guarantee: it only trips if a future edit reuses those exact names, so the same
defect rewritten with fresh variable names would sail past it. These tests
instead drive the parser past capacity and assert observable behaviour, so all
four sites stay pinned however they are spelled.

Two properties, asserted per mode:

1. **It raises, and it names the node.** A shortfall must abort generation, not
   trim it. The node name in the message is the operator-facing half of the
   fix — "GPU subnet too small" without "which node" sends someone hunting
   through a 144-node workbook.
2. **Atomicity.** A node that fits gets its FULL complement of addresses.
   Partial allocation is the exact failure mode that shipped, so the node
   sitting on the capacity boundary is asserted to be whole.

The GPU subnets here are deliberately narrow (a `/24`, the ADR-0044 floor)
so the boundary falls at a small node count. Production dual-plane fabrics use
a `/20`.
"""
import re
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from excel_parser import build_devices  # noqa: E402
from gpu_ip_allocation import (DUAL_PLANE_NICS_PER_NODE,  # noqa: E402
                               GPU_HOST_START_OFFSET, gpu_capacity)

# Row shapes mirror tests/test_zero_based_gpu_indexing.py. `INBAND` is what
# supplies `cpu_base` (the parser aliases any 'inband'/'cpu' VLAN name to the
# 'cpu' key), and the compute branch is gated on `cpu_base and gpu_base`.
BASE_VLANS = [
    {"id": 200, "name": "oob", "subnet": "192.168.200.0/24", "vni": 4200,
     "vrf": "OOB"},
    {"id": 300, "name": "INBAND", "subnet": "172.16.178.0/24", "vni": 4300,
     "vrf": "INBAND"},
]

RAIL = "192.168.0.0/24"  # ADR-0044 per-rail subnet, and the /24 floor


def _gpu_vlan(name, subnet=RAIL, vlan_id=900):
    return {"id": vlan_id, "name": name, "subnet": subnet,
            "gateway": f"{subnet.split('/')[0].rsplit('.', 1)[0]}.1",
            "vni": vlan_id + 4000, "vrf": "GPU"}


def _nodes(count):
    """`count` active compute rows, named as parse_nodes() hands them over."""
    return [{"name": f"su-01-node-{i:02d}", "role": f"su-01-node-{i:02d}",
             "mgmt_ip": f"192.168.200.{(i % 200) + 11}", "status": "Active"}
            for i in range(1, count + 1)]


def _wm_row(node_name, nic, profile, switch="gsl-plane1-01"):
    """One Wire Map row in _build_wiremap_row_list() shape."""
    return {"display_in_air": "Yes", "system_role": "gpu",
            "system_name": node_name, "nic_port": nic, "net_profile": profile,
            "switch_role": switch.rsplit("-", 1)[0], "switch_name": switch,
            "switch_port": "swp1s0"}


def _cable(nodes, profile, switch="gsl-plane1-01", nics=("eth3",)):
    return [_wm_row(n["name"], nic, profile, switch)
            for n in nodes for nic in nics]


# Each mode: (vlans, wiremap builder, gpu_vlan_mode, addresses consumed per
# node). The last field is what the call site passes as `count` to
# `gpu_host_ips`, and therefore what sets the per-node stride and the capacity.
#
# `single` mode's own `gpu_count` is `max(len(gpu NICs), 2)`; with no Wire Map
# there are no GPU NICs, so it floors at 2. Dual plane reserves a whole
# DUAL_PLANE_NICS_PER_NODE block per node regardless of how many NICs are
# cabled. Note dual plane is reached with gpu_vlan_mode='single' plus
# gpu_plane<N> VLANs — the mode name selects per-rail shapes, not this one.
MODES = {
    "per_rail_per_plane": (
        [_gpu_vlan("gpu_rail1_plane1")],
        lambda ns: _cable(ns, "GPU Rail 1 Plane 1"),
        "per_rail_per_plane", 1),
    "per_rail": (
        [_gpu_vlan("gpu_rail1")],
        lambda ns: _cable(ns, "GPU Rail 1"),
        "per_rail", 1),
    "dual_plane": (
        [_gpu_vlan("gpu_plane1")],
        lambda ns: _cable(ns, "GPU Network"),
        "single", DUAL_PLANE_NICS_PER_NODE),
    "single": (
        [_gpu_vlan("gpu")],
        lambda ns: None,
        "single", 2),
}


def _build(mode, node_count):
    gpu_vlans, cabler, gpu_vlan_mode, _ = MODES[mode]
    nodes = _nodes(node_count)
    return nodes, build_devices(nodes, BASE_VLANS + gpu_vlans,
                                wiremap_rows=cabler(nodes),
                                gpu_vlan_mode=gpu_vlan_mode)


def _gpu_ips(entry):
    return ([i["ip"] for i in entry.get("gpu_interfaces", [])]
            + list(entry.get("gpu_ips", [])))


def _capacity(mode):
    """How many nodes this mode's subnet seats, per the allocator itself."""
    return gpu_capacity(RAIL, MODES[mode][3])


# ── 1. a shortfall raises, and the message names the node ────────────────

@pytest.mark.parametrize("mode", list(MODES))
def test_overflow_raises_naming_the_unseatable_node(mode):
    """One node past capacity must abort generation, not get skipped.

    Pins all four converted call sites. Under the old code every one of these
    returned normally with the tail of the node list unaddressed.
    """
    cap = _capacity(mode)
    nodes = _nodes(cap + 1)
    first_unseatable = nodes[cap]["name"]  # 0-based index `cap` is the (cap+1)th

    with pytest.raises(ValueError, match=re.escape(first_unseatable)) as excinfo:
        _build(mode, cap + 1)

    msg = str(excinfo.value)
    # Specifically the index-overflow branch, not the "/24 floor" rejection —
    # otherwise a widened floor check could satisfy this test vacuously.
    assert "cannot seat node index" in msg
    assert f"node index {cap}" in msg
    assert RAIL in msg


@pytest.mark.parametrize("mode", list(MODES))
def test_overflow_message_is_actionable(mode):
    """The error must say what to do, not just that something is wrong."""
    cap = _capacity(mode)
    with pytest.raises(ValueError) as excinfo:
        _build(mode, cap + 1)
    msg = str(excinfo.value)
    assert "Widen the subnet" in msg
    assert f"holds {cap} node(s)" in msg


# ── 2. atomicity: a node that fits is whole ──────────────────────────────

@pytest.mark.parametrize("mode", list(MODES))
def test_at_capacity_every_node_is_fully_addressed(mode):
    """Exactly `capacity` nodes: all seated, uniform count, none starved.

    The node on the boundary is the one the old code dropped first, so this is
    the positive complement of the raise tests: no partial lists, no silent
    trimming, and no duplicate addresses.
    """
    cap = _capacity(mode)
    nodes, devices = _build(mode, cap)

    compute = {n["name"]: devices[n["name"]] for n in nodes}
    assert len(compute) == cap

    counts = {name: len(_gpu_ips(e)) for name, e in compute.items()}
    starved = [n for n, c in counts.items() if c == 0]
    assert not starved, f"{len(starved)} node(s) left unaddressed: {starved[:5]}"
    assert len(set(counts.values())) == 1, (
        f"non-uniform GPU address counts: {sorted(set(counts.values()))}")

    all_ips = [ip for e in compute.values() for ip in _gpu_ips(e)]
    assert len(all_ips) == len(set(all_ips)), "duplicate GPU addresses issued"

    # The last node in is the boundary case, and it must be whole.
    assert counts[nodes[-1]["name"]] == counts[nodes[0]["name"]]


def test_first_node_starts_at_the_fixed_offset():
    """gpu-01 sits at GPU_HOST_START_OFFSET on every mode's subnet."""
    base = RAIL.split("/")[0].rsplit(".", 1)[0]
    expected = f"{base}.{GPU_HOST_START_OFFSET}/24"
    for mode in MODES:
        nodes, devices = _build(mode, 1)
        assert _gpu_ips(devices[nodes[0]["name"]])[0] == expected, mode


def test_per_rail_node_gets_one_address_on_every_rail():
    """A NIC per rail means an address per rail — no rail may be dropped."""
    rails = [_gpu_vlan(f"gpu_rail{r}", f"192.168.{r}.0/24", 900 + r)
             for r in range(1, 5)]
    nodes = _nodes(1)
    wm = [_wm_row(nodes[0]["name"], f"eth{3 + r}", f"GPU Rail {r + 1}")
          for r in range(4)]
    devices = build_devices(nodes, BASE_VLANS + rails, wiremap_rows=wm,
                            gpu_vlan_mode="per_rail")

    ifaces = devices[nodes[0]["name"]]["gpu_interfaces"]
    assert len(ifaces) == 4, "a rail was dropped"
    assert [i["plane"] for i in ifaces] == ["rail1", "rail2", "rail3", "rail4"]
    # Same host octet on every rail — the documented per-rail invariant.
    assert [i["ip"] for i in ifaces] == [
        f"192.168.{r}.{GPU_HOST_START_OFFSET}/24" for r in range(1, 5)]


def test_dual_plane_node_gets_a_contiguous_block_for_all_its_nics():
    """Eight NICs on one plane draw eight consecutive addresses, not seven."""
    nodes = _nodes(1)
    nics = tuple(f"eth{3 + i}" for i in range(8))
    wm = _cable(nodes, "GPU Network", nics=nics)
    devices = build_devices(nodes, BASE_VLANS + [_gpu_vlan("gpu_plane1")],
                            wiremap_rows=wm, gpu_vlan_mode="single")

    ifaces = devices[nodes[0]["name"]]["gpu_interfaces"]
    assert len(ifaces) == 8, "a plane NIC was dropped"
    assert [i["ip"] for i in ifaces] == [
        f"192.168.0.{GPU_HOST_START_OFFSET + i}/24" for i in range(8)]
    assert all(i["plane"] == "plane1" for i in ifaces)


def test_dual_plane_rejects_more_nics_than_the_reserved_block():
    """Past DUAL_PLANE_NICS_PER_NODE on one plane, raise — never wrap into
    the next node's block, which would hand two nodes the same address."""
    nodes = _nodes(1)
    nics = tuple(f"eth{3 + i}" for i in range(DUAL_PLANE_NICS_PER_NODE + 1))
    wm = _cable(nodes, "GPU Network", nics=nics)
    # A /20 so the block itself fits and only the per-node NIC cap can trip.
    with pytest.raises(ValueError, match=re.escape(nodes[0]["name"])) as excinfo:
        build_devices(nodes,
                      BASE_VLANS + [_gpu_vlan("gpu_plane1", "192.168.0.0/20")],
                      wiremap_rows=wm, gpu_vlan_mode="single")
    assert "more than" in str(excinfo.value)
    assert "DUAL_PLANE_NICS_PER_NODE" in str(excinfo.value)
