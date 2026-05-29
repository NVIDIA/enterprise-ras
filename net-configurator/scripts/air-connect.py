#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Configure Air SSH connection details for the deployment's infra nodes.

Mode-aware: reads `_oob_uplink_mode` from the generated topology JSON.
  - L2 mode: prompts for oob-server-01 + dhcp-oob ports
  - L3 mode: prompts for utility + external-conn + external-dhcp ports

Writes results to the inventory host_vars files. Can also accept values
via CLI args for scripted use.

Usage:
    # Interactive (prompts for values, mode picked automatically)
    python scripts/air-connect.py --arch 2-8-9-400

    # Non-interactive (L2)
    python scripts/air-connect.py --arch 2-8-9-400 \
        --host <air-host> \
        --oob-server-port 26788 \
        --dhcp-oob-port 18252

    # Non-interactive (L3)
    python scripts/air-connect.py --arch 2-8-9-400 \
        --host <air-host> \
        --utility-port 25313 \
        --external-conn-port 22789 \
        --external-dhcp-port 10020

    # Check current settings
    python scripts/air-connect.py --arch 2-8-9-400 --show
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml


def detect_mode(project_root: Path, arch: str, site: str) -> str:
    """Return 'l2' or 'l3' for this site, by reading the topology JSON.

    Falls back to 'l2' (current default) if the topology hasn't been
    generated yet or doesn't carry the new `_oob_uplink_mode` field.
    """
    topo_path = (project_root / "output" / arch / site / "topology"
                 / f"{arch}-topology.json")
    if not topo_path.exists():
        return "l2"
    try:
        with open(topo_path) as f:
            t = json.load(f)
        return str(t.get("_oob_uplink_mode", "l2")).strip().lower() or "l2"
    except (json.JSONDecodeError, OSError):
        return "l2"


# Per-mode infra node names: (node_name, cli_arg_name, human_label)
L2_INFRA = [
    ("oob-server-01", "oob_server_port", "oob-server-01"),
    ("dhcp-oob",      "dhcp_oob_port",   "dhcp-oob"),
]
L3_INFRA = [
    ("utility",       "utility_port",       "utility"),
    ("external-conn", "external_conn_port", "external-conn"),
    ("external-dhcp", "external_dhcp_port", "external-dhcp"),
]


def load_yaml(path: Path) -> dict:
    """Load a YAML file, returning empty dict if missing or empty."""
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data


