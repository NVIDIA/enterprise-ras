#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Create an Air simulation from a generated topology, start it, and configure SSH access.

Imports the topology JSON into NGC Air, starts the simulation, creates SSH
services on the jump hosts, and updates host_vars with connection details.

ERA handles ZTP and server provisioning through its own infrastructure
(dnsmasq/nginx on dhcp-oob).  The only pre-boot configuration injected
via the Air API is Node Instructions for air-oob-switch (flat L2 bridge).

Usage:
    python scripts/air-deploy.py --arch 2-8-5-200
    python scripts/air-deploy.py --arch 2-8-5-200 --site new-site
    python scripts/air-deploy.py --arch 2-8-5-200 --title "My Custom Lab"

Or via Makefile:
    make air-deploy ARCH=2-8-5-200
"""

import argparse
import base64
import datetime as _dt
import ipaddress
import json
import shlex
import shutil
import ssl
import sys
import time
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import httpx
import yaml
from rich.console import Console

from concurrent.futures import ThreadPoolExecutor

from airlib.api import (
    create_node_instruction,
    create_service_for_node,
    create_ssh_service_for_node,
    delete_simulation,
    get_resource_budget,
    import_topology,
    list_simulations,
    poll_until_loaded,
    prefetch_node_ids,
    start_simulation,
    wait_for_inactive,
)
from airlib.auth import authenticate
from airlib.env import load_air_config, require_config
from airlib.errors import AirAPIError, AirError
from airlib.models import SimState
from airlib.ssh import build_ssh_args, check_port_open, get_key_fingerprint
from airlib.ext_storage_config import (
    CUST_STORAGE_ASN,
    build_daemons,
    build_eth0_netplan,
    build_frr_conf,
    discover_ext_storage_targets,
)
from oob_reserved import (
    AIR_MGMT_SVI_OCTET,
    DEFAULT_AIR_MGMT_SUBNET,
    EXTERNAL_DHCP_OCTET,
    OOB_SUBNET,
    UTILITY_OCTET,
)

console = Console()

# ---------------------------------------------------------------------------
# Air-mgmt plane addressing
#
# `air_mgmt_subnet` is operator-selectable (Air_Only sheet, "Air Management
# Subnet") and already flows into the generated inventory: excel_parser walks
# switch eth0 IPs across it and writes ztp_interfaces / ztp_allow_subnets from
# it. But every address on that plane was a bare `172.20.0.x` literal in this
# file, which never read the setting. Changing the subnet therefore produced a
# SPLIT BRAIN — inventory + ZTP config followed the new subnet while the nodes
# this script provisions stayed on 172.20.0.x, so DHCP was served on one plane
# and listened for on another and no switch ever got an address.
#
# Resolved ONCE from the generated inventory in main() and read through these
# helpers, so the generator and the provisioner cannot drift apart again.
# Defaults to 172.20.0.0/24, which keeps every existing deployment
# byte-identical.
# ---------------------------------------------------------------------------
_air_mgmt_net = ipaddress.IPv4Network(DEFAULT_AIR_MGMT_SUBNET)


def set_air_mgmt_subnet(subnet: str | None) -> None:
    """Pin the air-mgmt plane for this run. Blank/malformed keeps the default."""
    global _air_mgmt_net
    if not subnet or not str(subnet).strip():
        return
    try:
        _air_mgmt_net = ipaddress.IPv4Network(str(subnet).strip(), strict=False)
    except ValueError:
        console.print(
            f"[yellow]Warning:[/] invalid air_mgmt_subnet {subnet!r} — "
            f"keeping {air_mgmt_network()}"
        )


def air_mgmt_network() -> str:
    """The air-mgmt plane in CIDR form, e.g. '172.20.0.0/24'."""
    return str(_air_mgmt_net)


def air_mgmt_ip(octet: int) -> str:
    """Bare host address for `octet` on the air-mgmt plane."""
    return str(_air_mgmt_net.network_address + int(octet))


def air_mgmt_cidr(octet: int) -> str:
    """Host address + prefix for `octet`, e.g. '172.20.0.254/24'."""
    return f"{air_mgmt_ip(octet)}/{_air_mgmt_net.prefixlen}"


# ---------------------------------------------------------------------------
# OOB plane addressing
#
# ADR-0028 made the OOB VLAN Excel-sourced, and the FABRIC half landed: switch
# SVIs, the anycast gateway and the VLAN id all follow the workbook. The Air
# INFRASTRUCTURE half never did — `utility`'s foot on the OOB bridge, the PBR
# next-hop, external-conn's return routes and the server eth0 netplan all kept
# a literal `192.168.200.x` and a literal `/24`.
#
# Consequences on a workbook whose OOB VLAN is not 192.168.200.0/24 (observed on
# a brownfield 10.78.220.128/25): `utility` sits on an island with no route to
# the OOB VLAN, so validate-servers reports every server UNREACHABLE even though
# the servers are up and correctly addressed; and each server's eth0 gets a /24
# instead of the real /25 plus a default route via an address that does not
# exist on its segment.
#
# `common.oob_network` / `common.oob_gateway` are already in the generated
# inventory — these were simply never read. Defaults keep 192.168.200.0/24 + .1,
# so every shipped arch stays byte-identical.
# ---------------------------------------------------------------------------
_oob_net = ipaddress.IPv4Network(OOB_SUBNET)
_oob_gw = f"{_oob_net.network_address + 1}"


def set_oob_plane(network: str | None, gateway: str | None) -> None:
    """Pin the OOB plane for this run from `common`. Blank/malformed keeps the default."""
    global _oob_net, _oob_gw
    if network and str(network).strip():
        try:
            _oob_net = ipaddress.IPv4Network(str(network).strip(), strict=False)
            _oob_gw = f"{_oob_net.network_address + 1}"
        except ValueError:
            console.print(
                f"[yellow]Warning:[/] invalid oob_network {network!r} — keeping {_oob_net}")
    if gateway and str(gateway).strip():
        _oob_gw = str(gateway).strip().split("/")[0]


def oob_network() -> str:
    """The OOB plane in CIDR form, e.g. '192.168.200.0/24'."""
    return str(_oob_net)


def oob_prefixlen() -> int:
    return _oob_net.prefixlen


def oob_gateway() -> str:
    """Anycast/VRR gateway on the OOB plane (Excel `gateway`, else network+1)."""
    return _oob_gw


def oob_ip(octet: int) -> str:
    return str(_oob_net.network_address + int(octet))


def oob_cidr(octet: int) -> str:
    return f"{oob_ip(octet)}/{_oob_net.prefixlen}"


def cleanup_failed_sim(client, base_url, token, sim_id, arch):
    """Best-effort removal of a sim that was created but failed to start (#26).

    A created-but-unstarted sim is left in STORED state; repeated failed deploys
    accumulate orphans that must be cleared in the Air UI. Try to delete it. If
    delete also fails (e.g. the same 403 that blocked start — an API-key
    permission issue), tell the operator how to remove it manually. Returns True
    if the sim was removed, False otherwise. Never raises.
    """
    console.print("  Attempting to clean up the created simulation...")
    try:
        delete_simulation(client, base_url, token, sim_id)
        console.print(f"  ✓ Removed orphaned simulation {sim_id}")
        return True
    except AirError as del_exc:
        console.print(f"  ⚠️  Could not auto-remove it ({del_exc}).")
        console.print(f"     Remove manually: make air-destroy ARCH={arch}")
        console.print(f"     (or delete sim {sim_id} in the Air UI if that 403s too)")
        return False


# ---------------------------------------------------------------------------
# Local reports archive (fresh-sim boundary)
# ---------------------------------------------------------------------------


def _archive_stale_local_reports(project_root: Path, arch: str, site: str) -> None:
    reports_dir = project_root / "output" / arch / site / "reports"
    if not reports_dir.is_dir():
        return

    top_level = [p for p in reports_dir.glob("*.txt") if p.is_file()]
    raw_dir = reports_dir / "raw"
    raw_files = [p for p in raw_dir.iterdir() if p.is_file()] if raw_dir.is_dir() else []

    if not top_level and not raw_files:
        return

    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = reports_dir / "report-archive" / ts
    dest.mkdir(parents=True, exist_ok=True)

    for f in top_level:
        shutil.move(str(f), str(dest / f.name))
    if raw_files:
        (dest / "raw").mkdir(exist_ok=True)
        for f in raw_files:
            shutil.move(str(f), str(dest / "raw" / f.name))

    rel = dest.relative_to(project_root)
    console.print(
        f"  Archived stale local reports to [cyan]{rel}/[/] "
        "(fresh sim → clean upload state)"
    )


# ---------------------------------------------------------------------------
# Host vars update (replaces manual air-connect)
# ---------------------------------------------------------------------------

def update_host_vars(
    inv_dir: Path,
    node_name: str,
    host: str,
    port: int | str,
) -> None:
    """Update a node's host_vars with Air SSH service details."""
    path = inv_dir / "host_vars" / f"{node_name}.yml"
    data = {}
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}

    data["ansible_host"] = host
    data["ansible_port"] = int(port)
    data["ansible_user"] = "ubuntu"
    data.setdefault("hostname", node_name)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("---\n")
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Mode-aware infra-node resolver
# ---------------------------------------------------------------------------

def _resolve_infra_nodes(topology_json: dict) -> dict:
    """Return role → node-name mapping based on `oob_uplink_mode`.

    The L2 default uses the air-oob-switch flat-bridge trio (dhcp-oob,
    oob-server-01, air-oob-switch). The L3 mode uses the three Ubuntu
    nodes (external-conn, external-dhcp, utility) injected by
    `_inject_l3_oob_nodes` in the topology generator.

    All air-deploy.py code that targets infra nodes by name should go
    through this helper so the same logic works in both modes.
    """
    mode = topology_json.get("_oob_uplink_mode", "l2")
    if mode == "l3":
        return {
            "mode": "l3",
            # SSH jump host (Ansible target for everything else)
            "jump_host": "utility",
            # NAT egress (iptables MASQUERADE on eth0)
            "nat_host": "external-conn",
            # DHCP server for switch ZTP
            "dhcp_server": "external-dhcp",
            # Where to host the status page HTTP service
            "status_page_host": "utility",
            # SSH services to expose to the operator (TCP ports)
            "ssh_service_nodes": ["utility", "external-conn", "external-dhcp"],
            # Air mgmt L2 bridge — handled by ZTP/NOZTP as a regular Cumulus
            # switch (cust-net-edge-01 is already in Wire Map); no Air NI needed.
            "air_bridge": None,
        }
    # L2 default
    return {
        "mode": "l2",
        "jump_host": "dhcp-oob",
        "nat_host": "dhcp-oob",
        "dhcp_server": "dhcp-oob",
        "status_page_host": "dhcp-oob",
        "ssh_service_nodes": ["oob-server-01", "dhcp-oob"],
        "air_bridge": "air-oob-switch",
    }


# ---------------------------------------------------------------------------
# air-oob-switch Node Instructions
# ---------------------------------------------------------------------------

def _inject_air_oob_instructions(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    topology_json: dict,
) -> None:
    """Create Node Instructions to configure air-oob-switch as a VLAN-aware bridge.

    Port assignments:
      - Ports connected to switch eth0s / infra eth1 → untagged (air-mgmt)
      - Ports connected to OOB switch uplinks → access VLAN per OOB subnet
      - Ports connected to infra eth2+ → access VLAN per OOB subnet

    Must be called after import_topology() but before start_simulation().
    """
    air_meta = topology_json.get("_air_oob", {})
    oob_subnets = air_meta.get("oob_subnets", [])
    oob_switch_names = air_meta.get("oob_switch_names", [])

    # Map air-oob-switch ports to their peer (node:interface)
    port_peers: dict[str, tuple[str, str]] = {}  # swpN → (node, interface)
    for link in topology_json.get("content", {}).get("links", []):
        if not isinstance(link[0], dict) or not isinstance(link[1], dict):
            continue
        for i, ep in enumerate(link):
            if ep.get("node") == "air-oob-switch" and ep["interface"].startswith("swp"):
                other = link[1 - i]
                port_peers[ep["interface"]] = (other["node"], other["interface"])

    if not port_peers:
        return

    # Classify ports:
    # - air-mgmt (untagged): switch eth0s, infra eth1
    # - VLAN N (access): OOB switch uplinks, infra eth2+
    # VLAN IDs: use 200 + subnet_index (200, 201, 202, ...)
    air_mgmt_ports = []
    vlan_ports: dict[int, list[str]] = {}  # vlan_id → [swpN, ...]

    for swp, (peer_node, peer_iface) in sorted(port_peers.items(),
                                                 key=lambda x: int(x[0].replace("swp", ""))):
        # OOB switch uplink → assign VLAN based on mgmt SUBNET index (not switch index)
        # With 1 subnet and 3 switches, all go on VLAN 777.
        # With 3 subnets and 3 switches, each gets its own VLAN (777, 778, 779).
        if peer_node in oob_switch_names:
            switch_idx = oob_switch_names.index(peer_node)
            n_subnets = max(len(oob_subnets), 1)
            subnet_idx = switch_idx % n_subnets
            if peer_iface != "eth0":  # uplink, not eth0 (which is air-mgmt)
                vlan_id = 777 + subnet_idx
                vlan_ports.setdefault(vlan_id, []).append(swp)
                continue

        # Infra nodes (dhcp-oob, oob-server-01)
        if peer_node in ("dhcp-oob", "oob-server-01"):
            if peer_iface == "eth1":
                air_mgmt_ports.append(swp)  # air-mgmt (untagged)
            else:
                # eth2+ → map to VLAN by index (eth2=VLAN777, eth3=VLAN778, ...)
                eth_num = int(peer_iface.replace("eth", ""))
                vlan_id = 777 + (eth_num - 2)
                vlan_ports.setdefault(vlan_id, []).append(swp)
            continue

        # Everything else (switch eth0s) → air-mgmt (untagged)
        air_mgmt_ports.append(swp)

    # Build NVUE commands
    commands = [
        "nv set system hostname air-oob-switch",
        "nv set bridge domain br_default type vlan-aware",
    ]

    # Air-mgmt ports (untagged)
    if air_mgmt_ports:
        port_list = ",".join(air_mgmt_ports)
        commands.append(f"nv set interface {port_list} bridge domain br_default")

    # VLAN ports (access per VLAN)
    for vlan_id in sorted(vlan_ports):
        port_list = ",".join(vlan_ports[vlan_id])
        commands.append(f"nv set bridge domain br_default vlan {vlan_id}")
        commands.append(f"nv set interface {port_list} bridge domain br_default access {vlan_id}")

    commands.append("nv config apply -y")

    create_node_instruction(
        client, base_url, token, sim_id,
        node_name="air-oob-switch",
        commands=commands,
        name="air-oob-switch-vlan-bridge",
        wait_for_network=False,
    )


