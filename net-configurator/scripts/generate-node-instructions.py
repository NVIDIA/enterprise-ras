#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Generate pasteable Node Instruction scripts for every node displayed in Air.

Reads the generated inventory and topology for an architecture/site and
writes one bash script per node into the node-instructions/ directory.
The content mirrors what air-deploy.py would inject via the Air API at
deploy time, so OEMs can review every node's NI before launch.

Infrastructure nodes (custom content):
  - air-oob-switch  (VLAN-aware bridge)
  - oob-server-01   (OOB gateway: IP forwarding, static IPs, NAT)
  - dhcp-oob        (minimal networking so Ansible can run from it later)

Per-node scripts (NOZTP-style, matching air-deploy.py injection):
  - <server>.sh — hostname + netplan + lldp + (compute ARP-flux fix)
  - <switch>.sh — deferred-apply wrapper that sources the rendered NVUE
                  config under /opt/era/ on first boot

Only nodes that appear in the generated topology (Display in Air = Yes)
get a script.

Usage:
    python3 scripts/generate-node-instructions.py --arch 2-8-5-200 [--site default]
"""

import argparse
import base64
import importlib
import json
import shlex
import sys
from pathlib import Path

import yaml

# Pull the NI builders from air-deploy.py so this script and the runtime
# injector produce identical content. air-deploy.py has dashes in the name
# so importlib is the cleanest way to load it.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_air_deploy = importlib.import_module("air-deploy".replace("-", "_")) if False else None
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("air_deploy", _HERE / "air-deploy.py")
_air_deploy = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_air_deploy)
build_server_ni_commands = _air_deploy.build_server_ni_commands
build_switch_ni_commands = _air_deploy.build_switch_ni_commands
SERVER_NI_SKIP_PREFIXES = _air_deploy.SERVER_NI_SKIP_PREFIXES


def write_file_cmd(path: str, content: str) -> str:
    """Return a single-line bash command that writes `content` to `path`.

    Air's shell executor does not reliably handle multi-line heredocs, so
    we base64-encode the content and decode it inline.  This keeps the
    whole file-write as a single shell command that survives Air's parser.

    Both `path` and the base64 payload are shell-escaped before
    interpolation so a path containing spaces or shell metacharacters
    can't break the command. Base64 alphabet is apostrophe-safe on its
    own, but `shlex.quote` here keeps the class-of-bug pattern
    consistent with the ssh.py fix.
    """
    b64 = base64.b64encode(content.encode()).decode()
    return f"echo {shlex.quote(b64)} | base64 -d > {shlex.quote(path)}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    """Load a YAML file, returning an empty dict on failure."""
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"  WARNING: {path} not found", file=sys.stderr)
        return {}


def load_json(path: Path) -> dict:
    """Load a JSON file, returning an empty dict on failure."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"  WARNING: {path} not found", file=sys.stderr)
        return {}


