# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""VRF loopback allocation must never collide, at any N/S leaf count.

Regression gate for the stride-2 bug: VRF loopbacks used to be computed as
OOB=.n / INBAND=.2+n / EXIT=.4+n, which only holds for two N/S switches. At
three or more leaves the series overlapped each other and then ran into the
switch loopbacks — at 8 leaves `172.16.176.5` was simultaneously cl-01:EXIT,
cl-03:INBAND and cl-05:OOB, and cl-07's EXIT router-id equalled cl-01's *global*
BGP router-id (172.16.176.11).

Each VRF now owns a contiguous block (see VRF_LOOPBACK_BLOCKS in excel_parser).
"""

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from excel_parser import (  # noqa: E402
    LOOPBACK_BASE,
    PLANE_LOOPBACK_BLOCKS,
    VRF_LOOPBACK_BLOCKS,
    VRF_LOOPBACK_BLOCK_SIZE,
    generate_vrf_loopbacks,
    plane_loopback_octet,
)

# Largest plane in a shipped workbook: 16 gl leaves, 8 gs spines per plane.
MAX_PLANE_LEAVES = 16
MAX_PLANE_SPINES = 8

# Max N/S leaves across all shipped archs is 8 (2-8-9-800 / -SP at SU32).
MAX_LEAVES = 8
VLANS = [
    {"vrf": "OOB", "subnet": "192.168.200.0/24"},
    {"vrf": "INBAND", "subnet": "172.16.178.0/24"},
    {"vrf": "STORAGE", "subnet": "172.16.180.0/24"},
    {"vrf": "GPU", "subnet": "192.168.110.0/24"},
]


def _alloc(n_leaves, skip_gpu=False):
    """[(switch_name, vrf, ip)] for a fabric of n_leaves N/S switches."""
    out = []
    for i in range(1, n_leaves + 1):
        for vrf, ip in generate_vrf_loopbacks(VLANS, i, skip_gpu=skip_gpu).items():
            out.append((f"leaf-{i:02d}", vrf, ip.split("/")[0]))
    return out


@pytest.mark.parametrize("n_leaves", range(1, MAX_LEAVES + 1))
def test_no_vrf_loopback_collisions(n_leaves):
    """No IP may be claimed by two different (switch, VRF) pairs."""
    seen = {}
    for sw, vrf, ip in _alloc(n_leaves):
        assert ip not in seen, (
            f"{n_leaves}-leaf fabric: {ip} claimed by both {seen.get(ip)} and "
            f"{sw}:{vrf}"
        )
        seen[ip] = f"{sw}:{vrf}"


@pytest.mark.parametrize("n_leaves", range(1, MAX_LEAVES + 1))
def test_vrf_loopbacks_never_hit_switch_loopback_range(n_leaves):
    """VRF loopbacks must stay clear of the switch-loopback / VTEP ranges.

    Switch loopbacks live at .11-.60 (N/S leaf), .61-.100 (N/S spine) and
    .101-.150 (OOB switch); the VTEP reservation is .8/29 (.8-.15). cl-07's
    EXIT loopback previously landed on .11 — another switch's global router-id.
    """
    for sw, vrf, ip in _alloc(n_leaves):
        if not ip.startswith(LOOPBACK_BASE):
            continue                      # GPU rides the GPU data subnet
        last = int(ip.rsplit(".", 1)[1])
        assert last > 150, (
            f"{sw}:{vrf} = {ip} falls inside the switch-loopback/VTEP range "
            f"(.1-.150); VRF blocks must start above .150"
        )


def test_vrf_blocks_do_not_overlap_each_other():
    """The declared blocks themselves must be disjoint and big enough."""
    spans = {
        vrf: range(base + 1, base + VRF_LOOPBACK_BLOCK_SIZE + 1)
        for vrf, base in VRF_LOOPBACK_BLOCKS.items()
    }
    assert VRF_LOOPBACK_BLOCK_SIZE >= MAX_LEAVES, (
        f"block size {VRF_LOOPBACK_BLOCK_SIZE} < max N/S leaves {MAX_LEAVES}"
    )
    items = sorted(spans.items(), key=lambda kv: kv[1].start)
    for (a, ra), (b, rb) in zip(items, items[1:]):
        assert ra.stop <= rb.start, f"{a} block {ra} overlaps {b} block {rb}"
    for vrf, r in spans.items():
        assert r.stop - 1 <= 254, f"{vrf} block {r} runs past the /24"


def test_storage_gets_a_loopback_when_the_vrf_exists():
    """ERA-39: every arch declaring a STORAGE VRF gets a STORAGE loopback,
    rather than it being opt-in per workbook."""
    assert "STORAGE" in generate_vrf_loopbacks(VLANS, 1)
    no_storage = [v for v in VLANS if v["vrf"] != "STORAGE"]
    assert "STORAGE" not in generate_vrf_loopbacks(no_storage, 1)


def test_excel_override_still_wins():
    """Per-switch Loopbacks-sheet overrides must keep priority over the block."""
    got = generate_vrf_loopbacks(
        VLANS, 1, switch_overrides={"STORAGE": "172.16.176.7"}
    )
    assert got["STORAGE"] == "172.16.176.7/32"


def test_index_beyond_block_size_raises():
    """Fail loudly rather than silently colliding if a fabric outgrows a block."""
    with pytest.raises(ValueError, match="exceeds the per-VRF loopback block size"):
        generate_vrf_loopbacks(VLANS, VRF_LOOPBACK_BLOCK_SIZE + 1)


# --------------------------------------------------------------------------
# E/W plane blocks — same defect class as the N/S stride-2 bug above, but on
# the per-plane 10.<plane>.1.0/24: a gl leaf took `<index>`, its GPU-VRF
# loopback `10 + <index>`, a gs spine `4 + <index>`. Disjoint only while the
# plane stays under five leaves; at sixteen, gl-plane1-01's GPU loopback was
# also gl-plane1-11's switch loopback.
# --------------------------------------------------------------------------

def test_plane_blocks_do_not_overlap_each_other():
    spans = {
        name: range(base + 1, base + capacity + 1)
        for name, (base, capacity) in PLANE_LOOPBACK_BLOCKS.items()
    }
    items = sorted(spans.items(), key=lambda kv: kv[1].start)
    for (a, ra), (b, rb) in zip(items, items[1:]):
        assert ra.stop <= rb.start, f"{a} block {ra} overlaps {b} block {rb}"
    for name, r in spans.items():
        assert r.stop - 1 <= 254, f"{name} block {r} runs past the /24"


def test_plane_blocks_hold_the_largest_shipped_plane():
    """Capacity must exceed the biggest plane we ship, not merely equal it."""
    for block in ("leaf", "leaf_gpu"):
        assert PLANE_LOOPBACK_BLOCKS[block][1] >= MAX_PLANE_LEAVES
    for block in ("spine", "spine_gpu"):
        assert PLANE_LOOPBACK_BLOCKS[block][1] >= MAX_PLANE_SPINES


def test_no_plane_octet_is_claimed_twice_at_full_scale():
    """The property that actually broke: every switch/VRF pair gets its own /32."""
    claimed = {}
    for index in range(1, MAX_PLANE_LEAVES + 1):
        for block in ("leaf", "leaf_gpu"):
            octet = plane_loopback_octet(block, index)
            assert octet not in claimed, (
                f"{block}[{index}] -> .{octet} already taken by {claimed[octet]}"
            )
            claimed[octet] = f"{block}[{index}]"
    for index in range(1, MAX_PLANE_SPINES + 1):
        for block in ("spine", "spine_gpu"):
            octet = plane_loopback_octet(block, index)
            assert octet not in claimed, (
                f"{block}[{index}] -> .{octet} already taken by {claimed[octet]}"
            )
            claimed[octet] = f"{block}[{index}]"


def test_plane_index_beyond_capacity_raises():
    """Fail loudly rather than wrapping into the neighbouring block."""
    for block, (_base, capacity) in PLANE_LOOPBACK_BLOCKS.items():
        with pytest.raises(ValueError, match="outside the"):
            plane_loopback_octet(block, capacity + 1)
        with pytest.raises(ValueError, match="outside the"):
            plane_loopback_octet(block, 0)


def test_old_plane_layout_would_be_rejected():
    """Mutation check: the pre-fix `10 + index` GPU offset must not validate."""
    leaf_base, _ = PLANE_LOOPBACK_BLOCKS["leaf"]
    gpu_base, _ = PLANE_LOOPBACK_BLOCKS["leaf_gpu"]
    old_gpu = {10 + i for i in range(1, MAX_PLANE_LEAVES + 1)}
    leaves = {leaf_base + i for i in range(1, MAX_PLANE_LEAVES + 1)}
    assert old_gpu & leaves, "fixture no longer reproduces the original collision"
    new_gpu = {gpu_base + i for i in range(1, MAX_PLANE_LEAVES + 1)}
    assert not (new_gpu & leaves)
