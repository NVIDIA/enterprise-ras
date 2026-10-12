# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""The GPU capacity gate that `validate_dataplane_subnet_capacity` refused.

That function's docstring said "GPU subnets (variable NIC count, often /20) are
not checked here", and the exemption is exactly why 2-4-3-200/largescale could
ship addressing 27 of 32 nodes while validate_excel printed no errors. The CPU
subnet got this gate already (see the `.201`/54-of-128 comments there); these
tests are the GPU half.
"""
import sys
from pathlib import Path

import openpyxl

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import validate_excel as ve


class _Result:
    """Minimal stand-in for validate_excel's result collector."""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, sheet, msg):
        self.errors.append((sheet, msg))

    def warning(self, sheet, msg):
        self.warnings.append((sheet, msg))


def _nodes(n, function="gpu"):
    """`n` enabled compute nodes.

    The canonical Excel `Function` for a compute node is **"gpu"**, not
    "compute" — `_CANONICAL_TO_INTERNAL` in excel_parser maps 'gpu' ->
    'compute', and 'compute' is not a canonical role at all. Passing
    "compute" here makes `classify_host_role` fall through to name-pattern
    matching, the node count comes back 0, and every assertion below passes
    vacuously.
    """
    return [{"name": f"su-01-node-{i + 1:02d}", "function": function,
             "enabled": True} for i in range(n)]


def _rail_vlans(count, prefix=24):
    return [{"name": f"gpu_rail{r}", "subnet": f"192.168.{r}.0/{prefix}"}
            for r in range(count)]


def _aggregate_vlan(prefix=24):
    """Single aggregate GPU VLAN (name does not match the rail regex)."""
    return [{"name": "GPU", "subnet": f"192.168.110.0/{prefix}"}]


