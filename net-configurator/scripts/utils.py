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

    On hash collision (3-byte NIC portion has only ~16M values), retries
    with an incremented suffix until a free slot is found.
    """
    key = f"{seed}:{node}:{interface}"
    for attempt in range(64):
        tag = key if attempt == 0 else f"{key}#{attempt}"
        h = hashlib.md5(tag.encode()).hexdigest()
        mac = f"48:b0:2d:{h[0:2]}:{h[2:4]}:{h[4:6]}"
        existing = _mac_registry.get(mac)
        if existing is None:
            _mac_registry[mac] = key
            return mac
        if existing == key:
            return mac
    raise ValueError(
        f"MAC exhaustion: could not resolve collision for '{key}' after 64 attempts"
    )


def reset_mac_registry():
    """Clear the MAC collision registry. Call between independent generation runs."""
    _mac_registry.clear()


def classify_node(name: str) -> str:
    """Classify a node by its name into a fine-grained role.

    Returns one of:
        'core', 'csl', 'gsl', 'oob', 'air-oob', 'edge', 'infra', 'compute',
        'storage', 'support', 'k8s', 'bcme', 'unknown'

    Used by both the Excel parser and topology generator. Each caller
    maps these fine-grained roles to its own categories as needed.

    'csl' (CPU/Storage Leaf) and 'gsl' (GPU Spine/Leaf) appear in
    non-collapsed designs (e.g. 2-8-9-800 with convergence=dedicated_gpu)
    where the GPU fabric is split off from the converged fabric.

    Accepts both legacy hostname-as-role values (`core-01`) and canonical
    role strings (`core`, `csl`, `gsl-plane1`, …) from post-step-4 Excels.
    """
    n = (name or '').lower()
    # Canonical role direct match (post-step-4 Excels). Plane-specific
    # gsl-plane1/2 collapse to 'gsl' for the topology defaults.
    if n in ('core',):
        return 'core'
    # csl + the post-rename compute leaf/spine short names (cl/cs). These are
    # SN56xx 64-port compute-fabric switches and must get the switch resource
    # defaults (4096 MB) — Air rejects switches below its 2048 MB minimum, and
    # we standardise switches at 4096. Bare 'cs' is the 2-8-9-800 N/S spine
    # function (model ns_spine_function: cs); without this it fell through to
    # 'unknown' (1024 MB) and the sim imported INVALID.
    if n in ('csl', 'cl', 'cs'):
        return 'csl'
    if n in ('gsl', 'gsl-plane1', 'gsl-plane2', 'gl', 'gs'):
        return 'gsl'
    if n in ('oob-switch',):
        return 'oob'
    if n == 'air-oob':
        return 'air-oob'
    if n == 'edge':
        return 'edge'
    if n == 'gpu':
        return 'compute'
    if n in ('support', 'storage', 'k8s', 'bcme', 'oob-server', 'dhcp'):
        return n if n != 'oob-server' and n != 'dhcp' else 'infra'
    # ext-storage = customer-side simulated storage aggregate (Ubuntu + FRR
    # speaking BGP unnumbered eBGP back to CSL STORAGE VRF). Air-only.
    # Classified as 'infra' so OS resolves to Ubuntu (not Cumulus VX) and
    # the node is excluded from compute/storage/support host buckets.
    if n == 'ext-storage':
        return 'infra'
    # Legacy hostname-prefix fallbacks
    if n.startswith('core-'):
        return 'core'
    if n.startswith('csl-') or n.startswith('cl-') or n.startswith('cs-'):
        return 'csl'
    if n.startswith('gsl-') or n.startswith('gl-') or n.startswith('gs-'):
        return 'gsl'
    if n == 'air-oob-switch':
        return 'air-oob'
    if n.startswith('oob-switch-'):
        return 'oob'
    # Infra before edge — dhcp-edge is infra, not an edge switch.
    # external-conn / external-dhcp / utility are the L3-OOB Ubuntu trio.
    if any(x in n for x in ('dhcp', 'oob-server', 'external-conn', 'utility')):
        return 'infra'
    if 'edge' in n:
        return 'edge'
    if 'node' in n and ('su-' in n or n.startswith('node')):
        return 'compute'
    # 2-8-9-800-style naming: gpu-NN are HGX B300 compute nodes.
    if n.startswith('gpu-'):
        return 'compute'
    # ext-storage-* must be checked BEFORE the generic 'storage' prefix —
    # the `ext-` prefix distinguishes the customer-side aggregate from
    # cluster-managed storage hosts.
    if n.startswith('ext-storage'):
        return 'infra'
    if n.startswith('storage'):
        return 'storage'
    if n.startswith('k8s'):
        return 'k8s'
    if n.startswith('bcme'):
        return 'bcme'
    # 2-8-9-800-style control-plane nodes (Base Command Manager, Slurm head)
    if n.startswith('bcm-') or n.startswith('slurm-'):
        return 'support'
    if n.startswith('support'):
        return 'support'
    return 'unknown'


def is_switch(name: str) -> bool:
    """Check if a node is a switch (has front-panel swp ports).

    Accepts both legacy hostname-as-role values (`core-01`, `csl-02`,
    …) — handled via classify_node() prefix matching — and canonical
    role strings (`core`, `csl`, `gsl`, `gsl-plane1`, `gsl-plane2`,
    `oob-switch`, `edge`, `air-oob`).
    """
    n = (name or '').strip().lower()
    # Canonical role direct match (post-step-4 Excels)
    if n in ('core', 'csl', 'cs', 'cl', 'gsl', 'gsl-plane1', 'gsl-plane2',
             'gl-plane1', 'gl-plane2', 'gs-plane1', 'gs-plane2',
             'oob-switch', 'edge', 'air-oob'):
        return True
    # Legacy hostname-as-role fallback (3 live archs pre-migration)
    return classify_node(name) in ('core', 'csl', 'gsl', 'oob', 'edge', 'air-oob')


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

    # Step 1b: identify the "first OOB-peer row" that the topology generator
    # reserves as eth0 (see topology_generator.py:_oob_eth0). build_interface_map
    # must apply the same rule so that the netplan-side and topology-side eth
    # numbering stay in sync. Otherwise an extra BMC/IPMI row interleaved
    # before the bond ports shifts the bond down one slot (e.g. eth2/eth3
    # instead of eth1/eth2) — bond ends up pairing a CPU and a GPU NIC.
    eth0_row_key = None
    for r in rows:
        if not r.get('display_in_air'):
            continue
        if r.get('system_name') != node_name:
            continue
        if is_switch(r.get('system_role', '')):
            continue
        switch_role = r.get('switch_role', '') or ''
        if classify_node(switch_role) == 'oob' and r.get('switch_port'):
            eth0_row_key = (r.get('switch_name'), r.get('switch_port'))
            break

    # Step 2: Iterate rows, assign ethN, classify.
    # Reserve eth0 ONLY when an OOB-peer row was found (matches the
    # topology generator's _oob_eth0 logic, which also conditionally
    # reserves eth0). Pre-MR-!26 this was unconditional, which caused
    # off-by-one drift when a server had no OOB-peer row (IPMI rows
    # with blank Port (B), etc.) — topology started at eth0 but
    # netplan started at eth1.
    result = defaultdict(list)
    if eth0_row_key is not None:
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
        elif eth0_row_key and (r.get('switch_name'), r.get('switch_port')) == eth0_row_key:
            # This is the row the topology generator reserved as eth0.
            iface = "eth0"
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


_PLANE_RE = re.compile(r'-plane(\d+)(?:-|$)')


def plane_for_switch(switch_hostname: str) -> str | None:
    """Extract plane name from a switch hostname.

    'gsl-plane2-01' -> 'plane2'
    'oob-switch-01' -> None
    """
    if not switch_hostname:
        return None
    m = _PLANE_RE.search(switch_hostname)
    return f'plane{m.group(1)}' if m else None


def build_nic_destinations(rows, node_name: str) -> dict:
    """Build per-NIC destination mapping from Wire Map rows.

    Mirrors build_interface_map's logic (same A/B side scan, same ethN
    assignment) but returns the destination switch + port for each NIC
    instead of just listing NIC names.

    Returns:
        {iface: {'dst_switch': str, 'dst_port': str, 'profile': str}, ...}

    Used by the parser to determine which plane a GPU NIC belongs to
    (via plane_for_switch() on dst_switch).
    """
    # Pre-scan explicit ethN (A side then B side) — identical to build_interface_map
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

    # Mirror build_interface_map's eth0_row_key logic: identify the
    # first display-yes OOB-peer row and reserve eth0 for it. Without
    # this, build_nic_destinations would unconditionally skip eth0 and
    # shift every iface one slot vs build_interface_map — breaking
    # downstream code that joins the two (e.g. per-rail GPU IP allocation).
    eth0_row_key = None
    for r in rows:
        if not r.get('display_in_air'):
            continue
        if r.get('system_name') != node_name:
            continue
        if is_switch(r.get('system_role', '')):
            continue
        switch_role = r.get('switch_role', '') or ''
        if classify_node(switch_role) == 'oob' and r.get('switch_port'):
            eth0_row_key = (r.get('switch_name'), r.get('switch_port'))
            break

    result: dict = {}
    # Reserve eth0 ONLY when there's an OOB-peer row to anchor it to,
    # matching build_interface_map (and the topology generator).
    if eth0_row_key is not None:
        explicit_eth.add(0)
    eth_counter = 0

    def next_eth():
        nonlocal eth_counter
        while eth_counter in explicit_eth:
            eth_counter += 1
        idx = eth_counter
        eth_counter += 1
        return f"eth{idx}"

    # Pass A: node is system_name
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
            iface = f"eth{m.group(1)}" if m else next_eth()
            if iface not in result:
                result[iface] = {
                    'dst_switch': '',
                    'dst_port': '',
                    'profile': classify_net_profile(r.get('net_profile', '')),
                    'raw_profile': r.get('net_profile', '') or '',
                }
            continue

        switch_port = r.get('switch_port', '')
        if not switch_port:
            continue

        nic_port = r.get('nic_port', '') or ''
        m = re.search(r"eth(\d+)", nic_port)
        if m:
            iface = f"eth{m.group(1)}"
        elif eth0_row_key and (r.get('switch_name'), r.get('switch_port')) == eth0_row_key:
            iface = "eth0"
        else:
            iface = next_eth()
        if iface not in result:
            result[iface] = {
                'dst_switch': switch_name,
                'dst_port': switch_port,
                'profile': classify_net_profile(r.get('net_profile', '')),
                'raw_profile': r.get('net_profile', '') or '',
            }

    # Pass B: node is switch_name (other side of connection)
    for r in rows:
        if not r.get('display_in_air'):
            continue
        sn = r.get('switch_name', '') or r.get('switch_role', '')
        if sn != node_name:
            continue
        if is_switch(node_name):
            continue
        switch_port = r.get('switch_port', '') or ''
        m = re.search(r"eth(\d+)", switch_port)
        if not m:
            continue
        iface = f"eth{m.group(1)}"
        if iface not in result:
            result[iface] = {
                'dst_switch': r.get('system_name', ''),
                'dst_port': r.get('nic_port', ''),
                'profile': classify_net_profile(r.get('net_profile', '')),
                'raw_profile': r.get('net_profile', '') or '',
            }

    return result