def write_script(path: Path, content: str) -> None:
    """Write a script file and print confirmation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"  ✓ {path}")


# ---------------------------------------------------------------------------
# air-oob-switch: VLAN-aware bridge
# ---------------------------------------------------------------------------

def generate_air_oob_switch(topology: dict) -> str:
    """Generate NVUE commands for air-oob-switch bridge configuration.

    Port classification (mirrors _inject_air_oob_instructions in air-deploy.py):
      - switch eth0s / infra eth1 → untagged (air-mgmt)
      - OOB switch uplinks        → access VLAN per mgmt_subnet
      - infra eth2+               → access VLAN per mgmt_subnet
    """
    air_meta = topology.get("_air_oob", {})
    mgmt_subnets = air_meta.get("mgmt_subnets", [])
    oob_switch_names = air_meta.get("oob_switch_names", [])

    # Map air-oob-switch ports to their peer (node:interface)
    port_peers: dict[str, tuple[str, str]] = {}
    for link in topology.get("content", {}).get("links", []):
        if not isinstance(link[0], dict) or not isinstance(link[1], dict):
            continue
        for i, ep in enumerate(link):
            if ep.get("node") == "air-oob-switch" and ep["interface"].startswith("swp"):
                other = link[1 - i]
                port_peers[ep["interface"]] = (other["node"], other["interface"])

    if not port_peers:
        return "#!/bin/bash\necho 'ERROR: no air-oob-switch ports found in topology'\nexit 1\n"

    air_mgmt_ports: list[str] = []
    vlan_ports: dict[int, list[str]] = {}

    for swp, (peer_node, peer_iface) in sorted(
        port_peers.items(), key=lambda x: int(x[0].replace("swp", ""))
    ):
        if peer_node in oob_switch_names:
            switch_idx = oob_switch_names.index(peer_node)
            n_subnets = max(len(mgmt_subnets), 1)
            subnet_idx = switch_idx % n_subnets
            if peer_iface != "eth0":
                vlan_id = 777 + subnet_idx
                vlan_ports.setdefault(vlan_id, []).append(swp)
                continue

        if peer_node in ("dhcp-oob", "oob-server-01"):
            if peer_iface == "eth1":
                air_mgmt_ports.append(swp)
            else:
                eth_num = int(peer_iface.replace("eth", ""))
                vlan_id = 777 + (eth_num - 2)
                vlan_ports.setdefault(vlan_id, []).append(swp)
            continue

        air_mgmt_ports.append(swp)

    # Build NVUE commands
    commands = [
        "nv set system hostname air-oob-switch",
        "nv set bridge domain br_default type vlan-aware",
    ]

    if air_mgmt_ports:
        port_list = ",".join(air_mgmt_ports)
        commands.append(f"nv set interface {port_list} bridge domain br_default")

    for vlan_id in sorted(vlan_ports):
        port_list = ",".join(vlan_ports[vlan_id])
        commands.append(f"nv set bridge domain br_default vlan {vlan_id}")
        commands.append(f"nv set interface {port_list} bridge domain br_default access {vlan_id}")

    commands.append("nv config apply -y")

    lines = [
        "#!/bin/bash",
        "# Node Instruction: air-oob-switch — VLAN-aware bridge",
        "# Generated by: scripts/generate-node-instructions.py",
        "#",
        "# Paste this into the Air GUI → air-oob-switch → Node Instructions",
        "# BEFORE starting the simulation.",
        "",
    ]
    lines.extend(commands)
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# oob-server-01: gateway with IP forwarding + NAT
# ---------------------------------------------------------------------------

def generate_oob_server(host_vars: dict) -> str:
    """Generate bash script for oob-server-01 gateway configuration.

    Replicates what `make oob-setup` (roles/oob-server) does:
      1. Install net-tools, iptables, iptables-persistent
      2. Enable IP forwarding
      3. Configure netplan with static IPs
      4. NAT masquerade on eth0
    """
    interfaces = host_vars.get("oob_server_interfaces", [])

    # Build netplan YAML content.
    # Always include eth0 as DHCP — Air assigns the management/outbound IP via
    # DHCP, and omitting eth0 causes `netplan apply` to tear it down (breaking
    # internet reachability for NAT masquerade).
    ethernets = {"eth0": {"dhcp4": True}}
    for iface in interfaces:
        if iface["name"] == "eth0":
            continue  # never override Air's mgmt eth0
        ethernets[iface["name"]] = {
            "dhcp4": False,
            "addresses": [f"{iface['ip']}/{iface.get('netmask', 24)}"],
        }
        if "routes" in iface:
            ethernets[iface["name"]]["routes"] = iface["routes"]

    netplan = {
        "network": {
            "version": 2,
            "renderer": "networkd",
            "ethernets": ethernets,
        }
    }
    netplan_yaml = yaml.dump(netplan, default_flow_style=False, sort_keys=False)

    sysctl_conf = (
        "net.ipv4.ip_forward = 1\n"
        "net.ipv6.conf.all.disable_ipv6 = 1\n"
        "net.ipv6.conf.default.disable_ipv6 = 1\n"
        "net.ipv6.conf.lo.disable_ipv6 = 1\n"
    )

    # Interface summary for comments
    iface_comments = []
    for iface in interfaces:
        purpose = iface.get("purpose", "")
        iface_comments.append(f"#   {iface['name']}: {iface['ip']}/{iface.get('netmask', 24)} ({purpose})")

    lines = [
        "#!/bin/bash",
        "# Node Instruction: oob-server-01 — OOB gateway configuration",
        "# Generated by: scripts/generate-node-instructions.py",
        "#",
        "# Paste this into the Air GUI → oob-server-01 → Node Instructions",
        "# BEFORE starting the simulation.",
        "#",
        "# Configures:",
        "#   - IP forwarding (routing between OOB networks)",
        "#   - Static IPs on management interfaces",
        *iface_comments,
        "#   - NAT masquerade on eth0 (internet access for internal nodes)",
        "",
        'echo "=== oob-server-01: configuring OOB gateway ==="',
        "",
        "# --- 1. Install required packages ---",
        "export DEBIAN_FRONTEND=noninteractive",
        "apt-get update -qq",
        "apt-get install -y -qq net-tools iptables iptables-persistent",
        "",
        "# --- 2. Enable IP forwarding ---",
        write_file_cmd("/etc/sysctl.d/99-oob-forwarding.conf", sysctl_conf),
        "sysctl -p /etc/sysctl.d/99-oob-forwarding.conf",
        "",
        "# --- 3. Configure static IPs on OOB interfaces ---",
        write_file_cmd("/etc/netplan/01-oob-config.yaml", netplan_yaml),
        "chmod 600 /etc/netplan/01-oob-config.yaml",
        "netplan apply || true",
        "sleep 3",
        "",
    ]

    # Bring up interfaces explicitly (fallback)
    for iface in interfaces:
        lines.append(f"ip link set {iface['name']} up 2>/dev/null || true")
    lines.append("")

    lines.extend([
        "# --- 4. NAT masquerade for internet access ---",
        "iptables -t nat -C POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null || \\",
        "  iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE",
        "mkdir -p /etc/iptables",
        "iptables-save > /etc/iptables/rules.v4",
        "",
        "# --- 5. Verify ---",
        "echo ''",
        'echo "=== oob-server-01 configuration complete ==="',
        "ip -brief addr show",
        "echo ''",
        'echo "IP forwarding: $(sysctl -n net.ipv4.ip_forward)"',
        'echo "NAT masquerade: $(iptables -t nat -L POSTROUTING -n | grep -c MASQUERADE) rule(s)"',
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# dhcp-oob: minimal networking (Ansible + ZTP run from here later)
# ---------------------------------------------------------------------------

def generate_dhcp_oob(global_vars: dict) -> str:
    """Generate bash script for dhcp-oob minimal setup.

    This does NOT set up ZTP (dnsmasq/nginx) — that will be done via Ansible
    from dhcp-oob itself after the user clones the repo. This script only:
      1. Configures static IPs on ZTP interfaces (so dhcp-oob is reachable)
      2. Installs git + ansible prerequisites
      3. Sets hostname
    """
    ztp_interfaces = global_vars.get("ztp_interfaces", [])

    # Build netplan YAML.
    # Always include eth0 as DHCP — Air assigns management over eth0 and
    # `netplan apply` with a file that omits eth0 can tear it down,
    # disconnecting the node from Air's mgmt network.
    ethernets = {"eth0": {"dhcp4": True}}

    # Only the first interface with a gateway gets the default route
    # (avoids duplicate default routes that conflict)
    default_route_set = False
    for iface in ztp_interfaces:
        if iface["name"] == "eth0":
            continue  # never override Air's mgmt eth0
        prefix = iface["network"].split("/")[1] if "/" in iface["network"] else "24"
        entry: dict = {
            "dhcp4": False,
            "addresses": [f"{iface['ip']}/{prefix}"],
        }
        if "gateway" in iface and not default_route_set:
            entry["routes"] = [{"to": "0.0.0.0/0", "via": iface["gateway"]}]
            default_route_set = True
        ethernets[iface["name"]] = entry

    netplan = {
        "network": {
            "version": 2,
            "renderer": "networkd",
            "ethernets": ethernets,
        }
    }
    netplan_yaml = yaml.dump(netplan, default_flow_style=False, sort_keys=False)

    # Interface summary for comments
    iface_comments = []
    for iface in ztp_interfaces:
        purpose = iface.get("purpose", "")
        prefix = iface["network"].split("/")[1] if "/" in iface["network"] else "24"
        iface_comments.append(f"#   {iface['name']}: {iface['ip']}/{prefix} ({purpose})")

    lines = [
        "#!/bin/bash",
        "# Node Instruction: dhcp-oob — minimal networking + prerequisites",
        "# Generated by: scripts/generate-node-instructions.py",
        "#",
        "# Paste this into the Air GUI → dhcp-oob → Node Instructions",
        "# BEFORE starting the simulation.",
        "#",
        "# This script only sets up networking and installs prerequisites.",
        "# ZTP services (dnsmasq, nginx) are configured later by running",
        "# Ansible from dhcp-oob itself (see docs/MANUAL_FALLBACK_GUIDE.md).",
        "#",
        "# Interfaces:",
        *iface_comments,
        "",
        'echo "=== dhcp-oob: configuring networking + prerequisites ==="',
        "",
        "# --- 1. Set hostname ---",
        "hostnamectl set-hostname dhcp-oob",
        "",
        "# --- 2. Configure static IPs ---",
        write_file_cmd("/etc/netplan/01-ztp-interfaces.yaml", netplan_yaml),
        "chmod 600 /etc/netplan/01-ztp-interfaces.yaml",
        "netplan apply || true",
        "sleep 3",
        "",
        "# --- 3. Wait for internet access (via oob-server-01 NAT) ---",
        'echo "Waiting for internet access via oob-server-01..."',
        "for i in $(seq 1 30); do",
        '  if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then',
        '    echo "  Internet reachable after ${i}s"',
        "    break",
        "  fi",
        "  sleep 2",
        "done",
        "",
        "# --- 4. Disable systemd-networkd-wait-online (blocks boot on Air VMs) ---",
        "systemctl disable systemd-networkd-wait-online.service 2>/dev/null || true",
        "systemctl mask systemd-networkd-wait-online.service 2>/dev/null || true",
        "",
        "# --- 5. Install prerequisites ---",
        "export DEBIAN_FRONTEND=noninteractive",
        "apt-get update -qq",
        "apt-get install -y -qq git python3-pip python3-venv",
        "",
        "# --- 6. Verify ---",
        "echo ''",
        'echo "=== dhcp-oob configuration complete ==="',
        "ip -brief addr show",
        'echo ""',
        'echo "Next steps (run manually after SSH-ing into dhcp-oob):"',
        'echo "  1. git clone <repo-url> era-automation"',
        'echo "  2. cd era-automation"',
        'echo "  3. python3 -m venv .venv && source .venv/bin/activate"',
        'echo "  4. pip install -r requirements.txt"',
        'echo "  5. Copy your Excel file and run: make import EXCEL=<path>"',
        'echo "  6. make generate"',
        'echo "  7. make ztp-setup     # configures DHCP + nginx on this host"',
        'echo "  8. make deploy-servers # configures servers (direct SSH)"',
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Node Instruction scripts for manual Air deployment"
    )
    parser.add_argument("--arch", required=True, help="Architecture (e.g., 2-8-5-200)")
    parser.add_argument("--site", default="default", help="Site name (default: default)")
    args = parser.parse_args()

    base = Path("output") / args.arch / args.site
    inventory = base / "inventory"
    topo_dir = base / "topology"
    output_dir = topo_dir / "node-instructions"

    # Validate that generate has been run
    if not inventory.is_dir():
        print(f"ERROR: Inventory not found at {inventory}")
        print(f"  Run 'make generate ARCH={args.arch}' first.")
        sys.exit(1)

    print(f"Generating Node Instructions for {args.arch} (site: {args.site})")
    print(f"  Reading inventory from {inventory}")

    # Load data
    global_vars = load_yaml(inventory / "group_vars" / "all" / "main.yml")
    topo_file = topo_dir / f"{args.arch}-topology.json"
    topology = load_json(topo_file)

    if not topology:
        print(f"ERROR: Topology not found at {topo_file}")
        print(f"  Run 'make generate ARCH={args.arch}' first.")
        sys.exit(1)

    # Mode detection: L2 emits the air-oob-switch + dhcp-oob + oob-server-01
    # trio; L3 mode has no Air-injected bridge node and uses external-conn /
    # external-dhcp / utility (NI generation for the L3 trio is v2 follow-on).
    mode = topology.get("_oob_uplink_mode", "l2")

    # Generate scripts
    print(f"\n  Writing to {output_dir}/  (mode: {mode})")

    if mode == "l2":
        oob_host_vars = load_yaml(inventory / "host_vars" / "oob-server-01.yml")
        write_script(
            output_dir / "air-oob-switch.sh",
            generate_air_oob_switch(topology),
        )
        write_script(
            output_dir / "oob-server-01.sh",
            generate_oob_server(oob_host_vars),
        )
        write_script(
            output_dir / "dhcp-oob.sh",
            generate_dhcp_oob(global_vars),
        )
    else:
        print(
            "  L3 mode: skipping legacy L2 infra NI scripts "
            "(air-oob-switch / oob-server-01 / dhcp-oob).\n"
            "  L3 infra NI generation (external-conn / external-dhcp / utility) "
            "is a v2 follow-on;\n"
            "  for now `make air-deploy` handles the L3 trio programmatically."
        )

    # ── Per-node NI scripts for everything else displayed in Air ──
    #
    # Generates a .sh file for every server and switch that the topology
    # places in Air (Display in Air = Yes). Content matches what
    # air-deploy.py would POST via the Air API in NOZTP mode, so the OEM
    # can review the exact commands that will run on each node.
    topo_nodes = set(topology.get("content", {}).get("nodes", {}).keys())
    devices = global_vars.get("devices", {})
    common = global_vars.get("common", {})

    # Server NIs ----------------------------------------------------------
    server_count = 0
    for node_name, dev in sorted(devices.items()):
        if node_name not in topo_nodes:
            continue
        if any(node_name.startswith(p) for p in SERVER_NI_SKIP_PREFIXES):
            continue
        commands = build_server_ni_commands(node_name, dev, common)
        if not commands:
            continue
        script = "#!/bin/bash\n" + (
            f"# Generated by: scripts/generate-node-instructions.py\n"
            f"# Paste this into the Air GUI → {node_name} → Node Instructions.\n"
            "# This is the exact content air-deploy.py injects in NOZTP mode.\n\n"
        ) + "\n".join(commands) + "\n"
        write_script(output_dir / f"{node_name}.sh", script)
        server_count += 1

    # Switch NIs ----------------------------------------------------------
    secrets_path = inventory / "group_vars" / "all" / "secrets.yml"
    switch_password = "Cumu1usLinux!"  # documented placeholder
    if secrets_path.exists():
        with open(secrets_path) as f:
            sec = yaml.safe_load(f) or {}
        switch_password = sec.get("switch_password") or switch_password

    configs_dir = base / "configs"
    switch_count = 0
    for node_name in sorted(topo_nodes):
        if not any(node_name.startswith(p) for p in ("core-", "csl-", "gsl-", "oob-switch-")):
            continue
        if node_name == "air-oob-switch":
            continue  # custom script already written above
        config_file = configs_dir / f"{node_name}-config.sh"
        if not config_file.exists():
            print(f"  Warning: {node_name}: no rendered config at {config_file}; skipping")
            continue

        host_vars_path = inventory / "host_vars" / f"{node_name}.yml"
        host_ip = None
        if host_vars_path.exists():
            with open(host_vars_path) as f:
                hv = yaml.safe_load(f) or {}
            host_ip = hv.get("ansible_host")

        commands = build_switch_ni_commands(
            node_name, config_file.read_text(), host_ip, switch_password
        )
        script = "#!/bin/bash\n" + (
            f"# Generated by: scripts/generate-node-instructions.py\n"
            f"# Paste this into the Air GUI → {node_name} → Node Instructions.\n"
            "# This is the exact deferred-apply NI air-deploy.py injects in NOZTP mode.\n\n"
        ) + "\n".join(commands) + "\n"
        write_script(output_dir / f"{node_name}.sh", script)
        switch_count += 1

    infra_line = (
        "  Infrastructure (3):\n"
        "    air-oob-switch.sh  oob-server-01.sh  dhcp-oob.sh"
        if mode == "l2"
        else "  Infrastructure (0):  L3 mode — no manual-fallback NI in v1"
    )
    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Node Instruction scripts generated!

  Output: {output_dir}/

{infra_line}
  Servers ({server_count}):    one .sh per server with NOZTP-style hostname/netplan/lldp
  Switches ({switch_count}):    one .sh per switch with the deferred-apply wrapper

  Paste each script into the Air GUI before starting the simulation,
  or just review them to audit what air-deploy.py NOZTP mode will inject.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")


if __name__ == "__main__":
    main()
