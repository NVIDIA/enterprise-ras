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
import json
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

from airlib.api import (
    create_node_instruction,
    create_service_for_node,
    create_ssh_service_for_node,
    get_resource_budget,
    get_ssh_services,
    import_topology,
    list_simulations,
    poll_until_loaded,
    start_simulation,
    wait_for_inactive,
)
from airlib.auth import authenticate
from airlib.budget import format_budget_row
from airlib.env import load_air_config, require_config
from airlib.errors import AirAPIError, AirError
from airlib.models import SimState
from airlib.ssh import build_ssh_args, check_key_access, check_port_open, get_key_fingerprint

console = Console()


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
      - Ports connected to OOB switch uplinks → access VLAN per mgmt_subnet
      - Ports connected to infra eth2+ → access VLAN per mgmt_subnet

    Must be called after import_topology() but before start_simulation().
    """
    air_meta = topology_json.get("_air_oob", {})
    mgmt_subnets = air_meta.get("mgmt_subnets", [])
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
            n_subnets = max(len(mgmt_subnets), 1)
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
               if not any(n.startswith(p) for p in ("core-", "oob-switch-", "cust-net-edge", "air-oob"))]

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

    configured = 0
    for node_name in targets:
        try:
            create_node_instruction(
                client, base_url, token, sim_id,
                node_name=node_name,
                commands=commands,
                name=f"{node_name}-disable-unattended-upgrades",
                wait_for_network=False,
            )
            configured += 1
        except AirError:
            pass  # best-effort
    return configured


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

    # Gateway is the OOB server IP (first oob_server_interface, or default .1)
    gateway = "192.168.200.1"

    configured = 0
    for node_name, dev in sorted(devices.items()):
        eth0_ip = dev.get("eth0_ip")
        if not eth0_ip or node_name not in topo_nodes:
            continue
        # Skip switches and infra nodes — only configure servers
        if any(node_name.startswith(p) for p in ("core-", "oob-switch-", "oob-server",
                                                   "dhcp-", "cust-net-edge", "air-oob")):
            continue

        commands = [
            "# Disable DHCP and assign static management IP",
            "ip link set eth0 up",
            "ip addr flush dev eth0",
            f"ip addr add {eth0_ip}/24 dev eth0",
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
        """Start a netplan config dict with eth0 static management IP."""
        cfg = {"network": {"version": 2, "renderer": "networkd", "ethernets": {
            "eth0": {
                "dhcp4": False,
                "addresses": [f"{eth0_ip}/24"],
                "routes": [{"to": "0.0.0.0/0", "via": "192.168.200.1"}],
            },
        }}}
        return cfg

    def _build_bond_vlan_netplan(data_ifaces, bond_ip1, bond_ip2, network, gateway, vlan_id):
        """Build netplan dict for a bond+VLAN role (storage/support).

        Uses active-backup bonding (not 802.3ad) because Air's virtual
        EVPN-MH bonds span two switches and Linux LACP can't negotiate
        across different LACP system IDs.  Traffic is VLAN-tagged because
        the switch port PVID (300) differs from the role's VLAN.
        """
        cfg = _init_cfg()
        if not data_ifaces:
            return yaml.dump(cfg, default_flow_style=False, sort_keys=False)
        cfg["network"]["bonds"] = {}
        cfg["network"]["vlans"] = {}
        for iface in data_ifaces:
            cfg["network"]["ethernets"][iface] = {"dhcp4": False}
        if len(data_ifaces) >= 2:
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
        return yaml.dump(cfg, default_flow_style=False, sort_keys=False)

    # Compute nodes (su-*, node-*)
    if node_name.startswith("su-") or node_name.startswith("node-"):
        cpu_ifaces = [i for i in ifaces.get("cpu", []) if i != "eth0"]
        gpu_ifaces = [i for i in ifaces.get("gpu", []) if i != "eth0"]
        gpu_ips = dev.get("gpu_ips", [])
        cfg = _init_cfg()
        cfg["network"]["bonds"] = {}
        for iface in cpu_ifaces:
            cfg["network"]["ethernets"][iface] = {"dhcp4": False}
        gpu_network = common.get("gpu_network", "")
        gpu_gateway = common.get("gpu_gateway", "")
        gpu_vlan = int(common.get("gpu_vlan", 900))
        for idx, iface in enumerate(gpu_ifaces):
            if idx < len(gpu_ips):
                entry = {
                    "dhcp4": False,
                    "addresses": [gpu_ips[idx]],
                }
                # PBR on first GPU interface only (one rule per subnet)
                if idx == 0 and gpu_network and gpu_gateway:
                    entry["routing-policy"] = [{"from": gpu_network, "table": gpu_vlan}]
                    entry["routes"] = [{"to": "0.0.0.0/0", "via": gpu_gateway, "table": gpu_vlan}]
                cfg["network"]["ethernets"][iface] = entry
            else:
                cfg["network"]["ethernets"][iface] = {"dhcp4": False}
        cpu_network = common.get("cpu_network", "")
        cpu_gateway = common.get("cpu_gateway", "")
        cpu_vlan = int(common.get("cpu_vlan", 300))
        if cpu_ifaces:
            cfg["network"]["bonds"]["bond0"] = {
                "interfaces": list(cpu_ifaces),
                "addresses": [dev.get("bond_ip", "")],
                "nameservers": {"addresses": ["8.8.8.8", "8.8.4.4"]},
                "routing-policy": [{"from": cpu_network, "table": cpu_vlan}],
                "routes": [{"to": "0.0.0.0/0", "via": cpu_gateway, "table": cpu_vlan}],
                "parameters": {"mode": "active-backup", "primary": cpu_ifaces[0],
                               "mii-monitor-interval": 100},
            }
        if not cfg["network"]["bonds"]:
            del cfg["network"]["bonds"]
        return yaml.dump(cfg, default_flow_style=False, sort_keys=False)

    # Storage nodes — access VLAN 500 on switch, server sends untagged (IP on bond0)
    if node_name.startswith("storage"):
        data = [i for i in ifaces.get("storage", ifaces.get("cpu", [])) if i != "eth0"]
        storage_network = common.get("storage_network", "")
        storage_gateway = common.get("storage_gateway", "")
        storage_vlan = int(common.get("storage_vlan", 500))
        cfg = _init_cfg()
        if not data:
            return yaml.dump(cfg, default_flow_style=False, sort_keys=False)
        cfg["network"]["bonds"] = {}
        for iface in data:
            cfg["network"]["ethernets"][iface] = {"dhcp4": False}
        if len(data) >= 2:
            cfg["network"]["bonds"]["bond0"] = {
                "interfaces": [data[0], data[1]],
                "addresses": [dev.get("bond_ip1", "")],
                "nameservers": {"addresses": ["8.8.8.8", "8.8.4.4"]},
                "routing-policy": [{"from": storage_network, "table": storage_vlan}],
                "routes": [{"to": "0.0.0.0/0", "via": storage_gateway, "table": storage_vlan}],
                "parameters": {"mode": "active-backup", "primary": data[0],
                               "mii-monitor-interval": 100},
            }
        if len(data) >= 4 and dev.get("bond_ip2"):
            cfg["network"]["bonds"]["bond1"] = {
                "interfaces": [data[2], data[3]],
                "addresses": [dev.get("bond_ip2", "")],
                "nameservers": {"addresses": ["8.8.8.8", "8.8.4.4"]},
                "parameters": {"mode": "active-backup", "primary": data[2],
                               "mii-monitor-interval": 100},
            }
        if not cfg["network"]["bonds"]:
            del cfg["network"]["bonds"]
        return yaml.dump(cfg, default_flow_style=False, sort_keys=False)

    # Support nodes
    if node_name.startswith("support"):
        data = [i for i in ifaces.get("support", ifaces.get("cpu", [])) if i != "eth0"]
        return _build_bond_vlan_netplan(
            data, dev.get("bond_ip1", ""), dev.get("bond_ip2", ""),
            common.get("support_network", ""), common.get("support_gateway", ""),
            int(common.get("support_vlan", 400)),
        )

    return ""


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
    skip_prefixes = ("core-", "oob-switch-", "oob-server", "dhcp-", "cust-net-edge", "air-oob")

    configured = 0
    for node_name, dev in sorted(devices.items()):
        if node_name not in topo_nodes:
            continue
        if any(node_name.startswith(p) for p in skip_prefixes):
            continue

        commands = [f"# Full server configuration for {node_name}"]

        # Hostname
        commands.append(f"hostnamectl set-hostname {node_name}")

        # Netplan config — use base64 to avoid heredoc/quoting issues in Air shell executor
        netplan_yaml = _render_server_netplan(node_name, dev, common)
        if netplan_yaml:
            b64 = base64.b64encode(netplan_yaml.encode()).decode()
            commands.append(f"echo '{b64}' | base64 -d > /etc/netplan/10-netcfg.yaml")
            commands.append("netplan apply || true")

        # ARP flux fix — compute nodes have multiple GPU interfaces on the same
        # subnet; without this, Linux may respond to ARP on the wrong interface
        if node_name.startswith("su-") or node_name.startswith("node-"):
            commands.append("sysctl -w net.ipv4.conf.all.arp_ignore=1")
            commands.append("sysctl -w net.ipv4.conf.all.arp_announce=2")
            commands.append("echo 'net.ipv4.conf.all.arp_ignore=1' >> /etc/sysctl.d/90-arp-flux.conf")
            commands.append("echo 'net.ipv4.conf.all.arp_announce=2' >> /etc/sysctl.d/90-arp-flux.conf")

        # LLDP
        commands.append("DEBIAN_FRONTEND=noninteractive apt-get update -qq")
        commands.append("DEBIAN_FRONTEND=noninteractive apt-get install -y -qq lldpd")
        commands.append('echo "configure lldp portidsubtype ifname" > /etc/lldpd.d/port_info.conf')
        commands.append("systemctl restart lldpd")

        try:
            create_node_instruction(
                client, base_url, token, sim_id,
                node_name=node_name,
                commands=commands,
                name=f"{node_name}-full-config",
                wait_for_network=False,
            )
            configured += 1
        except AirError as exc:
            console.print(f"  [yellow]Warning:[/] {node_name}: {exc}")

    return configured


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
    args = parser.parse_args()

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
        console.print(f"  Ensure this key is registered in Air: Settings -> SSH Keys")
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
                response = input("  Create another with the same name? [y/N]: ").strip().lower()
                if response != "y":
                    console.print("  Cancelled.")
                    return 0
        except AirError as exc:
            console.print(f"[yellow]Warning:[/] Could not check existing simulations: {exc}")

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
        topology_json = json.loads(topology_data)
        console.print("Waiting for simulation to be ready...")
        state = wait_for_inactive(client, base_url, token, sim_id)
        if state != "INACTIVE":
            console.print(f"  [yellow]Warning:[/] Simulation state is {state}, expected INACTIVE")

        # Configure air-oob-switch via Node Instructions (flat L2 bridge)
        if "air-oob-switch" in topology_json.get("content", {}).get("nodes", {}):
            console.print("Configuring air-oob-switch via Node Instructions...")
            try:
                _inject_air_oob_instructions(
                    client, base_url, token, sim_id, topology_json,
                )
                console.print("  air-oob-switch: bridge config queued")
            except AirError as exc:
                console.print(
                    f"  [yellow]Warning:[/] Node Instructions failed: {exc}\n"
                    "  air-oob-switch can be configured manually via console."
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
            console.print(f"  Clean up with: make air-destroy ARCH={arch}")
            return 1

        # Poll until loaded (with error detection)
        node_errors = []

        def status_cb(state, elapsed):
            if state:
                console.print(f"  State: {state} ({elapsed}s)          ", end="\r")

        def error_cb(msg):
            node_errors.append(msg)

        final_state = poll_until_loaded(
            client, base_url, token, sim_id,
            status_callback=status_cb,
            error_callback=error_cb,
        )
        console.print()  # Clear status line

        if final_state != SimState.LOADED:
            console.print(f"[red]Error:[/] Simulation failed to start (state: {final_state})")
            if node_errors:
                console.print()
                for err in node_errors:
                    console.print(f"  [red]{err}[/]")
                console.print()
                if "capacity" in " ".join(node_errors).lower():
                    console.print("  The Air platform is out of capacity.")
                    console.print("  Try again later or shut down other simulations.")
            console.print(f"  Simulation ID: {sim_id}")
            console.print(f"  Clean up with: make air-destroy ARCH={arch}")
            console.print(f"  Check Air UI:  {base_url}")
            return 1

        console.print("  Simulation is running")

        # Create SSH services on jump hosts
        console.print("Creating SSH services on jump hosts...")
        ssh_services = {}
        for node_name in ["oob-server-01", "dhcp-oob"]:
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

        # Create HTTP service on dhcp-oob if status_page_enabled
        http_service = None
        main_yml = inv_dir / "group_vars" / "all" / "main.yml"
        if main_yml.exists():
            with open(main_yml) as f:
                _all_vars = yaml.safe_load(f) or {}
            if str(_all_vars.get("status_page_enabled", "")).lower() in ("yes", "true", "1"):
                console.print("Creating HTTP service on dhcp-oob (status page)...")
                try:
                    http_service = create_service_for_node(
                        client, base_url, token, sim_id, "dhcp-oob",
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
        console.print(f"  State:      LOADED")
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
