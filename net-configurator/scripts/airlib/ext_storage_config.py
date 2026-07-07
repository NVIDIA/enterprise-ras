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

# Customer-side storage aggregate ASN (distinct from the cluster's ASNs).
CUST_STORAGE_ASN = 4260000002


def discover_ext_storage_targets(topology_json: dict) -> list[dict]:
    """Discover ext-storage nodes and their CSL-facing peer interfaces.

    Returns one dict per ``ext-storage-*`` node (sorted by name):
        {idx, node_name, peer_ifaces, lo_ip, eth0_ip}

    ``peer_ifaces`` are the node's ``eth*`` interfaces that cable to a
    ``csl-* swp*`` port (the BGP-unnumbered peers); ``eth0`` outbound and any
    other Wire Map cabling are excluded. A node with no CSL-facing interface
    still appears with an empty ``peer_ifaces`` (caller decides to skip/warn).
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
                peer_node = link[1 - i].get("node", "")
                peer_iface = link[1 - i].get("interface", "")
                # Only peer toward CSLs on swp* (swp63s0/s1). Skip eth0
                # outbound and any other Wire Map cabling.
                if peer_node.startswith("csl-") and peer_iface.startswith("swp"):
                    peer_ifaces.append(ep["interface"])
        result.append({
            "idx": idx,
            "node_name": node_name,
            "peer_ifaces": sorted(set(peer_ifaces)),
            "lo_ip": f"10.187.5.{idx + 1}",
            "eth0_ip": f"172.20.0.{79 + idx}",
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


def build_eth0_netplan(eth0_ip: str) -> str:
    """Render the eth0 static-IP netplan (cust-net-edge-01 air-mgmt bridge leg).

    ``.79/.80`` sit below external-dhcp's ``.100-.200`` DHCP pool on this
    subnet, so no lease collision; default route via the cust-net-edge-01 SVI
    ``.254`` gives apt/DNS reachability.
    """
    return (
        "network:\n"
        "  version: 2\n"
        "  renderer: networkd\n"
        "  ethernets:\n"
        "    eth0:\n"
        f"      addresses: [{eth0_ip}/24]\n"
        "      routes:\n"
        "        - to: 0.0.0.0/0\n"
        "          via: 172.20.0.254\n"
        "      nameservers:\n"
        "        addresses: [8.8.8.8, 8.8.4.4]\n"
        "      dhcp4: false\n"
        "      dhcp6: false\n"
    )
