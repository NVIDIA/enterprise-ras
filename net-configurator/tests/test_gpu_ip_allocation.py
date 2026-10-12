# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Unit tests for the GPU host address allocator.

This module exists because GPU addressing had four hand-rolled call sites and
no owner. Three of them repeated `201 + idx` with a
`if offset >= net.num_addresses - 1: continue` guard, so from the 55th node
onward every rail subnet silently skipped that node; the fourth returned None
and the node was written with no GPU addresses at all. The property these tests
defend is that allocation is ATOMIC: every requested address, or an exception.
Never a short list, never a silent skip.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import gpu_ip_allocation as g

RAIL = "192.168.0.0/24"          # ADR-0044 per-rail subnet
AGG = "192.168.0.0/20"           # ADR-0044 aggregate single-mode plane


# ── the fixed start offset ────────────────────────────────────────────────

def test_start_offset_is_fifty():
    assert g.GPU_HOST_START_OFFSET == 50


def test_first_node_gets_dot_fifty():
    assert g.gpu_host_ips(RAIL, 0, 1) == ["192.168.0.50/24"]


def test_node_offset_is_start_plus_index_for_count_one():
    assert g.gpu_host_ips(RAIL, 7, 1) == ["192.168.0.57/24"]


def test_same_offset_across_different_rail_subnets():
    """gpu-07 must hold .57 on EVERY rail — this is what makes a rail
    fabric debuggable by eye, so it is asserted, not assumed."""
    a = g.gpu_host_ips("192.168.0.0/24", 7, 1)[0]
    b = g.gpu_host_ips("192.168.3.0/24", 7, 1)[0]
    assert a.split("/")[0].split(".")[-1] == b.split("/")[0].split(".")[-1] == "57"


# ── capacity ─────────────────────────────────────────────────────────────

def test_slash24_seats_205_nodes_at_one_address_each():
    assert g.gpu_capacity(RAIL, 1) == 205


def test_slash20_seats_4045_at_one_address_each():
    assert g.gpu_capacity(AGG, 1) == 4045


def test_capacity_halves_when_each_node_takes_two():
    assert g.gpu_capacity(RAIL, 2) == 102


# ── the exact boundary ───────────────────────────────────────────────────

def test_last_seatable_node_succeeds():
    assert g.gpu_host_ips(RAIL, 204, 1) == ["192.168.0.254/24"]


def test_one_past_the_end_raises_rather_than_returning_short():
    with pytest.raises(g.GpuCapacityError):
        g.gpu_host_ips(RAIL, 205, 1)


def test_broadcast_is_never_handed_out():
    ips = [g.gpu_host_ips(RAIL, i, 1)[0] for i in range(205)]
    assert "192.168.0.255/24" not in ips


def test_the_original_defect_index_is_now_seatable():
    """idx 54 used to compute `201 + 54 = .255`, which the old guard turned
    into a `continue` — the exact index where 2-4-3-200/largescale began
    losing nodes. It must now seat cleanly at .104."""
    assert g.gpu_host_ips(RAIL, 54, 1) == ["192.168.0.104/24"]


# ── atomicity ────────────────────────────────────────────────────────────

def test_multi_address_allocation_is_all_or_nothing():
    """The last node whose full block does not fit must raise, not return
    a truncated block."""
    with pytest.raises(g.GpuCapacityError):
        g.gpu_host_ips(RAIL, 102, 2)


def test_multi_address_block_is_contiguous():
    assert g.gpu_host_ips(RAIL, 3, 4) == [
        "192.168.0.62/24", "192.168.0.63/24",
        "192.168.0.64/24", "192.168.0.65/24",
    ]


# ── prefix floor (ADR-0044) ──────────────────────────────────────────────

@pytest.mark.parametrize("subnet", ["192.168.0.0/25", "192.168.0.0/26",
                                    "192.168.0.0/27", "192.168.0.0/30"])
def test_subnet_smaller_than_slash24_is_a_hard_error(subnet):
    """Raises the narrower TYPE, so callers branch on it instead of on wording.

    Asserting the message text here is what previously forced an internal
    ADR number into operator-visible output; the type carries the same
    information without shipping it.
    """
    with pytest.raises(g.GpuSubnetTooSmallError) as exc:
        g.gpu_host_ips(subnet, 0, 1)
    assert isinstance(exc.value, g.GpuCapacityError), "must stay catchable as capacity"
    assert "widen the subnet" in str(exc.value), "operator needs the remedy"


def test_slash24_and_slash20_are_both_accepted():
    assert g.gpu_host_ips(RAIL, 0, 1)
    assert g.gpu_host_ips(AGG, 0, 1)


def test_missing_subnet_raises():
    with pytest.raises(g.GpuCapacityError):
        g.gpu_host_ips("", 0, 1)


def test_malformed_subnet_raises():
    with pytest.raises(g.GpuCapacityError):
        g.gpu_host_ips("not-a-subnet", 0, 1)


# ── fabric claims stay clear of the host range ───────────────────────────

