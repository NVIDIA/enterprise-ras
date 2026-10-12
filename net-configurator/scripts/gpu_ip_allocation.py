#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Sole owner of GPU host address arithmetic (ADR-0062).

GPU addressing used to happen at four independent sites in `excel_parser.py`.
Three hand-rolled `host_offset = 201 + idx` and guarded it with
`if host_offset >= net.num_addresses - 1: continue`, which DROPPED that
interface and carried on; the fourth called `_dataplane_host_ips` without
`total=`, so it returned None and the node was written with no GPU addresses.
In a /24 the legacy `.201` base leaves 54 usable addresses, so from the 55th
node onward every rail subnet skipped that node. `2-4-3-200/largescale` shipped
that way: 27 of 32 nodes addressed, `validate_excel` reporting no errors.

Two properties prevent a recurrence:

1. **A fixed start offset of 50.** Fabric components claim the bottom of every
   GPU subnet — gateway at `.1`, GPU leaf SVIs from `.2` to roughly `.17`, which
   depends on the leaf count. Starting at `.50` clears all of them for any
   fabric this tool builds, which turns "walk the subnet skipping fabric
   addresses" into a contiguous run plus one assertion. `find_gpu_collisions`
   is that assertion.

   Core GPU VRF loopbacks used to claim `.5` upward here too, which put them in
   the same subnet as the SVIs and made the two collide at four cores. They now
   come from the switch's loopback pool, so a GPU subnet holds only the gateway,
   the SVIs and the hosts.

2. **Atomic allocation.** `gpu_host_ips` returns every address asked for or
   raises. It cannot return a short list, which is the single behaviour that
   caused the original defect.

