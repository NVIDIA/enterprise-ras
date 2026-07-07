#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Canonical reserved-IP registry for the flat OOB management subnet.

ERA deploys put every node's eth0 management IP on a single flat OOB /24
(``192.168.200.0/24``, matching the production EVPN-stretched VLAN 200). A
handful of octets on that subnet are claimed by fixed Air-infrastructure
nodes that the topology generator auto-injects (gateway, external-dhcp, the
L3-OOB jump ``utility``, ``external-conn``, ``ztp_server``, ``dhcp-oob``).

If a Nodes-tab host is ever handed one of those octets — or two hosts get the
same octet — the duplicate triggers an ARP/DAD war on VLAN 200 and ~60% packet
loss to the colliding host. This was root-caused 2026-06-24 on
``2-8-9-400/maxscale`` where server ``su-09-node-03`` and the ``utility`` jump
both landed on ``192.168.200.78`` (the sequential mgmt-IP walk reached the
``.77-.79`` infra trio only at maxscale).

This module is the SINGLE source of truth for those reserved octets so the
three places that need them cannot drift apart:

  - ``scripts/generate_arch_excel.py`` — skips them when walking Nodes-tab
    mgmt IPs (``next_mgmt_ip``).
  - ``scripts/excel_parser.py`` — skips the air-mgmt subset when walking
    switch eth0 IPs on the 172.20.0.0/24 plane.
  - ``scripts/validate_excel.py`` — a hard pre-deploy gate that fails loudly
    on any duplicate/collision.

