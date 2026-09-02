# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Data-plane host IPs must never collide with the switch SVIs on their VLAN.

`_dataplane_host_ips()` packs hosts from the bottom of a non-/24 VLAN subnet.
It used to reserve exactly ONE address -- the VRR/anycast gateway at
`network + 1` -- but `_svi_switch_ip()` then hands `network + 2`, `network + 3`,
... to each SVI-bearing switch. So on any non-/24 data VLAN the FIRST
support/storage node was allocated the same address as core-01's SVI.

Observed live on a brownfield Support VLAN `10.78.220.32/27`: both core SVIs
took .34/.35 and k8s-01 was given .34/.35 as well, so the gateway .33 never
ARPed and the entire support data plane was dead -- while every shipped /24
arch was unaffected, because /24 uses the legacy .101/.201 offsets that sit
far above the SVIs.

/24 subnets must stay byte-identical; this is a non-/24-only fix.
"""
import ipaddress
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import excel_parser as ep  # noqa: E402


def _cores(n=2):
    return [{"status": "Active", "category": "core"} for _ in range(n)]


# --- the live failure -----------------------------------------------------

def test_support_ips_do_not_collide_with_core_svis_on_a_slash27():
    """The exact production case: Support VLAN 10.78.220.32/27, two cores."""
    subnet, gw = "10.78.220.32/27", "10.78.220.33"
    svis = {ep._svi_switch_ip(subnet, gw, i) for i in (1, 2)}
    assert svis == {"10.78.220.34", "10.78.220.35"}

    reserved = ep._svi_reserved_offsets(_cores(2))
    allocated = set()
    for idx in range(3):                       # three support nodes
        ips = ep._dataplane_host_ips(subnet, idx, 2, 101, 2, reserved=reserved)
        assert ips, f"node {idx} got no IPs"
        allocated.update(i.split("/")[0] for i in ips)

    assert not (allocated & svis), f"server IPs collide with core SVIs: {allocated & svis}"
    assert gw not in allocated, "server was handed the anycast gateway"


def test_first_support_node_starts_above_every_svi():
    reserved = ep._svi_reserved_offsets(_cores(2))
    first = ep._dataplane_host_ips("10.78.220.32/27", 0, 2, 101, 2, reserved=reserved)
    assert first[0] == "10.78.220.36/27"   # .33 gw, .34/.35 SVIs, servers from .36


@pytest.mark.parametrize("prefix", [25, 26, 27, 28])
def test_no_collision_across_small_prefixes(prefix):
    net = ipaddress.ip_network(f"10.0.0.0/{prefix}")
    subnet = str(net)
    gw = str(net.network_address + 1)
    svis = {ep._svi_switch_ip(subnet, gw, i) for i in (1, 2)}
    reserved = ep._svi_reserved_offsets(_cores(2))
    ips = ep._dataplane_host_ips(subnet, 0, 2, 101, 2, reserved=reserved)
    if ips:  # /28 may legitimately not fit
        assert not ({i.split("/")[0] for i in ips} & svis)


# --- reservation sizing ---------------------------------------------------

def test_reserved_scales_with_switch_count():
    """Gateway + one SVI per SVI-bearing switch."""
    assert ep._svi_reserved_offsets(_cores(2)) == 4    # .0 net, .1 gw, .2/.3 SVI -> start .4
    assert ep._svi_reserved_offsets(_cores(4)) == 6


def test_reserved_falls_back_when_no_cores_parsed():
    """Never reserve less than the two-core default -- under-reserving is the bug."""
    assert ep._svi_reserved_offsets([]) == 4
    assert ep._svi_reserved_offsets(None) == 4


def test_inactive_switches_do_not_consume_reservations():
    nodes = _cores(2) + [{"status": "Inactive", "category": "core"}]
    assert ep._svi_reserved_offsets(nodes) == 4


# --- /24 must not move ----------------------------------------------------

def test_slash24_allocation_is_unchanged():
    """Shipped archs use /24 and must stay byte-identical."""
    reserved = ep._svi_reserved_offsets(_cores(2))
    for idx in range(3):
        legacy = ep._dataplane_host_ips("172.16.179.0/24", idx, 2, 101, 2, reserved=2)
        now = ep._dataplane_host_ips("172.16.179.0/24", idx, 2, 101, 2, reserved=reserved)
        assert legacy == now, "/24 allocation changed"
    assert ep._dataplane_host_ips("172.16.178.0/24", 0, 1, 201, 1,
                                  reserved=reserved)[0] == "172.16.178.201/24"


def test_default_reserved_preserves_legacy_two():
    """Callers that don't pass `reserved` keep the historical packing."""
    assert ep._dataplane_host_ips("10.0.0.0/27", 0, 2, 101, 2)[0] == "10.0.0.2/27"