def _inject_cust_net_edge_instructions(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    topology_json: dict,
    switch_password: str = "Cumu1usLinux!",
    common: dict | None = None,
) -> int:
    """Configure cust-net-edge-* for L3 OOB mode.

    cust-net-edge simulates the customer's network edge in Air. It plays
    two independent roles:

      1. **L2 bridge for the Air-mgmt VLAN**: every switch eth0,
         plus external-dhcp:eth1 and utility:eth2, lands on a cust-net-edge
         bridge port. Multiple edges are stitched into one L2 domain through
         a loop-free star centred on cust-net-edge-01. Only the hub owns the
         bridge SVI (.254 on air_mgmt_subnet; 172.20.0.254/24 by default).

      2. **Customer-side eBGP underlay peer** (EXIT edges): the
         cores' EXIT VRF carries `nv set vrf EXIT router bgp neighbor
         swp61s0 peer-group underlay-esl-external remote-as external`
         on the ports facing cust-net-edge. Without cust-net-edge running
         BGP back at the cores, the eBGP sessions never come up and the
         EXIT VRF doesn't propagate routes. EXIT egress to external-conn is
         deliberately routed on dedicated L3 ports, not on the mgmt bridge.

    cust-net-edge is an Air-sim-only node — it has no equivalent in real
    ERA deployments. So instead of rendering a real Ansible role + host_vars,
    we generate the NVUE config inline here from the topology JSON.

    Returns the number of cust-net-edge nodes configured.
    """
    nodes = topology_json.get("content", {}).get("nodes", {})
    targets = sorted(
        (n for n in nodes if n.startswith("cust-net-edge")),
        key=lambda n: int(n.rsplit("-", 1)[1]) if n.rsplit("-", 1)[-1].isdigit() else 0,
    )
    if not targets:
        return 0

    # eBGP customer-side ASN. Distinct from internal ERA ASN (typically
    # 4260394788 or similar). Stable across both cust-net-edge nodes so
    # they're in the same external AS.
    CUST_BGP_ASN = 4260000000

    # Customer-DC-side L3 ports the edge brings up with a static IP +
    # advertises via `redistribute connected`. Keyed by (peer_node,
    # peer_iface). Used for the EXIT-VRF inter-VRF DHCP relay path:
    # external-dhcp:eth2 lands here so cores' EXIT VRF learns
    # 10.88.88.0/24 via the existing eBGP ESL session.
    L3_PEER_PORTS: dict[tuple[str, str], str] = {
        ("external-dhcp", "eth2"): "10.88.88.1/24",
    }
    # EXIT egress links to the NAT host. These are intentionally NOT bridge
    # ports: the air-mgmt bridge is a single 172.20.0.0/24 domain with its SVI
    # on edge-01, while EXIT egress uses per-edge routed subnets so traffic
    # ECMP'd to either EXIT edge has a real path to external-conn.
    EXIT_EGRESS_PORTS: dict[tuple[str, str], tuple[str, str]] = {
        ("external-conn", "eth1"): ("172.20.1.254/24", "172.20.1.1"),
        ("external-conn", "eth2"): ("172.20.2.254/24", "172.20.2.1"),
        # ADR-0002 follow-through: edges 03/04 now carry EXIT uplinks too
        # (generate_arch_excel spreads them over four edges so no edge exceeds
        # the 64-port platform limit), so each needs its own routed egress
        # subnet on the same edge-0N <-> 172.20.N.0/24 pattern.
        ("external-conn", "eth3"): ("172.20.3.254/24", "172.20.3.1"),
        ("external-conn", "eth4"): ("172.20.4.254/24", "172.20.4.1"),
    }

    configured = 0
    for idx, edge_name in enumerate(targets):
        # Classify ports: bridge (peer is ethN, default), L3 (peer is a
        # known L3_PEER_PORTS entry), EXIT egress (external-conn leg), or BGP
        # (peer is swpXX).
        bridge_ports: list[str] = []
        bgp_ports: list[str] = []
        l3_ports: list[tuple[str, str]] = []  # (local_port, ipv4_addr)
        exit_egress_ports: list[tuple[str, str, str]] = []  # (local_port, ipv4_addr, default_via)
        for link in topology_json.get("content", {}).get("links", []):
            if not (isinstance(link[0], dict) and isinstance(link[1], dict)):
                continue
            for i, ep in enumerate(link):
                if (ep.get("node") != edge_name
                        or not ep.get("interface", "").startswith("swp")):
                    continue
                peer_node = link[1 - i].get("node", "")
                peer_iface = link[1 - i].get("interface", "")
                l3_key = (peer_node, peer_iface)
                if l3_key in L3_PEER_PORTS:
                    l3_ports.append((ep["interface"], L3_PEER_PORTS[l3_key]))
                elif l3_key in EXIT_EGRESS_PORTS:
                    addr, default_via = EXIT_EGRESS_PORTS[l3_key]
                    exit_egress_ports.append((ep["interface"], addr, default_via))
                elif peer_node.startswith("cust-net-edge"):
                    # Inter-edge trunk: edge↔edge link spans the
                    # air-mgmt L2 across the multi-edge star, so it's a BRIDGE
                    # port, not a BGP-underlay swp port.
                    bridge_ports.append(ep["interface"])
                elif peer_iface.startswith("eth"):
                    bridge_ports.append(ep["interface"])
                elif peer_iface.startswith("swp"):
                    bgp_ports.append(ep["interface"])

        def _port_sort_key(p: str) -> tuple:
            """Sort `swpNNN` and `swpNNNsSS` numerically (parent, sub)."""
            rest = p[3:] if p.startswith("swp") else p
            if "s" in rest:
                parent, sub = rest.split("s", 1)
                return (int(parent), int(sub))
            return (int(rest), -1)
        bridge_ports = sorted(set(bridge_ports), key=_port_sort_key)
        bgp_ports = sorted(set(bgp_ports), key=_port_sort_key)
        l3_ports = sorted(set(l3_ports), key=lambda item: _port_sort_key(item[0]))
        exit_egress_ports = sorted(
            set(exit_egress_ports),
            key=lambda item: _port_sort_key(item[0]),
        )

        # Loopback IP — stable per cust-net-edge in a customer-side block
        # that doesn't collide with ERA's 172.16.176.0/24.
        lo_ip = f"10.255.255.{idx + 1}"

        # Build the NVUE config as a .sh-style script — same shape as the
        # generated per-switch configs, so build_switch_ni_commands can
        # stage it via the deferred-apply systemd oneshot. Without the
        # deferred apply pattern, `nv config apply` races ifreload-nvue
        # and silently rolls back (same trap that bit the OOB switches).
        config_lines = [
            "#!/bin/bash",
            f"# NVUE config for {edge_name} (Air-only customer edge)",
            f"nv set system hostname {edge_name}",
            "nv set interface eth0 type eth",
            "nv set interface eth0 vrf mgmt",
            f"nv set interface lo ipv4 address {lo_ip}/32",
            "nv set interface lo type loopback",
        ]
        # Operator-configurable SSH login banners (same source as the
        # cluster-switch templates: Excel Settings.pre/post_login_message).
        # cust-net-edge is Air-only so we render the NVUE line inline here
        # instead of going through the role/template path. Same encoding
        # contract: single-quoted, embedded `'` → `'\''`, `{hostname}` /
        # `{site}` / `{arch}` substituted per-switch. See
        # docs/plans/2026-05-26-switch-login-messages-design.md.
        if common:
            _site = str(common.get("site", "default"))
            _arch = str(common.get("arch", ""))
            for kind, val in (
                ("pre-login", common.get("pre_login_message") or ""),
                ("post-login", common.get("post_login_message") or ""),
            ):
                if not val:
                    continue
                rendered = (str(val)
                            .replace("'", "'\\''")
                            .replace("{hostname}", edge_name)
                            .replace("{site}", _site)
                            .replace("{arch}", _arch))
                config_lines.append(
                    f"nv set system message {kind} '{rendered}'"
                )
        if bridge_ports:
            port_list = ",".join(bridge_ports)
            config_lines += [
                "nv set bridge domain br_default type vlan-aware",
                f"nv set interface {port_list} bridge domain br_default",
                # Bridge members must NOT run dhcp-client. Without this,
                # Cumulus boots swpN with dhcp4=true (Cumulus default for
                # any link-up interface), the port DHCPs from external-dhcp
                # *before* our NVUE config adds it to the bridge, gets a
                # /24 IP + a kernel default route. Symptom: cust-net-edge
                # ICMPs back "Destination Host Unreachable" with its loopback
                # as source for any transit traffic. Disabling dhcp-client
                # per-port keeps the bridge a pure L2 path.
                f"nv set interface {port_list} ipv4 dhcp-client state disabled",
                f"nv set interface {port_list} ipv6 dhcp-client state disabled",
            ]
            # Bridge SVI only on the hub. Spokes are pure L2 bridge members
            # plus a star trunk back to edge-01. The SVI is the on-link default
            # gateway for the air-mgmt DHCP scope; EXIT egress default routes
            # live on dedicated routed ports below.
            if edge_name == "cust-net-edge-01":
                config_lines += [
                    "nv set bridge domain br_default vlan 1",
                    "nv set interface vlan1 type svi",
                    f"nv set interface vlan1 ipv4 address "
                    f"{air_mgmt_cidr(AIR_MGMT_SVI_OCTET)}",
                ]

        # Routed L3 ports. `redistribute connected` in the BGP block below
        # carries these prefixes to cores' EXIT VRF via the existing eBGP ESL
        # sessions.
        for port, addr, default_via in exit_egress_ports:
            config_lines += [
                f"nv set interface {port} type swp",
                f"nv set interface {port} ipv4 address {addr}",
                f"nv set interface {port} ipv4 dhcp-client state disabled",
                f"nv set interface {port} ipv6 dhcp-client state disabled",
                f"nv set vrf default router static 0.0.0.0/0 via {default_via} type ipv4-address",
            ]
        for port, addr in l3_ports:
            config_lines += [
                f"nv set interface {port} type swp",
                f"nv set interface {port} ipv4 address {addr}",
                # Same dhcp-client-disable rationale as bridge_ports: avoid
                # Cumulus's default dhcp4=true on link-up racing our static
                # IP and stealing a kernel default route.
                f"nv set interface {port} ipv4 dhcp-client state disabled",
                f"nv set interface {port} ipv6 dhcp-client state disabled",
            ]
        if bgp_ports:
            config_lines += [
                f"nv set router bgp autonomous-system {CUST_BGP_ASN}",
                f"nv set router bgp router-id {lo_ip}",
                "nv set router bgp state enabled",
                "nv set vrf default router bgp address-family ipv4-unicast state enabled",
                "nv set vrf default router bgp address-family ipv4-unicast redistribute connected state enabled",
                "nv set vrf default router bgp state enabled",
                "nv set vrf default router bgp peer-group external remote-as external",
                "nv set vrf default router bgp peer-group external address-family ipv4-unicast state enabled",
                # default-route-origination advertises a synthetic 0.0.0.0/0
                # to the cores' EXIT VRF, which the existing OOB_FILTER then
                # leaks into OOB VRF — giving .200.x clients a usable outbound
                # default. The actual forwarding target is the Gap-A static
                # route below (0/0 via the edge's external-conn L3 leg).
                "nv set vrf default router bgp peer-group external address-family ipv4-unicast default-route-origination state enabled",
            ]
            for port in bgp_ports:
                config_lines += [
                    f"nv set vrf default router bgp neighbor {port} peer-group external",
                    f"nv set vrf default router bgp neighbor {port} type unnumbered",
                ]
        config_text = "\n".join(config_lines) + "\n"

        # No static eth0 IP on cust-net-edge — Air assigns it via OOB DHCP
        # (same as any other Cumulus VM in the sim). Pass host_ip=None.
        commands = build_switch_ni_commands(
            edge_name, config_text, host_ip=None,
            switch_password=switch_password,
        )

        try:
            create_node_instruction(
                client, base_url, token, sim_id,
                node_name=edge_name,
                commands=commands,
                name=f"{edge_name}-l3-edge",
                wait_for_network=False,
            )
            console.print(
                f"  {edge_name}: bridge={len(bridge_ports)} ports, "
                f"L3={len(l3_ports) + len(exit_egress_ports)} ports, "
                f"BGP={len(bgp_ports)} unnumbered peers, lo={lo_ip}/32 "
                f"(deferred-apply NI)")
            configured += 1
        except AirError as exc:
            console.print(
                f"  [yellow]Warning:[/] {edge_name} NI failed: {exc}")

    return configured


