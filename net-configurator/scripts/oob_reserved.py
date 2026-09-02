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
EXTERNAL_CONN_OCTET = 79   # external-conn (OOB plane: 192.168.200.79)
ZTP_SERVER_OCTET = 100     # ztp_server
DHCP_OOB_OCTET = 252       # dhcp-oob
# ext-storage-NN eth0 on the AIR-MGMT plane (172.20.0.79, .80, ...), assigned
# by scripts/airlib/ext_storage_config.py -- which imports these rather than
# defining its own copy. It previously owned EXT_STORAGE_FIRST_OCTET privately
# while this module's air-mgmt reserved set omitted it, so excel_parser's
# switch-eth0 walk handed .79 to a switch: at SU32 gs-plane2-08 and
# ext-storage-01 both answered for 172.20.0.79. ICMP still worked (whichever
# host won the ARP replied), so the switch looked healthy while every SSH to
# it landed on the wrong node -- validate-config reported it simply
# "unreachable".
EXT_STORAGE_FIRST_OCTET = 79
# Width of the octet band held open for ext-storage. ADR-0050 ships a PAIR,
# but the builder is not pair-only (its tests exercise ext-storage-03), so the
# band carries headroom: reserving an octet nothing uses is free, while
# under-reserving hands it to a switch and produces a silent duplicate.
EXT_STORAGE_MAX_NODES = 4

AIR_MGMT_SVI_OCTET = 254   # cust-net-edge-01 bridge SVI on the air-mgmt plane
                           # (the on-link default gateway for the air-mgmt
                           # DHCP scope). Named so air-deploy.py stops
                           # hardcoding it and follows air_mgmt_subnet.

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


# Octets that are taken on the air-mgmt /24 (172.20.0.0/24), where
# excel_parser walks switch eth0 IPs. ztp_server (.100) and dhcp-oob (.252)
# are genuinely OOB-only and stay unreserved here.
#
# .79+ is NOT one of those: EXTERNAL_CONN_OCTET 79 is the OOB plane's
# external-conn, but the SAME octet is independently the base for ext-storage
# eth0 on THIS plane. The two are unrelated addresses that happen to share a
# number, and the old comment here claimed ".79 external-conn does not live on
# that plane" -- true of external-conn, false of the plane. The walk therefore
# handed .79 to a switch and it collided with ext-storage-01.
AIR_MGMT_RESERVED_OCTETS = {0, GATEWAY_OCTET, EXTERNAL_DHCP_OCTET, UTILITY_OCTET,
                            AIR_MGMT_SVI_OCTET, 255} | {
    EXT_STORAGE_FIRST_OCTET + i for i in range(EXT_STORAGE_MAX_NODES)
}

# Same set, with the owner air-deploy.py provisions on each octet. Used to name
# the squatter when an operator pins a switch eth0 onto infrastructure, instead
# of failing with a bare octet number the operator has no way to interpret.
AIR_MGMT_RESERVED_OWNERS = {
    0: "network address",
    # NOT the gateway on this plane -- the air-mgmt default gateway is the
    # cust-net-edge-01 bridge SVI at AIR_MGMT_SVI_OCTET (.254), below.
    # GATEWAY_OCTET is the OOB plane's VRR (192.168.200.1); .1 is reserved
    # here only as a hole-punch so a switch eth0 never lands on an octet an
    # L2->L3 flip would need. Naming it "air-mgmt gateway" told an operator
    # who pinned a switch onto .1 that they had collided with a gateway that
    # does not exist on this subnet.
    GATEWAY_OCTET: "reserved (no owner on air-mgmt; gateway is the .254 SVI)",
    EXTERNAL_DHCP_OCTET: "external-dhcp (dnsmasq listener)",
    UTILITY_OCTET: "utility (L3-OOB jump)",
    **{EXT_STORAGE_FIRST_OCTET + i: f"ext-storage-{i + 1:02d} (eth0 on air-mgmt)"
       for i in range(EXT_STORAGE_MAX_NODES)},
    AIR_MGMT_SVI_OCTET: "cust-net-edge-01 bridge SVI (air-mgmt default gateway)",
    255: "broadcast address",
}

# Default air-mgmt subnet (Settings "Air Management Subnet"; overridable). The
# WHOLE /24 is off-limits to Nodes-tab hosts: switch eth0 IPs are auto-assigned
# across it, and the L3 trio + cust-net-edge SVI occupy fixed octets here:
#   .77 external-dhcp (dnsmasq listener)   .78 utility (jump foot on the bridge)
#   .254 cust-net-edge bridge SVI (gateway)
# A Nodes-tab host that lands anywhere in this subnet silently collides with a
# switch eth0 the operator can't see — same failure class as the OOB-plane bug.
DEFAULT_AIR_MGMT_SUBNET = "172.20.0.0/24"