def _wire_map_wb(rows_per_node):
    """Build an in-memory workbook with a Wire Map sheet.

    `rows_per_node` is a dict of {system_name: nic_count} for GPU-profile
    rows to insert. Required headers satisfy `build_wiremap_column_map`'s
    alias table; `Network Profile` starts with "GPU" so the helper counts them.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Wire Map"
    # Required canonical headers (aliases accepted by build_wiremap_column_map)
    ws.append(["System Name (A)", "Port (A)", "Network Profile",
               "System Name (B)", "Port (B)"])
    for node_name, nic_count in rows_per_node.items():
        for i in range(nic_count):
            ws.append([node_name, f"p{i}", "GPU Rail 1",
                       f"gpu-leaf-0{i + 1}", f"swp{i + 1}"])
    return wb


# ── clean cases (per_rail mode) ───────────────────────────────────────────

def test_144_nodes_fit_a_slash24_rail():
    """The largest shipped cell, 2-4-5-800/largescale."""
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, _nodes(144), _rail_vlans(4),
                                    {"gpu_vlan_mode": "per_rail"}, r)
    assert r.errors == []


def test_exactly_205_nodes_fit():
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, _nodes(205), _rail_vlans(1),
                                    {"gpu_vlan_mode": "per_rail"}, r)
    assert r.errors == []


# ── the shortfall the old code could not see (per_rail) ───────────────────

def test_206_nodes_do_not_fit_and_the_error_says_how_many_do():
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, _nodes(206), _rail_vlans(1),
                                    {"gpu_vlan_mode": "per_rail"}, r)
    assert len(r.errors) == 1
    msg = r.errors[0][1]
    assert "205" in msg and "206" in msg


def test_every_undersized_rail_is_reported_not_just_the_first():
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, _nodes(300), _rail_vlans(4),
                                    {"gpu_vlan_mode": "per_rail"}, r)
    assert len(r.errors) == 4


# ── the ADR-0044 prefix floor ────────────────────────────────────────────

def test_rail_subnet_smaller_than_slash24_is_an_error():
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, _nodes(4), _rail_vlans(1, prefix=27),
                                    {"gpu_vlan_mode": "per_rail"}, r)
    assert len(r.errors) == 1
    # The too-small branch must report the prefix floor and the remedy, and
    # must NOT fall through to the shortfall message, whose "holds only N of M"
    # arithmetic is meaningless below the floor.
    assert "/24 floor" in r.errors[0][1]
    assert "widen the subnet" in r.errors[0][1]
    assert "holds only" not in r.errors[0][1]


# ── non-GPU VLANs are none of this check's business ──────────────────────

def test_non_gpu_vlans_are_ignored():
    r = _Result()
    ve.validate_gpu_subnet_capacity(
        None, _nodes(500),
        [{"name": "cpu_inband", "subnet": "10.0.0.0/24"},
         {"name": "storage", "subnet": "10.0.1.0/24"}],
        {"gpu_vlan_mode": "per_rail"}, r)
    assert r.errors == []


def test_no_compute_nodes_means_nothing_to_check():
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, [], _rail_vlans(4),
                                    {"gpu_vlan_mode": "per_rail"}, r)
    assert r.errors == []


def test_disabled_nodes_do_not_count_toward_demand():
    # The extra node has function="gpu" (a genuine compute role) so it would
    # be counted IF enabled. It is excluded only because enabled=False.
    # If the `enabled is False` check were removed, this test would fail:
    # 206 nodes × 1 addr each exceeds the 205-node capacity of a /24 rail.
    nodes = _nodes(205) + [{"name": "su-99-node-01", "function": "gpu",
                            "enabled": False}]
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, nodes, _rail_vlans(1),
                                    {"gpu_vlan_mode": "per_rail"}, r)
    assert r.errors == []


# ── aggregate mode (single / dual-plane) ─────────────────────────────────
# These are the critical tests that were absent in the initial submission.
# `wb=None` activates the max(0, 2) = 2 per-node floor.
# The `_wm_cell` import is exercised in the real-workbook tests below.

def test_aggregate_mode_fits():
    """50 nodes at 2 NICs each (demand=100) sit in a /24 (capacity=102)."""
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, _nodes(50), _aggregate_vlan(),
                                    {"gpu_vlan_mode": "single"}, r)
    assert r.errors == []


def test_aggregate_mode_shortfall_names_fit_and_required():
    """103 nodes × 2 NICs exceeds /24 capacity of 102; error names both counts."""
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, _nodes(103), _aggregate_vlan(),
                                    {"gpu_vlan_mode": "single"}, r)
    assert len(r.errors) == 1
    msg = r.errors[0][1]
    assert "102" in msg and "103" in msg


def test_aggregate_wb_none_floor_is_2_fits_102_nodes():
    """With no workbook, demand defaults to 2/node. A /24 seats exactly 102."""
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, _nodes(102), _aggregate_vlan(),
                                    {"gpu_vlan_mode": "single"}, r)
    assert r.errors == []


def test_aggregate_wb_none_floor_is_2_fails_103_nodes():
    """103 nodes at the wb=None floor of 2 each exceeds /24 capacity of 102."""
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, _nodes(103), _aggregate_vlan(),
                                    {"gpu_vlan_mode": "single"}, r)
    assert len(r.errors) == 1


# ── _gpu_nics_per_compute_node: Wire Map read + _wm_cell import ──────────

def test_gpu_nics_per_compute_node_reads_wire_map():
    """A Wire Map with 3 GPU rows for node-01 and 2 for node-02 → max is 3.

    This test actually executes `_wm_cell`, so a NameError from a missing
    `_wm_cell` import in validate_excel.py will surface here.
    """
    wb = _wire_map_wb({"su-01-node-01": 3, "su-01-node-02": 2})
    result = ve._gpu_nics_per_compute_node(wb)
    assert result == 3


def test_gpu_nics_per_compute_node_no_wire_map_sheet_returns_zero():
    """A workbook without a `Wire Map` sheet returns 0 (triggers the fallback)."""
    wb = openpyxl.Workbook()
    assert ve._gpu_nics_per_compute_node(wb) == 0


def test_gpu_nics_per_compute_node_wb_none_returns_zero():
    """wb=None is the common test-fixture case; must return 0, not raise."""
    assert ve._gpu_nics_per_compute_node(None) == 0


def test_aggregate_mode_uses_wire_map_nic_count():
    """With 3 NICs per node from Wire Map, capacity at 3/node applies.

    A /24 at 3/node holds (205)//3 = 68 nodes. 68 fits; 69 does not.
    """
    wb = _wire_map_wb({"su-01-node-01": 3})  # only need count, not real node list
    r_ok = _Result()
    ve.validate_gpu_subnet_capacity(wb, _nodes(68), _aggregate_vlan(),
                                    {"gpu_vlan_mode": "single"}, r_ok)
    assert r_ok.errors == []

    r_fail = _Result()
    ve.validate_gpu_subnet_capacity(wb, _nodes(69), _aggregate_vlan(),
                                    {"gpu_vlan_mode": "single"}, r_fail)
    assert len(r_fail.errors) == 1


# ── plane aggregates are sized by the RESERVED block, not the NIC count ──
# The parser's plane branch (`elif gpu_planes and wiremap_rows`) hands every
# node a fixed DUAL_PLANE_NICS_PER_NODE block per plane and indexes into it,
# so demand there is the block size and not how many NICs the node populates.
# Sizing these rows by the Wire Map count made the gate pass workbooks the
# parser then refused — a /20 seats 449 nodes at 9 NICs each but only 252 at
# the reserved 16, so everything in between validated clean and died in
# `make import`.

def _plane_vlans(count=2, prefix=20):
    """`gpu_plane<N>` rows on /20s, the shape the parser reads into gpu_planes."""
    return [{"name": f"gpu_plane{p}", "subnet": f"192.168.{p * 16}.0/{prefix}"}
            for p in range(count)]


def test_plane_aggregate_is_sized_by_the_reserved_block_not_the_nic_count():
    """253 nodes: fits at the Wire Map's 9 NICs, does not fit at the real 16.

    This is the divergence itself. Before the fix `per_node` came back as 9
    here, 253 <= 449 passed, and the parser then raised on node 253.
    """
    wb = _wire_map_wb({"su-01-node-01": 9})
    r = _Result()
    ve.validate_gpu_subnet_capacity(wb, _nodes(253), _plane_vlans(1),
                                    {"gpu_vlan_mode": "single"}, r)
    assert len(r.errors) == 1, "must fail on the block the parser reserves"
    msg = r.errors[0][1]
    assert "252" in msg and "253" in msg
    assert "16 address(es) each" in msg, f"must report the block size: {msg}"


def test_252_nodes_is_the_plane_boundary_and_still_passes():
    """The gate must not overshoot: exactly 252 blocks of 16 fit a /20."""
    wb = _wire_map_wb({"su-01-node-01": 9})
    r = _Result()
    ve.validate_gpu_subnet_capacity(wb, _nodes(252), _plane_vlans(1),
                                    {"gpu_vlan_mode": "single"}, r)
    assert r.errors == []


def test_every_undersized_plane_is_reported():
    wb = _wire_map_wb({"su-01-node-01": 9})
    r = _Result()
    ve.validate_gpu_subnet_capacity(wb, _nodes(253), _plane_vlans(2),
                                    {"gpu_vlan_mode": "single"}, r)
    assert len(r.errors) == 2


def test_a_flat_single_row_keeps_the_wire_map_count():
    """Only `gpu_plane<N>` takes the block stride.

    A flat aggregate row goes down the parser's other path on `gpu_count`, so
    it must keep sizing by the Wire Map — 68 nodes at 3 NICs fits a /24, and
    would fail outright if the 16-address block leaked onto this row.
    """
    wb = _wire_map_wb({"su-01-node-01": 3})
    r = _Result()
    ve.validate_gpu_subnet_capacity(wb, _nodes(68), _aggregate_vlan(),
                                    {"gpu_vlan_mode": "single"}, r)
    assert r.errors == []


def test_rail_plane_rows_stay_at_one_address_per_node():
    """`gpu_rail0_plane0` is a per-rail row, not a plane aggregate.

    Both regexes could claim this name; the rail branch is checked first and
    must win, or per_rail_per_plane workbooks would be sized 16x too large.
    """
    wb = _wire_map_wb({"su-01-node-01": 9})
    r = _Result()
    ve.validate_gpu_subnet_capacity(
        wb, _nodes(205),
        [{"name": "gpu_rail0_plane0", "subnet": "192.168.0.0/24"}],
        {"gpu_vlan_mode": "per_rail_per_plane"}, r)
    assert r.errors == []


def test_a_plane_row_in_per_rail_mode_does_not_invent_a_shortfall():
    """The parser allocates from its rail rows in per_rail mode and ignores a
    stray plane row, so the gate must ignore it too rather than sizing it."""
    wb = _wire_map_wb({"su-01-node-01": 9})
    r = _Result()
    ve.validate_gpu_subnet_capacity(wb, _nodes(300), _plane_vlans(1),
                                    {"gpu_vlan_mode": "per_rail"}, r)
    assert r.errors == []


def test_without_a_wire_map_the_plane_stride_is_not_applied():
    """The parser's plane branch requires `wiremap_rows` and otherwise falls
    through to the flat path, so a Wire Map-less workbook keeps the old floor:
    300 nodes at 2/node fits a /20 that would reject them at 16."""
    r = _Result()
    ve.validate_gpu_subnet_capacity(None, _nodes(300), _plane_vlans(1),
                                    {"gpu_vlan_mode": "single"}, r)
    assert r.errors == []


def test_a_name_the_parser_rejects_as_a_plane_is_not_given_the_block():
    """`gpu plane 0` fails the parser's `^gpu_plane(\\d+)$`, so it is allocated
    on the flat path. A looser regex here would size it by a rule the
    generator is not using and fail a workbook that generates fine."""
    wb = _wire_map_wb({"su-01-node-01": 3})
    r = _Result()
    ve.validate_gpu_subnet_capacity(
        wb, _nodes(68), [{"name": "gpu plane 0", "subnet": "192.168.0.0/24"}],
        {"gpu_vlan_mode": "single"}, r)
    assert r.errors == []