ADR-0044 fixes the geometry this relies on: `/24` per rail, `/20` per aggregate
plane. A GPU subnet smaller than a `/24` is a hard error, not a fallback.
"""
from __future__ import annotations

import ipaddress

# First address offered to a GPU host interface, as an offset from the subnet
# base. Clears every fabric claim (see module docstring) with wide margin.
GPU_HOST_START_OFFSET = 50

# The SMALLEST allowed GPU subnet is a /24, so a prefix LENGTH above 24 is
# rejected. ADR-0044 ships /24 per rail and /20 aggregate (length 20).
MAX_GPU_PREFIX_LEN = 24

# Per-node stride on aggregate plane subnets. Preserves the historical
# 16-NIC-per-node headroom the dual-plane path reserved in its /20.
DUAL_PLANE_NICS_PER_NODE = 16


class GpuCapacityError(ValueError):
    """A GPU subnet cannot seat every host it was asked to seat.

    Raised rather than returning a partial result: a partly addressed GPU
    subnet is the defect this module exists to prevent.
    """


class GpuSubnetTooSmallError(GpuCapacityError):
    """The subnet is narrower than the /24 floor, so no host count can fit.

    Distinct from a shortfall: widening is the only remedy, where a shortfall
    can also be resolved by reducing the host count. Callers select the right
    operator message from the TYPE — never by matching text in the message,
    which couples their control flow to wording.
    """


def _network(subnet):
    """Parse `subnet`, raising GpuCapacityError for anything unusable.

    Callers gate real deployments on this, so an empty or malformed subnet is
    an error to report, never a None to skip past.
    """
    if not subnet:
        raise GpuCapacityError("no GPU subnet declared")
    try:
        return ipaddress.ip_network(str(subnet).strip(), strict=False)
    except ValueError as exc:
        raise GpuCapacityError(f"GPU subnet {subnet!r} is not a valid network: {exc}") from exc


def gpu_fabric_offsets(n_gpu_leaves=0, n_cores=0):
    """Offsets the FABRIC claims at the bottom of a GPU subnet -> owner name.

    Returned for error messages and for `find_gpu_collisions`; the allocator
    itself never consults it, because `GPU_HOST_START_OFFSET` sits above every
    entry. Owners are reported so a collision names what it hit instead of
    printing a bare number, mirroring `OOB_RESERVED_OCTETS` in oob_reserved.py.

    Offsets are stated here as `base + i` over a zero-based `i`, which is what
    the loop below uses. The parser writes the same claims from one-based
    ordinals (`1 + switch_ordinal`), so the first GPU leaf lands on .2 either
    way — the two conventions describe the same addresses.

    `n_cores` is accepted and deliberately ignored. Core GPU VRF loopbacks were
    once claimed here at `5 + i`, because the parser cut them from the first GPU
    VLAN's subnet; they now come from the switch's own loopback pool
    (`VRF_LOOPBACK_BLOCKS['GPU']` in loopback_allocation.py) and never land in a
    GPU subnet. The parameter stays so callers and `find_gpu_collisions` keep
    their signature, and so the reason it is empty is recorded rather than
    looking like an omission.
    """
    claims = {0: "network address", 1: "VRR/anycast gateway"}
    for i in range(max(int(n_gpu_leaves or 0), 0)):
        claims.setdefault(2 + i, f"GPU leaf SVI (switch ordinal {i + 1})")
    return claims


def gpu_capacity(subnet, per_node=1):
    """How many NODES `subnet` seats at `per_node` addresses each, from .50.

    Excludes the broadcast address. A /24 at one address per node seats 205
    (.50 through .254).
    """
    net = _network(subnet)
    usable = int(net.num_addresses) - 1 - GPU_HOST_START_OFFSET
    if usable <= 0:
        return 0
    return usable // max(int(per_node), 1)


def gpu_host_ips(subnet, idx, count=1):
    """`count` consecutive GPU host addresses for node `idx`, as 'ip/prefix'.

    Offsets are ``50 + count*idx`` through ``50 + count*idx + count - 1``. With
    `count=1` every node holds the SAME offset in every GPU subnet, so gpu-07
    is `.57` on every rail — deliberate, and asserted by the tests.

    Atomic: returns `count` addresses or raises GpuCapacityError.
    """
    net = _network(subnet)
    if net.prefixlen > MAX_GPU_PREFIX_LEN:
        raise GpuSubnetTooSmallError(
            f"GPU subnet {subnet} is a /{net.prefixlen}, smaller than the "
            f"/{MAX_GPU_PREFIX_LEN} floor. GPU subnets must be a /24 per rail "
            f"or a /20 per aggregate plane; widen the subnet.")
    idx, count = int(idx), int(count)
    if idx < 0:
        raise ValueError(f"node index must be >= 0, got {idx}")
    if count < 1:
        raise ValueError(f"address count must be >= 1, got {count}")

    start = GPU_HOST_START_OFFSET + count * idx
    last = start + count - 1
    broadcast = int(net.num_addresses) - 1
    if last >= broadcast:
        raise GpuCapacityError(
            f"GPU subnet {subnet} cannot seat node index {idx} at {count} "
            f"address(es) each: it needs offset {last}, but the last usable "
            f"offset is {broadcast - 1}. This subnet holds "
            f"{gpu_capacity(subnet, count)} node(s) from offset "
            f"{GPU_HOST_START_OFFSET}. Widen the subnet or reduce the host count.")
    return [f"{net.network_address + start + k}/{net.prefixlen}"
            for k in range(count)]


def find_gpu_collisions(n_gpu_leaves=0, n_cores=0):
    """Fabric claims that intrude into the host range at or above .50.

    Expected to be empty for every fabric this tool builds. A non-empty result
    means the fixed-start assumption has been invalidated by fabric growth and
    `GPU_HOST_START_OFFSET` must be raised — a loud, deliberate decision rather
    than a silent collision.
    """
    return sorted((off, owner)
                  for off, owner in gpu_fabric_offsets(n_gpu_leaves, n_cores).items()
                  if off >= GPU_HOST_START_OFFSET)