def _inject_ext_storage_instructions(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    topology_json: dict,
) -> int:
    """Configure ext-storage-{01,02} as Ubuntu + FRR speaking BGP unnumbered.

    ext-storage simulates the customer's external storage aggregate switch
    in Air — the upstream device the CSL swp63s0/s1 storage uplinks land
    on per ERA-00011's "Uplink to Aggregate Switch - Private Storage
    Network" pattern. The CSL side already emits L3 swp config in VRF
    STORAGE with `peer-group underlay-era-storage` (unnumbered, BFD,
    eBGP); this function brings up the other end of the session.

    NI uses `wait_for_network=True` so Air defers script execution until
    the node's network reachability is established (eth0 has IP, default
    route works, DNS resolves). Without this, apt-get races ahead of
    external-conn NAT readiness and fails with "Temporary failure
    resolving 'archive.ubuntu.com'" — observed deterministically on
    ext-storage-01 across multiple redeploys.

    Each ext-storage gets:
      - eth0 static IP 172.20.0.{79+idx}/24 on cust-net-edge-01 bridge,
        default route via .254 on air_mgmt_subnet (cust-net-edge-01 SVI)
        for apt access
      - Loopback at 10.187.5.{idx+1}/32 (customer-side block, distinct
        from cluster's 172.16.176.0/21 supernet)
      - FRR (apt-installed) with BGP unnumbered on each eth* facing a
        CSL swp63 port, eBGP ASN 4260000002, `no bgp ebgp-requires-policy`
        (FRR 8.1+ defaults this to ENABLED which silently drops
        eBGP advertisements that don't have an outbound route-map —
        matches NVUE/FRR-on-Cumulus "traditional" behavior)
      - Explicit `network <lo>/32` + `redistribute connected` so the
        loopback advertises back to CSLs

    Returns the number of ext-storage nodes configured.
    """
    # Discovery + FRR/netplan builders live in airlib.ext_storage_config so
    # `make fix-ext-storage` reuses the exact same config (no drift).
    # ERA-93: the plane is operator-selectable, so pass it rather than letting
    # the builder fall back to its 172.20.0.x literal.
    targets = discover_ext_storage_targets(topology_json,
                                           air_mgmt_subnet=air_mgmt_network())
    if not targets:
        return 0

    configured = 0
    for _t in targets:
        node_name = _t["node_name"]
        peer_ifaces = _t["peer_ifaces"]
        lo_ip = _t["lo_ip"]
        eth0_ip = _t["eth0_ip"]
        if not peer_ifaces:
            console.print(f"  [yellow]Warning:[/] {node_name} has no CSL-facing "
                          f"interfaces; skipping FRR config")
            continue

        # FRR config, daemons, and eth0 netplan all come from the shared
        # builder (airlib.ext_storage_config) so this NI path and
        # `make fix-ext-storage` can never diverge.
        frr_conf_b64 = base64.b64encode(
            build_frr_conf(node_name, lo_ip, peer_ifaces).encode()
        ).decode()
        daemons_b64 = base64.b64encode(build_daemons().encode()).decode()
        eth0_netplan_b64 = base64.b64encode(
            build_eth0_netplan(eth0_ip, air_mgmt_network()).encode()
        ).decode()

        # NI #1: boot-time IP setup. wait_for_network=False so this runs
        # immediately at boot — there's no dependency on outside
        # reachability. Idempotent (the ip addr/route commands all use
        # `|| true` or `replace` semantics).
        netcfg_commands = [
            f"# ext-storage boot-time IP setup for {node_name}",
            "set -x",
            "ip link set lo up",
            f"ip addr add {lo_ip}/32 dev lo 2>/dev/null || true",
            *[f"ip link set {iface} up || true" for iface in peer_ifaces],
            # eth0 netplan — static IP on cust-net-edge-01 air-mgmt bridge.
            f"echo '{eth0_netplan_b64}' | base64 -d > /etc/netplan/99-era-ext-storage.yaml",
            "chmod 600 /etc/netplan/99-era-ext-storage.yaml",
            "netplan apply || true",
            "sleep 3",
            # Manual fallback if netplan-apply didn't take.
            "ip link set eth0 up || true",
            f"ip addr replace {eth0_ip}/{oob_prefixlen()} dev eth0 || true",
            f"ip route replace default via "
            f"{air_mgmt_ip(AIR_MGMT_SVI_OCTET)} dev eth0 || true",
        ]

        # NI #2: FRR install. wait_for_network=True with reachability_ip
        # pointing at the eth0 IP that NI #1 just assigned. Air's agent
        # pings this IP from inside the VM before running the script;
        # once NI #1 has set the IP, NI #2's reachability check passes
        # (pinging own assigned IP returns immediately) and apt-get can
        # run with DNS working.
        frr_commands = [
            f"# ext-storage FRR install for {node_name}",
            "set -x",
            # Belt-and-suspenders DNS-readiness gate (Air's reachability
            # check verifies our IP is up, but DNS depends on
            # external-dhcp / external-conn NAT being up too).
            "for i in $(seq 1 60); do "
            "  if getent hosts archive.ubuntu.com >/dev/null 2>&1; then "
            "    echo \"DNS up after $((i*5))s\"; break; "
            "  fi; "
            "  sleep 5; "
            "done",
            "export DEBIAN_FRONTEND=noninteractive",
            "apt-get update -qq",
            "apt-get install -y -qq frr frr-pythontools",
            f"echo '{daemons_b64}' | base64 -d > /etc/frr/daemons",
            f"echo '{frr_conf_b64}' | base64 -d > /etc/frr/frr.conf",
            "chown frr:frr /etc/frr/daemons /etc/frr/frr.conf",
            "chmod 640 /etc/frr/daemons /etc/frr/frr.conf",
            "systemctl enable frr",
            "systemctl restart frr",
            "sleep 3",
            "vtysh -c 'show bgp summary' || true",
        ]

        try:
            # NI #1 — IP setup, no wait. Must come first so NI #2's
            # reachability check can find a configured eth0 IP.
            create_node_instruction(
                client, base_url, token, sim_id,
                node_name=node_name,
                commands=netcfg_commands,
                name=f"{node_name}-boot-net",
                wait_for_network=False,
            )
            # NI #2 — FRR install, gated on reachability. Air's agent
            # processes NIs sequentially on a single Instruction Handler
            # thread, so #1 always completes before #2 starts.
            create_node_instruction(
                client, base_url, token, sim_id,
                node_name=node_name,
                commands=frr_commands,
                name=f"{node_name}-frr-bgp",
                wait_for_network=True,
                reachability_ip=eth0_ip,
            )
            console.print(
                f"  {node_name}: 2 NIs queued — boot-net + FRR install, "
                f"{len(peer_ifaces)} CSL peers, lo={lo_ip}/32, "
                f"ASN {CUST_STORAGE_ASN}")
            configured += 1
        except AirError as exc:
            console.print(
                f"  [yellow]Warning:[/] {node_name} NI failed: {exc}")

    return configured


def _inject_l3_trio_netplan_ni(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    inv_dir: Path,
    topology_json: dict,
) -> int:
    """Bring up eth1+ on the L3 OOB trio at first boot via Node Instructions.

    The setup-ztp-server playbook (run later via switch-ztp-deploy) also writes
    netplan for external-dhcp, but it runs AFTER the sim is up — so before the
    operator runs Ansible, the L3 trio's data-plane interfaces are DOWN. That
    breaks any "deploy and wait for switches to ZTP themselves" flow. Inject
    netplan at first boot too, so ZTP works regardless of when (or whether)
    Ansible runs.

    Hard-coded IP plan for v1 (matches what setup-ztp-server.yml renders):
      - external-dhcp:eth1 = 172.20.0.77/24 (air-mgmt subnet, dnsmasq listens)
      - external-conn:eth1 = 172.20.1.1/24 (routed EXIT egress via edge-01)
        + route <air_mgmt_subnet> via 172.20.1.254 (return path to air-mgmt)
        + route 192.168.200.0/24 via 172.20.1.254 (OOB return path)
      - external-conn:eth2 = 172.20.2.1/24 (routed EXIT egress via edge-02)
        + backup route 192.168.200.0/24 via 172.20.2.254
      - external-conn:eth3/eth4 = 172.20.3.1/24 / 172.20.4.1/24 (routed EXIT
        egress via edge-03/-04, present once the fabric spreads its EXIT
        uplinks over four edges -- SU32; see cust_edge_count())
        + backup OOB routes via .254 on each, at higher metrics.
        The NAT NI later installs an ECMP route for OOB return traffic over
        whichever of these legs the topology actually has.
      - utility:eth1       = 192.168.200.78/24 (VLAN 200 / OOB VRF)
      - utility:eth2       = 172.20.0.78/24  (Air-mgmt bridge; reach to switch eth0s)

    Returns the number of nodes configured.
    """
    # Per-interface spec: required "addr"; optional PBR keys to route a
    # specific source IP through a non-main table (preserves eth0 default
    # for Air mgmt / jump-box reachability).
    L3_TRIO_NETPLAN: dict = {
        "external-dhcp": {
            "eth1": {"addr": air_mgmt_cidr(EXTERNAL_DHCP_OCTET)},
            # eth2: customer-DC-side DHCP listener for EXIT-VRF inter-VRF
            # relay testing. Connected via cust-net-edge-01:swpN to the
            # cores' EXIT VRF underlay; cust-net-edge runs
            # `redistribute connected` so cores learn 10.88.88.0/24 via
            # the existing eBGP ESL session. 10.88.88.0/24 is
            # deliberately distant from 192.168.x to keep test-log greps
            # unambiguous vs OOB traffic. See
            # docs/plans/2026-05-27-l3-oob-exit-dhcp-relay.md.
            "eth2": {
                "addr": "10.88.88.88/24",
                # Return route for DHCPOFFER unicast back to giaddr.
                # OFFER's destination is the core's INBAND-VRF VLAN SVI
                # (e.g. 172.16.179.2 for VLAN 400). external-dhcp's
                # default route points at eth0 (Air outbound), so without
                # this specific route the OFFER egresses Air outbound
                # and dies. 172.16.0.0/16 covers all ERA INBAND service
                # subnets (172.16.176.0/21 supernet); routing back via
                # cust-net-edge → cores' EXIT VRF → INBAND VRF leak.
                "routes": [
                    {"to": "172.16.0.0/16", "via": "10.88.88.1"},
                ],
            },
        },
        "external-conn": {
            "eth1": {
                "addr": "172.20.1.1/24",
                # eth1 is the edge-01 EXIT egress leg. Management traffic
                # returns only through edge-01 because edge-01 owns the
                # 172.20.0.0/24 bridge SVI; OOB return traffic starts here
                # and the NAT NI later replaces it with ECMP across both legs.
                "routes": [
                    {"to": air_mgmt_network(), "via": "172.20.1.254"},
                    {"to": oob_network(), "via": "172.20.1.254", "metric": 100},
                ],
            },
            # Second EXIT egress leg to cust-net-edge-02 on a separate /24 so
            # cores ECMP outbound to either edge resolves to a real NAT path.
            "eth2": {
                "addr": "172.20.2.1/24",
                "routes": [
                    {"to": oob_network(), "via": "172.20.2.254", "metric": 200},
                ],
            },
            # Third and fourth EXIT egress legs. ADR-0002 follow-through:
            # generate_arch_excel now spreads customer uplinks over four edges
            # so no edge exceeds the 64-port platform limit, and every edge
            # carrying EXIT uplinks needs a real NAT path or its traffic
            # black-holes. Same pattern, ascending metric so edge-01 stays the
            # preferred OOB return path.
            "eth3": {
                "addr": "172.20.3.1/24",
                "routes": [
                    {"to": oob_network(), "via": "172.20.3.254", "metric": 300},
                ],
            },
            "eth4": {
                "addr": "172.20.4.1/24",
                "routes": [
                    {"to": oob_network(), "via": "172.20.4.254", "metric": 400},
                ],
            },
        },
        "utility": {
            "eth1": {
                "addr": oob_cidr(UTILITY_OCTET),
                # PBR: utility's main default stays via eth0 (Air mgmt) so
                # Air's SSH service / our jump-box access keep working.
                # Source-policy rule diverts traffic from .200.78 into
                # table 200, whose default is via the oob-switch VRR
                # (192.168.200.1) → cust-net-edge → external-conn
                # MASQUERADE → internet.
                "pbr_table": 200,
                "pbr_table_default_via": oob_gateway(),
                "pbr_from": oob_ip(UTILITY_OCTET),
            },
            # eth2: utility's direct foot on the Air-mgmt L2 bridge
            # (cust-net-edge-01). Required so Ansible plays from utility
            # can ssh to switch eth0s on 172.20.0.0/24 (validate-config
            # otherwise fails with "Connection Failed: N/N"). Static IP
            # avoids a DHCP-race against external-dhcp at first boot;
            # .78 mirrors utility's .200.78 mnemonic on the OOB plane.
            "eth2": {"addr": air_mgmt_cidr(UTILITY_OCTET)},
        },
    }
    nodes = topology_json.get("content", {}).get("nodes", {})

    # Interfaces each node actually has in THIS topology. The spec above is a
    # superset -- external-conn only grows eth3/eth4 once the fabric spreads
    # its EXIT uplinks over four edges (SU32). Emitting a netplan stanza for an
    # interface the node does not have would put a static address and backup
    # routes on a link that never comes up.
    topo_ifaces: dict[str, set] = {}
    for link in topology_json.get("content", {}).get("links", []):
        if not isinstance(link, list):
            continue
        for endpoint in link:
            if isinstance(endpoint, dict) and endpoint.get("node"):
                topo_ifaces.setdefault(endpoint["node"], set()).add(
                    endpoint.get("interface")
                )

    configured = 0
    for node_name, ifaces in L3_TRIO_NETPLAN.items():
        if node_name not in nodes:
            continue
        present = topo_ifaces.get(node_name, set())
        eth_blocks = []
        for iface, spec in ifaces.items():
            if iface not in present:
                continue
            lines = [
                f"    {iface}:",
                f"      addresses: [{spec['addr']}]",
                "      dhcp4: false",
                "      dhcp6: false",
            ]
            # Collect every route — both plain `routes:` entries and the
            # synthetic 0/0 route a `pbr_table` spec implies — into one
            # block so we emit a single `routes:` header. YAML can't have
            # two `routes:` keys at the same level.
            all_routes = list(spec.get("routes") or [])
            if "pbr_table" in spec:
                all_routes.append({
                    "to": "0.0.0.0/0",
                    "via": spec["pbr_table_default_via"],
                    "table": spec["pbr_table"],
                })
            if all_routes:
                lines.append("      routes:")
                for route in all_routes:
                    lines.append(f"        - to: {route['to']}")
                    lines.append(f"          via: {route['via']}")
                    if "table" in route:
                        lines.append(f"          table: {route['table']}")
                    if "metric" in route:
                        lines.append(f"          metric: {route['metric']}")
            if "pbr_table" in spec:
                lines += [
                    "      routing-policy:",
                    f"        - from: {spec['pbr_from']}",
                    f"          table: {spec['pbr_table']}",
                ]
            eth_blocks.append("\n".join(lines))
        eths_yaml = "\n".join(eth_blocks)
        netplan = (
            "network:\n  version: 2\n  renderer: networkd\n  ethernets:\n"
            + eths_yaml + "\n"
        )
        netplan_b64 = base64.b64encode(netplan.encode()).decode()
        commands = [
            f"# L3 trio first-boot netplan for {node_name}",
            "set -x",
            f"echo '{netplan_b64}' | base64 -d > /etc/netplan/99-era-l3.yaml",
            "chmod 600 /etc/netplan/99-era-l3.yaml",
            # Try netplan apply; if it can't bring the interface up yet
            # (carrier missing), bring it up manually as a fallback.
            "netplan apply || true",
            "sleep 2",
            *[f"ip link set {iface} up || true" for iface in ifaces],
            *[f"ip addr replace {spec['addr']} dev {iface} || true"
              for iface, spec in ifaces.items()],
        ]
        try:
            create_node_instruction(
                client, base_url, token, sim_id,
                node_name=node_name,
                commands=commands,
                name=f"{node_name}-l3-netplan",
                wait_for_network=False,
            )
            emitted = [i for i in ifaces if i in present]
            console.print(f"  {node_name}: L3 netplan queued ({', '.join(emitted)})")
            configured += 1
        except AirError as exc:
            console.print(f"  [yellow]Warning:[/] {node_name} netplan NI failed: {exc}")
    return configured



