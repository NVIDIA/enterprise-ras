#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
ERA Excel Parser — generates Ansible inventory from wiremap Excel templates.

Parses the Nodes and Wire Map sheets from each architecture's Excel file and
produces host_vars, group_vars, and hosts files under output/<arch>/<site>/inventory/.

Usage:
    # Generate inventory for a single architecture
    python3 scripts/excel_parser.py --arch 2-8-5-200

    # Generate inventory for a specific site
    python3 scripts/excel_parser.py --arch 2-8-5-200 --site customer-a

    # Discover and generate all architectures
    python3 scripts/excel_parser.py
"""

import openpyxl
import re
import yaml
from collections import defaultdict
from pathlib import Path

from utils import generate_mac, classify_node as _classify_node, is_switch, build_interface_map

# Default disabled interfaces (fallback if not in Settings)
DEFAULT_DISABLED_INTERFACES = {
    '2-4-3-200': [60, 62, 64],
    '2-8-5-200': [50, 52, 60, 62, 64],
    '2-8-9-400': [54, 56, 58, 60, 62, 64],
}

# Loopback network base
LOOPBACK_BASE = '172.16.176'

# Role-based host octet ranges for management IP assignment.
# Ranges are spaced to avoid overlap even with large compute counts (up to ~40 nodes).
#   compute: .11+   support: .51+   storage: .61+   k8s: .71+   bcme: .81+
ROLE_HOST_BASE = {
    'compute': 11, 'support': 51, 'storage': 61,
    'k8s': 71, 'bcme': 81, 'unknown': 91,
}


def ports_to_range_string(port_nums):
    """Convert a set of port numbers to compact NVUE swp range notation.

    e.g. {1,2,3,5,7,8} -> 'swp1-3,swp5,swp7-8'
    """
    if not port_nums:
        return ''
    nums = sorted(port_nums)
    ranges = []
    start = end = nums[0]
    for n in nums[1:]:
        if n == end + 1:
            end = n
        else:
            ranges.append((start, end))
            start = end = n
    ranges.append((start, end))
    parts = []
    for s, e in ranges:
        parts.append(f'swp{s}-{e}' if s != e else f'swp{s}')
    return ','.join(parts)


# generate_mac() imported from utils.py — shared with topology_generator.py


def classify_host_role(name: str) -> str:
    """Determine a host's data-plane role from its name.

    Returns one of: 'compute', 'storage', 'support', 'k8s', 'bcme', 'switch', 'infra', 'unknown'

    Delegates to utils.classify_node() for the core logic, then maps
    'core'/'oob'/'edge' → 'switch' for backward compatibility.
    """
    role = _classify_node(name)
    if role in ('core', 'oob', 'edge'):
        return 'switch'
    return role


def _build_wiremap_row_list(ws_wiremap, ws_air_only=None):
    """Read Wire Map (and optionally Air_Only) into a list of dicts.

    Returns rows in the same order the topology generator processes them:
    Air_Only rows first, then Wire Map rows.  Each row is a dict with keys
    matching what build_interface_map() expects.

    Column mapping (0-based from iter_rows):
      Wire Map:  [0]=Display in Air, [1]=System Role, [2]=System Name,
                 [3]=NIC/Port, [6]=Network Profile, [10]=Switch Role,
                 [11]=Switch Name, [12]=Switch Port
      Air_Only:  [0]=Display in Air, [1]=System Role, [2]=System Name,
                 [3]=NIC/Port, [4]=Network Profile, [5]=Switch Role,
                 [6]=Switch Name, [7]=Switch Port
    """
    def _parse_sheet(ws, is_air_only=False):
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True), 1):
            if i == 1:
                continue  # skip header
            if is_air_only:
                if len(row) < 8:
                    continue  # skip non-data rows (e.g., version mapping table)
                display_raw = str(row[0]).strip().lower() if row[0] else ''
                system_role = str(row[1]).strip() if row[1] else ''
                system_name = (str(row[2]).strip() if row[2] else '') or system_role
                nic_port = str(row[3]).strip() if row[3] else ''
                net_profile = str(row[4]).strip() if row[4] else ''
                switch_role = str(row[5]).strip() if row[5] else ''
                switch_name = (str(row[6]).strip() if row[6] else '') or switch_role
                switch_port = str(row[7]).strip() if row[7] else ''
            else:
                display_raw = str(row[0]).strip().lower() if row[0] else ''
                system_role = str(row[1]).strip() if row[1] else ''
                system_name = (str(row[2]).strip() if row[2] else '') or system_role
                nic_port = str(row[3]).strip() if len(row) > 3 and row[3] else ''
                net_profile = str(row[6]).strip() if len(row) > 6 and row[6] else ''
                switch_role = str(row[10]).strip() if len(row) > 10 and row[10] else ''
                switch_name = (str(row[11]).strip() if len(row) > 11 and row[11] else '') or switch_role
                switch_port = str(row[12]).strip() if len(row) > 12 and row[12] else ''

            if not system_role:
                continue

            rows.append({
                'display_in_air': display_raw == 'yes',
                'system_role': system_role,
                'system_name': system_name,
                'nic_port': nic_port,
                'net_profile': net_profile,
                'switch_role': switch_role,
                'switch_name': switch_name,
                'switch_port': switch_port,
            })
        return rows

    result = []
    # Air_Only rows first (same as topology generator)
    if ws_air_only is not None:
        result.extend(_parse_sheet(ws_air_only, is_air_only=True))
    result.extend(_parse_sheet(ws_wiremap, is_air_only=False))
    return result


def build_devices(nodes, vlans, mgmt_subnets, node_oob_mapping=None, wiremap_rows=None):
    """Build the devices dict for dnsmasq DHCP reservations and server netplan config.

    Generates:
      - eth0_ip + mac for ALL non-switch hosts (for DHCP reservations)
      - Data-plane IPs for known roles:
        - compute: bond_ip (CPU subnet), gpu_ip1/gpu_ip2 (GPU subnet)
        - storage: bond_ip1/bond_ip2 (storage subnet)
        - support: bond_ip1/bond_ip2 (support subnet)

    When node_oob_mapping is provided (from Wire Map 'Air - Management' rows),
    eth0_ip is derived from the OOB switch's subnet rather than the Nodes tab.
    This ensures each node gets an IP on the correct OOB subnet matching the
    topology (source of truth pattern).

    MACs are auto-generated deterministically (matching topology_generator.py)
    unless already present in the Excel Nodes tab.

    Args:
        nodes: list of node dicts from parse_nodes() [{name, mac, mgmt_ip, ...}]
        vlans: list of vlan dicts from parse_vlans() [{id, name, subnet, ...}]
        mgmt_subnets: list of management subnet strings (for round-robin assignment)
        node_oob_mapping: dict {node_name: oob_switch_name} from Wire Map
        wiremap_rows: list of dicts from _build_wiremap_row_list() for interface mapping
    """
    devices = {}
    node_oob_mapping = node_oob_mapping or {}

    # Build subnet lookup by VLAN name (lowercase), with normalized aliases
    subnet_map = {}
    for vlan in vlans:
        if vlan.get('name') and vlan.get('subnet'):
            key = vlan['name'].lower()
            subnet_map[key] = vlan['subnet']
            # Add short aliases for multi-word VLAN names
            if 'cpu' in key or 'in-band' in key:
                subnet_map['cpu'] = vlan['subnet']
            if 'gpu' in key:
                subnet_map['gpu'] = vlan['subnet']
            if 'storage' in key:
                subnet_map['storage'] = vlan['subnet']
            if 'support' in key:
                subnet_map['support'] = vlan['subnet']

    # Extract base IPs from subnets (e.g., '172.16.178.0/24' → '172.16.178')
    def subnet_base(subnet_str):
        return subnet_str.split('/')[0].rsplit('.', 1)[0] if subnet_str else None

    cpu_base = subnet_base(subnet_map.get('cpu'))
    gpu_base = subnet_base(subnet_map.get('gpu'))
    storage_base = subnet_base(subnet_map.get('storage'))
    support_base = subnet_base(subnet_map.get('support'))

    # Track per-role indices for sequential IP assignment
    role_index = {'compute': 0, 'storage': 0, 'support': 0}

    for node in nodes:
        name = node.get('name', '')
        if not name or not node.get('enabled', True):
            continue

        # Use Function column ('role') for switch/infra classification — the Name column
        # may be an OEM hostname (e.g. 'nw-switch01') that doesn't match known patterns
        role = classify_host_role(node.get('role', name))

        # Skip switches and Air infrastructure nodes
        if role in ('switch', 'infra'):
            continue

        # MAC: use Excel value if present, otherwise auto-generate
        mac = node.get('mac') or generate_mac(name, "eth0")

        # eth0_ip: always use Nodes tab mgmt_ip as the authoritative source
        eth0_ip = node.get('mgmt_ip', '')

        entry = {
            'eth0_ip': eth0_ip,
            'mac': mac,
        }

        # Build interface mapping from Wire Map (if available)
        iface_map = {}
        if wiremap_rows:
            iface_map = build_interface_map(wiremap_rows, name)
            if iface_map:
                entry['interfaces'] = iface_map

        # Compute data-plane IPs based on role
        if role == 'compute' and cpu_base and gpu_base:
            idx = role_index['compute']
            gpu_count = max(len(iface_map.get('gpu', [])), 2)
            host_offset = 201 + gpu_count * idx
            if host_offset + gpu_count - 1 <= 254:
                entry['bond_ip'] = f"{cpu_base}.{host_offset}/24"
                # Generate one GPU IP per GPU interface
                gpu_ips = [f"{gpu_base}.{host_offset + g}/24"
                           for g in range(gpu_count)]
                entry['gpu_ips'] = gpu_ips
                # Backward compatibility
                if len(gpu_ips) >= 1:
                    entry['gpu_ip1'] = gpu_ips[0]
                if len(gpu_ips) >= 2:
                    entry['gpu_ip2'] = gpu_ips[1]
            role_index['compute'] += 1

        elif role == 'storage' and storage_base:
            idx = role_index['storage']
            host_offset = 101 + 2 * idx
            if host_offset + 1 <= 254:
                entry['bond_ip1'] = f"{storage_base}.{host_offset}/24"
                entry['bond_ip2'] = f"{storage_base}.{host_offset + 1}/24"
            role_index['storage'] += 1

        elif role in ('support', 'k8s', 'bcme') and support_base:
            idx = role_index['support']
            host_offset = 101 + 2 * idx
            if host_offset + 1 <= 254:
                entry['bond_ip1'] = f"{support_base}.{host_offset}/24"
                entry['bond_ip2'] = f"{support_base}.{host_offset + 1}/24"
            role_index['support'] += 1

        devices[name] = entry

    # Note: switches are NOT added to devices — they get DHCP reservations
    # from the ZTP section of the dnsmasq template (using host_vars mac_address).

    return devices


def parse_oob_switch_configs(ws, ws_air_only=None):
    """Parse Wire Map (and optionally Air_Only) sheet to derive OOB switch port configs.

    Wire Map columns (0-based):
      1  = System Role  (the node/server side of the connection)
      3  = NIC/Port
      10 = Switch Role  (which switch this cable plugs into)
      12 = Switch Port  (which port on that switch)

    Air_Only columns (0-based):
      1  = System Role
      5  = Switch Role
      7  = Switch Port

    Logic:
      - Rows where Switch Role is 'oob-switch-*' and Switch Port is a plain swpN
        (no sub-port) are OOB switch port assignments.
      - If the System Role on that row starts with 'core-', the port is an uplink
        to a core switch → spine_bond_members.
      - All other ports are access ports serving BMC/IPMI connections.
      - Air_Only rows (dhcp-oob, oob-server-01, dhcp-edge) are always access ports.
      - The port on each OOB switch connected to dhcp-oob is tracked as dhcp_oob_port
        so the ZTP MAC can be computed as generate_mac(function_name, dhcp_oob_port).

    Returns:
      {oob_switch_name: {
          'access_ports': 'swp1-43',
          'uplink_ports': 'swp1-43,swp49,swp51',
          'spine_bond_members': ['swp49', 'swp51'],
          'dhcp_oob_port': 'swp44',   # port connected to dhcp-oob (ZTP port)
      }}
    """
    oob_access = defaultdict(set)
    oob_uplink = defaultdict(set)
    dhcp_oob_ports: dict = {}  # {oob_switch_function_name: port_str}

    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        if i == 1:
            continue  # header row
        switch_role = str(row[10]).strip() if row[10] else ''
        system_role = str(row[1]).strip() if row[1] else ''
        nic_port = str(row[3]).strip() if row[3] else ''
        switch_port = str(row[12]).strip() if row[12] else ''

        if not switch_role.startswith('oob-switch-') or not switch_port or switch_port == 'None':
            continue

        # Track which port dhcp-oob connects to (this is the ZTP interface)
        if system_role == 'dhcp-oob':
            dhcp_oob_ports[switch_role] = switch_port

        # Only plain swpN ports (no sub-ports like swp49s0 on OOB switches)
        m = re.match(r'^swp(\d+)$', switch_port)
        if not m:
            continue
        port_num = int(m.group(1))

        # Core fabric uplinks use swpN on the core side; core eth0 is management
        if system_role.startswith('core-') and nic_port != 'eth0':
            oob_uplink[switch_role].add(port_num)
        else:
            oob_access[switch_role].add(port_num)

    # Also include Air_Only rows (virtual nodes: dhcp-oob, oob-server-01, dhcp-edge)
    # Air_Only columns (0-based): 1=system_role, 5=switch_role, 7=switch_port
    if ws_air_only is not None:
        for i, row in enumerate(ws_air_only.iter_rows(values_only=True), 1):
            if i == 1:
                continue  # header row
            system_role_ao = str(row[1]).strip() if len(row) > 1 and row[1] else ''
            switch_role = str(row[5]).strip() if len(row) > 5 and row[5] else ''
            switch_port = str(row[7]).strip() if len(row) > 7 and row[7] else ''

            if not switch_role.startswith('oob-switch-') or not switch_port or switch_port == 'None':
                continue

            # Track dhcp-oob port (Air_Only takes priority over Wire Map)
            if system_role_ao == 'dhcp-oob':
                dhcp_oob_ports[switch_role] = switch_port

            m = re.match(r'^swp(\d+)$', switch_port)
            if not m:
                continue
            oob_access[switch_role].add(int(m.group(1)))

    result = {}
    for sw in set(oob_access) | set(oob_uplink):
        access_nums = oob_access[sw]
        uplink_nums = oob_uplink[sw]
        entry = {
            'access_ports': ports_to_range_string(access_nums),
            'uplink_ports': ports_to_range_string(access_nums | uplink_nums),
            'spine_bond_members': [f'swp{n}' for n in sorted(uplink_nums)],
        }
        if sw in dhcp_oob_ports:
            entry['dhcp_oob_port'] = dhcp_oob_ports[sw]
        result[sw] = entry
    return result


# Air virtual nodes — these exist in Air simulations but not in physical deployments
AIR_VIRTUAL_NODES = {"dhcp-oob", "oob-server-01", "dhcp-edge"}


def parse_air_virtual_nodes(ws, new_format=False):
    """Detect Air virtual nodes from rows with 'Air - ' network profiles.

    For the old format, reads Wire Map (col 7=profile, col 2=system_role, col 11=switch_role).
    For the new format, reads Air_Only sheet (col 5=profile, col 2=system_role, col 6=switch_role).

    Returns a set of virtual node names found (e.g. {'dhcp-oob', 'oob-server-01'}).
    """
    virtual_nodes = set()
    # New Air_Only sheet: System Role=col2, Network Profile=col5, Switch Role=col6
    # Old Wire Map sheet: System Role=col2, Network Profile=col7, Switch Role=col11
    profile_col = 4 if new_format else 6   # 0-based
    switch_col  = 5 if new_format else 10  # 0-based

    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        if i == 1:
            continue
        if len(row) <= profile_col:
            continue  # skip short rows (e.g., version mapping table)
        profile = str(row[profile_col]).strip() if row[profile_col] else ''
        if not profile.startswith('Air - '):
            continue
        system_role = str(row[1]).strip() if row[1] else ''
        switch_role = str(row[switch_col]).strip() if row[switch_col] else ''
        if system_role in AIR_VIRTUAL_NODES:
            virtual_nodes.add(system_role)
        if switch_role in AIR_VIRTUAL_NODES:
            virtual_nodes.add(switch_role)
    return virtual_nodes


def parse_air_settings(ws_air_only):
    """Read key-value settings from the Air_Only sheet.

    Scans for rows where col1 is a known setting name.
    Returns dict: {'air_mgmt_subnet': '172.20.0.0/24', ...}
    """
    _KNOWN_KEYS = {
        'air management subnet': 'air_mgmt_subnet',
    }
    settings = {}
    for i, row in enumerate(ws_air_only.iter_rows(values_only=True), 1):
        if len(row) < 2 or not row[0]:
            continue
        key = str(row[0]).strip().lower()
        if key in _KNOWN_KEYS and row[1]:
            settings[_KNOWN_KEYS[key]] = str(row[1]).strip()
    return settings


def parse_node_mgmt_mapping(ws, new_format=False):
    """Parse Wire Map eth0 rows to find node → OOB switch mappings.

    Old format: detects rows where profile contains 'Air - Management'.
    New format: detects rows where nic_port=='eth0' and switch connects to an OOB switch
                (Air - Management profile was replaced by OOB / IPMI in the Wire Map).

    Returns dict: {node_name: oob_switch_name}
    e.g. {'su-01-node-01': 'oob-switch-03', 'support-01': 'oob-switch-01'}
    """
    mapping = {}
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        if i == 1:
            continue
        nic_port    = str(row[3]).strip()  if row[3]  else ''
        profile     = str(row[6]).strip()  if row[6]  else ''
        switch_role = str(row[10]).strip() if row[10] else ''

        if nic_port != 'eth0' or not switch_role.startswith('oob-switch'):
            continue

        if new_format:
            # New format: eth0 OOB connections use OOB / IPMI profile in Wire Map
            system_role = str(row[1]).strip() if row[1] else ''
            if system_role:
                mapping[system_role] = switch_role
        else:
            # Old format: only rows explicitly tagged 'Air - Management'
            if 'Air' in profile and 'Management' in profile:
                system_role = str(row[1]).strip() if row[1] else ''
                if system_role:
                    mapping[system_role] = switch_role
    return mapping


# Hardware constants for SN5610/SN5600 per role type.
# breakout = number of sub-ports per physical port.
# lanes    = physical lanes per sub-port (determines sub-port speed).
_ROLE_HW = {
    'cpu':     {'breakout': 4, 'lanes': 2},   # 4x100G, bonded 2 lanes = 200G
    'gpu':     {'breakout': 2, 'lanes': 4},   # 2x200G direct
    'support': {'breakout': 4, 'lanes': 2},   # same as cpu
    'storage': {'breakout': 4, 'lanes': 2},   # bonded storage nodes
    'isl':     {'breakout': 2, 'lanes': 4},   # 2x200G direct
    'oob':     {'breakout': 8, 'lanes': 1},   # 8x50G uplinks to OOB switches
    'edge':    {'breakout': 8, 'lanes': 1},   # 8x50G uplinks to customer edge
    'storage_uplink': {'breakout': 8, 'lanes': 1},  # 8x50G uplinks to storage switches
}

# Map role type -> VLANs & Profiles sheet profile name (for config lookup)
_ROLE_PROFILE_NAME = {
    'cpu':             'CPU/In-Band Network',
    'gpu':             'GPU Network',
    'support':         'Support',
    'storage':         'Storage',
    'oob':             'OOB Uplink',
    'oob_access':      'OOB / IPMI',
    'edge':            'Edge Uplink',
    'isl':             'ISL',
    'storage_uplink':  'Storage Uplink',
}


def _classify_node_profile(net_prof):
    """Return role type for a node-to-core Wire Map profile."""
    p = net_prof.lower()
    if 'cpu' in p or 'in-band' in p:
        return 'cpu'
    if 'gpu' in p:
        return 'gpu'
    if 'support' in p:
        return 'support'
    if 'storage' in p:
        return 'storage'
    return None


def _classify_core_profile(net_prof, sw_roles):
    """Return role type for a core-as-system Wire Map profile."""
    p = net_prof.lower()
    sw = ' '.join(r.lower() for r in sw_roles)
    if 'isl' in p:
        return 'isl'
    # OOB uplinks: "OOB Uplink", "OOB...Uplink", "SN2201 Uplink", or uplink to oob-switch
    if ('oob' in p and 'uplink' in p) or ('sn2201' in p) or ('uplink' in p and 'oob-switch' in sw):
        return 'oob'
    # Storage uplinks: "Storage Uplink" or connects to storage switch
    if ('storage' in p and 'uplink' in p) or ('storage' in sw and 'oob-switch' not in sw and 'edge' not in sw):
        return 'storage_uplink'
    # Edge/EXIT uplinks: "Edge Uplink", "ESL Uplink", or generic uplink
    if 'edge' in p or 'uplink' in p or 'esl' in p:
        return 'edge'
    return None


def parse_core_port_config(ws_wiremap, ws_vlans_profiles):
    """Derive core switch port configuration from the Wire Map sheet.

    Reads two classes of Wire Map rows:
      A. Node-to-core connections: sys_role != core-*, sw_role == core-*
         Switch Port (swpNsX) tells us which core port serves which network profile.
      B. Core-as-system connections: sys_role == core-01
         NIC/Port (swpNsX) tells us the core's own uplinks (OOB, ISL, Edge, Storage).
         Plain integers indicate 'Port Disabled by Neighbor' (adjacent disabled port).

    Returns a dict suitable for merging into group_vars/core.yml:
      network_roles, gpu_interfaces, isl_interfaces, edge_interfaces,
      storage_interfaces (if any), interfaces_disabled.
    """
    # --- Step 1: Build profile config from VLANs & Profiles sheet ---
    # Find the "Port Profiles" section header, then read rows below it.
    # Columns (within Port Profiles section):
    #   1=Profile, 2=Port Mode, 3=Native/Access VLAN, 4=Allowed VLANs,
    #   5=Untagged VLAN, 6=VRF, 7=LACP Bypass, 8=Port Speed
    profile_config = {}   # profile_name -> {mode, native, allowed, untagged, vrf, lacp_bypass}
    in_profiles_section = False
    for row in range(1, ws_vlans_profiles.max_row + 1):
        cell_val = ws_vlans_profiles.cell(row, 1).value
        if isinstance(cell_val, str) and cell_val.strip() == 'Port Profiles':
            in_profiles_section = True
            continue  # skip the section header row
        if not in_profiles_section:
            continue
        name = cell_val
        mode = ws_vlans_profiles.cell(row, 2).value
        if isinstance(name, str) and name.strip() == 'Profile':
            continue  # skip column header row
        if not isinstance(name, str) or not mode:
            continue
        native = ws_vlans_profiles.cell(row, 3).value
        allowed = ws_vlans_profiles.cell(row, 4).value
        untagged = ws_vlans_profiles.cell(row, 5).value
        vrf = ws_vlans_profiles.cell(row, 6).value
        lacp_bypass_val = ws_vlans_profiles.cell(row, 7).value
        breakout_val = ws_vlans_profiles.cell(row, 9).value
        lanes_val = ws_vlans_profiles.cell(row, 10).value
        profile_config[name] = {
            'mode': mode,
            'native': native,
            'allowed': allowed,
            'untagged': untagged,
            'vrf': str(vrf).strip() if vrf else None,
            'lacp_bypass': str(lacp_bypass_val).strip().lower() in ('yes', 'true', '1')
                          if lacp_bypass_val else False,
            'breakout': int(breakout_val) if breakout_val else None,
            'lanes': int(lanes_val) if lanes_val else None,
        }
    # Backward compat alias
    profile_vlans = profile_config

    def _profile_for_role(role_type):
        """Return the full profile config dict for a role type, or empty dict."""
        prof = _ROLE_PROFILE_NAME.get(role_type)
        if prof and prof in profile_config:
            return profile_config[prof]
        return {}

    def _vlan_for_role(role_type):
        return _profile_for_role(role_type).get('native')

    # --- Step 2: Collect Wire Map rows ---
    # node_profiles[prof][base_port] = {subports}
    node_profiles = defaultdict(lambda: defaultdict(set))
    # core_ports[prof] = [(base_port, subport, sw_role), ...]
    core_ports = defaultdict(list)
    disabled_ports = []

    for row in range(2, ws_wiremap.max_row + 1):
        sys_role = str(ws_wiremap.cell(row, 2).value or '').strip()
        nic_port = str(ws_wiremap.cell(row, 4).value or '').strip()
        net_prof = str(ws_wiremap.cell(row, 7).value or '').strip()
        sw_role  = str(ws_wiremap.cell(row, 11).value or '').strip()
        sw_port  = str(ws_wiremap.cell(row, 13).value or '').strip()

        if not sys_role or not net_prof:
            continue

        if sys_role == 'core-01':
            # Core is the "system" side — nic_port is the core's own port
            prof_lower = net_prof.lower()
            if 'disabled' in prof_lower or 'neighbor' in prof_lower:
                m = re.match(r'^(?:swp)?(\d+)$', nic_port)
                if m:
                    disabled_ports.append(int(m.group(1)))
            elif 'unused' in prof_lower or 'usused' in prof_lower:
                pass  # intentionally unused sub-ports — skip
            else:
                m = re.match(r'^swp(\d+)s(\d+)$', nic_port)
                if m:
                    core_ports[net_prof].append((int(m.group(1)), int(m.group(2)), sw_role))

        elif not sys_role.startswith('core-') and sw_role.startswith('core-'):
            # Node/server connecting to core switch
            m = re.match(r'^swp(\d+)s(\d+)$', sw_port)
            if m:
                node_profiles[net_prof][int(m.group(1))].add(int(m.group(2)))

    # --- Step 3: Merge profiles of the same role type ---
    # node side: merge base_port→subport maps per role type
    role_node_ports = defaultdict(lambda: defaultdict(set))  # role_type→base→{subs}
    for prof, ports in node_profiles.items():
        rt = _classify_node_profile(prof)
        if rt:
            for base, subs in ports.items():
                role_node_ports[rt][base] |= subs

    # core side: merge entries per role type
    role_core_entries = defaultdict(list)  # role_type→[(base, sub, sw_role)]
    for prof, entries in core_ports.items():
        rt = _classify_core_profile(prof, [e[2] for e in entries])
        if rt:
            role_core_entries[rt].extend(entries)

    # --- Step 4: Build output structures ---
    def _port_overrides(port_data, breakout):
        """Return port_overrides dict for ports with fewer active subports than breakout."""
        overrides = {}
        for base, subs in port_data.items():
            active = sorted(subs)
            if active != list(range(breakout)):
                overrides[base] = {'subports': active}
        return overrides

    network_roles = {}
    gpu_interfaces = None
    isl_interfaces = None
    edge_interfaces = None
    storage_interfaces = None

    # Process node-to-core roles
    for rt, port_data in role_node_ports.items():
        hw = _ROLE_HW[rt]
        prof = _profile_for_role(rt)
        breakout = prof.get('breakout') or hw['breakout']
        lanes = prof.get('lanes') or hw['lanes']
        base_ports = sorted(port_data.keys())
        vlan = prof.get('native')

        if rt == 'gpu':
            gpu_interfaces = {
                'ports': base_ports,
                'breakout': breakout,
                'lanes': lanes,
                'vlan': vlan,
                'state': 'up',
                'port_overrides': {},
            }
        else:
            overrides = _port_overrides(port_data, breakout)
            role_cfg = {
                'ports': base_ports,
                'breakout': breakout,
                'lanes': lanes,
                'vlan': vlan,
                'lacp_bypass': prof.get('lacp_bypass', False),
                'port_overrides': overrides,
                'bond_overrides': {},
            }
            if prof.get('untagged'):
                role_cfg['vlan_untagged'] = int(prof['untagged'])
            if prof.get('vrf'):
                role_cfg['vrf'] = prof['vrf']
            network_roles[rt] = role_cfg

    # Process core-as-system roles
    for rt, entries in role_core_entries.items():
        hw = _ROLE_HW[rt]
        prof = _profile_for_role(rt)
        breakout = prof.get('breakout') or hw['breakout']
        lanes = prof.get('lanes') or hw['lanes']
        port_data = defaultdict(set)
        for base, sub, _ in entries:
            port_data[base].add(sub)
        base_ports = sorted(port_data.keys())
        overrides = _port_overrides(port_data, breakout)

        if rt == 'isl':
            isl_cfg = {
                'ports': base_ports,
                'breakout': breakout,
                'lanes': lanes,
                'port_overrides': overrides if overrides else {},
            }
            if prof.get('vrf'):
                isl_cfg['vrf'] = prof['vrf']
            isl_interfaces = isl_cfg
        elif rt == 'oob':
            network_roles['oob'] = {
                'ports': base_ports,
                'breakout': breakout,
                'lanes': lanes,
                'vlan': prof.get('native'),
                'lacp_bypass': prof.get('lacp_bypass', False),
                'port_overrides': overrides,
                'bond_overrides': {},
            }
        elif rt == 'edge':
            edge_cfg = {
                'ports': base_ports,
                'breakout': breakout,
                'lanes': lanes,
                'port_overrides': overrides,
            }
            if prof.get('vrf'):
                edge_cfg['vrf'] = prof['vrf']
            edge_interfaces = edge_cfg
        elif rt == 'storage_uplink':
            # If any storage_uplink port is already claimed by another role
            # (e.g. support on port 26 in 2-4-3-200), inherit that role's
            # breakout/lanes — a physical port can only have one breakout mode.
            effective_breakout = breakout
            effective_lanes = lanes
            for p in base_ports:
                for existing_role in network_roles.values():
                    if p in existing_role.get('ports', []):
                        effective_breakout = existing_role['breakout']
                        effective_lanes = existing_role['lanes']
                        break
            overrides = _port_overrides(port_data, effective_breakout)
            storage_interfaces = {
                'ports': base_ports,
                'breakout': effective_breakout,
                'lanes': effective_lanes,
                'vlan': prof.get('native'),
                'lacp_bypass': prof.get('lacp_bypass', False),
                'port_overrides': overrides,
                'bond_overrides': {},
            }

    # Add storage_uplink into network_roles as 'storage'
    if storage_interfaces and 'storage' not in network_roles:
        network_roles['storage'] = storage_interfaces

    result = {
        'network_roles': network_roles,
        'interfaces_disabled': sorted(set(disabled_ports)),
    }
    if gpu_interfaces:
        result['gpu_interfaces'] = gpu_interfaces
    if isl_interfaces:
        result['isl_interfaces'] = isl_interfaces
    if edge_interfaces:
        result['edge_interfaces'] = edge_interfaces

    return result


def parse_settings(ws):
    """Parse the Settings sheet into a dictionary."""
    settings = {}
    for row in range(1, ws.max_row + 1):
        key = ws.cell(row=row, column=1).value
        value = ws.cell(row=row, column=2).value
        if key and value is not None:
            # Normalize key to snake_case
            key_clean = key.lower().replace(' ', '_').replace('-', '_')
            settings[key_clean] = value
    return settings


def parse_versions(ws):
    """Parse the VERSIONS table from the Settings sheet.

    Looks for a row with 'Switch Function' in column 1 and reads the rows
    below it as function → cumulus_version pairs.

    Returns dict: {'core': '5.16.1', 'oob': '5.15.1'} or {} if not found.
    """
    versions = {}
    in_versions = False
    for row in range(1, ws.max_row + 1):
        key = ws.cell(row=row, column=1).value
        if key is None:
            continue
        key_str = str(key).strip()
        if key_str.lower() == 'switch function':
            in_versions = True
            continue
        if in_versions:
            # Stop at blank row or a new section header (no value in col 2)
            value = ws.cell(row=row, column=2).value
            if not key_str or value is None:
                break
            versions[key_str.lower()] = str(value).strip()
    return versions


def parse_nodes(ws):
    """Parse the Nodes sheet into a list of node dictionaries."""
    nodes = []

    # Build column map from header row (row 1)
    col_map = {}
    for c in range(1, ws.max_column + 1):
        val = ws.cell(row=1, column=c).value
        if val:
            col_map[str(val).strip().lower()] = c

    def _col(key, default):
        return col_map.get(key, default)

    func_col    = _col('function', 1)
    name_col    = _col('name', 2)
    mac_col     = _col('mac address for ztp', _col('mac address', _col('mac', 3)))
    mgmt_col    = _col('mgmt ip address', _col('mgmt ip', _col('management ip', 4)))
    prefix_col  = _col('prefix', 5)
    gateway_col = _col('gateway', 6)
    ztp_col     = _col('ztp', None)
    enabled_col = _col('enabled', None)

    for row in range(2, ws.max_row + 1):
        role = ws.cell(row=row, column=func_col).value
        if not role:
            continue

        # Check Enabled column — default to Active if column missing
        enabled_val = str(ws.cell(row=row, column=enabled_col).value or 'Yes').strip().lower() if enabled_col else 'yes'
        is_active = enabled_val in ('yes', 'true', '1', '')

        node = {
            'role': str(role).strip(),
            'name': ws.cell(row=row, column=name_col).value or role,
            'status': 'Active' if is_active else 'Disabled',
            'mac_address': ws.cell(row=row, column=mac_col).value or '',
            'mgmt_ip': ws.cell(row=row, column=mgmt_col).value or '',
            'prefix': ws.cell(row=row, column=prefix_col).value or 24,
            'gateway': ws.cell(row=row, column=gateway_col).value or '',
        }
        if ztp_col:
            node['ztp'] = ws.cell(row=row, column=ztp_col).value or ''
        nodes.append(node)

    return nodes


def parse_vlans(ws):
    """Parse VLANs from the VLANs & Profiles sheet (now with VRF and VNI columns)."""
    vlans = []
    
    # Find column indices from header row (row 2)
    headers = {}
    for col in range(1, ws.max_column + 1):
        val = ws.cell(row=2, column=col).value
        if val:
            headers[val.lower().replace(' ', '_')] = col
    
    # Get column indices with defaults
    id_col = headers.get('vlan_id', 1)
    name_col = headers.get('name', 2)
    purpose_col = headers.get('purpose', 3)
    subnet_col = headers.get('subnet', 4)
    vrf_col = headers.get('vrf', 5)
    vni_col = headers.get('vni', None)
    
    # VLANs section starts at row 3 (after header row 2)
    for row in range(3, ws.max_row + 1):
        vlan_id = ws.cell(row=row, column=id_col).value
        if vlan_id is None or not isinstance(vlan_id, int):
            break  # End of VLAN section
        
        vlan = {
            'id': vlan_id,
            'name': ws.cell(row=row, column=name_col).value,
            'purpose': ws.cell(row=row, column=purpose_col).value,
            'subnet': ws.cell(row=row, column=subnet_col).value,
            'vrf': ws.cell(row=row, column=vrf_col).value or 'default',
        }
        
        # VNI: use column value if present, else derive as VLAN_ID + 4000
        if vni_col:
            vni = ws.cell(row=row, column=vni_col).value
            vlan['vni'] = int(vni) if vni else (vlan_id + 4000)
        else:
            vlan['vni'] = vlan_id + 4000
        
        vlans.append(vlan)
    
    return vlans


def parse_vrfs(ws):
    """Parse VRFs section from the VLANs & Profiles sheet."""
    vrfs = {}
    
    # Find VRFs section
    vrfs_row = None
    for row in range(1, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == 'VRFs':
            vrfs_row = row
            break
    
    if vrfs_row is None:
        return vrfs
    
    # Parse VRF data (starts 2 rows after header)
    for row in range(vrfs_row + 2, ws.max_row + 1):
        vrf_name = ws.cell(row=row, column=1).value
        if vrf_name is None or vrf_name == 'Port Profiles':
            break
        
        vrfs[vrf_name] = {
            'name': vrf_name,
            'description': ws.cell(row=row, column=2).value,
            'l3_vni': ws.cell(row=row, column=3).value,
            'vlan': ws.cell(row=row, column=4).value,
        }
    
    return vrfs


def parse_prefix_lists_sheet(ws):
    """
    Parse the 'Prefix lists' sheet (Option C BGP policy).
    Columns: List name, Rule id, Match (CIDR), Max prefix length.
    Row 1 may be a merged note row; header is 'List name' row; data below.
    Returns dict: list_id -> [ {id, match, max_len}, ... ] for use as overrides.
    """
    overrides = {}
    if ws.max_row < 2:
        return overrides
    # Find header row (row with "List name" in col 1); data starts next row
    header_row = 1
    for r in range(1, min(ws.max_row + 1, 5)):
        val = ws.cell(row=r, column=1).value
        if val and str(val).strip().lower() == 'list name':
            header_row = r
            break
    data_start = header_row + 1
    for row in range(data_start, ws.max_row + 1):
        list_name = ws.cell(row=row, column=1).value
        rule_id = ws.cell(row=row, column=2).value
        match_val = ws.cell(row=row, column=3).value
        if not list_name or not str(list_name).strip():
            continue
        list_id = str(list_name).strip()
        if list_id.lower() == 'list name':
            continue  # skip header row if it appears in data range
        rule = {
            'id': str(rule_id).strip() if rule_id else str(row - 1),
            'match': str(match_val).strip() if match_val else '',
        }
        max_len_val = ws.cell(row=row, column=4).value
        if max_len_val is not None and str(max_len_val).strip():
            rule['max_len'] = str(int(max_len_val)) if isinstance(max_len_val, (int, float)) else str(max_len_val).strip()
        if not rule['match']:
            continue
        if list_id not in overrides:
            overrides[list_id] = []
        overrides[list_id].append(rule)
    return overrides


def generate_prefix_lists(vlans, core_num, loopback_base=None, prefix_list_overrides=None):
    """Generate prefix_list configurations based on VLANs and switch number."""
    prefix_lists = []
    
    # ALL_PREFIXES - always present
    prefix_lists.append({
        'id': 'ALL_PREFIXES',
        'rule': [{'id': '10', 'match': '0.0.0.0/0', 'max_len': '32'}]
    })
    
    # Group VLANs by VRF
    vrf_vlans = {}
    for vlan in vlans:
        vrf = vlan['vrf']
        if vrf not in vrf_vlans:
            vrf_vlans[vrf] = []
        vrf_vlans[vrf].append(vlan)
    
    lb = loopback_base or LOOPBACK_BASE
    # EXIT_LOCAL_IF - for EXIT VRF loopback (per-switch)
    prefix_lists.append({
        'id': 'EXIT_LOCAL_IF',
        'rule': [{'id': '10', 'match': f'{lb}.{4 + core_num}/32', 'max_len': '32'}]
    })
    
    # INBAND VRF prefix lists (per-switch loopback IPs)
    if 'INBAND' in vrf_vlans:
        inband_rules = []
        # INBAND loopback (per-switch)
        inband_rules.append({'id': '10', 'match': f'{lb}.{2 + core_num}/32', 'max_len': '32'})
        rule_id = 20
        for vlan in vrf_vlans['INBAND']:
            if vlan['subnet']:
                subnet_base = vlan['subnet'].rsplit('.', 1)[0]
                inband_rules.append({'id': str(rule_id), 'match': f'{subnet_base}.{1 + core_num}/32', 'max_len': '32'})
                rule_id += 10
        prefix_lists.append({'id': 'INBAND_LOCAL_IF', 'rule': inband_rules})
        
        # INBAND_PREFIXES
        inband_prefix_rules = []
        rule_id = 10
        for vlan in vrf_vlans['INBAND']:
            if vlan['subnet']:
                inband_prefix_rules.append({'id': str(rule_id), 'match': vlan['subnet'], 'max_len': '32'})
                rule_id += 10
        inband_prefix_rules.append({'id': str(rule_id), 'match': f'{lb}.{2 + core_num}/32', 'max_len': '32'})
        prefix_lists.append({'id': 'INBAND_PREFIXES', 'rule': inband_prefix_rules})
    
    # ERA_PREFIXES - loopback supernet
    prefix_lists.append({
        'id': 'ERA_PREFIXES',
        'rule': [
            {'id': '10', 'match': f'{lb}.0/21', 'max_len': '24'},
            {'id': '20', 'match': f'{lb}.0/24', 'max_len': '32'},
        ]
    })
    
    # OOB VRF prefix lists (per-switch loopback IPs)
    if 'OOB' in vrf_vlans:
        oob_vlan = vrf_vlans['OOB'][0]
        if oob_vlan['subnet']:
            oob_subnet_base = oob_vlan['subnet'].rsplit('.', 1)[0]
            
            prefix_lists.append({
                'id': 'LOCAL_OOB_LOOPBACK',
                'rule': [{'id': '10', 'match': f'{lb}.{core_num}/32', 'max_len': '32'}]
            })
            
            prefix_lists.append({
                'id': 'OOB_LOCAL_IF',
                'rule': [
                    {'id': '10', 'match': f'{lb}.{core_num}/32', 'max_len': '32'},
                    {'id': '20', 'match': f'{oob_subnet_base}.{1 + core_num}/32', 'max_len': '32'},
                ]
            })
            
            prefix_lists.append({
                'id': 'OOB_PREFIXES',
                'rule': [
                    {'id': '10', 'match': oob_vlan['subnet'], 'max_len': '32'},
                    {'id': '20', 'match': f'{lb}.{core_num}/32', 'max_len': '32'},
                ]
            })
    
    # VTEP_PREFIXES
    prefix_lists.append({
        'id': 'VTEP_PREFIXES',
        'rule': [{'id': '5', 'match': f'{lb}.8/29', 'max_len': '32'}]
    })

    # Option C: override any list with rules from Excel 'Prefix lists' sheet
    if prefix_list_overrides:
        for pl in prefix_lists:
            if pl['id'] in prefix_list_overrides:
                pl['rule'] = prefix_list_overrides[pl['id']]

    return prefix_lists


def generate_vrf_loopbacks(vlans, core_num, loopback_base=None):
    """Generate VRF loopback IP assignments - unique per switch."""
    lb = loopback_base or LOOPBACK_BASE
    # VRF loopback IPs increment per switch:
    # core-01: EXIT=.5, INBAND=.3, OOB=.1
    # core-02: EXIT=.6, INBAND=.4, OOB=.2
    vrf_loopbacks = {
        'EXIT': f'{lb}.{4 + core_num}/32',
        'INBAND': f'{lb}.{2 + core_num}/32',
        'OOB': f'{lb}.{core_num}/32',
    }
    
    # GPU VRF loopback from GPU VLAN subnet
    for vlan in vlans:
        if vlan['vrf'] == 'GPU' and vlan['subnet']:
            gpu_subnet_base = vlan['subnet'].rsplit('.', 1)[0]
            vrf_loopbacks['GPU'] = f'{gpu_subnet_base}.{4 + core_num}/32'
            break
    
    return vrf_loopbacks


def get_oob_nodes_for_inventory(nodes, settings):
    """
    Return OOB switch nodes for inventory, driven by Settings management_switches
    and mgmt_subnets.

    SVI IPs and gateways are derived from Settings mgmt_subnets:
      - Single subnet (e.g., 192.168.200.0/24): gateway=.1, SVI IPs=.2,.3,.4
      - Multiple subnets: each switch gets its own subnet, gateway=.1, SVI=.2
    """
    oob_from_sheet = sorted(
        [n for n in nodes if n['status'] != 'Disabled' and n['role'].startswith('oob-switch-')],
        key=lambda x: x['role'],
    )
    try:
        n_oob = int(settings.get('management_switches', 0) or 0)
    except (TypeError, ValueError):
        n_oob = 0
    if n_oob <= 0:
        n_oob = len(oob_from_sheet)
    result = list(oob_from_sheet[:n_oob])

    # Parse mgmt_subnets from Settings tab
    mgmt_subnets_str = str(settings.get('mgmt_subnets', '')).strip()
    mgmt_subnets = [s.strip() for s in mgmt_subnets_str.split(',') if s.strip()] if mgmt_subnets_str else []

    # Pad with synthetic nodes if needed
    while len(result) < n_oob:
        k = len(result) + 1
        result.append({
            'role': f"oob-switch-{k:02d}",
            'name': f"oob-switch-{k:02d}",
            'status': 'Active',
            'mac_address': '',
            'mgmt_ip': '',
            'prefix': 24,
            'gateway': '',
        })

    # Derive SVI IPs and gateways from mgmt_subnets
    if len(mgmt_subnets) == 1:
        # Single subnet: all switches share it
        # Gateway = .1, SVI IPs = .2, .3, .4, ...
        subnet_str = mgmt_subnets[0]
        net_ip, prefix = subnet_str.split('/')
        prefix = int(prefix)
        base = net_ip.rsplit('.', 1)[0]
        net_last = int(net_ip.rsplit('.', 1)[1])
        for i, node in enumerate(result):
            node['svi_ip'] = f"{base}.{net_last + 2 + i}"
            node['gateway'] = f"{base}.{net_last + 1}"
            node['prefix'] = prefix
    elif len(mgmt_subnets) >= len(result):
        # Multiple subnets: one per switch
        # Gateway = .1, SVI = .2 in each subnet
        for i, node in enumerate(result):
            subnet_str = mgmt_subnets[i]
            net_ip, prefix = subnet_str.split('/')
            prefix = int(prefix)
            base = net_ip.rsplit('.', 1)[0]
            net_last = int(net_ip.rsplit('.', 1)[1])
            node['svi_ip'] = f"{base}.{net_last + 2}"
            node['gateway'] = f"{base}.{net_last + 1}"
            node['prefix'] = prefix
    else:
        # Fallback: not enough subnets — use what we have
        for i, node in enumerate(result):
            if i < len(mgmt_subnets):
                subnet_str = mgmt_subnets[i]
                net_ip, prefix = subnet_str.split('/')
                prefix = int(prefix)
                base = net_ip.rsplit('.', 1)[0]
                net_last = int(net_ip.rsplit('.', 1)[1])
                node['svi_ip'] = f"{base}.{net_last + 2}"
                node['gateway'] = f"{base}.{net_last + 1}"
                node['prefix'] = prefix

    return result


def categorize_nodes(nodes, settings=None):
    """Categorize nodes by their role type. OOB count is driven by settings management_switches."""
    settings = settings or {}
    categories = {
        'core': [],
        'oob': [],
        'gpu_nodes': [],
        'support': [],
        'storage': [],
        'k8s': [],
    }
    for node in nodes:
        if node['status'] == 'Disabled':
            continue
        role = node['role']
        if role.startswith('core-'):
            categories['core'].append(node)
        elif role.startswith('oob-switch-'):
            # Collected below via get_oob_nodes_for_inventory
            pass
        elif role.startswith('su-') and 'node' in role:
            categories['gpu_nodes'].append(node)
        elif role.startswith('support-') or role.startswith('k8s-'):
            categories['support'].append(node)
        elif role.startswith('storage-'):
            categories['storage'].append(node)
    categories['oob'] = get_oob_nodes_for_inventory(nodes, settings)
    return categories


def generate_hosts_file(settings, nodes, output_dir, air_virtual_nodes=None):
    """Generate the Ansible hosts inventory file."""
    arch = settings.get('architecture', '2-4-3-200')
    categories = categorize_nodes(nodes, settings)
    air_virtual_nodes = air_virtual_nodes or set()
    
    lines = [
        "# ============================================================================",
        f"# {arch} Deployment Inventory (Generated from Excel)",
        "# ============================================================================",
        f"# {len(categories['core'])} Core switches, {len(categories['oob'])} OOB switches",
        "# ============================================================================",
        "",
    ]
    
    # Core switches
    if categories['core']:
        lines.append("[core]")
        for node in sorted(categories['core'], key=lambda x: x['role']):
            lines.append(node['role'])
        lines.append("")
    
    # OOB switches
    if categories['oob']:
        lines.append("[oob]")
        for node in sorted(categories['oob'], key=lambda x: x['role']):
            lines.append(node['role'])
        lines.append("")
    
    # GPU nodes — use node['name'] (OEM name) so inventory_hostname matches devices dict key
    if categories['gpu_nodes']:
        lines.append("[nodes]")
        for node in sorted(categories['gpu_nodes'], key=lambda x: x['name'] or x['role']):
            lines.append(node['name'] or node['role'])
        lines.append("")

    # Storage
    if categories['storage']:
        lines.append("[storage]")
        for node in sorted(categories['storage'], key=lambda x: x['name'] or x['role']):
            lines.append(node['name'] or node['role'])
        lines.append("")

    # Support
    if categories['support']:
        lines.append("[support]")
        for node in sorted(categories['support'], key=lambda x: x['name'] or x['role']):
            lines.append(node['name'] or node['role'])
        lines.append("")
    
    # Air virtual node groups (only if Air rows exist in Wire Map)
    dhcp_nodes = sorted(n for n in air_virtual_nodes if n.startswith('dhcp-'))
    oob_server_nodes = sorted(n for n in air_virtual_nodes if n.startswith('oob-server'))
    has_air = bool(dhcp_nodes or oob_server_nodes)

    if dhcp_nodes:
        lines.append("[dhcp]")
        lines.extend(dhcp_nodes)
        lines.append("")

    if oob_server_nodes:
        lines.append("[oob-server]")
        lines.extend(oob_server_nodes)
        lines.append("")

    # Groups
    lines.extend([
        "[switches:children]",
        "core",
        "oob",
        "",
        "[switches:vars]",
        "ansible_user=cumulus",
        "",
    ])
    servers_children = [g for g in ["nodes", "storage", "support"] if categories.get({"nodes": "gpu_nodes"}.get(g, g))]
    if dhcp_nodes:
        servers_children.append("dhcp")
    if oob_server_nodes:
        servers_children.append("oob-server")
    lines.extend([
        "[servers:children]",
        *servers_children,
        "",
        "[servers:vars]",
        "ansible_user=ubuntu",
        "",
    ])
    
    output_file = output_dir / "hosts"
    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))
    
    return output_file


def generate_host_vars(nodes, vlans, output_dir, arch, settings, prefix_list_overrides=None, oob_switch_configs=None, vrfs=None, air_settings=None):
    """Generate host_vars YAML files for each node. OOB count from Settings management_switches. prefix_list_overrides from Excel 'Prefix lists' sheet (Option C). oob_switch_configs derived from Wire Map."""
    host_vars_dir = output_dir / "host_vars"
    host_vars_dir.mkdir(exist_ok=True)
    generated_files = []
    categories = categorize_nodes(nodes, settings)
    nodes_to_process = (
        categories['core'] + categories['oob'] + categories['gpu_nodes']
        + categories['storage'] + categories['support']
    )
    loopback_base = str(settings.get('loopback_base') or LOOPBACK_BASE).strip()

    # Air management subnet for switch eth0 IPs
    air_settings = air_settings or {}
    air_mgmt_subnet = air_settings.get('air_mgmt_subnet', '172.20.0.0/24')
    air_mgmt_base = air_mgmt_subnet.split('/')[0].rsplit('.', 1)[0]
    settings['_air_mgmt_base'] = air_mgmt_base  # pass to switch host_vars generation
    air_switch_idx = 1  # .201, .202, .203, ...

    for node in nodes_to_process:
        role = node['role']
        
        # Build host vars
        host_vars = {
            'ansible_host': node['mgmt_ip'],
            # Use the Excel Name column as hostname — this is the OEM/customer name.
            # Config files and DHCP hostname use this value so ZTP downloads match
            # what Air names the VM (from the topology JSON node name).
            'hostname': node['name'] or role,
        }
        
        # Switches ZTP via eth0 on the air-mgmt subnet.
        # Auto-assign air-mgmt IPs (.200+ for switches) and eth0 MACs.
        if is_switch(role):
            topo_name = node['name'] or role
            host_vars['mac_address'] = generate_mac(topo_name, 'eth0')
            host_vars['ip_assignment_mode'] = 'dhcp'
            host_vars['ansible_host'] = f"{air_mgmt_base}.{200 + air_switch_idx}"
            air_switch_idx += 1

        # Add VLAN interfaces for core switches
        if role.startswith('core-'):
            core_num = int(role.split('-')[1])
            host_vars['router_id'] = f"{loopback_base}.{10 + core_num}"
            host_vars['lo_ip'] = f"{loopback_base}.{10 + core_num}/32"
            
            vlan_interfaces = []
            for vlan in vlans:
                if vlan['subnet']:
                    # Parse subnet to get base IP
                    subnet_parts = vlan['subnet'].split('/')
                    base_ip = subnet_parts[0].rsplit('.', 1)[0]
                    
                    vlan_interfaces.append({
                        'id': f"vlan{vlan['id']}",
                        'ip': f"{base_ip}.{1 + core_num}/{subnet_parts[1]}",
                        'vrr': f"{base_ip}.1/{subnet_parts[1]}",
                        'vlan': str(vlan['id']),
                        'vrf': vlan['vrf'],  # Use VRF from VLAN definition
                    })
            
            if vlan_interfaces:
                host_vars['vlan_interfaces'] = vlan_interfaces
            
            # Generate prefix_lists (loopback_base from Excel Settings; Option C overrides from Prefix lists sheet)
            host_vars['prefix_list'] = generate_prefix_lists(vlans, core_num, loopback_base, prefix_list_overrides)
            # Generate VRF loopbacks (loopback_base from Excel Settings)
            host_vars['vrf_loopbacks'] = generate_vrf_loopbacks(vlans, core_num, loopback_base)
            
            # Disabled interfaces - read from settings or use defaults
            disabled_ports = settings.get('disabled_ports', '')
            if disabled_ports:
                host_vars['interfaces_disabled'] = [int(p.strip()) for p in str(disabled_ports).split(',')]
            elif arch in DEFAULT_DISABLED_INTERFACES:
                host_vars['interfaces_disabled'] = DEFAULT_DISABLED_INTERFACES[arch]
        
        # Add OOB switch specific variables derived from Wire Map
        if role.startswith('oob-switch-'):
            # SVI IP on VLAN 200 — pre-computed by get_oob_nodes_for_inventory()
            # (sequential .2/.3/.4 if single subnet, or per-switch if multi-subnet)
            host_vars['svi_ip'] = f"{node.get('svi_ip', node['mgmt_ip'])}/{node['prefix']}"
            host_vars['default_gateway'] = node['gateway']

            oob_switch_configs = oob_switch_configs or {}
            if role in oob_switch_configs:
                cfg = oob_switch_configs[role]
                host_vars['access_ports'] = cfg['access_ports']
                host_vars['uplink_ports'] = cfg['uplink_ports']
                host_vars['spine_bond_members'] = cfg['spine_bond_members']
            else:
                # Fallback: no Wire Map data for this switch
                host_vars['access_ports'] = 'swp1-48'
                host_vars['uplink_ports'] = 'swp1-49,swp51'
                host_vars['spine_bond_members'] = ['swp49', 'swp51']

        
        # Write YAML file — filename must match the inventory hostname.
        # Switches use role as inventory hostname; servers use node name.
        inv_hostname = role if is_switch(role) else (node['name'] or role)
        output_file = host_vars_dir / f"{inv_hostname}.yml"
        with open(output_file, 'w') as f:
            f.write("---\n")
            f.write(f"# Host variables for {inv_hostname} (Generated from Excel)\n")
            yaml.dump(host_vars, f, default_flow_style=False, sort_keys=False)
        
        generated_files.append(output_file)
    
    return generated_files


def generate_group_vars(settings, vlans, vrfs, output_dir, arch, nodes=None, port_config=None, node_oob_mapping=None, versions=None, wiremap_rows=None, air_settings=None):
    """Generate group_vars YAML files."""
    group_vars_dir = output_dir / "group_vars"
    group_vars_dir.mkdir(exist_ok=True)
    generated_files = []
    
    # all.yml (ntp_servers here so core and oob both get it from group_vars/all)
    # Accept comma- or newline-separated (Excel may show one per line with wrap_text)
    ntp_str = settings.get('ntp_servers', '')
    ntp_list = [s.strip() for s in re.split(r'[,\n]', str(ntp_str)) if ntp_str and s.strip()] if ntp_str else []
    if not ntp_list:
        ntp_list = [
            '0.cumulusnetworks.pool.ntp.org',
            '1.cumulusnetworks.pool.ntp.org',
            '2.cumulusnetworks.pool.ntp.org',
            '3.cumulusnetworks.pool.ntp.org',
        ]
    all_vars = {
        'architecture': settings.get('architecture', '2-4-3-200'),
        'scalable_units': settings.get('scalable_units', 8),
        'nodes_per_su': settings.get('nodes_per_su', 4),
        'tiers': settings.get('tiers', 1),
        'convergence': settings.get('convergence', 'full'),
        'ntp_servers': ntp_list,
    }

    # Add VLAN/network info
    common = {}
    for vlan in vlans:
        # Normalize VLAN name to valid identifier (e.g. "cpu/in-band" → "cpu")
        raw_name = vlan['name'].lower() if vlan['name'] else f"vlan{vlan['id']}"
        name_key = raw_name.split('/')[0].replace('-', '_').replace(' ', '_')
        if vlan['subnet']:
            subnet_parts = vlan['subnet'].split('/')
            base_ip = subnet_parts[0].rsplit('.', 1)[0]
            common[f"{name_key}_network"] = vlan['subnet']
            common[f"{name_key}_gateway"] = f"{base_ip}.1"
            common[f"{name_key}_vlan"] = vlan['id']
    
    all_vars['common'] = common

    # LDAP (#3): read ldap_* settings and generate ldap block
    ldap_enabled = str(settings.get('ldap_enabled', 'No')).strip().lower() in ('yes', 'true', '1')
    ldap_servers_str = str(settings.get('ldap_servers', '')).strip()
    ldap_server_ips = [s.strip() for s in ldap_servers_str.split(',') if s.strip()] if ldap_servers_str else []
    all_vars['ldap'] = {
        'enabled': ldap_enabled,
        'domain': settings.get('ldap_domain', 'example.com'),
        'organization': settings.get('ldap_organization', 'Example Org'),
        'admin_password': '{{ ldap_admin_password }}',
        'base_dn': settings.get('ldap_base_dn', ''),
        'root_dn': settings.get('ldap_root_dn', ''),
        'servers': [{'ip': ip, 'priority': i + 1} for i, ip in enumerate(ldap_server_ips)],
    }

    # LDAP users (default placeholder accounts)
    all_vars['ldap']['users'] = [
        {'firstname': 'John', 'lastname': 'Doe', 'username': 'jdoe', 'password': '{{ ldap_user_default_password }}'},
        {'firstname': 'Alice', 'lastname': 'Smith', 'username': 'asmith', 'password': '{{ ldap_user_default_password }}'},
    ]

    # Status page toggle (for Air HTTP service + nginx basic auth)
    status_page_enabled = str(settings.get('status_page_enabled', 'No')).strip().lower() in ('yes', 'true', '1')
    all_vars['status_page_enabled'] = status_page_enabled

    # Build devices dict from Nodes tab (for DHCP reservations + server netplan config)
    mgmt_subnets_str = str(settings.get('mgmt_subnets', '')).strip()
    mgmt_subnets = [s.strip() for s in mgmt_subnets_str.split(',') if s.strip()] if mgmt_subnets_str else []
    devices = build_devices(nodes or [], vlans, mgmt_subnets, node_oob_mapping, wiremap_rows)
    if devices:
        all_vars['host_dhcp'] = True
        all_vars['devices'] = devices
        auto_mac_count = sum(1 for d in devices.values() if d.get('mac', '').startswith('48:b0:2d:'))
        # Count hosts missing data-plane IPs due to overflow or unknown role
        no_dataplane = sum(1 for d in devices.values()
                          if not any(k in d for k in ('bond_ip', 'bond_ip1', 'gpu_ip1')))
        print(f"  Devices: {len(devices)} hosts ({auto_mac_count} with auto-generated MACs)")
        if no_dataplane:
            roles_without = set()
            for name, d in devices.items():
                if not any(k in d for k in ('bond_ip', 'bond_ip1', 'gpu_ip1')):
                    roles_without.add(classify_host_role(name))
            print(f"    {no_dataplane} hosts without data-plane IPs (roles: {', '.join(sorted(roles_without))})")

    all_vars['switch_user'] = 'cumulus'

    # Generate ztp_interfaces from Air Management Subnet (for switch ZTP on air-oob-switch)
    air_settings = air_settings or {}
    air_mgmt_subnet = air_settings.get('air_mgmt_subnet', '172.20.0.0/24')
    air_mgmt_base, air_mgmt_prefix = air_mgmt_subnet.rsplit('/', 1)
    air_mgmt_base = air_mgmt_base.rsplit('.', 1)[0]  # e.g., "172.20.0"
    air_mgmt_net_octet = int(air_mgmt_subnet.split('/')[0].rsplit('.', 1)[1])  # network last octet

    all_vars['air_mgmt_subnet'] = air_mgmt_subnet

    # Build ztp_interfaces: eth1 (air-mgmt for switch ZTP) + ethN per mgmt_subnet
    ztp_ifaces = [{
        'name': 'eth1',
        'ip': f"{air_mgmt_base}.77",
        'network': air_mgmt_subnet,
        'gateway': f"{air_mgmt_base}.1",
        'purpose': 'air-mgmt',
        'dnsmasq_listen': True,
    }]
    # Parse mgmt_subnets for per-VLAN interfaces
    mgmt_subnets_str = str(settings.get('mgmt_subnets', '')).strip()
    mgmt_subnets_list = [s.strip() for s in mgmt_subnets_str.split(',') if s.strip()] if mgmt_subnets_str else []
    for i, subnet_str in enumerate(mgmt_subnets_list):
        net_ip, prefix = subnet_str.split('/')
        prefix = int(prefix)
        base = net_ip.rsplit('.', 1)[0]
        net_last = int(net_ip.rsplit('.', 1)[1])
        ztp_ifaces.append({
            'name': f'eth{2 + i}',
            'ip': f"{base}.{net_last + 78}",
            'network': subnet_str,
            'gateway': f"{base}.{net_last + 1}",
            'purpose': f'mgmt-subnet-{i + 1}',
            'dnsmasq_listen': True,
        })
    all_vars['ztp_interfaces'] = ztp_ifaces

    # Merge source inventory all.yml for variables the parser doesn't generate
    # (ztp_*, ssh_*, cumulus_target_version, nvue_syntax, etc.)
    project_root = Path(__file__).resolve().parent.parent
    source_all = project_root / "inventories" / arch / "group_vars" / "all.yml"
    if source_all.exists():
        with open(source_all) as f:
            source_vars = yaml.safe_load(f) or {}
        merged_count = 0
        for key, value in source_vars.items():
            if key not in all_vars:
                all_vars[key] = value
                merged_count += 1
        if merged_count:
            print(f"    Merged {merged_count} variables from source inventory (inventories/{arch}/group_vars/all.yml)")

    # Write to all/main.yml (directory form — all/secrets.yml also lives here)
    all_dir = group_vars_dir / "all"
    all_dir.mkdir(exist_ok=True)
    all_file = all_dir / "main.yml"
    with open(all_file, 'w') as f:
        f.write("---\n")
        f.write("# ============================================================================\n")
        f.write("# Global Variables - Applied to All Switches\n")
        f.write("# ============================================================================\n")
        yaml.dump(all_vars, f, default_flow_style=False, sort_keys=False)
    generated_files.append(all_file)

    # Remove stale flat all.yml if it exists (avoid Ansible double-loading)
    stale_all = group_vars_dir / "all.yml"
    if stale_all.exists():
        stale_all.unlink()
    
    # core.yml - Core switch configuration from Excel
    bgp_asn = settings.get('bgp_asn', 4260394788)
    core_vars = {
        'timezone': settings.get('timezone', 'Etc/Zulu'),
        'pre_login_message': """#####################################################################################
