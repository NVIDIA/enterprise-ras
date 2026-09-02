#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Single source of truth for switch loopback allocation.

Both sides of the pipeline need this and they had drifted apart. The arch
generator (data-models/generate_arch_excel.py) writes loopbacks into the
Loopbacks tab; excel_parser derives them when a cell is blank. When the N/S and
E/W blocks were re-spaced, only the parser was updated — so the generator kept
emitting the pre-re-space layout and every regenerated workbook disagreed with
the shipped one (GPU VRF loopback `.11` where the workbook says `.21`, plane 2
on `10.1.2.x` where the fabric uses `10.2.1.x`).

Importing this module from both is what stops that recurring. Same arrangement
as asn_allocation.py.

Blocks are NON-OVERLAPPING by construction. Changing an offset silently
renumbers already-shipped arches — keep them stable and disjoint.

N/S fabric, within `<loopback_base>.0/24`:

    .1   - .10   reserved
    .11  - .60   N/S leaf loopbacks   (VTEP + global router-id)
    .61  - .100  N/S spine loopbacks
    .101 - .150  OOB-switch loopbacks
    .151 - .214  per-VRF loopbacks    (VRF_LOOPBACK_BLOCKS)
    .215 - .254  spare

E/W plane, within `10.<plane>.1.0/24` — note the plane is the SECOND octet, not
the third. Every role on a plane used to invent its own offset, which stayed
disjoint only while a plane held fewer than five leaves; at sixteen the leaf and
GPU ranges overlapped. One declared block per role instead, with a capacity that
is checked rather than assumed.
"""

# --- N/S ---------------------------------------------------------------------

# 16 wide against a maximum of 8 N/S leaves (2-8-9-800 / -SP at SU32) — 2x
# headroom. Starts at .151 so the switch-loopback ranges above are untouched.
# All of these stay inside ERA_PREFIXES' `<base>.0/24 le 32` entry, so
# advertisement behaviour is unchanged.
VRF_LOOPBACK_BLOCK_SIZE = 16
VRF_LOOPBACK_BLOCKS = {
    'OOB':     150,
    'INBAND':  166,
    'EXIT':    182,
    'STORAGE': 198,
}

# --- E/W ---------------------------------------------------------------------

#   .1  - .20   leaf       gl / gsl switch loopback
#   .21 - .40   leaf_gpu   gl / gsl GPU-VRF loopback
#   .41 - .50   spine      gs switch loopback
#   .51 - .60   spine_gpu  gs GPU-VRF loopback (pinned in workbooks; the gs
#                          template does not render one today)
#   .61 - .254  spare
#
# Capacities exceed the largest shipped plane (16 leaves, 8 spines) so a plane
# can grow without a re-space, and overflow raises rather than colliding.
PLANE_LOOPBACK_BLOCKS = {
    'leaf':      (0, 20),
    'leaf_gpu':  (20, 20),
    'spine':     (40, 10),
    'spine_gpu': (50, 10),
}


def vrf_loopback_octet(vrf, index):
    """Final octet for a 1-based switch `index` inside a per-VRF block."""
    base = VRF_LOOPBACK_BLOCKS[vrf]
    if not 1 <= index <= VRF_LOOPBACK_BLOCK_SIZE:
        raise ValueError(
            f"switch index {index} is outside the '{vrf}' VRF loopback block "
            f"(capacity {VRF_LOOPBACK_BLOCK_SIZE}); widen the block and "
            f"re-space VRF_LOOPBACK_BLOCKS in loopback_allocation.py"
        )
    return base + index


def plane_loopback_octet(block, index):
    """Final octet for a 1-based `index` inside a plane loopback block.

    Raises rather than wrapping into the neighbouring block — a duplicate /32
    across two switches is far harder to diagnose in the field than a
    parse-time error naming the block that ran out of room.
    """
    base, capacity = PLANE_LOOPBACK_BLOCKS[block]
    if not 1 <= index <= capacity:
        raise ValueError(
            f"plane switch index {index} is outside the '{block}' loopback "
            f"block (capacity {capacity}); widen the block and re-space "
            f"PLANE_LOOPBACK_BLOCKS in loopback_allocation.py"
        )
    return base + index


def plane_loopback(plane, block, index):
    """Full plane loopback address (no mask). Plane is the SECOND octet."""
    return f"10.{int(plane)}.1.{plane_loopback_octet(block, index)}"