``scripts/air-deploy.py`` is the *owner* that actually assigns these IPs to
the L3 trio; its octets are exported here as named constants so its netplan
literals stay tied to this registry.
"""
import ipaddress

# The flat OOB management subnet every node's eth0 lands on.
OOB_SUBNET = "192.168.200.0/24"

# L3-OOB trio + service octets, assigned by scripts/air-deploy.py. Named so the
# air-deploy netplan and the reserved set below share one definition.
GATEWAY_OCTET = 1          # oob VRR / oob-server-01 eth1 (192.168.200.1)
EXTERNAL_DHCP_OCTET = 77   # external-dhcp:eth1
UTILITY_OCTET = 78         # utility (L3-OOB jump): eth1 on .200, eth2 on air-mgmt
EXTERNAL_CONN_OCTET = 79   # external-conn
ZTP_SERVER_OCTET = 100     # ztp_server
DHCP_OOB_OCTET = 252       # dhcp-oob

# octet -> human owner label, on the flat OOB /24 (192.168.200.0/24), for an
# L3-OOB deployment. The EXIT-VRF trio (external-dhcp .77 / utility .78 /
# external-conn .79) + ztp_server .100 exist ONLY in L3 mode. This is also the
# defensive superset the generator's mgmt-IP walk skips in BOTH modes (so a
# later L2->L3 flip never renumbers nodes onto an octet L3 needs).
OOB_RESERVED_OCTETS = {
    0: "network address",
    GATEWAY_OCTET: "gateway / OOB VRR",
    EXTERNAL_DHCP_OCTET: "external-dhcp",
    UTILITY_OCTET: "utility (L3-OOB jump)",
    EXTERNAL_CONN_OCTET: "external-conn",
    ZTP_SERVER_OCTET: "ztp_server",
    DHCP_OOB_OCTET: "dhcp-oob",
    254: "reserved",
    255: "broadcast address",
}

# Reserved octets for an L2-OOB deployment (the system default). The L3 EXIT-VRF
# trio (.77/.78/.79) and ztp_server (.100) do NOT exist here — the L2 OOB plane
# carries only the gateway/oob-server-01 (.1) and dhcp-oob (.252) as fixed,
# non-Nodes-tab infrastructure. Used by the validate-excel gate so it does not
# false-flag a Nodes-tab host that legitimately uses .77/.78/.79 in L2 mode.
OOB_RESERVED_OCTETS_L2 = {
    0: "network address",
    GATEWAY_OCTET: "gateway / oob-server-01",
    DHCP_OOB_OCTET: "dhcp-oob",
    254: "reserved",
    255: "broadcast address",
}


def oob_reserved_for_mode(oob_uplink_mode):
    """Return the flat-OOB reserved-octet owner map for the given OOB mode.

    'l3' -> the full L3 set (EXIT-VRF trio + ztp_server). Anything else,
    including None/blank/unknown, -> the L2 set (matches the system default in
    excel_parser._normalize_oob_uplink_mode).
    """
    if str(oob_uplink_mode or "").strip().lower() == "l3":
        return OOB_RESERVED_OCTETS
    return OOB_RESERVED_OCTETS_L2


# Subset of the reserved octets that ALSO collide on the air-mgmt /24
# (172.20.0.0/24), where excel_parser walks switch eth0 IPs. The OOB-only
# service IPs (.79 external-conn, .100 ztp_server, .252 dhcp-oob) do not live
# on that plane, so the switch-eth0 walk reserves only the L3-trio + endpoints.
# Kept as an explicit literal (NOT derived) so the switch-eth0 walk stays
# byte-identical to historical output.
AIR_MGMT_RESERVED_OCTETS = {0, GATEWAY_OCTET, EXTERNAL_DHCP_OCTET, UTILITY_OCTET, 254, 255}

# Default air-mgmt subnet (Settings "Air Management Subnet"; overridable). The
# WHOLE /24 is off-limits to Nodes-tab hosts: switch eth0 IPs are auto-assigned
# across it, and the L3 trio + cust-net-edge SVI occupy fixed octets here:
#   .77 external-dhcp (dnsmasq listener)   .78 utility (jump foot on the bridge)
#   .254 cust-net-edge bridge SVI (gateway)
# A Nodes-tab host that lands anywhere in this subnet silently collides with a
# switch eth0 the operator can't see — same failure class as the OOB-plane bug.
DEFAULT_AIR_MGMT_SUBNET = "172.20.0.0/24"


def oob_octet(ip_str):
    """Return the final octet of ``ip_str`` if it falls in OOB_SUBNET, else None.

    Accepts plain ``a.b.c.d`` or ``a.b.c.d/NN`` strings. Anything malformed,
    empty, or outside 192.168.200.0/24 returns ``None`` (the caller treats
    out-of-subnet IPs as "not our concern").
    """
    if not ip_str:
        return None
    host = str(ip_str).strip().split('/')[0]
    try:
        addr = ipaddress.IPv4Address(host)
    except ValueError:
        return None
    if addr not in ipaddress.IPv4Network(OOB_SUBNET):
        return None
    return int(host.split('.')[-1])


def find_oob_collisions(node_claims, reserved_octets=None):
    """Detect mgmt-IP collisions on the flat OOB /24.

    Args:
        node_claims: iterable of ``(label, ip_str)`` pairs — typically one per
            Nodes-tab host (``label`` is a human row/function descriptor).
        reserved_octets: octet->owner map to seed as implicit claimants;
            defaults to the L3 superset (``OOB_RESERVED_OCTETS``). Callers that
            know the OOB mode should pass ``oob_reserved_for_mode(mode)`` so an
            L2 deployment is not flagged for legitimately using an L3-only octet
            (.77/.78/.79).

    Returns:
        A list of ``(octet, owners)`` tuples, sorted by octet, for every
        ``.200.x`` address claimed by more than one owner. Reserved octets are
        seeded as implicit owners (e.g. ``"reserved: utility (L3-OOB jump)"``),
        so a single node landing on a reserved octet is reported as a 2-owner
        collision. Octets claimed by exactly one owner are not returned.
    """
    if reserved_octets is None:
        reserved_octets = OOB_RESERVED_OCTETS
    by_octet = {}
    for octet, owner in reserved_octets.items():
        by_octet.setdefault(octet, []).append(f"reserved: {owner}")

    for label, ip_str in node_claims:
        octet = oob_octet(ip_str)
        if octet is None:
            continue
        by_octet.setdefault(octet, []).append(label)

    collisions = []
    for octet in sorted(by_octet):
        owners = by_octet[octet]
        # A reserved octet alone (only its seeded owner) is fine; flag only
        # when a Nodes-tab claim joins it, or two real nodes collide.
        node_owners = [o for o in owners if not o.startswith("reserved: ")]
        if len(owners) > 1 and node_owners:
            collisions.append((octet, owners))
    return collisions


def air_mgmt_intruders(node_claims, air_mgmt_subnet=DEFAULT_AIR_MGMT_SUBNET):
    """Detect Nodes-tab hosts that land inside the air-mgmt subnet.

    The air-mgmt /24 is reserved end-to-end for auto-assigned switch eth0 IPs
    and the fixed L3-trio / SVI octets — Nodes-tab hosts belong on the OOB
    plane, never here. Any node IP inside this subnet is a silent collision
    waiting to happen.

    Args:
        node_claims: iterable of ``(label, ip_str)`` pairs.
        air_mgmt_subnet: the Settings "Air Management Subnet" CIDR.

    Returns:
        A list of ``(label, ip_str)`` for every claim inside the subnet,
        in input order. Empty/malformed CIDR returns ``[]`` (nothing to gate).
    """
    if not air_mgmt_subnet:
        return []
    try:
        net = ipaddress.IPv4Network(str(air_mgmt_subnet).strip(), strict=False)
    except ValueError:
        return []

    intruders = []
    for label, ip_str in node_claims:
        if not ip_str:
            continue
        host = str(ip_str).strip().split('/')[0]
        try:
            addr = ipaddress.IPv4Address(host)
        except ValueError:
            continue
        if addr in net:
            intruders.append((label, ip_str))
    return intruders