#  Welcome to NVIDIA Cumulus VX (TM)                                                #
#  NVIDIA Cumulus VX (TM) is a community supported virtual appliance designed       #
#  for experiencing, testing and prototyping NVIDIA Cumulus' latest technology. #
#  For any questions or technical support, visit our community site at:             #
#  https://www.nvidia.com/en-us/support                                             #
#####################################################################################
""",
        'mh_mac': settings.get('mh_mac', '44:38:39:FF:00:AA'),
        'anycast_mac': settings.get('anycast_mac', '44:38:39:ff:00:ff'),
        'bgp_asn': bgp_asn,
    }
    # Per-function cumulus version from VERSIONS table (new format only)
    if versions and versions.get('core'):
        core_vars['cumulus_target_version'] = versions['core']
    # NTP servers — reuse ntp_list parsed earlier for all_vars
    core_vars['ntp_servers'] = ntp_list

    # Add VLANs list
    core_vars['vlans'] = [v['id'] for v in vlans]
    
    # Build VNIs dict from VLANs (VNI always present — fallback is VLAN_ID + 4000)
    core_vars['vnis'] = {v['id']: v['vni'] for v in vlans}
    
    # VRF VNIs from VRFs section
    if vrfs:
        vrf_vnis = {}
        for vrf_name, vrf_data in vrfs.items():
            if vrf_data.get('l3_vni'):
                vrf_vnis[vrf_name] = int(vrf_data['l3_vni'])
        if vrf_vnis:
            core_vars['vrf_vnis'] = vrf_vnis
    
    # Add disabled interfaces — Wire Map takes precedence over settings/defaults
    if port_config and port_config.get('interfaces_disabled'):
        core_vars['interfaces_disabled'] = port_config['interfaces_disabled']
    else:
        disabled_ports_str = settings.get('disabled_ports', '')
        if disabled_ports_str:
            core_vars['interfaces_disabled'] = [
                int(p.strip()) for p in str(disabled_ports_str).split(',') if p.strip()
            ]
        else:
            core_vars['interfaces_disabled'] = DEFAULT_DISABLED_INTERFACES.get(arch, [])

    # num_physical_ports (#4): SN5610 default is 64; override via Settings
    core_vars['num_physical_ports'] = int(settings.get('num_physical_ports', 64))

    # Inject Wire Map-derived port topology (network_roles, gpu/isl/edge_interfaces)
    if port_config:
        if port_config.get('network_roles'):
            core_vars['network_roles'] = port_config['network_roles']
        for key in ('gpu_interfaces', 'isl_interfaces', 'edge_interfaces'):
            if port_config.get(key):
                core_vars[key] = port_config[key]

    # dhcp_relay (#2):
    #   OOB relay servers = management IPs of OOB switches (derived from Nodes sheet)
    #   EXIT relay servers = exit_dhcp_servers setting (customer DHCP servers)
    oob_nodes = get_oob_nodes_for_inventory(nodes or [], settings)
    oob_relay_servers = [n['mgmt_ip'] for n in oob_nodes if n.get('mgmt_ip')]
    exit_dhcp_str = str(settings.get('exit_dhcp_servers', '')).strip()
    exit_relay_servers = [s.strip() for s in exit_dhcp_str.split(',') if s.strip()] if exit_dhcp_str else []
    dhcp_relay = []
    if exit_relay_servers:
        dhcp_relay.append({
            'vrf': 'EXIT',
            'interfaces': 'edge',
            'vrf_vlan': 3004,
            'servers': exit_relay_servers,
        })
    if oob_relay_servers:
        dhcp_relay.append({
            'vrf': 'OOB',
            'interfaces': ['vlan200'],
            'vrf_vlan': 3001,
            'servers': oob_relay_servers,
        })
    if dhcp_relay:
        core_vars['dhcp_relay'] = dhcp_relay

    # Merge in source inventory variables that the Excel parser doesn't generate.
    # Excel-derived values take precedence; source inventory fills in complex routing
    # config (vrf_config, default_vrf_bgp, nve_vxlan, route_map, community_list, etc.)
    project_root = Path(__file__).resolve().parent.parent
    source_core = project_root / "inventories" / arch / "group_vars" / "core.yml"
    if source_core.exists():
        with open(source_core) as f:
            source_vars = yaml.safe_load(f) or {}
        merged_count = 0
        for key, value in source_vars.items():
            if key not in core_vars:
                core_vars[key] = value
                merged_count += 1
        if merged_count:
            print(f"    Merged {merged_count} variables from source inventory (inventories/{arch}/group_vars/core.yml)")

    core_file = group_vars_dir / "core.yml"
    with open(core_file, 'w') as f:
        f.write("---\n")
        f.write(f"# Core Switch Configuration (Generated from Excel + Source Inventory - {arch})\n\n")
        yaml.dump(core_vars, f, default_flow_style=False, sort_keys=False)
    generated_files.append(core_file)

    # oob.yml — generated from Excel when versions table is present (new format),
    # otherwise copied from source inventory (old format).
    import shutil
    oob_file = group_vars_dir / "oob.yml"
    if versions is not None:
        # New format: generate oob.yml from Excel data + source inventory merge
        oob_vlan_id = next((v['id'] for v in vlans if v.get('name', '').startswith('OOB')), 200)
        pre_login_msg = core_vars['pre_login_message']
        oob_vars = {
            'pre_login_message': pre_login_msg,
            'timezone': settings.get('timezone', 'Etc/Zulu'),
            'oob_vlan': str(oob_vlan_id),
        }
        if versions.get('oob'):
            oob_vars['cumulus_target_version'] = versions['oob']
        # Merge source inventory oob.yml for vars we don't derive from Excel
        source_oob = project_root / "inventories" / arch / "group_vars" / "oob.yml"
        if source_oob.exists():
            with open(source_oob) as f:
                source_oob_vars = yaml.safe_load(f) or {}
            merged_oob = 0
            for key, value in source_oob_vars.items():
                if key not in oob_vars:
                    oob_vars[key] = value
                    merged_oob += 1
            if merged_oob:
                print(f"    Merged {merged_oob} variables from source inventory (inventories/{arch}/group_vars/oob.yml)")
        with open(oob_file, 'w') as f:
            f.write("---\n")
            f.write("# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.\n")
            f.write("# SPDX-License-Identifier: MIT\n")
            f.write(f"# OOB Switch Configuration (Generated from Excel + Source Inventory - {arch})\n\n")
            yaml.dump(oob_vars, f, default_flow_style=False, sort_keys=False)
        generated_files.append(oob_file)
    else:
        # Old format: copy from source inventory if not already present
        src = project_root / "inventories" / arch / "group_vars" / "oob.yml"
        if src.exists() and not oob_file.exists():
            shutil.copy2(src, oob_file)
            generated_files.append(oob_file)

    # Copy switches.yml and servers.yml from source inventory (not derived from Excel)
    for extra_file in ["switches.yml", "servers.yml"]:
        src = project_root / "inventories" / arch / "group_vars" / extra_file
        dst = group_vars_dir / extra_file
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            generated_files.append(dst)

    # Also copy secrets.yml template if not present
    secrets_dst = all_dir / "secrets.yml"
    if not secrets_dst.exists():
        secrets_src = project_root / "inventories" / arch / "group_vars" / "all" / "secrets.yml"
        if not secrets_src.exists():
            secrets_src = project_root / "inventories" / "secrets.yml.example"
        if secrets_src.exists():
            shutil.copy2(secrets_src, secrets_dst)

    return generated_files


def process_excel_template(excel_path, output_dir):
    """Process an Excel template and generate inventory files.

    Args:
        excel_path: Path to the Excel workbook.
        output_dir: Final output directory (e.g. output/<arch>/<site>/inventory/).
                    Files are written directly here — no subdirectories are created.
    """
    print(f"\nProcessing: {excel_path}")

    wb = openpyxl.load_workbook(excel_path, data_only=True)

    # Detect format: new format has Air_Only sheet
    new_format = 'Air_Only' in wb.sheetnames

    # Parse sheets
    settings = parse_settings(wb['Settings'])
    versions = parse_versions(wb['Settings']) if new_format else {}
    nodes = parse_nodes(wb['Nodes'])
    vlans = parse_vlans(wb['VLANs & Profiles'])
    vrfs = parse_vrfs(wb['VLANs & Profiles'])
    prefix_list_overrides = parse_prefix_lists_sheet(wb['Prefix lists']) if 'Prefix lists' in wb.sheetnames else None
    air_virtual_nodes = set()
    node_oob_mapping = {}
    wiremap_rows = None
    if 'Wire Map' in wb.sheetnames:
        ws_wm = wb['Wire Map']
        ws_air_only = wb['Air_Only'] if 'Air_Only' in wb.sheetnames else None
        oob_switch_configs = parse_oob_switch_configs(ws_wm, ws_air_only)
        port_config = parse_core_port_config(ws_wm, wb['VLANs & Profiles'])
        node_oob_mapping = parse_node_mgmt_mapping(ws_wm, new_format=new_format)
        # Build combined wiremap rows for interface mapping (same order as topology generator)
        wiremap_rows = _build_wiremap_row_list(ws_wm, ws_air_only)
        if new_format:
            # New format: Air virtual nodes come from dedicated Air_Only sheet
            air_virtual_nodes = parse_air_virtual_nodes(wb['Air_Only'], new_format=True)
            # dhcp-oob and oob-server-01 are always present (created programmatically
            # by the topology generator even if not listed in Air_Only)
            air_virtual_nodes |= {'dhcp-oob', 'oob-server-01'}
            # Air settings (Air Management Subnet, etc.)
            air_settings = parse_air_settings(wb['Air_Only'])
        else:
            # Old format: Air virtual nodes are tagged rows in Wire Map
            air_virtual_nodes = parse_air_virtual_nodes(ws_wm, new_format=False)
            air_settings = {}
    else:
        oob_switch_configs = {}
        port_config = None

    print(f"  Format: {'new (Air_Only sheet)' if new_format else 'legacy'}")
    print(f"  Settings: {len(settings)} items")
    if versions:
        print(f"  Versions: {versions}")
    print(f"  Nodes: {len(nodes)} total ({len([n for n in nodes if n['status'] == 'Active'])} active)")
    print(f"  VLANs: {len(vlans)}, VRFs: {len(vrfs)} defined")
    if prefix_list_overrides:
        print(f"  Prefix list overrides: {list(prefix_list_overrides.keys())}")
    print(f"  OOB switches from Wire Map: {sorted(oob_switch_configs.keys())}")
    if air_virtual_nodes:
        print(f"  Air virtual nodes: {sorted(air_virtual_nodes)}")
    if node_oob_mapping:
        print(f"  Node mgmt mapping: {len(node_oob_mapping)} nodes with eth0 → OOB switch from Wire Map")
    if port_config:
        roles = list(port_config.get('network_roles', {}).keys())
        extras = [k for k in ('gpu_interfaces', 'isl_interfaces', 'edge_interfaces') if port_config.get(k)]
        print(f"  Core port config from Wire Map: roles={roles} direct={extras} disabled={port_config['interfaces_disabled']}")

    # Get architecture name
    arch = settings.get('architecture', Path(excel_path).stem)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate files
    hosts_file = generate_hosts_file(settings, nodes, output_dir, air_virtual_nodes)
    print(f"  Generated: {hosts_file}")

    host_vars_files = generate_host_vars(nodes, vlans, output_dir, arch, settings, prefix_list_overrides, oob_switch_configs, vrfs, air_settings)

    # Merge host_vars for Air virtual nodes from source inventory.
    # These nodes don't appear in the Excel Nodes sheet but need host_vars.
    # Merge preserves air-deploy.py connection details (ansible_host/port)
    # while updating config vars (oob_server_interfaces, etc.)
    host_vars_dir = output_dir / "host_vars"
    project_root = Path(excel_path).resolve().parent.parent.parent.parent
    # Air Management Subnet for virtual node IPs
    _air_mgmt = air_settings.get('air_mgmt_subnet', '172.20.0.0/24')
    _air_base = _air_mgmt.split('/')[0].rsplit('.', 1)[0]
    _air_prefix = int(_air_mgmt.split('/')[1])

    _connection_keys = {'ansible_host', 'ansible_port', 'ansible_user'}
    for vnode in sorted(air_virtual_nodes):
        src = project_root / "inventories" / arch / "host_vars" / f"{vnode}.yml"
        dst = host_vars_dir / f"{vnode}.yml"
        if not src.exists():
            continue
        with open(src) as f:
            src_vars = yaml.safe_load(f) or {}
        # Load existing output (may have real SSH details from air-deploy)
        existing = {}
        if dst.exists():
            with open(dst) as f:
                existing = yaml.safe_load(f) or {}
        # Merge: source vars as base, preserve existing connection keys
        merged = {**src_vars}
        for key in _connection_keys:
            if key in existing and existing[key] != 'CHANGE_ME':
                merged[key] = existing[key]

        # oob-server-01: eth1 (air-mgmt gateway) + ethN per mgmt_subnet
        if 'oob-server' in vnode:
            _mgmt_str = str(settings.get('mgmt_subnets', '')).strip()
            _mgmt_list = [s.strip() for s in _mgmt_str.split(',') if s.strip()] if _mgmt_str else []
            oob_ifaces = [{
                'name': 'eth1',
                'ip': f"{_air_base}.1",
                'netmask': _air_prefix,
                'network': _air_mgmt,
                'purpose': 'Air Management Gateway',
            }]
            for i, subnet_str in enumerate(_mgmt_list):
                net_ip, prefix = subnet_str.split('/')
                prefix = int(prefix)
                base = net_ip.rsplit('.', 1)[0]
                net_last = int(net_ip.rsplit('.', 1)[1])
                oob_ifaces.append({
                    'name': f'eth{2 + i}',
                    'ip': f"{base}.{net_last + 1}",
                    'netmask': prefix,
                    'network': subnet_str,
                    'purpose': f'OOB Mgmt Subnet {i + 1} Gateway',
                })
            merged['oob_server_interfaces'] = oob_ifaces

        with open(dst, 'w') as f:
            f.write("---\n")
            yaml.dump(merged, f, default_flow_style=False, sort_keys=False)
        host_vars_files.append(dst)

    print(f"  Generated: {len(host_vars_files)} host_vars files")
    
    group_vars_files = generate_group_vars(settings, vlans, vrfs, output_dir, arch, nodes, port_config, node_oob_mapping, versions=versions or None, wiremap_rows=wiremap_rows, air_settings=air_settings)
    print(f"  Generated: {len(group_vars_files)} group_vars files")

    # Loopback visibility (#5): print assignments so users know what IPs get configured
    lb = str(settings.get('loopback_base') or LOOPBACK_BASE).strip()
    core_nodes = sorted([n for n in nodes if n['role'].startswith('core-')], key=lambda x: x['role'])
    if core_nodes:
        print(f"  Loopback assignments (base={lb}):")
        for node in core_nodes:
            core_num = int(node['role'].split('-')[1])
            print(f"    {node['role']}: lo={lb}.{10+core_num}  OOB={lb}.{core_num}  INBAND={lb}.{2+core_num}  EXIT={lb}.{4+core_num}")
    
    return output_dir


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Parse ERA Excel templates and generate Ansible inventory.",
    )
    parser.add_argument('--arch', metavar='ARCH',
                        help="Process only this architecture (e.g. 2-8-5-200)")
    parser.add_argument('--site', metavar='SITE', default='default',
                        help="Site name (default: 'default')")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent.parent
    input_dir = base_dir / "input"
    output_base = base_dir / "output"

    print("=" * 60)
    print("ERA Excel → Inventory Generator")
    print("=" * 60)

    if args.arch:
        # Process a single architecture/site
        excel_path = input_dir / args.arch / args.site / f"{args.arch}.xlsx"
        if not excel_path.exists():
            print(f"❌  Excel not found: {excel_path}")
            raise SystemExit(1)
        output_dir = output_base / args.arch / args.site / "inventory"
        process_excel_template(excel_path, output_dir)
        print(f"\n✅ Inventory written to: {output_dir.relative_to(base_dir)}/")
    else:
        # Discover and process all default templates
        templates = sorted(input_dir.glob("*/default/*.xlsx"))
        if not templates:
            print(f"No templates found under {input_dir}/<arch>/default/")
            return
        for template in templates:
            arch = template.stem
            output_dir = output_base / arch / "default" / "inventory"
            process_excel_template(template, output_dir)
        print(f"\n✅ Inventories written to: output/<arch>/default/inventory/")

    print("=" * 60)


if __name__ == "__main__":
    main()
