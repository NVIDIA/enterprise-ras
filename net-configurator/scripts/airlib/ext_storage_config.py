# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Shared ext-storage FRR/netplan config builder.

`ext-storage-*` nodes simulate the customer's external storage aggregate
switch in Air — the upstream device the CSL `swp63s0/s1` storage uplinks land
on (ERA-00011 "Uplink to Aggregate Switch - Private Storage Network"). They
run Ubuntu + FRR speaking BGP-unnumbered eBGP back to the CSLs in VRF STORAGE.

This module is the single source of truth for that config so the two callers
can never drift:
  - ``scripts/air-deploy.py`` (``_inject_ext_storage_instructions``) — installs
    it at sim-create time via Node Instructions.
  - ``scripts/fix-ext-storage-frr.py`` (``make fix-ext-storage``) — re-installs
    it on a node whose first-boot ``apt-get install frr`` lost the DNS/NAT race.

The builder functions are pure (topology/args in, strings out) and unit-tested
byte-for-byte, so a change here changes both paths together.
"""
from __future__ import annotations

import ipaddress

# Customer-side storage aggregate ASN (distinct from the cluster's ASNs).
CUST_STORAGE_ASN = 4260000002

# ERA-93 / ADR-0056: the air-mgmt plane is operator-selectable (Air_Only sheet,
# "Air Management Subnet"). These builders used to hardcode 172.20.0.79+ and
# 172.20.0.254, so a deployment that moved the plane got ext-storage nodes
# addressed on a subnet that does not exist — the same class of defect as
# ERA-90, in a path no shipped topology exercised. The literals survive as the
# DEFAULT so untouched deployments render byte-identically.
DEFAULT_AIR_MGMT_SUBNET = "172.20.0.0/24"

# Imported, NOT redefined. This module used to own EXT_STORAGE_FIRST_OCTET
# privately while oob_reserved's air-mgmt reserved set omitted it, so
# excel_parser's switch-eth0 walk handed .79 to a switch and it collided with
# ext-storage-01. The reserved set is the registry; this is a consumer of it.
try:  # normal import (scripts/ on sys.path)
    from oob_reserved import EXT_STORAGE_FIRST_OCTET, EXT_STORAGE_MAX_NODES
except ImportError:  # imported as scripts.airlib.* from a different root
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from oob_reserved import EXT_STORAGE_FIRST_OCTET, EXT_STORAGE_MAX_NODES
AIR_MGMT_SVI_OCTET = 254       # cust-net-edge-01 bridge SVI = the default route


def _air_mgmt_net(air_mgmt_subnet: str | None) -> ipaddress.IPv4Network:
    """Parse the air-mgmt plane, falling back to the historical default.

    A malformed value falls back rather than raising: this runs inside sim
    creation, and the operator's own validate-excel gate is where a bad CIDR
    should be reported.
    """
    try:
        return ipaddress.IPv4Network(str(air_mgmt_subnet).strip(), strict=False)
    except (ValueError, AttributeError):
        return ipaddress.IPv4Network(DEFAULT_AIR_MGMT_SUBNET)


def discover_ext_storage_targets(
    topology_json: dict,
    air_mgmt_subnet: str | None = DEFAULT_AIR_MGMT_SUBNET,
) -> list[dict]:
    """Discover ext-storage nodes and their CSL-facing peer interfaces.

    Returns one dict per ``ext-storage-*`` node (sorted by name):
        {idx, node_name, peer_ifaces, lo_ip, eth0_ip}

    ``peer_ifaces`` are the node's ``eth*`` interfaces (other than ``eth0``)
    that cable to a switch ``swp*`` port — the BGP-unnumbered peers. Selection
    is structural rather than name-based: the storage-facing switch is
    ``core-*``, ``cl-*`` or ``csl-*`` depending on arch and scale, and one node
    may fan out across up to eight of them. ``eth0`` outbound is excluded by
    interface name. A node with no storage-facing interface still appears with
    an empty ``peer_ifaces`` (caller decides to skip/warn).
    """
    content = topology_json.get("content", {})
    nodes = content.get("nodes", {})
    links = content.get("links", [])
    targets = sorted(n for n in nodes if n.startswith("ext-storage-"))

    result: list[dict] = []
    for idx, node_name in enumerate(targets):
        peer_ifaces: list[str] = []
        for link in links:
            if not (isinstance(link[0], dict) and isinstance(link[1], dict)):
                continue
            for i, ep in enumerate(link):
                if (ep.get("node") != node_name
                        or not ep.get("interface", "").startswith("eth")):
                    continue
                peer_iface = link[1 - i].get("interface", "")
                # Structural, NOT name-based: any eth* other than eth0 that
                # lands on a switch port is a storage uplink. The storage-facing
                # switch is called core-*, cl-* or csl-* depending on arch and
                # scale, and keying on one of those names made this silently
                # no-op for 8 of the 14 shipped topologies.
                # eth0 must be excluded by INTERFACE: its cust-net-edge peer
                # port is a swp* too, so "peer is a switch port" alone is not
                # enough to tell outbound from storage.
                if ep.get("interface") != "eth0" and peer_iface.startswith("swp"):
                    peer_ifaces.append(ep["interface"])
        if idx >= EXT_STORAGE_MAX_NODES:
            # Past the band oob_reserved holds open for us, so excel_parser's
            # switch-eth0 walk may already have handed this octet to a switch.
            # Fail here rather than ship a duplicate address: the collision is
            # invisible in Air (ICMP is answered by whichever host wins the
            # ARP) and only shows up as a switch that is inexplicably
            # unreachable over SSH.
            raise ValueError(
                f"{node_name} would take air-mgmt octet "
                f"{EXT_STORAGE_FIRST_OCTET + idx}, past the "
                f"{EXT_STORAGE_MAX_NODES}-node band reserved in "
                f"oob_reserved.AIR_MGMT_RESERVED_OCTETS. Widen "
                f"EXT_STORAGE_MAX_NODES so the switch-eth0 walk skips it too."
            )
        result.append({
            "idx": idx,
            "node_name": node_name,
            "peer_ifaces": sorted(set(peer_ifaces)),
            "lo_ip": f"10.187.5.{idx + 1}",
            "eth0_ip": str(_air_mgmt_net(air_mgmt_subnet).network_address
                           + EXT_STORAGE_FIRST_OCTET + idx),
        })
    return result


def build_frr_conf(node_name: str, lo_ip: str, peer_ifaces: list[str]) -> str:
    """Render ``/etc/frr/frr.conf`` for one ext-storage node.

    BGP-unnumbered eBGP with ``capability extended-nexthop`` (RFC 5549
    IPv4-over-IPv6 next-hop, what NVUE/FRR-on-Cumulus use for unnumbered) and
    ``no bgp ebgp-requires-policy`` (FRR 8.1+ otherwise silently drops the
    redistributed-connected loopback advert).
    """
    lines = [
        "frr version 8.4",
        "frr defaults traditional",
        f"hostname {node_name}",
        "no ipv6 forwarding",
        "!",
        "interface lo",
        f" ip address {lo_ip}/32",
        "!",
        f"router bgp {CUST_STORAGE_ASN}",
        f" bgp router-id {lo_ip}",
        " no bgp default ipv4-unicast",
        " no bgp ebgp-requires-policy",
        " neighbor STORAGE peer-group",
        " neighbor STORAGE remote-as external",
        " neighbor STORAGE capability extended-nexthop",
    ]
    for iface in peer_ifaces:
        lines.append(f" neighbor {iface} interface peer-group STORAGE")
    lines += [
        " !",
        " address-family ipv4 unicast",
        f"  network {lo_ip}/32",
        "  redistribute connected",
        "  neighbor STORAGE activate",
        " exit-address-family",
        "!",
        "line vty",
        "!",
    ]
    return "\n".join(lines) + "\n"


def build_daemons() -> str:
    """Render ``/etc/frr/daemons`` — bgpd only."""
    lines = [
        "bgpd=yes",
        "ospfd=no", "ospf6d=no", "ripd=no", "ripngd=no", "isisd=no",
        "pimd=no", "ldpd=no", "nhrpd=no", "eigrpd=no", "babeld=no",
        "sharpd=no", "pbrd=no", "bfdd=no", "fabricd=no", "vrrpd=no",
        "vtysh_enable=yes",
        'zebra_options="  -A 127.0.0.1 -s 90000000"',
        'bgpd_options="   -A 127.0.0.1"',
    ]
    return "\n".join(lines) + "\n"


def build_eth0_netplan(
    eth0_ip: str,
    air_mgmt_subnet: str | None = DEFAULT_AIR_MGMT_SUBNET,
) -> str:
    """Render the eth0 static-IP netplan (cust-net-edge-01 air-mgmt bridge leg).

    ``.79/.80`` sit below external-dhcp's ``.100-.200`` DHCP pool on this
    subnet, so no lease collision; default route via the cust-net-edge-01 SVI
    (offset ``.254``) gives apt/DNS reachability.

    ERA-93: prefix length and gateway are derived from ``air_mgmt_subnet``. They
    were literal ``/24`` and ``172.20.0.254``, so moving the plane produced a
    netplan whose default route pointed at an address on a different network.
    """
    _net = _air_mgmt_net(air_mgmt_subnet)
    _gateway = _net.network_address + AIR_MGMT_SVI_OCTET
    return (
        "network:\n"
        "  version: 2\n"
        "  renderer: networkd\n"
        "  ethernets:\n"
        "    eth0:\n"
        f"      addresses: [{eth0_ip}/{_net.prefixlen}]\n"
        "      routes:\n"
        "        - to: 0.0.0.0/0\n"
        f"          via: {_gateway}\n"
        "      nameservers:\n"
        "        addresses: [8.8.8.8, 8.8.4.4]\n"
        "      dhcp4: false\n"
        "      dhcp6: false\n"
    )
