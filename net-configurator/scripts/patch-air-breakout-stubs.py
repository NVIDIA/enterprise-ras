#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Patch Air topology JSON with breakout sub-port stubs.

Air VX only creates interfaces that have topology links. When testing a
switches-only deployment (no servers), ports configured with breakout
but lacking Wire Map connections get stub parent ports (swpN) instead of
sub-ports (swpNs0, swpNs1). This causes nv config apply to fail on
interfaces that don't exist in the simulation.

This script reads the generated inventory to find which ports have
breakout configured, then replaces parent stubs with sub-port stubs in
the topology JSON.

Usage:
    python3 scripts/patch-air-breakout-stubs.py --arch 2-4-5-800 --site mc1-switches

Only runs when AIR_SWITCHES_ONLY=1 is passed to make generate.
Does not modify any other files or affect real hardware deployments.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from utils import generate_mac


def main():
    parser = argparse.ArgumentParser(description="Patch Air topology with breakout stubs")
    parser.add_argument("--arch", required=True)
    parser.add_argument("--site", default="default")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    topo_path = project_root / "output" / args.arch / args.site / "topology" / f"{args.arch}-topology.json"

    if not topo_path.exists():
        print(f"  No topology at {topo_path} — skipping")
        return

    # Read generated inventory group_vars to find breakout parents
    inv_dir = project_root / "output" / args.arch / args.site / "inventory"
    gv_dir = inv_dir / "group_vars"

    # Collect all breakout definitions from group_vars
    breakout_map = {}  # node_pattern -> {port: num_subports}

    # Read gpu_breakout_parents and isl_breakout_parents from plane group_vars
    for gv_file in gv_dir.glob("*.yml"):
        with open(gv_file) as f:
            gv = yaml.safe_load(f) or {}

        gpu_parents = gv.get("gpu_breakout_parents", "")
        isl_parents = gv.get("isl_breakout_parents", "")

        if not gpu_parents and not isl_parents:
            continue

        # Determine which hosts this group applies to
        group_name = gv_file.stem  # e.g. gsl_plane1
        hosts_file = inv_dir / "hosts"
        hosts_in_group = _get_hosts_in_group(hosts_file, group_name)

        for host in hosts_in_group:
            if host not in breakout_map:
                breakout_map[host] = {}
            for port_str in _parse_port_list(gpu_parents):
                breakout_map[host][port_str] = 2  # 2x breakout
            for port_str in _parse_port_list(isl_parents):
                breakout_map[host][port_str] = 2

    # Also check for 8x breakout (N/S spines with OOB ports)
    # Read from cs.yml if it has smn_ports
    for gv_file in gv_dir.glob("*.yml"):
        with open(gv_file) as f:
            gv = yaml.safe_load(f) or {}
        smn_ports = gv.get("smn_ports", "")
        isl_leaf = gv.get("isl_leaf_ports", "")
        isl_core = gv.get("isl_core_ports", "")
        if not any([smn_ports, isl_leaf, isl_core]):
            continue
        group_name = gv_file.stem
        hosts_in_group = _get_hosts_in_group(inv_dir / "hosts", group_name)
        for host in hosts_in_group:
            if host not in breakout_map:
                breakout_map[host] = {}
            for port_str in _parse_port_list(smn_ports):
                breakout_map[host][port_str] = 8
            for port_str in _parse_port_list(isl_leaf):
                breakout_map[host][port_str] = 2
            for port_str in _parse_port_list(isl_core):
                breakout_map[host][port_str] = 2

    if not breakout_map:
        print("  No breakout config found — nothing to patch")
        return

    # Patch topology
    topo = json.load(open(topo_path))
    links = topo["content"]["links"]
    added = 0

    for node, ports in breakout_map.items():
        # Get already-connected interfaces for this node
        connected = set()
        for link in links:
            if not isinstance(link, list) or not isinstance(link[0], dict):
                continue
            for ep in link:
                if isinstance(ep, dict) and ep.get("node") == node:
                    connected.add(ep["interface"])

        for port_name, num_subs in ports.items():
            port_num = int(re.search(r'\d+', port_name).group())
            # Remove parent stub if exists
            links = [
                l for l in links
                if not (
                    isinstance(l, list) and len(l) == 2
                    and isinstance(l[0], dict) and l[1] == "unconnected"
                    and l[0].get("node") == node
                    and l[0].get("interface") == f"swp{port_num}"
                )
            ]
            # Add sub-port stubs
            for sub in range(num_subs):
                sp = f"swp{port_num}s{sub}"
                if sp not in connected:
                    links.append([
                        {"interface": sp, "node": node,
                         "mac": generate_mac(node, sp), "network_pci": None},
                        "unconnected"
                    ])
                    added += 1

    topo["content"]["links"] = links
    json.dump(topo, open(topo_path, "w"))
    print(f"  Patched: {added} sub-port stubs added")


def _get_hosts_in_group(hosts_file: Path, group_name: str) -> list:
    """Parse Ansible hosts file and return hosts in a given group."""
    hosts = []
    in_group = False
    for line in hosts_file.read_text().splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            in_group = (s[1:-1].split(":")[0] == group_name)
            continue
        if in_group and s and not s.startswith("#") and "=" not in s:
            hosts.append(s)
    return hosts


def _parse_port_list(port_str: str) -> list:
    """Parse 'swp1,swp2,swp3' or 'swp1-11' into individual port names."""
    if not port_str:
        return []
    ports = []
    for token in str(port_str).split(","):
        token = token.strip()
        if not token:
            continue
        # Range: swp1-11 or 1-11
        m = re.match(r'(?:swp)?(\d+)-(\d+)', token)
        if m:
            for i in range(int(m.group(1)), int(m.group(2)) + 1):
                ports.append(f"swp{i}")
        else:
            # Single: swp1 or 1
            m2 = re.match(r'(?:swp)?(\d+)', token)
            if m2:
                ports.append(f"swp{m2.group(1)}")
    return ports


if __name__ == "__main__":
    main()