def _networks(subnets):
    """Parse ``subnets`` into IPv4Network objects, skipping malformed entries.

    ``None`` means "the historical default plane" — a workbook that declares
    nothing still gets 192.168.200.0/24 checked. An explicit list that parses to
    nothing yields nothing: silently substituting the default there is how a
    gate starts protecting a subnet the deployment does not use.
    """
    if subnets is None:
        subnets = [OOB_SUBNET]
    nets = []
    for entry in subnets:
        text = str(entry or "").strip()
        if not text:
            continue
        try:
            nets.append(ipaddress.IPv4Network(text, strict=False))
        except ValueError:
            continue  # malformed VLAN subnets are reported by their own gate
    return nets


def _parse_host(ip_str):
    """``a.b.c.d`` or ``a.b.c.d/NN`` -> IPv4Address, or None if unusable."""
    if not ip_str:
        return None
    try:
        return ipaddress.IPv4Address(str(ip_str).strip().split('/')[0])
    except ValueError:
        return None


def oob_octet(ip_str, subnets=None):
    """Return ``ip_str``'s offset within whichever declared OOB subnet holds it.

    ERA-93: this used to hard-code 192.168.200.0/24 and return ``None`` for
    everything else, which made every caller blind on a brownfield workbook.
    ``subnets`` is the list of OOB VLAN subnets the workbook declares; omit it
    for the historical default plane.

    The value is an OFFSET FROM THE NETWORK ADDRESS, not the literal last
    octet, because that is what ``air-deploy.py`` assigns from
    (``oob_ip(octet) == network_address + octet``). On 192.168.200.0/24 the two
    are identical, which is why the distinction went unnoticed; on
    10.78.220.128/25 the utility jump (octet 78) is ``.206``, and a gate keyed
    on the last octet would reserve an address nobody uses while leaving the
    real one open.

    Anything malformed, empty, or outside every declared subnet returns
    ``None``.
    """
    addr = _parse_host(ip_str)
    if addr is None:
        return None
    for net in _networks(subnets):
        if addr in net:
            return int(addr) - int(net.network_address)
    return None


def find_oob_collisions(node_claims, reserved_octets=None, subnets=None):
    """Detect mgmt-IP collisions on the OOB management plane(s).

    Args:
        node_claims: iterable of ``(label, ip_str)`` pairs — typically one per
            Nodes-tab host (``label`` is a human row/function descriptor).
        reserved_octets: octet->owner map to seed as implicit claimants;
            defaults to the L3 superset (``OOB_RESERVED_OCTETS``). Callers that
            know the OOB mode should pass ``oob_reserved_for_mode(mode)`` so an
            L2 deployment is not flagged for legitimately using an L3-only octet
            (.77/.78/.79). Each octet is seeded at ``network_address + octet``
            of every declared subnet, matching ``air-deploy.py``, and skipped
            where that address falls outside the network (a /25 OOB VLAN simply
            has no offset 252, so dhcp-oob is not reserved there).
        subnets: OOB VLAN subnets the workbook declares. ``None`` keeps the
            historical 192.168.200.0/24 default.

    Returns:
        A list of ``(address, owners)`` tuples, sorted by address, for every
        address claimed by more than one owner. Reserved addresses are seeded as
        implicit owners (e.g. ``"reserved: utility (L3-OOB jump)"``), so a
        single node landing on one is reported as a 2-owner collision.
        Addresses claimed by exactly one owner are not returned.

        The key is the ADDRESS, not an octet: with more than one OOB VLAN in
        play an octet no longer identifies an address, and the error message has
        to name the address the operator must actually change.

    Duplicate detection deliberately considers EVERY parseable claim, in or out
    of the declared subnets. Two Nodes-tab hosts sharing an address is wrong
    wherever it happens, and making that finding conditional on a subnet
    literal is precisely what let ERA-92 through.
    """
    if reserved_octets is None:
        reserved_octets = OOB_RESERVED_OCTETS

    by_addr = {}
    for net in _networks(subnets):
        for octet, owner in (reserved_octets or {}).items():
            addr = net.network_address + int(octet)
            if addr in net:
                by_addr.setdefault(str(addr), []).append(f"reserved: {owner}")

    for label, ip_str in node_claims:
        addr = _parse_host(ip_str)
        if addr is None:
            continue
        by_addr.setdefault(str(addr), []).append(label)

    collisions = []
    for addr in sorted(by_addr, key=lambda a: int(ipaddress.IPv4Address(a))):
        owners = by_addr[addr]
        # A reserved address alone (only its seeded owner) is fine; flag only
        # when a Nodes-tab claim joins it, or two real nodes collide.
        node_owners = [o for o in owners if not o.startswith("reserved: ")]
        if len(owners) > 1 and node_owners:
            collisions.append((addr, owners))
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