def _external_conn_egress_legs(topology_json: dict) -> list:
    """EXIT egress leg numbers on external-conn, from the topology itself.

    Returns e.g. [1, 2, 3, 4] for the four `external-conn:ethN <->
    cust-net-edge-0N` routed legs at SU32, or [1, 2] on smaller fabrics. eth0
    is the outbound/NAT interface and is never an egress leg.
    """
    legs = set()
    for link in topology_json.get("content", {}).get("links", []):
        if not isinstance(link, list) or len(link) != 2:
            continue
        if not all(isinstance(ep, dict) for ep in link):
            continue
        for ep, peer in (link, link[::-1]):
            if ep.get("node") != "external-conn":
                continue
            if not str(peer.get("node", "")).startswith("cust-net-edge"):
                continue
            iface = str(ep.get("interface", ""))
            if iface.startswith("eth") and iface[3:].isdigit():
                n = int(iface[3:])
                if n > 0:
                    legs.add(n)
    return sorted(legs)

def _inject_external_conn_nat_ni(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    topology_json: dict,
) -> bool:
    """Enable IP forwarding + MASQUERADE on external-conn for L3 outbound NAT.

    L3 mode declares external-conn as the `nat_host` (analogous to L2's
    oob-server-01). The Ansible `oob-server` role normally configures this
    at `make oob-setup` time, but NOZTP skips Ansible entirely — so the
    NAT host needs a Node Instruction to come up self-sufficient on first
    boot. Mirrors `roles/oob-server/tasks/main.yml` lines 35-50 + 160-161.
    """
    if "external-conn" not in topology_json.get("content", {}).get("nodes", {}):
        return False
    commands = [
        "# L3 NAT host: enable forwarding + MASQUERADE on eth0",
        "set -e",
        "echo 'net.ipv4.ip_forward=1' > /etc/sysctl.d/99-era-forwarding.conf",
        "sysctl -p /etc/sysctl.d/99-era-forwarding.conf",
        "iptables -t nat -C POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null || \\",
        "  iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE",
        "mkdir -p /etc/iptables",
        "iptables-save > /etc/iptables/rules.v4 || true",
        # Return routes after un-MASQUERADE. Management subnet traffic must
        # return through edge-01's SVI; OOB client traffic can return through
        # ANY EXIT edge, so ECMP over every egress leg this topology actually
        # has. Derived rather than pinned to eth1/eth2: the number of EXIT
        # edges scales with the fabric (four at SU32), and a leg missing from
        # this list black-holes the return path for traffic that arrived on it.
        f"ip route replace {air_mgmt_network()} via 172.20.1.254 "
        f"dev eth1 || true",
    ]
    egress_legs = _external_conn_egress_legs(topology_json)
    if egress_legs:
        commands.append(f"ip route replace {oob_network()} \\")
        for i, leg in enumerate(egress_legs):
            last = i == len(egress_legs) - 1
            commands.append(
                f"  nexthop via 172.20.{leg}.254 dev eth{leg}"
                + (" || \\" if last else " \\")
            )
        commands.append(
            f"  ip route replace {oob_network()} via 172.20.1.254 dev eth1 || true"
        )
    try:
        create_node_instruction(
            client, base_url, token, sim_id,
            node_name="external-conn",
            commands=commands,
            name="external-conn-nat",
            wait_for_network=False,
        )
        console.print("  external-conn: NAT (ip_forward + MASQUERADE eth0) queued")
        return True
    except AirError as exc:
        console.print(f"  [yellow]Warning:[/] external-conn NAT NI failed: {exc}")
        return False


def _inject_ubuntu_node_instructions(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    topology_json: dict,
) -> int:
    """Disable unattended-upgrades on Ubuntu nodes to prevent dpkg lock issues.

    Applies to all infra nodes (dhcp-oob, oob-server-01) and server nodes.
    Returns the number of nodes configured.
    """
    topo_nodes = set(topology_json.get("content", {}).get("nodes", {}).keys())
    # Target Ubuntu nodes (infra + servers, not switches)
    targets = [n for n in sorted(topo_nodes)
               if not any(n.startswith(p) for p in SWITCH_HOST_PREFIXES + ("cust-net-edge", "air-oob"))]

    commands = [
        "# Disable unattended-upgrades to prevent dpkg lock contention",
        "systemctl disable --now unattended-upgrades || true",
        "systemctl disable --now apt-daily.timer || true",
        "systemctl disable --now apt-daily-upgrade.timer || true",
        "kill -9 $(pgrep -f unattended-upgr) 2>/dev/null || true",
        "# Disable networkd-wait-online — most interfaces have no link partner in Air",
        "# and the service blocks boot for 5+ minutes waiting for them",
        "systemctl disable --now systemd-networkd-wait-online.service || true",
    ]

    jobs = [
        {
            "node_name": node_name,
            "commands": commands,
            "name": f"{node_name}-disable-unattended-upgrades",
            "wait_for_network": False,
        }
        for node_name in targets
    ]
    return _parallel_create_nis(
        client, base_url, token, sim_id, jobs, best_effort=True,
    )


def _inject_server_ip_instructions(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    inv_dir: Path,
    topology_json: dict,
) -> int:
    """Assign static eth0 IPs to server nodes via Node Instructions.

    Reads the generated inventory devices dict for eth0_ip assignments,
    then creates a shell instruction per server to disable DHCP and set
    the static IP.  Returns the number of servers configured.
    """
    # Load devices from generated inventory
    main_yml = inv_dir / "group_vars" / "all" / "main.yml"
    if not main_yml.exists():
        return 0
    with open(main_yml) as f:
        all_vars = yaml.safe_load(f) or {}
    devices = all_vars.get("devices", {})
    if not devices:
        return 0

    # Determine which nodes are in the topology (skip devices not in simulation)
    topo_nodes = set(topology_json.get("content", {}).get("nodes", {}).keys())

    # Gateway is the OOB anycast/VRR address from the workbook (common.oob_gateway).
    gateway = oob_gateway()

    configured = 0
    for node_name, dev in sorted(devices.items()):
        eth0_ip = dev.get("eth0_ip")
        if not eth0_ip or node_name not in topo_nodes:
            continue
        # Skip switches and infra nodes — only configure servers
        if any(node_name.startswith(p) for p in SERVER_NI_SKIP_PREFIXES):
            continue

        commands = [
            "# Disable DHCP and assign static management IP",
            "ip link set eth0 up",
            "ip addr flush dev eth0",
            f"ip addr add {eth0_ip}/{oob_prefixlen()} dev eth0",
            f"ip route add default via {gateway} dev eth0 || true",
        ]

        try:
            create_node_instruction(
                client, base_url, token, sim_id,
                node_name=node_name,
                commands=commands,
                name=f"{node_name}-eth0-ip",
                wait_for_network=False,
            )
            configured += 1
        except AirError as exc:
            console.print(f"  [yellow]Warning:[/] {node_name}: {exc}")

    return configured


# ---------------------------------------------------------------------------
# Full server configuration via Node Instructions
# ---------------------------------------------------------------------------

def _render_server_netplan(node_name: str, dev: dict, common: dict) -> str:
    """Render netplan YAML for a server node.

    Always includes eth0 with a static management IP so that netplan apply
    doesn't revert eth0 to DHCP (which may not respond in Air).
    Returns empty string only if the device has no eth0_ip.
    """
    ifaces = dev.get("interfaces", {})
    eth0_ip = dev.get("eth0_ip", "")
    if not eth0_ip:
        return ""

    def _init_cfg():
        """Start a netplan config dict with eth0 static management IP.

        Explicitly disable DHCPv6 and IPv6 router advertisements: Air's OOB
        plane has no DHCPv6 server or IPv6 RA source, and without these
        flags networkd leaves eth0 in `configuring` state indefinitely
        (waiting on DHCPv6), which blocks systemd-networkd-wait-online
        and adds ~5 minutes to every server boot.
        """
        cfg = {"network": {"version": 2, "renderer": "networkd", "ethernets": {
            "eth0": {
                "dhcp4": False,
                "dhcp6": False,
                "accept-ra": False,
                "addresses": [f"{eth0_ip}/{oob_prefixlen()}"],
                "routes": [{"to": "0.0.0.0/0", "via": oob_gateway()}],
            },
        }}}
        return cfg

    def _build_bond_vlan_netplan(data_ifaces, bond_ip1, bond_ip2, network, gateway, vlan_id):
        """Build netplan dict for a bond+VLAN role (storage/support).

        Uses active-backup bonding (not 802.3ad) because Air's virtual
        EVPN-MH bonds span two switches and Linux LACP can't negotiate
        across different LACP system IDs.  Traffic is VLAN-tagged because
        the switch port PVID (300) differs from the role's VLAN.

        Data NICs get optional:true so systemd-networkd-wait-online
        doesn't block boot waiting on them. Skip bond/vlan definitions
        entirely when bond_ip1 is missing (parser overflow) — otherwise
        netplan apply chokes on empty-string addresses.
        """
        cfg = _init_cfg()
        if not data_ifaces:
            return yaml.dump(cfg, default_flow_style=False, sort_keys=False)
        cfg["network"]["bonds"] = {}
        cfg["network"]["vlans"] = {}
        for iface in data_ifaces:
            cfg["network"]["ethernets"][iface] = {"dhcp4": False, "optional": True}
        if len(data_ifaces) >= 2 and bond_ip1:
            cfg["network"]["bonds"]["bond0"] = {
                "interfaces": [data_ifaces[0], data_ifaces[1]],
                "parameters": {"mode": "active-backup", "primary": data_ifaces[0],
                               "mii-monitor-interval": 100},
            }
            cfg["network"]["vlans"][f"bond0.{vlan_id}"] = {
                "id": vlan_id,
                "link": "bond0",
                "addresses": [bond_ip1],
                "nameservers": {"addresses": ["8.8.8.8", "8.8.4.4"]},
                "routing-policy": [{"from": network, "table": vlan_id}],
                "routes": [{"to": "0.0.0.0/0", "via": gateway, "table": vlan_id}],
            }
        if len(data_ifaces) >= 4 and bond_ip2:
            cfg["network"]["bonds"]["bond1"] = {
                "interfaces": [data_ifaces[2], data_ifaces[3]],
                "parameters": {"mode": "active-backup", "primary": data_ifaces[2],
                               "mii-monitor-interval": 100},
            }
            cfg["network"]["vlans"][f"bond1.{vlan_id}"] = {
                "id": vlan_id,
                "link": "bond1",
                "addresses": [bond_ip2],
                "nameservers": {"addresses": ["8.8.8.8", "8.8.4.4"]},
            }
        if not cfg["network"]["bonds"]:
            del cfg["network"]["bonds"]
            del cfg["network"]["vlans"]
        return yaml.dump(cfg, default_flow_style=False, sort_keys=False)

    # Role comes from the Excel `Function` column (docs/ROLES.md), which is
    # authoritative; the name-prefix tests below are a FALLBACK for workbooks
    # predating the role being carried in `devices`. Dispatching on the name
    # alone silently returned "" — no netplan, no IP, no error — for any host
    # whose name doesn't start with a blessed prefix (e.g. the site-prefixed
    # `<site>-gpu-01`). Same failure class as the ext-storage name filter.
    _role = str(dev.get("role") or "").strip().lower()

    # Compute nodes (Function=gpu/compute; legacy names su-*, node-*, gpu-NN)
    if _role == "compute" or (not _role and (
            node_name.startswith("su-") or node_name.startswith("node-")
            or node_name.startswith("gpu-"))):
        cpu_ifaces = [i for i in ifaces.get("cpu", []) if i != "eth0"]
        gpu_ifaces = [i for i in ifaces.get("gpu", []) if i != "eth0"]
        gpu_ips = dev.get("gpu_ips", [])
        gpu_interfaces = dev.get("gpu_interfaces", [])
        cfg = _init_cfg()
        cfg["network"]["bonds"] = {}
        # Data NICs get optional:true so systemd-networkd-wait-online
        # doesn't block boot when an interface has no IP yet (e.g. GPU
        # NICs past the per-plane stride limit, or members of a bond
        # whose bond_ip is missing).
        for iface in cpu_ifaces:
            cfg["network"]["ethernets"][iface] = {"dhcp4": False, "optional": True}
        if gpu_interfaces:
            # Dual-plane: each NIC gets its plane's gateway + a per-plane PBR table
            for gnic in gpu_interfaces:
                cfg["network"]["ethernets"][gnic["iface"]] = {
                    "dhcp4": False,
                    "optional": True,
                    "addresses": [gnic["ip"]],
                    "routing-policy": [
                        {"from": gnic["ip"].split("/")[0] + "/32",
                         "table": gnic["table"]},
                    ],
                    "routes": [
                        {"to": "0.0.0.0/0", "via": gnic["gateway"],
                         "table": gnic["table"]},
                    ],
                }
            assigned = {g["iface"] for g in gpu_interfaces}
            for iface in gpu_ifaces:
                if iface not in assigned:
                    cfg["network"]["ethernets"][iface] = {"dhcp4": False, "optional": True}
        else:
            # Single-plane: existing logic — PBR on first GPU NIC only
            gpu_network = common.get("gpu_network", "")
            gpu_gateway = common.get("gpu_gateway", "")
            gpu_vlan = int(common.get("gpu_vlan", 900))
            for idx, iface in enumerate(gpu_ifaces):
                if idx < len(gpu_ips):
                    entry = {
                        "dhcp4": False,
                        "optional": True,
                        "addresses": [gpu_ips[idx]],
                    }
                    # PBR on first GPU interface only (one rule per subnet)
                    if idx == 0 and gpu_network and gpu_gateway:
                        entry["routing-policy"] = [{"from": gpu_network, "table": gpu_vlan}]
                        entry["routes"] = [{"to": "0.0.0.0/0", "via": gpu_gateway, "table": gpu_vlan}]
                    cfg["network"]["ethernets"][iface] = entry
                else:
                    cfg["network"]["ethernets"][iface] = {"dhcp4": False, "optional": True}
        cpu_network = common.get("cpu_network", "")
        cpu_gateway = common.get("cpu_gateway", "")
        cpu_vlan = int(common.get("cpu_vlan", 300))
        # Skip bond0 entirely when bond_ip is missing — otherwise netplan
        # apply rolls back the whole file (including eth0 static IP).
        if cpu_ifaces and dev.get("bond_ip"):
            cfg["network"]["bonds"]["bond0"] = {
                "interfaces": list(cpu_ifaces),
                "addresses": [dev.get("bond_ip")],
                "nameservers": {"addresses": ["8.8.8.8", "8.8.4.4"]},
                "routing-policy": [{"from": cpu_network, "table": cpu_vlan}],
                "routes": [{"to": "0.0.0.0/0", "via": cpu_gateway, "table": cpu_vlan}],
                "parameters": {"mode": "active-backup", "primary": cpu_ifaces[0],
                               "mii-monitor-interval": 100},
            }
        if not cfg["network"]["bonds"]:
            del cfg["network"]["bonds"]
        return yaml.dump(cfg, default_flow_style=False, sort_keys=False)

    # Storage nodes. The switch storage port is either:
    #   - ACCESS/untagged on the storage VLAN (collapsed-core archs, e.g.
    #     `access 500`) → the server must put the IP on the RAW bond and send
    #     untagged frames; or
    #   - a TAGGED trunk member (e.g. `vlan 400,500` native 300 on 2-4-5-800)
    #     → the server must tag via bond.<vlan>.
    # `common.storage_vlan_tagged` (set by the parser from the Storage role's
    # actual VLAN membership) selects which. A mismatch drops frames at the
    # switch port → gateway unreachable. Defaults to untagged when absent (the
    # historically-safe collapsed-core behavior).
    #
    # Dual-bond same-subnet PBR (orthogonal to tagging): when 4 storage NICs
    # split into two bonds in the same storage /24, each bond gets its own PBR
    # /32 src rule + table so the kernel's connected-route ambiguity doesn't
    # race bond0 vs bond1 ARP resolution.
    if _role == "storage" or (not _role and node_name.startswith("storage")):
        data = [i for i in ifaces.get("storage", ifaces.get("cpu", [])) if i != "eth0"]
        storage_gateway = common.get("storage_gateway", "")
        storage_vlan = int(common.get("storage_vlan", 500))
        tagged = bool(common.get("storage_vlan_tagged", False))
        cfg = _init_cfg()
        if not data:
            return yaml.dump(cfg, default_flow_style=False, sort_keys=False)
        cfg["network"]["bonds"] = {}
        cfg["network"]["vlans"] = {}
        for iface in data:
            cfg["network"]["ethernets"][iface] = {"dhcp4": False, "optional": True}

        def _add_storage_bond(bond_name, members, ip, table):
            cfg["network"]["bonds"][bond_name] = {
                "interfaces": members,
                "parameters": {"mode": "active-backup", "primary": members[0],
                               "mii-monitor-interval": 100},
            }
            src = ip.split("/")[0]
            policy = [{"from": f"{src}/32", "table": table}]
            routes = [{"to": "0.0.0.0/0", "via": storage_gateway, "table": table}]
            ns = {"addresses": ["8.8.8.8", "8.8.4.4"]}
            if tagged:
                # Tag storage on a VLAN sub-interface of the bond.
                cfg["network"]["vlans"][f"{bond_name}.{storage_vlan}"] = {
                    "id": storage_vlan, "link": bond_name, "addresses": [ip],
                    "nameservers": ns, "routing-policy": policy, "routes": routes,
                }
            else:
                # Untagged access port: IP rides the raw bond.
                cfg["network"]["bonds"][bond_name].update({
                    "addresses": [ip], "nameservers": ns,
                    "routing-policy": policy, "routes": routes,
                })

        bond_ip1 = dev.get("bond_ip1") or ""
        bond_ip2 = dev.get("bond_ip2") or ""
        if len(data) >= 2 and bond_ip1:
            _add_storage_bond("bond0", [data[0], data[1]], bond_ip1, storage_vlan)
        if len(data) >= 4 and bond_ip2:
            # Distinct table id for bond1 so its default route doesn't collide.
            _add_storage_bond("bond1", [data[2], data[3]], bond_ip2, storage_vlan + 1)
        if not cfg["network"]["vlans"]:
            del cfg["network"]["vlans"]
        if not cfg["network"]["bonds"]:
            del cfg["network"]["bonds"]
        return yaml.dump(cfg, default_flow_style=False, sort_keys=False)

    # Support / control-plane nodes
    # Includes the legacy `support-` prefix and the 2-8-9-800-style
    # bcm-/slurm-/k8s- prefixes — they all attach via dual DPU ports
    # to the converged-fabric (CSL) switches with VLAN-tagged Support
    # traffic (default native VLAN 400).
    if _role in ("support", "k8s", "bcme") or (not _role and (
            node_name.startswith("support") or node_name.startswith("bcm-")
            or node_name.startswith("slurm-") or node_name.startswith("k8s-"))):
        data = [i for i in ifaces.get("support", ifaces.get("cpu", [])) if i != "eth0"]
        return _build_bond_vlan_netplan(
            data, dev.get("bond_ip1", ""), dev.get("bond_ip2", ""),
            common.get("support_network", ""), common.get("support_gateway", ""),
            int(common.get("support_vlan", 400)),
        )

    return ""