def test_fabric_offsets_name_their_owners():
    claims = g.gpu_fabric_offsets(n_gpu_leaves=16, n_cores=2)
    assert claims[1] == "VRR/anycast gateway"
    assert "leaf" in claims[2].lower()


def test_no_fabric_claim_reaches_the_host_range():
    """The whole reason .50 needs no skip-list.

    Measured: the largest architectures (2-4-5-800, 2-8-9-800 largescale)
    have 32 GPU leaf switches in total, 16 per plane, and a single rail
    subnet is served by at most one plane's worth. 16 leaves tops out at
    offset .17, which is what the generated configs show. Asserting 32
    leaves is therefore a 2x over-estimate and still clears .50.
    """
    assert g.find_gpu_collisions(n_gpu_leaves=32, n_cores=8) == []
    assert max(g.gpu_fabric_offsets(16, 2)) == 17


def test_cores_claim_nothing_in_a_gpu_subnet():
    """Core GPU VRF loopbacks left the GPU subnet entirely.

    They used to be claimed at `5 + i` here, mirroring a parser that cut
    them from rail 0. That put them in the same /24 as the per-switch SVIs
    counting up from .2, so a four-core fabric collided core-04's SVI with
    core-01's loopback on .5. They now come from the switch's own loopback
    pool, so no core count may add a claim.
    """
    assert g.gpu_fabric_offsets(n_gpu_leaves=0, n_cores=0) == \
           g.gpu_fabric_offsets(n_gpu_leaves=0, n_cores=64), \
           "core count must not affect GPU-subnet claims"
    # The specific address the old scheme handed core-01, and the one a
    # 4-core fabric would have duplicated.
    for cores in (1, 2, 4, 64):
        assert 5 not in g.gpu_fabric_offsets(n_gpu_leaves=0, n_cores=cores)


def test_the_fixed_start_has_a_known_breaking_point():
    """Leaf SVIs are `2 + ordinal`, so the 49th leaf in ONE GPU subnet
    lands exactly on .50. This documents the real headroom instead of
    assuming it is unlimited: 48 leaves is still clear, 49 collides. If a
    future fabric approaches this, GPU_HOST_START_OFFSET must be raised —
    a loud decision, which is what find_gpu_collisions exists to force.

    Note the breaking point is now purely a leaf-count property; `n_cores`
    is passed but claims nothing (see test_cores_claim_nothing_in_a_gpu_subnet).
    """
    assert g.find_gpu_collisions(n_gpu_leaves=48, n_cores=8) == []
    assert g.find_gpu_collisions(n_gpu_leaves=49, n_cores=8) == [
        (50, "GPU leaf SVI (switch ordinal 49)")]


# ── the four call-site shapes ────────────────────────────────────────────

def test_per_rail_shape_one_address_per_node():
    assert len(g.gpu_host_ips(RAIL, 0, 1)) == 1


def test_single_mode_shape_one_address_per_nic():
    assert len(g.gpu_host_ips(RAIL, 0, 8)) == 8


def test_dual_plane_shape_uses_the_named_stride():
    """Node 1 starts at offset 50 + 16*1 = 66 in the aggregate /20."""
    ips = g.gpu_host_ips(AGG, 1, g.DUAL_PLANE_NICS_PER_NODE)
    assert len(ips) == 16
    assert ips[0] == "192.168.0.66/20"
    assert ips[-1] == "192.168.0.81/20"


def test_largescale_worst_case_fits():
    """2-4-5-800/largescale is the largest shipped cell at 144 nodes."""
    assert g.gpu_host_ips(RAIL, 143, 1) == ["192.168.0.193/24"]


# ── the parser no longer hand-rolls GPU offsets ──────────────────────────

PARSER = SCRIPTS_DIR / "excel_parser.py"


def test_parser_has_no_hardcoded_201_gpu_offset():
    """The three duplicated `201 + idx` formulas must be gone. Their
    presence is the defect, not a style question.

    Scope: this pins the ORIGINAL IDENTIFIERS only. Renaming the variable
    defeats it, so it is not the safety net for the pattern — the behavioural
    tests in test_parser_gpu_capacity.py are, because they drive each of the
    four call sites past capacity and require a raise.
    """
    src = PARSER.read_text()
    assert "host_offset = 201 + idx" not in src
    assert "plane_offset = 201 + 16 * idx" not in src


def test_parser_has_no_silent_skip_guard_in_gpu_paths():
    """`if host_offset >= net.num_addresses - 1: continue` dropped a NIC and
    carried on. Nothing may reintroduce a skip in a GPU path.

    Scope: same caveat as above — a rewrite using fresh names and the correct
    .50 base would pass this while regrowing the defect. That case is covered
    behaviourally in test_parser_gpu_capacity.py, which was written after
    proving exactly that rewrite passes these two greps.
    """
    src = PARSER.read_text()
    assert "if host_offset >= net.num_addresses - 1" not in src
    assert "if plane_offset >= net.num_addresses - 1" not in src


def test_parser_imports_the_allocator():
    assert "from gpu_ip_allocation import" in PARSER.read_text()
