#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Configure Air SSH connection details for oob-server-01 and dhcp-oob.

Prompts for the Air worker hostname and SSH ports, then writes them
to the inventory host_vars files. Can also accept values via CLI args
for scripted use.

Usage:
    # Interactive (prompts for values)
    python scripts/air-connect.py --arch 2-8-9-400

    # Non-interactive
    python scripts/air-connect.py --arch 2-8-9-400 \
        --host worker34.air-inside.nvidia.com \
        --oob-server-port 26788 \
        --dhcp-oob-port 18252

    # Check current settings
    python scripts/air-connect.py --arch 2-8-9-400 --show
"""

import argparse
import re
import sys
from pathlib import Path

import yaml


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
        worker34.air-inside.nvidia.com:26788
        ssh -p 26788 ubuntu@worker34.air-inside.nvidia.com
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
    """Display current Air connection settings."""
    inv_dir = project_root / "output" / arch / site / "inventory" / "host_vars"

    for node in ["oob-server-01", "dhcp-oob"]:
        path = inv_dir / f"{node}.yml"
        data = load_yaml(path)
        host = data.get("ansible_host", "NOT SET")
        port = data.get("ansible_port", "NOT SET")
        print(f"  {node}: {host}:{port}")


def configure(arch: str, site: str, project_root: Path,
              host: str = None, oob_port: int = None,
              dhcp_port: int = None) -> None:
    """Set Air connection details in host_vars."""
    inv_dir = project_root / "output" / arch / site / "inventory" / "host_vars"

    if not inv_dir.exists():
        print(f"  Error: inventory not found at {inv_dir}")
        print(f"  Run 'make generate ARCH={arch}' first.")
        sys.exit(1)

    # Interactive prompts if values not provided
    if not host or not oob_port or not dhcp_port:
        print()
        print("  Enter Air SSH service details.")
        print("  (Paste the host:port from Air's Services tab)")
        print()

    if not host:
        current_data = load_yaml(inv_dir / "oob-server-01.yml")
        current_host = current_data.get("ansible_host", "")
        if current_host and "CHANGE_ME" not in current_host:
            default_host = current_host
        else:
            default_host = None
        host = prompt_value("  Air hostname (e.g. worker34.air-inside.nvidia.com)",
                            default_host)
        if not host:
            print("  Error: hostname is required")
            sys.exit(1)

    if not oob_port:
        raw = prompt_value("  oob-server-01 SSH port (or host:port)")
        parsed_host, parsed_port = parse_host_port(raw)
        if parsed_host:
            host = parsed_host
        oob_port = parsed_port
        if not oob_port:
            print("  Error: could not parse port")
            sys.exit(1)

    if not dhcp_port:
        raw = prompt_value("  dhcp-oob SSH port (or host:port)")
        parsed_host, parsed_port = parse_host_port(raw)
        if parsed_host:
            host = parsed_host
        dhcp_port = parsed_port
        if not dhcp_port:
            print("  Error: could not parse port")
            sys.exit(1)

    # Update oob-server-01
    oob_path = inv_dir / "oob-server-01.yml"
    oob_data = load_yaml(oob_path)
    oob_data["ansible_host"] = host
    oob_data["ansible_port"] = oob_port
    oob_data["ansible_user"] = "ubuntu"
    oob_data.setdefault("hostname", "oob-server-01")
    save_yaml(oob_path, oob_data)

    # Update dhcp-oob
    dhcp_path = inv_dir / "dhcp-oob.yml"
    dhcp_data = load_yaml(dhcp_path)
    dhcp_data["ansible_host"] = host
    dhcp_data["ansible_port"] = dhcp_port
    dhcp_data["ansible_user"] = "ubuntu"
    dhcp_data.setdefault("hostname", "dhcp-oob")
    save_yaml(dhcp_path, dhcp_data)

    print()
    print(f"  oob-server-01 -> {host}:{oob_port}")
    print(f"  dhcp-oob      -> {host}:{dhcp_port}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Configure Air SSH connection details")
    ap.add_argument("--arch", required=True, help="Architecture")
    ap.add_argument("--site", default="default", help="Site name")
    ap.add_argument("--host", help="Air worker hostname")
    ap.add_argument("--oob-server-port", type=int,
                    help="oob-server-01 SSH port")
    ap.add_argument("--dhcp-oob-port", type=int,
                    help="dhcp-oob SSH port")
    ap.add_argument("--show", action="store_true",
                    help="Show current settings and exit")
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    if args.show:
        show_config(args.arch, args.site, project_root)
        return 0

    configure(
        args.arch, args.site, project_root,
        host=args.host,
        oob_port=args.oob_server_port,
        dhcp_port=args.dhcp_oob_port,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