# Switch hostname prefixes — nodes with front-panel swp ports that receive the
# NVUE deferred-apply NI, and must NEVER get a server/Ubuntu NI. Must list EVERY
# switch role, including the split N/S + GPU roles (cl/cs/gl/gs) introduced by the
# 2026-06 role rename, and the pre_cabled_rack rack-local OOB switches
# (rack-oob-su-<SU>-<N>) introduced by ADR-0060. Omitting those here is what
# handed multi-tier largescale switches a server NI (apt-get) instead of their
# config → stuck "ZTP in progress" under NOZTP. Single source of truth:
# generate-node-instructions.py imports this.
SWITCH_HOST_PREFIXES = ("core-", "csl-", "cl-", "cs-", "gsl-", "gl-", "gs-", "oob-switch-", "rack-oob-")
SERVER_NI_SKIP_PREFIXES = SWITCH_HOST_PREFIXES + ("oob-server", "dhcp-", "cust-net-edge", "air-oob")


def build_server_ni_commands(node_name: str, dev: dict, common: dict) -> list[str]:
    """Build the Node Instruction command list for one server node.

    Shared by air-deploy.py (runtime injection) and generate-node-instructions.py
    (review-time .sh file emission) so both produce identical content.

    Returns [] if the node has no eth0_ip (nothing to configure).
    """
    if not dev.get("eth0_ip"):
        return []

    commands = [f"# Full server configuration for {node_name}"]

    # Hostname — quote the Excel-derived name so a hostname like `n;reboot` or
    # `n$(id)` can't break out into arbitrary shell during first-boot
    # provisioning (same class-of-bug fix as ztp.sh.j2 | quote and airlib/ssh.py).
    commands.append(f"hostnamectl set-hostname {shlex.quote(node_name)}")

    # Netplan config — base64 to avoid heredoc/quoting issues in Air shell executor.
    # Air's image ships `/etc/netplan/40-air.yaml` and cloud-init drops
    # `/etc/netplan/50-cloud-init.yaml`, both of which set `dhcp4: true` for eth0.
    # Netplan merges every .yaml in /etc/netplan/, and the other two files
    # override our `dhcp4: false`/`dhcp6: false` — leaving DHCP enabled and
    # networkd stuck in `configuring` waiting for a non-existent DHCP server.
    # Remove the others before applying ours.
    netplan_yaml = _render_server_netplan(node_name, dev, common)
    if netplan_yaml:
        b64 = base64.b64encode(netplan_yaml.encode()).decode()
        commands.append("rm -f /etc/netplan/40-air.yaml /etc/netplan/50-cloud-init.yaml")
        commands.append(f"echo '{b64}' | base64 -d > /etc/netplan/10-netcfg.yaml")
        commands.append("chmod 600 /etc/netplan/10-netcfg.yaml")
        commands.append("netplan apply || true")

    # ARP-flux fix — hosts with multiple L3 interfaces in the SAME subnet need
    # strict ARP so Linux doesn't answer/announce on the "wrong" NIC. Without
    # it, EVPN MAC-mobility flaps the anycast VRR binding and the gateway
    # blackholes replies. Two host classes hit this:
    #
    #  * Dual-plane GPU hosts (`gpu_interfaces`/`gpu_ips`): 16 NICs across
    #    plane1+plane2 -> ~85% loss on gpu-gw ping. The parser also emits
    #    per-NIC PBR tables (`gpu_interfaces[].table`) — a route table per NIC
    #    with one default route + a `from <NIC-IP>/32 lookup <table>` rule — so
    #    `arp_filter=1` is safe here: the route lookup for an ARP request now
    #    resolves to a single unambiguous interface.
    #
    #  * Dual-bond storage hosts (`bond_ip1` + `bond_ip2`, both in the storage
    #    subnet/VLAN): two bonds, one subnet -> intermittent 100% loss on
    #    storage-gw (root-caused live on a 2-8-9-800 largescale sim — only the
    #    storage nodes were missing these sysctls the GPU hosts already got).
    #    Storage has NO per-NIC PBR, so `arp_filter=1` would be ambiguous;
    #    `arp_ignore=1` + `arp_announce=2` (the canonical flux fix, matching
    #    `roles/nodes/tasks/main.yml`) is sufficient and safe.
    #
    # Production BlueField-3 SuperNICs handle this in hardware; the sysctls are
    # the Air-sim equivalent.
    is_gpu_host = bool(dev.get("gpu_interfaces") or dev.get("gpu_ips"))
    is_multi_bond_host = bool(dev.get("bond_ip1") and dev.get("bond_ip2"))
    if is_gpu_host or is_multi_bond_host:
        arp_sysctls = [
            "net.ipv4.conf.all.arp_ignore=1",
            "net.ipv4.conf.all.arp_announce=2",
        ]
        if is_gpu_host:  # arp_filter is only safe with the gpu per-NIC PBR tables
            arp_sysctls.append("net.ipv4.conf.all.arp_filter=1")
        for _s in arp_sysctls:
            commands.append(f"sysctl -w {_s}")
        commands.append("cat > /etc/sysctl.d/90-arp-flux.conf <<'EOF'\n"
                        + "".join(f"{_s}\n" for _s in arp_sysctls)
                        + "EOF")

    # LLDP
    commands.append("DEBIAN_FRONTEND=noninteractive apt-get update -qq")
    commands.append("DEBIAN_FRONTEND=noninteractive apt-get install -y -qq lldpd")
    commands.append('echo "configure lldp portidsubtype ifname" > /etc/lldpd.d/port_info.conf')
    commands.append("systemctl restart lldpd")

    return commands


def _inject_server_full_config(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    inv_dir: Path,
    topology_json: dict,
) -> int:
    """Inject full server configuration (hostname + netplan + lldp) via Node Instructions.

    This replaces the deploy-servers-via-jump Ansible path for Air deployments.
    Each server gets a single Node Instruction that configures everything on first boot.
    """
    main_yml = inv_dir / "group_vars" / "all" / "main.yml"
    if not main_yml.exists():
        return 0
    with open(main_yml) as f:
        all_vars = yaml.safe_load(f) or {}
    devices = all_vars.get("devices", {})
    common = all_vars.get("common", {})
    if not devices:
        return 0

    topo_nodes = set(topology_json.get("content", {}).get("nodes", {}).keys())

    jobs = []
    for node_name, dev in sorted(devices.items()):
        if node_name not in topo_nodes:
            continue
        if any(node_name.startswith(p) for p in SERVER_NI_SKIP_PREFIXES):
            continue

        commands = build_server_ni_commands(node_name, dev, common)
        if not commands:
            continue
        jobs.append({
            "node_name": node_name,
            "commands": commands,
            "name": f"{node_name}-full-config",
            "wait_for_network": False,
        })

    return _parallel_create_nis(client, base_url, token, sim_id, jobs)


# ---------------------------------------------------------------------------
# No-ZTP switch configuration via Node Instructions
# ---------------------------------------------------------------------------

def _parallel_create_nis(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    jobs: list[dict],
    *,
    max_workers: int = 12,
    best_effort: bool = False,
) -> int:
    """POST many Node Instructions concurrently. Returns the count that succeeded.

    ``jobs`` is a list of dicts forwarded as create_node_instruction kwargs
    (node_name, commands, name, wait_for_network, reachability_ip). The node
    name->id cache is warmed once up front so the threads don't race to fetch
    it. httpx.Client is safe to share across threads. ``best_effort`` swallows
    per-node errors (matches the old disable-unattended behavior); otherwise the
    failing node name is logged.
    """
    if not jobs:
        return 0
    # Warm the per-sim node-id cache once (single fetch) before fanning out.
    prefetch_node_ids(client, base_url, token, sim_id)

    def _one(job: dict):
        try:
            create_node_instruction(
                client, base_url, token, sim_id,
                node_name=job["node_name"],
                commands=job["commands"],
                name=job.get("name", ""),
                wait_for_network=job.get("wait_for_network", False),
                reachability_ip=job.get("reachability_ip"),
            )
            return (job["node_name"], None)
        except AirError as exc:
            return (job["node_name"], exc)

    ok = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for name, err in ex.map(_one, jobs):
            if err is None:
                ok += 1
            elif not best_effort:
                console.print(f"  [yellow]Warning:[/] {name}: {err}")
    return ok