def save_yaml(path: Path, data: dict) -> None:
    """Write a dict to a YAML file with clean formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("---\n")
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def parse_host_port(value: str):
    """Parse 'host:port' or just 'port' from a string.

    Handles formats like:
        <air-host>:26788
        ssh -p 26788 ubuntu@<air-host>
        26788
    Returns (host, port) or (None, port).
    """
    # Try ssh command format: ssh -p <port> <user>@<host>
    m = re.search(r"-p\s+(\d+)\s+\S+@([\w.-]+)", value)
    if m:
        return m.group(2), int(m.group(1))

    # Try host:port
    m = re.match(r"([\w.-]+):(\d+)$", value.strip())
    if m:
        return m.group(1), int(m.group(2))

    # Try bare port
    m = re.match(r"(\d+)$", value.strip())
    if m:
        return None, int(m.group(1))

    return None, None


def prompt_value(prompt: str, current: str = None) -> str:
    """Prompt user for a value, showing current if set."""
    if current:
        display = f"{prompt} [{current}]: "
    else:
        display = f"{prompt}: "
    val = input(display).strip()
    return val if val else (current or "")


def show_config(arch: str, site: str, project_root: Path) -> None:
    """Display current Air connection settings (mode-aware)."""
    mode = detect_mode(project_root, arch, site)
    infra = L3_INFRA if mode == "l3" else L2_INFRA
    inv_dir = project_root / "output" / arch / site / "inventory" / "host_vars"

    print(f"  Mode: {mode}")
    for node_name, _, label in infra:
        path = inv_dir / f"{node_name}.yml"
        data = load_yaml(path)
        host = data.get("ansible_host", "NOT SET")
        port = data.get("ansible_port", "NOT SET")
        print(f"  {label}: {host}:{port}")


def configure(arch: str, site: str, project_root: Path,
              host: str = None, ports: dict = None) -> None:
    """Set Air connection details in host_vars (mode-aware).

    ports is a dict like {'oob_server_port': 22, 'dhcp_oob_port': 23}
    or {'utility_port': 22, 'external_conn_port': 23, 'external_dhcp_port': 24}
    depending on mode. Missing entries prompt interactively.
    """
    mode = detect_mode(project_root, arch, site)
    infra = L3_INFRA if mode == "l3" else L2_INFRA
    ports = ports or {}

    inv_dir = project_root / "output" / arch / site / "inventory" / "host_vars"
    if not inv_dir.exists():
        print(f"  Error: inventory not found at {inv_dir}")
        print(f"  Run 'make generate ARCH={arch}' first.")
        sys.exit(1)

    print(f"  Mode: {mode}")
    missing_ports = [a for _, a, _ in infra if not ports.get(a)]
    if not host or missing_ports:
        print()
        print("  Enter Air SSH service details.")
        print("  (Paste the host:port from Air's Services tab)")
        print()

    if not host:
        # Use the first infra node's existing host as the default if real.
        first_node = infra[0][0]
        current = load_yaml(inv_dir / f"{first_node}.yml").get("ansible_host", "")
        default_host = current if current and "CHANGE_ME" not in current else None
        host = prompt_value("  Air hostname (the host shown in the Air SSH service)",
                            default_host)
        if not host:
            print("  Error: hostname is required")
            sys.exit(1)

    for node_name, arg_name, label in infra:
        if not ports.get(arg_name):
            raw = prompt_value(f"  {label} SSH port (or host:port)")
            parsed_host, parsed_port = parse_host_port(raw)
            if parsed_host:
                host = parsed_host
            if not parsed_port:
                print(f"  Error: could not parse port for {label}")
                sys.exit(1)
            ports[arg_name] = parsed_port

        path = inv_dir / f"{node_name}.yml"
        data = load_yaml(path)
        data["ansible_host"] = host
        data["ansible_port"] = ports[arg_name]
        data["ansible_user"] = "ubuntu"
        data.setdefault("hostname", node_name)
        save_yaml(path, data)

    print()
    for node_name, arg_name, label in infra:
        print(f"  {label:14s} -> {host}:{ports[arg_name]}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Configure Air SSH connection details (mode-aware)")
    ap.add_argument("--arch", required=True, help="Architecture")
    ap.add_argument("--site", default="default", help="Site name")
    ap.add_argument("--host", help="Air worker hostname")
    # L2 ports
    ap.add_argument("--oob-server-port", type=int,
                    help="oob-server-01 SSH port (L2 mode)")
    ap.add_argument("--dhcp-oob-port", type=int,
                    help="dhcp-oob SSH port (L2 mode)")
    # L3 ports
    ap.add_argument("--utility-port", type=int,
                    help="utility SSH port (L3 mode)")
    ap.add_argument("--external-conn-port", type=int,
                    help="external-conn SSH port (L3 mode)")
    ap.add_argument("--external-dhcp-port", type=int,
                    help="external-dhcp SSH port (L3 mode)")
    ap.add_argument("--show", action="store_true",
                    help="Show current settings and exit")
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    if args.show:
        show_config(args.arch, args.site, project_root)
        return 0

    ports = {
        "oob_server_port":   args.oob_server_port,
        "dhcp_oob_port":     args.dhcp_oob_port,
        "utility_port":      args.utility_port,
        "external_conn_port":  args.external_conn_port,
        "external_dhcp_port":  args.external_dhcp_port,
    }
    configure(
        args.arch, args.site, project_root,
        host=args.host,
        ports={k: v for k, v in ports.items() if v is not None},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
