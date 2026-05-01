#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Shared utilities for ERA automation scripts.

Functions here are used by both excel_parser.py and topology_generator.py
to ensure consistent behavior (e.g., deterministic MAC generation).
"""

import hashlib
import re
from collections import defaultdict


# Module-level MAC registry for collision detection within a generation run.
_mac_registry: dict[str, str] = {}


def generate_mac(node: str, interface: str, seed: str = "era") -> str:
    """Generate a deterministic MAC address from node + interface.

    Uses MD5 hash of '{seed}:{node}:{interface}' to produce a consistent
    MAC in the 48:b0:2d:xx:xx:xx range. This ensures topology JSON MACs
    and DHCP reservation MACs always match for the same node/interface.

    Raises ValueError if a collision is detected (different inputs producing
    the same MAC).
    """
    h = hashlib.md5(f"{seed}:{node}:{interface}".encode()).hexdigest()
    mac = f"48:b0:2d:{h[0:2]}:{h[2:4]}:{h[4:6]}"

    key = f"{seed}:{node}:{interface}"
    existing = _mac_registry.get(mac)
    if existing is not None and existing != key:
        raise ValueError(
            f"MAC collision detected: {mac} generated for both "
            f"'{existing}' and '{key}'"
        )
    _mac_registry[mac] = key
    return mac


def reset_mac_registry():
    """Clear the MAC collision registry. Call between independent generation runs."""
    _mac_registry.clear()


def classify_node(name: str) -> str:
    """Classify a node by its name into a fine-grained role.

    Returns one of:
        'core', 'oob', 'air-oob', 'edge', 'infra', 'compute', 'storage',
        'support', 'k8s', 'bcme', 'unknown'

    Used by both the Excel parser and topology generator. Each caller
    maps these fine-grained roles to its own categories as needed.
    """
    n = name.lower()
    if n.startswith('core-'):
        return 'core'
    if n == 'air-oob-switch':
        return 'air-oob'
    if n.startswith('oob-switch-'):
        return 'oob'
    # Infra before edge — dhcp-edge is infra, not an edge switch
    if any(x in n for x in ('dhcp', 'oob-server')):
        return 'infra'
    if 'edge' in n:
        return 'edge'
    if 'node' in n and ('su-' in n or n.startswith('node')):
        return 'compute'
    if n.startswith('storage'):
        return 'storage'
    if n.startswith('k8s'):
        return 'k8s'
    if n.startswith('bcme'):
        return 'bcme'
    if n.startswith('support'):
        return 'support'
    return 'unknown'


def is_switch(name: str) -> bool:
    """Check if a node is a switch (has front-panel swp ports)."""
    return classify_node(name) in ('core', 'oob', 'edge', 'air-oob')


def is_valid_hostname(name: str) -> bool:
    """Check if a name is a valid RFC1123 hostname (no spaces, special chars)."""
    return bool(re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$', name))


def classify_net_profile(net_profile: str) -> str:
    """Classify a Wire Map Network Profile string into a canonical key.

    Returns one of: 'cpu', 'gpu', 'oob', 'support', 'storage', 'unknown'.

    Examples:
        'CPU/In-Band Network'   -> 'cpu'
        'GPU Network'           -> 'gpu'
        'OOB / IPMI'            -> 'oob'
        'Air - Management'      -> 'oob'
        'Support'               -> 'support'
        'Storage'               -> 'storage'
    """
    p = net_profile.lower().strip()
    if not p:
        return 'unknown'
    if 'cpu' in p or 'in-band' in p or 'in_band' in p:
        return 'cpu'
    if 'gpu' in p:
        return 'gpu'
    if 'oob' in p or 'ipmi' in p or 'bmc' in p or 'air - management' in p:
        return 'oob'
    if 'support' in p:
        return 'support'
    if 'storage' in p:
        return 'storage'
    return 'unknown'


def build_interface_map(rows, node_name: str) -> dict:
    """Build per-node interface-to-profile mapping from Wire Map rows.

    Checks BOTH sides of each Wire Map row:
      - "A side": node appears as system_name (nic_port is the interface)
      - "B side": node appears as switch_name (switch_port is the interface)

    This handles cases like storage nodes where the Wire Map lists connections
    from the core switch's perspective (core-01:swp49s6 → storage-01:eth1).

    For the A side, replicates the topology generator's ethN assignment:
      1. Pre-scan for explicit ethN in nic_port
      2. Assign sequential ethN for hardware NIC names, skipping explicit ones
    For the B side, uses switch_port directly (already has ethN names).

    Args:
        rows: List of dicts with keys: display_in_air, system_name,
              system_role, nic_port, net_profile, switch_name, switch_port.
              Must be in the same order as the topology generator processes
              them (Air_Only rows first, then Wire Map rows).
        node_name: The actual node name to filter for (checked on both sides).

    Returns:
        Dict keyed by profile classification, e.g.:
        {'cpu': ['eth3', 'eth4'], 'storage': ['eth1', 'eth2'], 'oob': ['eth0']}
        Only keys with at least one interface are included.
    """
    # Step 1: Pre-scan for explicit ethN assignments (A side only)
    explicit_eth = set()
    for r in rows:
        if not r.get('display_in_air'):
            continue
        if r.get('system_name') != node_name:
            continue
        if is_switch(r.get('system_role', '')):
            continue
        m = re.search(r"eth(\d+)", r.get('nic_port', '') or '')
        if m:
            explicit_eth.add(int(m.group(1)))

    # Also pre-scan B side for explicit ethN in switch_port
    for r in rows:
        if not r.get('display_in_air'):
            continue
        sn = r.get('switch_name', '') or r.get('switch_role', '')
        if sn != node_name:
            continue
        if is_switch(node_name):
            continue
        m = re.search(r"eth(\d+)", r.get('switch_port', '') or '')
        if m:
            explicit_eth.add(int(m.group(1)))

    # Step 2: Iterate rows, assign ethN, classify
    # Reserve eth0 for OOB management (matches topology_generator's _oob_eth0 logic).
    result = defaultdict(list)
    explicit_eth.add(0)
    eth_counter = 0

    def next_eth():
        nonlocal eth_counter
        while eth_counter in explicit_eth:
            eth_counter += 1
        idx = eth_counter
        eth_counter += 1
        return f"eth{idx}"

    seen_ifaces = set()

    # Pass A: rows where node is system_name
    for r in rows:
        if not r.get('display_in_air'):
            continue
        if r.get('system_name') != node_name:
            continue
        if is_switch(r.get('system_role', '')):
            continue

        switch_role = r.get('switch_role', '')
        if not switch_role or switch_role.upper() == 'NA':
            continue
        switch_name = r.get('switch_name', '')
        if not is_valid_hostname(r.get('system_name', '')) or (
            switch_role.lower() != 'outbound' and not is_valid_hostname(switch_name)
        ):
            continue
        if switch_role.lower() == 'outbound':
            nic_port = r.get('nic_port', '') or ''
            m = re.search(r"eth(\d+)", nic_port)
            if m:
                _port = f"eth{m.group(1)}"
            else:
                _port = next_eth()
            if _port not in seen_ifaces:
                seen_ifaces.add(_port)
                profile = classify_net_profile(r.get('net_profile', ''))
                result[profile].append(_port)
            continue

        switch_port = r.get('switch_port', '')
        if not switch_port:
            continue

        nic_port = r.get('nic_port', '') or ''
        m = re.search(r"eth(\d+)", nic_port)
        if m:
            iface = f"eth{m.group(1)}"
        else:
            iface = next_eth()

        if iface not in seen_ifaces:
            seen_ifaces.add(iface)
            profile = classify_net_profile(r.get('net_profile', ''))
            result[profile].append(iface)

    # Pass B: rows where node is switch_name (the "other side" of the connection)
    # This catches cases like storage nodes listed as the switch side of core→storage rows
    for r in rows:
        if not r.get('display_in_air'):
            continue
        sn = r.get('switch_name', '') or r.get('switch_role', '')
        if sn != node_name:
            continue
        # Skip if node is a switch (switches use swpN, not ethN)
        if is_switch(node_name):
            continue
        # The interface on this side is switch_port
        switch_port = r.get('switch_port', '') or ''
        m = re.search(r"eth(\d+)", switch_port)
        if not m:
            continue
        iface = f"eth{m.group(1)}"

        if iface not in seen_ifaces:
            seen_ifaces.add(iface)
            profile = classify_net_profile(r.get('net_profile', ''))
            result[profile].append(iface)

    return dict(result)