def _inject_switch_config_via_ni(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    inv_dir: Path,
    configs_dir: Path,
    topology_json: dict,
) -> int:
    """Inject the rendered NVUE config into every switch via Node Instructions.

    Used when --no-ztp is set. Each switch receives a single Node Instruction
    that:
      1. Decodes the rendered <hostname>-config.sh from base64
      2. Sources it (stages all `nv set` commands)
      3. Stages the cumulus password change too
      4. Runs `nv config apply -y && nv config save` (one apply pass)
      5. Sets the Linux passwd for the cumulus user

    This skips the entire DHCP→ZTP→fetch→apply→reboot path. Switches come up
    with config already applied — typical Air boot+apply finishes in ~30s
    instead of 5+ minutes per switch.

    Reads inventory hosts file to enumerate switches (csl/gsl/oob/core/edge).
    air-oob-switch is configured separately by _inject_air_oob_instructions.
    Returns the number of switches configured.
    """
    hosts_file = inv_dir / "hosts"
    if not hosts_file.exists():
        return 0

    # Parse the [switches:children] section to discover all switch hosts.
    # Simpler approach: walk groups and find any host whose role is a switch
    # (using the same classification scheme as elsewhere in the codebase).
    # Read hosts under [csl], [gsl_plane1], [gsl_plane2], [oob], [core] sections.
    # We don't pull from Ansible directly; the hosts file's syntax is regular
    # enough to parse with a quick line walker.
    switches: list[str] = []
    current_group: str = ""
    for line in hosts_file.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("[") and s.endswith("]"):
            # Group header. Strip ":children" / ":vars" suffixes.
            current_group = s[1:-1].split(":")[0]
            continue
        if "=" in s:  # ansible_user=... etc.
            continue
        # Hosts in switch groups (skip child-group markers like 'core' under [switches:children])
        if current_group in ("core", "csl", "cs", "cl", "gsl_plane1", "gsl_plane2",
                             "gl_plane1", "gl_plane2", "gs_plane1", "gs_plane2",
                             "oob", "edge"):
            # Expand range syntax: oob-switch-[01:02] → oob-switch-01, oob-switch-02
            if "[" in s and ":" in s and "]" in s:
                prefix, rng = s.split("[", 1)
                lo_hi, suffix = rng.split("]", 1)
                lo, hi = lo_hi.split(":")
                width = max(len(lo), len(hi))
                for i in range(int(lo), int(hi) + 1):
                    switches.append(f"{prefix}{str(i).zfill(width)}{suffix}")
            else:
                switches.append(s)

    topo_nodes = set(topology_json.get("content", {}).get("nodes", {}).keys())
    switches = sorted(set(s for s in switches if s in topo_nodes))
    if not switches:
        return 0

    # Read switch password from secrets.yml (plaintext for dev; vault-decrypted
    # path is handled by Ansible elsewhere).
    secrets_path = inv_dir / "group_vars" / "all" / "secrets.yml"
    switch_password = "Cumu1usLinux!"  # default fallback
    if secrets_path.exists():
        with open(secrets_path) as f:
            secrets = yaml.safe_load(f) or {}
        switch_password = secrets.get("switch_password", switch_password)

    # Build the per-switch NI command lists (local file I/O — fast), then POST
    # them all concurrently. Previously this looped serially and each
    # create_node_instruction re-fetched every node, which dominated maxscale
    # air-deploy time.
    jobs = []
    for hostname in switches:
        config_file = configs_dir / f"{hostname}-config.sh"
        if not config_file.exists():
            console.print(f"  [yellow]Warning:[/] {hostname}: config file not found at {config_file}")
            continue

        config_text = config_file.read_text()

        # Look up this switch's mgmt IP from host_vars.
        host_ip = None
        host_vars_path = inv_dir / "host_vars" / f"{hostname}.yml"
        if host_vars_path.exists():
            with open(host_vars_path) as f:
                hv = yaml.safe_load(f) or {}
            host_ip = hv.get("ansible_host")

        commands = build_switch_ni_commands(hostname, config_text, host_ip, switch_password)
        jobs.append({
            "node_name": hostname,
            "commands": commands,
            "name": f"{hostname}-no-ztp-config",
            "wait_for_network": False,
        })

    return _parallel_create_nis(client, base_url, token, sim_id, jobs)


def build_switch_ni_commands(
    hostname: str, config_text: str, host_ip: str | None, switch_password: str
) -> list[str]:
    """Build the No-ZTP deferred-apply Node Instruction command list for one switch.

    Shared by air-deploy.py (runtime injection) and generate-node-instructions.py
    (review-time .sh emission). The returned commands:
      - drop the rendered NVUE config + an apply wrapper + a systemd oneshot
        unit onto the switch
      - enable + start the unit so it runs after multi-user.target on first
        boot (avoiding the ifreload-nvue race we kept losing on synchronous
        applies)
      - cancel any in-progress ZTP so it doesn't fight our apply
    """
    config_b64 = base64.b64encode(config_text.encode()).decode()

    # Static eth0 lines — only injected when we have a usable IP.
    # /24 matches the air-mgmt subnet (always 172.20.0.0/24 in our setup).
    # We disable the dhcp-client too so the rendered config's default
    # DHCP behavior doesn't fight our static address.
    if host_ip:
        static_eth0_lines = (
            "# NOZTP: no DHCP server, set eth0 static (matches the IP\n"
            "# dnsmasq would have handed out for this switch's MAC).\n"
            "# Use 5.16 NVUE syntax — `ipv4 address`, not `ip address` —\n"
            "# otherwise apply succeeds but eth0 doesn't actually get the\n"
            "# IP and the switch becomes unreachable (silent rollback).\n"
            "nv set interface eth0 ipv4 dhcp-client state disabled\n"
            f"nv set interface eth0 ipv4 address {host_ip}/24\n"
        )
        eth0_linux_lines = (
            "# Belt-and-suspenders: set eth0 at the Linux level too so we\n"
            "# stay reachable even if NVUE apply rolls back below.\n"
            "ip link set eth0 up || true\n"
            f"ip addr replace {host_ip}/24 dev eth0 || true\n"
        )
    else:
        static_eth0_lines = (
            "# WARNING: no ansible_host in host_vars; eth0 left unconfigured.\n"
        )
        eth0_linux_lines = ""

    apply_script = (
        "#!/bin/bash\n"
        # NOTE: no top-level `set -e` — we manage failure via the retry loop so
        # a single transient nvued error doesn't strand the switch.
        "set -x\n"
        "# 1. Linux-level eth0 for debug access during apply.\n"
        + eth0_linux_lines
        + "# 2. Stage + apply NVUE config, RETRYING on transient nvued errors.\n"
        "#    During a large concurrent first boot (e.g. 232-node maxscale) the\n"
        "#    nvued REST daemon can return 'The server encountered an internal\n"
        "#    error' mid-apply — especially on the multi-edge bridge hub with\n"
        "#    its big bridge-domain config. A single failure used to leave\n"
        "#    era-apply.service failed (set -e exited before disable), stranding\n"
        "#    the switch (e.g. cust-net-edge-01: bridge SVI + EXIT eBGP never\n"
        "#    came up). Retry until nvued settles.\n"
        "ok=0\n"
        "for attempt in 1 2 3 4 5 6; do\n"
        "  if (\n"
        "      set -e\n"
        f"      . /opt/era/{hostname}-config.sh\n"
        + static_eth0_lines
        + "      nv config apply --assume-yes\n"
        # `nv config apply` can print 'Error: The server encountered an
        # internal error' and STILL EXIT 0 — observed on cust-net-edge-02
        # (2-4-5-800 e2e, 2026-08-10): `nv config save` ran 92ms after the
        # error inside this very `set -e` subshell, which is only possible
        # with a zero exit. The apply's exit status therefore proves nothing,
        # and the retry loop below never fired: one apply in the whole log,
        # ok=1, unit self-disabled, era-apply.service reported SUCCESS on a
        # switch with no config and hostname `cumulus`.
        #
        # So read the APPLIED config back and require this switch's identity
        # in it. Written to a file rather than piped: no SIGPIPE ambiguity,
        # and it leaves the evidence on the box for post-mortem (same rule as
        # ADR-0052 — do not discard what a later failure will need).
        + "      nv config show -o commands > /opt/era/applied-config.txt\n"
        + "      grep -qF "
        + shlex.quote(f"nv set system hostname {hostname}")
        + " /opt/era/applied-config.txt || {\n"
        + "        echo 'era-apply: apply exited 0 but the applied config has no"
        + f" hostname {hostname} — treating as FAILED' >&2\n"
        + "        exit 1\n"
        + "      }\n"
        + "      nv config save\n"
        "  ); then ok=1; break; fi\n"
        "  echo \"era-apply: attempt $attempt failed (nvued transient?); \"\\\n"
        "       \"discarding pending + retrying in 20s\" >&2\n"
        "  nv config detach 2>/dev/null || true\n"
        "  sleep 20\n"
        "done\n"
        "if [ \"$ok\" != 1 ]; then\n"
        "  echo 'era-apply: all attempts failed — leaving unit enabled for retry' >&2\n"
        "  exit 1\n"
        "fi\n"
        # chpasswd AFTER a successful nv config apply to avoid the PAM
        # reconcile_password_with_nvue.sh hook racing with nvued at boot.
        # The hook calls `nv config apply` internally; if nvued is still
        # initializing, the CLI hangs and blocks the entire apply.sh.
        + "set +x\n"
        + f"echo {shlex.quote('cumulus:' + switch_password)} | chpasswd\n"
        + "set -x\n"
        "# First-boot only — only disable after a SUCCESSFUL apply, so a failed\n"
        "# run stays enabled and re-attempts on the next boot.\n"
        "systemctl disable era-apply.service\n"
        "# Stop the retry timer too — it exists only to cover a missed first\n"
        "# trigger, so once the apply has landed it has no further job.\n"
        "systemctl disable --now era-apply.timer 2>/dev/null || true\n"
    )
    apply_b64 = base64.b64encode(apply_script.encode()).decode()

    unit_text = (
        "[Unit]\n"
        "Description=ERA first-boot NVUE config apply\n"
        "After=multi-user.target nvued.service ifreload-nvue.service\n"
        "Requires=nvued.service\n"
        "Wants=ifreload-nvue.service\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        "Environment=HOME=/root\n"
        "Environment=USER=root\n"
        "Environment=LOGNAME=root\n"
        "Environment=SHELL=/bin/bash\n"
        "Environment=LANG=C\n"
        "Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
        "ExecStart=/opt/era/apply.sh\n"
        "RemainAfterExit=true\n"
        "StandardOutput=journal\n"
        "StandardError=journal\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )
    unit_b64 = base64.b64encode(unit_text.encode()).decode()

    # Retry timer — the apply MUST NOT depend on either trigger below firing.
    #
    # Both existing triggers can miss, and when they do the node is stranded
    # until someone reboots it:
    #   * WantedBy=multi-user.target only fires if the NI lands BEFORE that
    #     target is reached. A node with fast networking reaches it first.
    #   * the explicit `systemctl start --no-block … || true` is best-effort;
    #     any failure is swallowed and nothing ever retries.
    #
    # Observed 2026-08-05 on 2-4-5-800: NI files landed on cust-net-edge-01 and
    # -02 76ms apart (12:31:19.028 / 12:31:18.952), yet era-apply ran at
    # 12:32:42 on -01 and not until a manual reboot at 12:46:27 on -02. The
    # discriminator was boot speed — networking.service took 1m07s on -01 but
    # 418ms on -02, so -02 passed multi-user.target before the NI arrived and
    # lost its only remaining trigger. The 8 switches bridged behind -02 stayed
    # unreachable, which is what the e2e cell reports as a flat 0/16.
    #
    # apply.sh is already idempotent and self-disabling on success, so simply
    # re-running it until it succeeds is safe. The timer disables itself in the
    # same breath, so this costs nothing once the apply lands.
    timer_text = (
        "[Unit]\n"
        "Description=Retry ERA first-boot NVUE apply until it succeeds\n"
        "\n"
        "[Timer]\n"
        "OnBootSec=30s\n"
        "OnUnitInactiveSec=30s\n"
        "AccuracySec=1s\n"
        "Unit=era-apply.service\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )
    timer_b64 = base64.b64encode(timer_text.encode()).decode()

    return [
        f"# No-ZTP deferred-apply NI for {hostname}.",
        "# Drops rendered NVUE config + apply wrapper + a systemd oneshot,",
        "# enables the unit (WantedBy=multi-user.target), and exits. systemd",
        "# schedules era-apply.service after multi-user.target — by which",
        "# point ifreload-nvue.service has completed its initial pass and",
        "# our apply runs cleanly with no race.",
        "# A retry timer backs both triggers up; see the comment in",
        "# build_switch_ni_commands for why neither is sufficient alone.",
        "set -x",
        "mkdir -p /opt/era",
        f"echo '{config_b64}' | base64 -d > /opt/era/{hostname}-config.sh",
        f"chmod 755 /opt/era/{hostname}-config.sh",
        f"echo '{apply_b64}' | base64 -d > /opt/era/apply.sh",
        "chmod 755 /opt/era/apply.sh",
        f"echo '{unit_b64}' | base64 -d > /etc/systemd/system/era-apply.service",
        f"echo '{timer_b64}' | base64 -d > /etc/systemd/system/era-apply.timer",
        "systemctl daemon-reload || true",
        "systemctl enable era-apply.service || true",
        # Cancel any in-progress ZTP so it doesn't fight our apply.
        "/usr/lib/cumulus/ztp -X 2>&1 || /usr/lib/cumulus/ztp -d 2>&1 || true",
        # Kick the unit; if multi-user.target hasn't fired yet, WantedBy starts it later.
        "systemctl start --no-block era-apply.service || true",
        # Safety net: fires 30s after boot and every 30s while era-apply is
        # inactive, so a missed trigger costs seconds instead of a reboot.
        "systemctl enable --now era-apply.timer || true",
    ]


def _inject_dhcp_oob_netplan_ni(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    inv_dir: Path,
    topology_json: dict,
) -> bool:
    """Bring up dhcp-oob's eth1/eth2 via Node Instructions in NOZTP mode.

    Normally this is done by `setup-ztp-server.yml` (Step 8), which we skip
    when NOZTP=1. Without it dhcp-oob has only eth0 (Air mgmt-link, 169.254.x.x)
    and can't reach the OOB / Air-mgmt subnets — validate-* playbooks fail
    because dhcp-oob is the SSH jump host for everything else.

    Reads the same `ztp_interfaces` list the playbook uses and renders an
    equivalent /etc/netplan/99-ztp-interfaces.yaml on dhcp-oob. Returns True
    if the NI was queued.
    """
    if "dhcp-oob" not in topology_json.get("content", {}).get("nodes", {}):
        return False

    main_yml = inv_dir / "group_vars" / "all" / "main.yml"
    if not main_yml.exists():
        return False
    with open(main_yml) as f:
        all_vars = yaml.safe_load(f) or {}
    ztp_ifaces = all_vars.get("ztp_interfaces") or []
    if not ztp_ifaces:
        return False

    # Build netplan YAML matching roles/ztp-server/templates/netplan-ztp.yaml.j2
    netplan = {"network": {"version": 2, "renderer": "networkd", "ethernets": {}}}
    for iface in ztp_ifaces:
        name = iface.get("name")
        ip = iface.get("ip")
        net = iface.get("network", "")
        prefix = net.split("/")[1] if "/" in net else "24"
        if not (name and ip):
            continue
        netplan["network"]["ethernets"][name] = {
            "addresses": [f"{ip}/{prefix}"],
            "dhcp4": False,
            "dhcp6": False,
        }
    if not netplan["network"]["ethernets"]:
        return False

    netplan_yaml = yaml.dump(netplan, default_flow_style=False, sort_keys=False)
    netplan_b64 = base64.b64encode(netplan_yaml.encode()).decode()

    commands = [
        "# NOZTP: bring up dhcp-oob's eth1/eth2 (normally done by",
        "# setup-ztp-server.yml, which is skipped when NOZTP=1).",
        "set -x",
        f"echo '{netplan_b64}' | base64 -d > /etc/netplan/99-ztp-interfaces.yaml",
        "chmod 600 /etc/netplan/99-ztp-interfaces.yaml",
        "netplan apply || true",
    ]

    try:
        create_node_instruction(
            client, base_url, token, sim_id,
            node_name="dhcp-oob",
            commands=commands,
            name="dhcp-oob-noztp-netplan",
            wait_for_network=False,
        )
        console.print(f"  ✓ dhcp-oob: NI queued ({len(netplan['network']['ethernets'])} interfaces)")
        return True
    except AirError as exc:
        console.print(f"  [red]ERROR:[/] dhcp-oob: NI POST failed — {exc}")
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an Air simulation and configure SSH access.",
    )
    parser.add_argument("--arch", required=True, help="Architecture (e.g., 2-8-5-200)")
    parser.add_argument("--site", default="default", help="Site name (default: 'default')")
    parser.add_argument("--title", help="Custom simulation title (default: ERA-<ARCH>-<SITE>)")
    parser.add_argument("--skip-budget-check", action="store_true",
                        help="Skip pre-deploy resource budget check")
    parser.add_argument("--server-config", action="store_true",
                        help="Inject full server config (hostname, netplan, lldp) via Node Instructions")
    parser.add_argument("--no-ztp", action="store_true",
                        help="Skip ZTP path entirely — inject rendered NVUE configs into "
                             "every switch via Node Instructions (Air-only fast path). "
                             "Switches come up with config already applied; no DHCP/HTTP "
                             "fetches and no reboot loop. Default: ZTP-on (off).")
    parser.add_argument("--retry-on-capacity", type=int, default=0, metavar="N",
                        help="When sim start fails with Air platform 'out of capacity', "
                             "destroy the failed sim, wait, and retry up to N times. "
                             "Default 0 = no retry (current behavior).")
    parser.add_argument("--retry-delay", type=int, default=300, metavar="SECONDS",
                        help="Seconds to wait between capacity retries. Default 300 (5 min).")
    args = parser.parse_args()

    # NOZTP implies full server config: the L2-era pipeline always brought
    # bonds/VLANs/netplan up via NI in NOZTP mode, and validate-* flows
    # depend on those interfaces existing. Honor an explicit --server-config
    # too; this only flips the default when the operator didn't pass it.
    if args.no_ztp and not args.server_config:
        args.server_config = True
        console.print(
            "[bold yellow]NOZTP:[/] enabling --server-config implicitly "
            "(bonds/VLANs/netplan via Node Instructions)."
        )

    project_root = Path(__file__).resolve().parent.parent
    arch = args.arch
    site = args.site
    sim_title = args.title or f"ERA-{site}-{arch}"

    # Paths
    inv_dir = project_root / "output" / arch / site / "inventory"
    topology_path = project_root / "output" / arch / site / "topology" / f"{arch}-topology.json"

    if not topology_path.exists():
        console.print(f"[red]Error:[/] Topology not found: {topology_path}")
        console.print(f"  Run 'make generate ARCH={arch}' first.")
        return 1

    if not inv_dir.exists():
        console.print(f"[red]Error:[/] Inventory not found: {inv_dir}")
        console.print(f"  Run 'make generate ARCH={arch}' first.")
        return 1

    # Pin the air-mgmt plane from the generated inventory BEFORE anything
    # builds a Node Instruction. Every air-mgmt address this script emits is
    # derived from it (see set_air_mgmt_subnet), so it has to be resolved
    # before the first _inject_* call, not alongside them.
    _main_yml = inv_dir / "group_vars" / "all" / "main.yml"
    if _main_yml.exists():
        try:
            with open(_main_yml) as _f:
                set_air_mgmt_subnet((yaml.safe_load(_f) or {}).get("air_mgmt_subnet"))
        except (OSError, yaml.YAMLError) as exc:
            console.print(f"[yellow]Warning:[/] could not read air_mgmt_subnet: {exc}")
    if air_mgmt_network() != DEFAULT_AIR_MGMT_SUBNET:
        console.print(f"  Air-mgmt plane: {air_mgmt_network()} (non-default)")

    # Same for the OOB plane (ADR-0028): `common.oob_network`/`oob_gateway` are
    # Excel-derived and already in the inventory; pin them before any Node
    # Instruction is built so infra feet, PBR next-hops and server eth0 netplan
    # all land on the workbook's OOB VLAN instead of a literal 192.168.200.x.
    if _main_yml.exists():
        try:
            with open(_main_yml) as _f:
                _common = (yaml.safe_load(_f) or {}).get("common", {}) or {}
            set_oob_plane(_common.get("oob_network"), _common.get("oob_gateway"))
        except (OSError, yaml.YAMLError) as exc:
            console.print(f"[yellow]Warning:[/] could not read oob_network: {exc}")
    if oob_network() != OOB_SUBNET:
        console.print(f"  OOB plane: {oob_network()} gw {oob_gateway()} (non-default)")

    # Archive any stale local reports before this fresh sim provisions.
    # upload-reports.yml uses Ansible's with_fileglob, which would ship any
    # leftover .txt + raw/* from a prior sim onto the new sim's status page.
    # Move them aside so the new sim only receives reports this run produced.
    _archive_stale_local_reports(project_root, arch, site)

    # Load configuration
    try:
        config = load_air_config(arch, site, project_root)
        require_config(config, "base_url", "api_key")
    except AirError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return exc.exit_code

    base_url = config["base_url"]
    ssh_key_path = config.get("ssh_key_path", "~/.ssh/id_ed25519")

    # SSH key reminder
    try:
        fingerprint = get_key_fingerprint(ssh_key_path)
        console.print(f"  SSH key: {fingerprint}")
        console.print("  Ensure this key is registered in Air: Settings -> SSH Keys")
    except AirError as exc:
        console.print(f"[yellow]Warning:[/] Could not read SSH key: {exc}")

    # Load topology
    topology_data = topology_path.read_bytes()
    topology_json = json.loads(topology_data)
    topology_nodes = topology_json.get("content", {}).get("nodes", {})
    console.print(f"  Topology: {len(topology_nodes)} nodes")

    # Disable zstd Accept-Encoding — httpx has a bug with zstd decompressor reuse
    headers = {"Accept-Encoding": "gzip, deflate, br"}
    with httpx.Client(timeout=120, verify=ssl.create_default_context(), headers=headers) as client:
        # Authenticate
        console.print(f"Authenticating with {base_url}...")
        try:
            token = authenticate(
                client, base_url,
                config.get("username", ""),
                config["api_key"],
            )
            console.print("  Authenticated successfully")
        except AirError as exc:
            console.print(f"[red]Error:[/] {exc}")
            return exc.exit_code

        # Pre-deploy budget check
        if not args.skip_budget_check:
            try:
                budget = get_resource_budget(client, base_url, token)
                req_cpu = sum(p.get("cpu", 2) for p in topology_nodes.values())
                req_mem = sum(p.get("memory", 2048) for p in topology_nodes.values())
                proj_cpu = budget.cpu_used + req_cpu
                proj_mem = budget.memory_used + req_mem
                warns = []
                if budget.cpu > 0 and proj_cpu / budget.cpu > 0.90:
                    warns.append(f"CPU: {proj_cpu}/{budget.cpu} vCPUs")
                if budget.memory > 0 and proj_mem / budget.memory > 0.90:
                    warns.append(f"Memory: {proj_mem}/{budget.memory} MB")
                if warns:
                    console.print("[yellow]Warning:[/] Deployment would exceed 90% of budget:")
                    for w in warns:
                        console.print(f"  - {w}")
                    console.print("  Use --skip-budget-check to override")
                else:
                    console.print(f"  Budget OK: {req_cpu} CPU, {req_mem} MB memory needed")
            except AirError as exc:
                console.print(f"[yellow]Warning:[/] Budget check failed: {exc}")

        # Check for existing simulation with same name
        try:
            existing = list_simulations(client, base_url, token)
            dupes = [s for s in existing if s.title == sim_title and getattr(s, 'state', '').upper() != 'DELETED']
            if dupes:
                console.print(f"[yellow]Warning:[/] Simulation '{sim_title}' already exists:")
                for s in dupes:
                    owner_str = f"  owner: {s.owner}" if s.owner else ""
                    console.print(f"  [{s.state}] {s.id}{owner_str}")
                try:
                    response = input("  Create another with the same name? [y/N]: ").strip().lower()
                except EOFError:
                    # Non-interactive (CI / piped `make deploy` / nohup): don't
                    # crash with a raw EOFError — cancel cleanly with guidance.
                    console.print("  No TTY to confirm and a same-named sim exists — cancelled. "
                                  "Destroy it first (make air-destroy) or deploy with a unique SITE.")
                    return 0
                if response != "y":
                    console.print("  Cancelled.")
                    return 0
        except AirError as exc:
            console.print(f"[yellow]Warning:[/] Could not check existing simulations: {exc}")

        # Import + start + poll loop with optional capacity retry.
        # max_attempts = 1 + args.retry_on_capacity (default 1 = no retry).
        max_attempts = 1 + max(0, args.retry_on_capacity)
        deploy_attempt = 0
        sim_id = None
        sim_actual_title = sim_title
        topology_json = json.loads(topology_data)
        node_errors: list = []
        final_state = None
        infra = _resolve_infra_nodes(topology_json)
        while True:
            deploy_attempt += 1
            if deploy_attempt > 1:
                console.print(
                    f"[bold yellow]Retry {deploy_attempt}/{max_attempts}[/] — "
                    f"waiting {args.retry_delay}s for Air capacity to free up..."
                )
                try:
                    time.sleep(args.retry_delay)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Retry cancelled by user.[/]")
                    return 1

            # Import topology
            console.print(f"Importing topology: {topology_path.name}...")
            try:
                sim = import_topology(client, base_url, token, topology_data)
            except AirError as exc:
                console.print(f"[red]Error:[/] {exc}")
                return exc.exit_code
            sim_id = sim["id"]
            sim_actual_title = sim.get("name") or sim.get("title") or sim_title
            console.print(f"  Created simulation: {sim_actual_title} ({sim_id})")

            # Wait for simulation to reach INACTIVE (nodes become queryable)
            console.print("Waiting for simulation to be ready...")
            state = wait_for_inactive(client, base_url, token, sim_id)
            if state == "INVALID":
                # Air accepts the import with HTTP 200 and a simulation id, then
                # rejects it asynchronously into INVALID with ZERO nodes, and
                # puts no reason on the simulation object. The overwhelmingly
                # common cause is a node below its image's declared
                # `minimum_resources` — Air enforces cpu, memory AND storage,
                # and one offending node rejects the WHOLE simulation.
                #
                # This used to be a warning, so the run carried on and issued
                # every Node Instruction against a sim with no nodes, emitting
                # a wall of "Node 'X' not found in simulation. Available: " and
                # finally dying at start with "must be in the INACTIVE state" —
                # none of which names the actual cause. Fail here instead.
                raise AirAPIError(
                    f"Simulation {sim_id} was rejected by Air (state INVALID, "
                    "no nodes created).\n"
                    "  Air returns HTTP 200 on import and rejects "
                    "asynchronously, so this is the first point it is visible.\n"
                    "  Most likely cause: a node is below its image's declared "
                    "minimum_resources (cpu, memory or storage). Air enforces "
                    "all three, at exactly the declared value, and one "
                    "under-provisioned node invalidates the entire simulation.\n"
                    "  Check the image's minimum via GET /api/v3/images/ and "
                    "compare against NODE_DEFAULTS in "
                    "scripts/topology_generator.py.\n"
                    "  See internal-docs/validation-evidence/"
                    "2026-08-11-cumulus-518-air-minimum-resources.md"
                )
            if state != "INACTIVE":
                console.print(f"  [yellow]Warning:[/] Simulation state is {state}, expected INACTIVE")

            # Configure air-oob-switch via Node Instructions (L2 mode only — L3
            # uses cust-net-edge-01 which is a Wire-Map Cumulus node configured
            # by ZTP/NOZTP like any other switch).
            if infra["air_bridge"] and infra["air_bridge"] in topology_json.get("content", {}).get("nodes", {}):
                console.print(f"Configuring {infra['air_bridge']} via Node Instructions...")
                try:
                    _inject_air_oob_instructions(
                        client, base_url, token, sim_id, topology_json,
                    )
                    console.print(f"  {infra['air_bridge']}: bridge config queued")
                except AirError as exc:
                    console.print(
                        f"  [yellow]Warning:[/] Node Instructions failed: {exc}\n"
                        f"  {infra['air_bridge']} can be configured manually via console."
                    )
            elif infra["mode"] == "l3":
                # No air-oob-switch in L3, but cust-net-edge-01 still needs an
                # L2 bridge so DHCP can flow between switch eth0s and
                # external-dhcp before any BGP/EVPN is up on the OOB plane.
                if "cust-net-edge-01" in topology_json.get("content", {}).get("nodes", {}):
                    # Load the same switch_password used for the regular OOB/
                    # core/csl/gsl NIs so cust-net-edge nodes share creds.
                    edge_password = "Cumu1usLinux!"
                    secrets_path = inv_dir / "group_vars" / "all" / "secrets.yml"
                    if secrets_path.exists():
                        with open(secrets_path) as f:
                            sec = yaml.safe_load(f) or {}
                        edge_password = sec.get("switch_password", edge_password)
                    # Pull `common` (incl. pre/post-login banner text + site +
                    # arch) so the cust-net-edge NVUE config gets the same
                    # operator-configurable banners the cluster switches do.
                    _common: dict = {}
                    _main_yml = inv_dir / "group_vars" / "all" / "main.yml"
                    if _main_yml.exists():
                        with open(_main_yml) as f:
                            _common = (yaml.safe_load(f) or {}).get("common", {}) or {}
                    console.print("Configuring cust-net-edge as L2 mgmt bridge + eBGP underlay via Node Instructions...")
                    _inject_cust_net_edge_instructions(
                        client, base_url, token, sim_id, topology_json,
                        switch_password=edge_password,
                        common=_common,
                    )
                else:
                    console.print(
                        "[yellow]Warning:[/] L3 mode requested but cust-net-edge-01 "
                        "not in topology — skipping L2 bridge NI. Switches will not ZTP."
                    )
                # Bring up eth1+ on the L3 trio at first boot so switch ZTP
                # works even before the operator runs setup-ztp-server.yml.
                console.print("Configuring L3 trio first-boot netplan via Node Instructions...")
                _inject_l3_trio_netplan_ni(
                    client, base_url, token, sim_id, inv_dir, topology_json,
                )
                # Install FRR + BGP unnumbered on ext-storage-* nodes (if any).
                # 2-8-9-800 ships these as the customer-side aggregate that
                # the CSL STORAGE VRF uplinks peer to via eBGP unnumbered.
                # No-op for archs that don't declare ext-storage in Nodes tab.
                console.print("Configuring ext-storage FRR/BGP via Node Instructions...")
                _inject_ext_storage_instructions(
                    client, base_url, token, sim_id, topology_json,
                )
                # Enable IP forwarding + MASQUERADE on external-conn so OOB
                # clients can reach the internet through it (the L3 nat_host).
                console.print("Configuring external-conn NAT (ip_forward + MASQUERADE)...")
                _inject_external_conn_nat_ni(
                    client, base_url, token, sim_id, topology_json,
                )

            # Disable unattended-upgrades on Ubuntu nodes
            console.print("Disabling unattended-upgrades on Ubuntu nodes...")
            try:
                n_ubuntu = _inject_ubuntu_node_instructions(
                    client, base_url, token, sim_id, topology_json,
                )
                if n_ubuntu:
                    console.print(f"  {n_ubuntu} nodes configured")
            except AirError as exc:
                console.print(f"  [yellow]Warning:[/] {exc}")

            # No-ZTP mode: inject rendered NVUE config into every switch via NI.
            # Must happen before start_simulation() so the config is staged on first boot.
            if args.no_ztp:
                configs_dir = project_root / "output" / arch / site / "configs"
                console.print("[bold]No-ZTP mode:[/] injecting NVUE configs into switches via Node Instructions...")
                try:
                    n_sw = _inject_switch_config_via_ni(
                        client, base_url, token, sim_id, inv_dir, configs_dir, topology_json,
                    )
                    console.print(f"  {n_sw} switches configured via Node Instructions (no DHCP/ZTP)")
                except AirError as exc:
                    console.print(f"  [red]Error:[/] No-ZTP injection failed: {exc}")
                    console.print(f"  Simulation ID: {sim_id}")
                    console.print(f"  Clean up with: make air-destroy ARCH={arch}")
                    return 1

                # In NOZTP mode we skip setup-ztp-server.yml, which is also what
                # normally configures the jump-host infra node's eth1/eth2.
                # Without these, the jump host has only its Air mgmt-link IP and
                # can't reach the OOB network — so validate-* playbooks (which
                # use it as the SSH jump host) all fail. Inject the same netplan
                # via NI here.
                if infra["mode"] == "l2":
                    console.print("[bold]No-ZTP mode:[/] configuring dhcp-oob interfaces via Node Instructions...")
                    try:
                        _inject_dhcp_oob_netplan_ni(
                            client, base_url, token, sim_id, inv_dir, topology_json,
                        )
                    except AirError as exc:
                        console.print(f"  [red]Error:[/] dhcp-oob NI failed: {exc}")
                        console.print(f"  Simulation ID: {sim_id}")
                        console.print(f"  Clean up with: make air-destroy ARCH={arch}")
                        return 1
                else:
                    # L3 mode: the infra-node netplan was ALREADY injected
                    # unconditionally above via _inject_l3_trio_netplan_ni
                    # (first-boot NI brings up utility eth1/eth2, external-dhcp
                    # eth1/eth2, external-conn eth1/eth2). Unlike L2 — where
                    # dhcp-oob's netplan is only set up here in the NOZTP path —
                    # L3 needs no extra NOZTP-specific step: validate-* can ssh
                    # switch eth0s via utility:eth2 on the air-mgmt bridge.
                    console.print(
                        "  L3 infra-node netplan already injected via first-boot NI "
                        "(utility/external-* eth1+) — no extra NOZTP step needed."
                    )

            # Server configuration: either full config (--server-config) or just eth0 IPs
            if args.server_config:
                console.print("Injecting full server config (hostname + netplan + lldp)...")
                try:
                    n_full = _inject_server_full_config(
                        client, base_url, token, sim_id, inv_dir, topology_json,
                    )
                    if n_full:
                        console.print(f"  {n_full} servers configured via Node Instructions")
                        console.print("  deploy-servers-via-jump is NOT needed for these nodes")
                    else:
                        console.print("  No servers to configure")
                except AirError as exc:
                    console.print(f"  [yellow]Warning:[/] Server config injection failed: {exc}")
                    console.print("  Servers can still be configured with: make deploy-servers-via-jump")
            else:
                # Without --server-config, just assign static eth0 IPs (original behavior)
                console.print("Assigning server management IPs...")
                try:
                    n_servers = _inject_server_ip_instructions(
                        client, base_url, token, sim_id, inv_dir, topology_json,
                    )
                    if n_servers:
                        console.print(f"  {n_servers} servers configured with static eth0 IPs")
                    else:
                        console.print("  No server IPs to assign")
                except AirError as exc:
                    console.print(f"  [yellow]Warning:[/] Server IP assignment failed: {exc}")

            # Start simulation
            console.print("Starting simulation...")
            try:
                start_simulation(client, base_url, token, sim_id)
            except AirError as exc:
                console.print(f"[red]Error:[/] Failed to start: {exc}")
                console.print(f"  Simulation ID: {sim_id}")
                cleanup_failed_sim(client, base_url, token, sim_id, arch)
                return 1

            # Poll until loaded (with error detection)
            node_errors = []

            def status_cb(state, elapsed):
                if state:
                    console.print(f"  State: {state} ({elapsed}s)          ", end="\r")

            def error_cb(msg):
                node_errors.append(msg)

            # Boot time scales with node count (~5-6s/node on a busy Air host).
            # The default 60-poll (600s) cap aborts large fabrics mid-boot — a
            # healthy 219-node 2-8-9-800 SU32 takes ~14min to reach ACTIVE. Scale
            # the wait to the topology size (interval=10s) with a 600s floor.
            _node_count = len(topology_json.get("content", {}).get("nodes", {}))
            _max_polls = max(60, (_node_count * 6) // 10)
            final_state = poll_until_loaded(
                client, base_url, token, sim_id,
                max_polls=_max_polls,
                status_callback=status_cb,
                error_callback=error_cb,
            )
            console.print()  # Clear status line

            if final_state == SimState.LOADED:
                break  # success — exit retry loop

            # Failure path. Detect platform capacity errors and optionally retry.
            console.print(f"[red]Error:[/] Simulation failed to start (state: {final_state})")
            if node_errors:
                console.print()
                for err in node_errors:
                    console.print(f"  [red]{err}[/]")
                console.print()

            # Air's "out of capacity" failure shows up two ways:
            #  1. A node_error string containing "capacity" (rare path).
            #  2. The sim sits stuck in STORED state past the poll timeout,
            #     never progressing to LOADING (common path observed in prod).
            # Treat both as "capacity-style" failures eligible for retry.
            is_capacity = (
                (bool(node_errors) and "capacity" in " ".join(node_errors).lower())
                or final_state == SimState.STORED
            )
            can_retry = is_capacity and deploy_attempt < max_attempts
            if can_retry:
                console.print(
                    f"  [yellow]Air platform out of capacity.[/] "
                    f"Destroying failed sim and retrying "
                    f"({deploy_attempt}/{max_attempts} attempts used)..."
                )
                try:
                    delete_simulation(client, base_url, token, sim_id)
                    console.print(f"  Destroyed failed sim ({sim_id})")
                except AirError as exc:
                    console.print(f"  [yellow]Warning:[/] Failed to delete failed sim: {exc}")
                sim_id = None
                continue

            # Final failure (non-capacity, or out of retries).
            if is_capacity:
                console.print("  The Air platform is out of capacity.")
                console.print(
                    "  Out of retry attempts. Try again later, shut down other "
                    "simulations, or rerun with a higher --retry-on-capacity."
                )
            console.print(f"  Simulation ID: {sim_id}")
            console.print(f"  Clean up with: make air-destroy ARCH={arch}")
            console.print(f"  Check Air UI:  {base_url}")
            return 1

        console.print("  Simulation is running")

        # Create SSH services on jump hosts (mode-aware).
        console.print("Creating SSH services on jump hosts...")
        ssh_services = {}
        for node_name in infra["ssh_service_nodes"]:
            if node_name not in topology_json.get("content", {}).get("nodes", {}):
                continue
            try:
                service = create_ssh_service_for_node(
                    client, base_url, token, sim_id, node_name,
                )
                ssh_services[node_name] = service
                console.print(f"  {node_name}: {service.host}:{service.src_port}")
            except AirError as exc:
                console.print(f"  [yellow]Warning:[/] Failed for {node_name}: {exc}")

        # Wait for SSH services TCP port to open (Air proxy ready) — skip slow cloud-init wait
        if ssh_services:
            console.print("Waiting for SSH services...")
            for node_name, service in ssh_services.items():
                if not service.is_ready:
                    console.print(f"  [yellow]Warning:[/] {node_name} SSH service not ready")
                    continue
                # Wait for TCP port to open (Air proxy ready) — up to 60s
                tcp_ready = False
                for _ in range(12):  # 60 seconds (12 × 5s)
                    if check_port_open(service.host, service.src_port):
                        tcp_ready = True
                        break
                    time.sleep(5)

                if tcp_ready:
                    console.print(f"  {node_name} SSH port open (cloud-init will finish during ZTP)")
                else:
                    console.print(f"  [yellow]Warning:[/] {node_name} TCP port not open after 60s")

        # Create HTTP service on the status-page host if status_page_enabled
        # (mode-aware — L2 hosts on dhcp-oob, L3 hosts on utility).
        http_service = None
        main_yml = inv_dir / "group_vars" / "all" / "main.yml"
        if main_yml.exists():
            with open(main_yml) as f:
                _all_vars = yaml.safe_load(f) or {}
            if str(_all_vars.get("status_page_enabled", "")).lower() in ("yes", "true", "1"):
                sp_host = infra["status_page_host"]
                console.print(f"Creating HTTP service on {sp_host} (status page)...")
                try:
                    http_service = create_service_for_node(
                        client, base_url, token, sim_id, sp_host,
                        service_name="HTTP", node_port=80,
                    )
                    console.print(f"  ZTP status page: http://{http_service.host}:{http_service.src_port}")
                except AirError as exc:
                    console.print(f"  [yellow]Warning:[/] Failed to create HTTP service: {exc}")

        # Save HTTP service URL to inventory if created
        if http_service and http_service.is_ready:
            status_page_url = f"http://{http_service.host}:{http_service.src_port}"
            main_yml_path = inv_dir / "group_vars" / "all" / "main.yml"
            if main_yml_path.exists():
                with open(main_yml_path) as f:
                    inv_data = yaml.safe_load(f) or {}
                inv_data["status_page_url"] = status_page_url
                with open(main_yml_path, "w") as f:
                    yaml.dump(inv_data, f, default_flow_style=False, sort_keys=False)
                console.print(f"  Saved status page URL to inventory: {status_page_url}")

        # Update host_vars with SSH service details
        if ssh_services:
            console.print("Updating inventory host_vars...")
            for node_name, service in ssh_services.items():
                if service.is_ready:
                    update_host_vars(inv_dir, node_name, service.host, service.src_port)
                    console.print(f"  Updated {node_name}: {service.host}:{service.src_port}")

        # Summary
        console.print()
        console.print("[bold]Deployment complete.[/]")
        console.print()
        console.print(f"  Simulation: {sim_actual_title}")
        console.print(f"  ID:         {sim_id}")
        console.print("  State:      LOADED")
        console.print()

        for node_name, service in ssh_services.items():
            if service.is_ready:
                ssh_args = build_ssh_args(service.host, service.src_port, "ubuntu", ssh_key_path)
                console.print(f"  {node_name}: {' '.join(ssh_args)}")

        if http_service and http_service.is_ready:
            console.print()
            console.print(f"  [bold]ZTP Status Page:[/] http://{http_service.host}:{http_service.src_port}")

        console.print()
        console.print("[bold]Next steps:[/]")
        console.print(f"  1. Deploy ZTP configs:  make switch-ztp-deploy ARCH={arch}")
        console.print(f"  2. Deploy servers:      make deploy-servers-via-jump ARCH={arch}")
        console.print(f"  3. Validate:            make validate-ztp ARCH={arch}")
        console.print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
