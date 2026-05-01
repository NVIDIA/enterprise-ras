#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Validate an ERA Excel configuration file before import/generate.

Checks sheet structure, required fields, IP/subnet formats, VLAN integrity,
duplicate ports, and cross-sheet consistency. Reports all issues found
rather than stopping at the first error.

Usage:
    python3 scripts/validate_excel.py input/2-8-5-200/default/2-8-5-200.xlsx
    python3 scripts/validate_excel.py /path/to/any-config.xlsx
    make validate-excel EXCEL=input/2-8-5-200/default/2-8-5-200.xlsx
"""

import argparse
import ipaddress
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ARCHS = ("2-4-3-200", "2-8-5-200", "2-8-9-400")

REQUIRED_SHEETS = ["Settings", "Nodes", "VLANs & Profiles"]

REQUIRED_SETTINGS_KEYS = [
    "architecture",
    "mgmt_subnets",
    "management_switches",
    "bgp_asn",
    "loopback_base",
]

OPTIONAL_SETTINGS_KEYS = [
    "site_name",
    "deploy_in_air",
    "tiers",
    "convergence",
    "disabled_ports",
    "exit_dhcp_servers",
    "ldap_enabled",
    "ldap_domain",
    "ldap_base_dn",
    "ldap_root_dn",
    "ldap_servers",
    "telemetry_enabled",
    "netq_ip",
    "timezone",
    "mh_mac",
    "anycast_mac",
    "ztp_enabled",
    "ztp_server",
    "ntp_servers",
    "num_physical_ports",
]

# Node columns (1-based)
NODE_COL_FUNCTION = 1
NODE_COL_NAME = 2
NODE_COL_MAC = 3
NODE_COL_MGMT_IP = 4
NODE_COL_PREFIX = 5
NODE_COL_GATEWAY = 6

# Wire Map columns (1-based)
WM_COL_SYSTEM_ROLE = 2
WM_COL_NIC_PORT = 4
WM_COL_NETWORK_PROFILE = 7
WM_COL_SWITCH_ROLE = 11
WM_COL_SWITCH_PORT = 13

# Air_Only columns (1-based)
AIR_COL_SYSTEM_ROLE = 2
AIR_COL_NETWORK_PROFILE = 5
AIR_COL_SWITCH_ROLE = 6
AIR_COL_SWITCH_PORT = 8

MAC_RE = re.compile(r'^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$')
PORT_RE = re.compile(r'^(swp\d+([s]\d+)?|eth\d+|enp\d+s\d+f\d+(np\d+)?)$')


# ---------------------------------------------------------------------------
# Result collector
# ---------------------------------------------------------------------------

class ValidationResult:
    """Collects errors and warnings across all checks."""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, sheet, msg):
        self.errors.append(f"[{sheet}] {msg}")

    def warn(self, sheet, msg):
        self.warnings.append(f"[{sheet}] {msg}")

    @property
    def ok(self):
        return len(self.errors) == 0

    def summary(self):
        lines = []
        if self.errors:
            lines.append(f"\n{'='*60}")
            lines.append(f"ERRORS ({len(self.errors)})")
            lines.append(f"{'='*60}")
            for e in self.errors:
                lines.append(f"  ❌  {e}")
        if self.warnings:
            lines.append(f"\n{'='*60}")
            lines.append(f"WARNINGS ({len(self.warnings)})")
            lines.append(f"{'='*60}")
            for w in self.warnings:
                lines.append(f"  ⚠️  {w}")
        if self.ok and not self.warnings:
            lines.append("\n✅  All checks passed — Excel is valid.")
        elif self.ok:
            lines.append(f"\n✅  No errors found ({len(self.warnings)} warnings).")
        else:
            lines.append(f"\n❌  Validation failed: {len(self.errors)} error(s), {len(self.warnings)} warning(s).")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cell(ws, row, col):
    """Get cell value, stripping strings."""
    v = ws.cell(row=row, column=col).value
    if isinstance(v, str):
        return v.strip()
    return v


def _is_valid_ip(ip_str):
    """Check if string is a valid IPv4 address."""
    try:
        ipaddress.IPv4Address(ip_str)
        return True
    except (ValueError, ipaddress.AddressValueError):
        return False


def _is_valid_cidr(cidr_str):
    """Check if string is a valid IPv4 network in CIDR notation."""
    try:
        ipaddress.IPv4Network(cidr_str, strict=False)
        return True
    except (ValueError, ipaddress.AddressValueError):
        return False


# ---------------------------------------------------------------------------
# Sheet-level validators
# ---------------------------------------------------------------------------

def validate_sheets(wb, result):
    """Check that all required sheets exist."""
    for sheet in REQUIRED_SHEETS:
        if sheet not in wb.sheetnames:
            result.error("Workbook", f"Missing required sheet: '{sheet}'")

    if 'Wire Map' not in wb.sheetnames:
        result.warn("Workbook", "Missing 'Wire Map' sheet — topology and port config will not be generated.")

    if 'Air_Only' not in wb.sheetnames:
        result.warn("Workbook", "Missing 'Air_Only' sheet — Air virtual nodes will not be detected.")


def validate_settings(ws, result):
    """Validate Settings sheet keys and value formats."""
    settings = {}
    for row in range(1, ws.max_row + 1):
        key = _cell(ws, row, 1)
        val = _cell(ws, row, 2)
        if key is None:
            continue
        key_lower = str(key).strip().lower().replace(' ', '_').replace('-', '_')
        # Skip section headers and column headers
        if key_lower in ('setting', 'value', 'general', 'air_deployment',
                         'network', 'management', 'telemetry', 'advanced',
                         'versions', 'switch_function'):
            continue
        settings[key_lower] = val

    # Required keys
    for k in REQUIRED_SETTINGS_KEYS:
        if k not in settings or settings[k] is None or str(settings[k]).strip() == '':
            result.error("Settings", f"Missing required key: '{k}'")

    # Architecture
    arch = str(settings.get('architecture', '')).strip()
    if arch and arch not in VALID_ARCHS:
        result.error("Settings", f"Invalid architecture: '{arch}' (valid: {', '.join(VALID_ARCHS)})")

    # mgmt_subnets — CSV of CIDRs
    mgmt = settings.get('mgmt_subnets')
    if mgmt:
        for part in str(mgmt).split(','):
            part = part.strip()
            if part and not _is_valid_cidr(part):
                result.error("Settings", f"Invalid CIDR in mgmt_subnets: '{part}'")

    # management_switches — positive integer
    ms = settings.get('management_switches')
    if ms is not None:
        try:
            ms_int = int(ms)
            if ms_int < 1:
                result.error("Settings", f"management_switches must be >= 1, got {ms_int}")
        except (TypeError, ValueError):
            result.error("Settings", f"management_switches must be an integer, got '{ms}'")

    # bgp_asn — must be a valid ASN (positive integer)
    asn = settings.get('bgp_asn')
    if asn is not None:
        try:
            asn_int = int(asn)
            if asn_int < 1:
                result.error("Settings", f"bgp_asn must be positive, got {asn_int}")
        except (TypeError, ValueError):
            result.error("Settings", f"bgp_asn must be an integer, got '{asn}'")

    # loopback_base — first 3 octets of IP
    lb = settings.get('loopback_base')
    if lb:
        lb_str = str(lb).strip()
        if not _is_valid_ip(f"{lb_str}.1"):
            result.error("Settings", f"Invalid loopback_base: '{lb_str}' (expected first 3 octets, e.g. '172.16.176')")

    # disabled_ports — CSV of integers
    dp = settings.get('disabled_ports')
    if dp:
        for part in str(dp).split(','):
            part = part.strip()
            if part:
                try:
                    int(part)
                except ValueError:
                    result.error("Settings", f"Invalid port number in disabled_ports: '{part}'")

    # ztp_server — valid IP
    ztp = settings.get('ztp_server')
    if ztp and str(ztp).strip():
        if not _is_valid_ip(str(ztp).strip()):
            result.error("Settings", f"Invalid ztp_server IP: '{ztp}'")

    # MAC addresses
    for key in ('mh_mac', 'anycast_mac'):
        mac = settings.get(key)
        if mac and str(mac).strip():
            if not MAC_RE.match(str(mac).strip()):
                result.error("Settings", f"Invalid MAC format for {key}: '{mac}'")

    # ldap_servers — CSV of IPs
    ldap_servers = settings.get('ldap_servers')
    if ldap_servers and str(ldap_servers).strip():
        for part in str(ldap_servers).split(','):
            part = part.strip()
            if part and not _is_valid_ip(part):
                result.error("Settings", f"Invalid IP in ldap_servers: '{part}'")

    # exit_dhcp_servers — CSV of IPs
    exit_dhcp = settings.get('exit_dhcp_servers')
    if exit_dhcp and str(exit_dhcp).strip():
        for part in str(exit_dhcp).split(','):
            part = part.strip()
            if part and not _is_valid_ip(part):
                result.error("Settings", f"Invalid IP in exit_dhcp_servers: '{part}'")

    return settings


def validate_nodes(ws, result, settings=None):
    """Validate Nodes sheet: required columns, IP formats, duplicates.

    Returns a list of dicts with parsed node data for cross-validation:
        [{'function': str, 'ip': str, 'prefix': int, 'gateway': str, 'row': int}, ...]
    """
    # Verify headers
    headers = [_cell(ws, 1, c) for c in range(1, ws.max_column + 1)]
    required_headers = ['Function', 'Mgmt IP Address']
    for h in required_headers:
        if h not in headers:
            result.error("Nodes", f"Missing required column header: '{h}'")

    # Find column indices from headers
    col_map = {}
    for c in range(1, ws.max_column + 1):
        h = _cell(ws, 1, c)
        if h:
            col_map[h] = c

    func_col = col_map.get('Function', NODE_COL_FUNCTION)
    name_col = col_map.get('Name', NODE_COL_NAME)
    mac_col = col_map.get('MAC Address for ZTP', NODE_COL_MAC)
    ip_col = col_map.get('Mgmt IP Address', NODE_COL_MGMT_IP)
    prefix_col = col_map.get('Prefix', NODE_COL_PREFIX)
    gateway_col = col_map.get('Gateway', NODE_COL_GATEWAY)

    functions_seen = []
    ips_seen = []
    parsed_nodes = []
    node_count = 0
    has_core = False

    # When deploying in Air, switches get auto-assigned mgmt IPs — don't require them
    deploy_in_air = False
    if settings:
        deploy_in_air = str(settings.get('deploy_in_air', '')).strip().lower() in ('yes', 'true', '1')

    # Determine which function names are switches
    switch_prefixes = ('core-', 'oob-switch-', 'edge-')

    for row in range(2, ws.max_row + 1):
        func = _cell(ws, row, func_col)
        if func is None or str(func).strip() == '':
            continue

        node_count += 1
        func_str = str(func).strip()

        if func_str.startswith('core-'):
            has_core = True

        is_switch_node = any(func_str.startswith(p) for p in switch_prefixes)

        # Duplicate function names
        functions_seen.append((func_str, row))

        node_data = {'function': func_str, 'row': row,
                     'ip': None, 'prefix': None, 'gateway': None}

        # Mgmt IP — optional for switches in Air deployments (auto-assigned)
        ip = _cell(ws, row, ip_col)
        if ip is None or str(ip).strip() == '':
            if not (deploy_in_air and is_switch_node):
                result.error("Nodes", f"Row {row} ({func_str}): Missing management IP")
        else:
            ip_str = str(ip).strip()
            if not _is_valid_ip(ip_str):
                result.error("Nodes", f"Row {row} ({func_str}): Invalid IP address: '{ip_str}'")
            else:
                ips_seen.append((ip_str, row, func_str))
                node_data['ip'] = ip_str

        # Prefix
        prefix = _cell(ws, row, prefix_col)
        if prefix is not None:
            try:
                p = int(prefix)
                if p < 0 or p > 32:
                    result.error("Nodes", f"Row {row} ({func_str}): Prefix out of range: {p}")
                else:
                    node_data['prefix'] = p
            except (TypeError, ValueError):
                result.error("Nodes", f"Row {row} ({func_str}): Invalid prefix: '{prefix}'")

        # Gateway
        gw = _cell(ws, row, gateway_col)
        if gw is not None and str(gw).strip():
            gw_str = str(gw).strip()
            if not _is_valid_ip(gw_str):
                result.error("Nodes", f"Row {row} ({func_str}): Invalid gateway: '{gw}'")
            else:
                node_data['gateway'] = gw_str

        # Gateway within node's own subnet
        # This is a warning, not an error — in ERA multi-subnet mgmt designs,
        # the OOB server on the first subnet acts as a router, so nodes on
        # other subnets may legitimately use a gateway from a different subnet.
        if node_data['ip'] and node_data['prefix'] and node_data['gateway']:
            try:
                node_net = ipaddress.IPv4Network(
                    f"{node_data['ip']}/{node_data['prefix']}", strict=False)
                gw_addr = ipaddress.IPv4Address(node_data['gateway'])
                if gw_addr not in node_net:
                    result.warn("Nodes",
                                f"Row {row} ({func_str}): Gateway {node_data['gateway']} "
                                f"is outside node subnet {node_net}")
            except ValueError:
                pass  # Already reported above

        # MAC
        mac = _cell(ws, row, mac_col)
        if mac is not None and str(mac).strip():
            if not MAC_RE.match(str(mac).strip()):
                result.error("Nodes", f"Row {row} ({func_str}): Invalid MAC format: '{mac}'")

        parsed_nodes.append(node_data)

    # Must have at least core-01 and core-02
    if not has_core:
        result.error("Nodes", "No core switches found (need at least core-01 and core-02)")

    # Check node count
    if node_count == 0:
        result.error("Nodes", "No nodes found — sheet appears empty")

    # Duplicate function names
    func_counts = Counter(f for f, _ in functions_seen)
    for func_name, count in func_counts.items():
        if count > 1:
            rows = [r for f, r in functions_seen if f == func_name]
            result.error("Nodes", f"Duplicate function name '{func_name}' on rows: {rows}")

    # Duplicate IPs
    ip_counts = Counter(ip for ip, _, _ in ips_seen)
    for ip_addr, count in ip_counts.items():
        if count > 1:
            entries = [(r, f) for ip, r, f in ips_seen if ip == ip_addr]
            result.error("Nodes", f"Duplicate management IP '{ip_addr}' used by: {entries}")

    return parsed_nodes


def validate_vlans(ws, result):
    """Validate VLANs & Profiles sheet: VLAN section integrity.

    Returns a list of parsed VLAN dicts for cross-validation:
        [{'id': int, 'name': str, 'subnet': str, 'gateway': str, 'network': IPv4Network, 'row': int}, ...]
    """
    # Check header row
    header_row2 = _cell(ws, 2, 1)
    if header_row2 != 'VLAN ID':
        result.warn("VLANs & Profiles", f"Expected 'VLAN ID' header in row 2 col 1, got: '{header_row2}'")

    vlan_ids = []
    vlan_names = []
    parsed_vlans = []

    # Parse VLAN rows (start row 3, end when col 1 is empty or non-integer)
    for row in range(3, ws.max_row + 1):
        vlan_id = _cell(ws, row, 1)
        if vlan_id is None:
            break
        try:
            vlan_id = int(vlan_id)
        except (TypeError, ValueError):
            break  # Hit the VRFs section or something else

        name = _cell(ws, row, 2)
        subnet = _cell(ws, row, 4)
        gateway = _cell(ws, row, 5)

        vlan_ids.append((vlan_id, row))
        vlan_data = {'id': vlan_id, 'name': str(name).strip() if name else '',
                     'subnet': None, 'gateway': None, 'network': None, 'row': row}

        if name:
            vlan_names.append((str(name).strip(), row))

        # VLAN ID range
        if vlan_id < 1 or vlan_id > 4094:
            result.error("VLANs & Profiles", f"Row {row}: VLAN ID {vlan_id} out of valid range (1-4094)")

        # Subnet
        if subnet and str(subnet).strip():
            subnet_str = str(subnet).strip()
            if not _is_valid_cidr(subnet_str):
                result.error("VLANs & Profiles", f"Row {row} (VLAN {vlan_id}): Invalid subnet: '{subnet}'")
            else:
                vlan_data['subnet'] = subnet_str
                try:
                    vlan_data['network'] = ipaddress.IPv4Network(subnet_str, strict=False)
                except ValueError:
                    pass
        else:
            result.warn("VLANs & Profiles", f"Row {row} (VLAN {vlan_id}): No subnet defined")

        # Gateway
        if gateway and str(gateway).strip():
            gw_str = str(gateway).strip()
            if not _is_valid_ip(gw_str):
                result.error("VLANs & Profiles", f"Row {row} (VLAN {vlan_id}): Invalid gateway: '{gw_str}'")
            else:
                vlan_data['gateway'] = gw_str

        # Gateway within VLAN subnet
        if vlan_data['network'] and vlan_data['gateway']:
            gw_addr = ipaddress.IPv4Address(vlan_data['gateway'])
            if gw_addr not in vlan_data['network']:
                result.error("VLANs & Profiles",
                             f"Row {row} (VLAN {vlan_id}): Gateway {vlan_data['gateway']} "
                             f"is outside VLAN subnet {vlan_data['network']}")

        parsed_vlans.append(vlan_data)

    if not vlan_ids:
        result.error("VLANs & Profiles", "No VLANs found")

    # Duplicate VLAN IDs
    id_counts = Counter(vid for vid, _ in vlan_ids)
    for vid, count in id_counts.items():
        if count > 1:
            rows = [r for v, r in vlan_ids if v == vid]
            result.error("VLANs & Profiles", f"Duplicate VLAN ID {vid} on rows: {rows}")

    # Duplicate VLAN names
    name_counts = Counter(n.lower() for n, _ in vlan_names)
    for name, count in name_counts.items():
        if count > 1:
            rows = [r for n, r in vlan_names if n.lower() == name]
            result.error("VLANs & Profiles", f"Duplicate VLAN name '{name}' on rows: {rows}")

    # Overlapping subnets
    nets = [(v['id'], v['network'], v['row']) for v in parsed_vlans if v['network']]
    for i in range(len(nets)):
        for j in range(i + 1, len(nets)):
            vid_a, net_a, row_a = nets[i]
            vid_b, net_b, row_b = nets[j]
            if net_a.overlaps(net_b):
                result.error("VLANs & Profiles",
                             f"Overlapping subnets: VLAN {vid_a} ({net_a}, row {row_a}) "
                             f"overlaps with VLAN {vid_b} ({net_b}, row {row_b})")

    return parsed_vlans


def validate_wire_map(ws, result, sheet_name="Wire Map"):
    """Validate Wire Map sheet: port formats and duplicate detection.

    Returns the set of (switch_role, switch_port) assignments for
    cross-sheet duplicate checking.
    """
    is_air_only = (sheet_name == "Air_Only")

    if is_air_only:
        sys_role_col = AIR_COL_SYSTEM_ROLE
        profile_col = AIR_COL_NETWORK_PROFILE
        sw_role_col = AIR_COL_SWITCH_ROLE
        sw_port_col = AIR_COL_SWITCH_PORT
    else:
        sys_role_col = WM_COL_SYSTEM_ROLE
        profile_col = WM_COL_NETWORK_PROFILE
        sw_role_col = WM_COL_SWITCH_ROLE
        sw_port_col = WM_COL_SWITCH_PORT

    # Track (switch_role, switch_port) assignments
    port_assignments = defaultdict(list)
    # Track (system_role, nic_port) for source-side duplicates
    source_assignments = defaultdict(list)
    row_count = 0

    for row in range(2, ws.max_row + 1):
        sys_role = _cell(ws, row, sys_role_col)
        if sys_role is None or str(sys_role).strip() == '':
            continue

        row_count += 1
        sys_role_str = str(sys_role).strip()
        sw_role = _cell(ws, row, sw_role_col)
        sw_port = _cell(ws, row, sw_port_col)

        # Skip rows with no switch assignment
        if sw_role is None or sw_port is None:
            continue

        sw_role_str = str(sw_role).strip()
        sw_port_str = str(sw_port).strip()

        if not sw_role_str or not sw_port_str:
            continue

        # Skip "outbound" links (virtual, no physical port)
        if sw_role_str.lower() == 'outbound':
            continue

        # Validate switch port format
        if not PORT_RE.match(sw_port_str):
            # Allow integer-only port numbers (some sheets use just numbers)
            try:
                int(sw_port_str)
            except ValueError:
                result.warn(sheet_name, f"Row {row}: Unusual switch port format: '{sw_port_str}' on {sw_role_str}")

        # Track for duplicate detection
        port_assignments[(sw_role_str, sw_port_str)].append((row, sys_role_str))

        # Source-side: track NIC/Port per system
        if not is_air_only:
            nic_port = _cell(ws, row, WM_COL_NIC_PORT)
            if nic_port and str(nic_port).strip():
                nic_str = str(nic_port).strip()
                source_assignments[(sys_role_str, nic_str)].append((row, sw_role_str, sw_port_str))

    # Report duplicate switch ports (same switch, same port, different rows)
    for (sw_role, sw_port), entries in port_assignments.items():
        if len(entries) > 1:
            detail = "; ".join(f"row {r} ({sys})" for r, sys in entries)
            result.error(sheet_name, f"Duplicate switch port: {sw_role} {sw_port} used {len(entries)} times — {detail}")

    # Report duplicate source ports (same system, same NIC, different rows)
    # This is a warning, not an error — dual-homed OOB (same NIC to two
    # switches) is a legitimate pattern in ERA architectures.
    for (sys_role, nic_port), entries in source_assignments.items():
        if len(entries) > 1:
            detail = "; ".join(f"row {r} → {sw}:{sp}" for r, sw, sp in entries)
            result.warn(sheet_name, f"Source port used multiple times: {sys_role} {nic_port} ({len(entries)}x) — {detail}")

    if row_count == 0:
        result.warn(sheet_name, "No data rows found")

    return port_assignments


def validate_cross_sheet_ports(wm_ports, air_ports, result):
    """Check for port conflicts between Wire Map and Air_Only sheets."""
    for key in air_ports:
        if key in wm_ports:
            sw_role, sw_port = key
            wm_detail = "; ".join(f"row {r} ({sys})" for r, sys in wm_ports[key])
            air_detail = "; ".join(f"row {r} ({sys})" for r, sys in air_ports[key])
            result.warn("Cross-sheet", f"Port {sw_role} {sw_port} defined in both Wire Map ({wm_detail}) and Air_Only ({air_detail}) — Air_Only takes priority")


def validate_cross_sheet_data(settings, parsed_nodes, parsed_vlans, result):
    """Cross-validate data between Settings, Nodes, and VLANs sheets."""
    # --- Node mgmt IPs within mgmt_subnets ---
    mgmt_raw = settings.get('mgmt_subnets')
    if mgmt_raw and parsed_nodes:
        mgmt_nets = []
        for part in str(mgmt_raw).split(','):
            part = part.strip()
            if part:
                try:
                    mgmt_nets.append(ipaddress.IPv4Network(part, strict=False))
                except ValueError:
                    pass  # Already reported in Settings validation

        if mgmt_nets:
            for node in parsed_nodes:
                if not node['ip']:
                    continue
                try:
                    addr = ipaddress.IPv4Address(node['ip'])
                except ValueError:
                    continue
                in_any = any(addr in net for net in mgmt_nets)
                if not in_any:
                    result.warn("Cross-sheet",
                                f"Node {node['function']} (row {node['row']}): "
                                f"mgmt IP {node['ip']} is not within any mgmt_subnet "
                                f"({', '.join(str(n) for n in mgmt_nets)})")

    # --- mgmt_subnets overlap with VLAN subnets ---
    if mgmt_raw and parsed_vlans:
        mgmt_nets = []
        for part in str(mgmt_raw).split(','):
            part = part.strip()
            if part:
                try:
                    mgmt_nets.append(ipaddress.IPv4Network(part, strict=False))
                except ValueError:
                    pass

        for mnet in mgmt_nets:
            for vlan in parsed_vlans:
                if vlan['network'] and mnet.overlaps(vlan['network']):
                    # OOB VLAN (200) overlapping with mgmt is expected
                    # since mgmt_subnets ARE the OOB management networks.
                    # Only warn for non-OOB VLANs.
                    if vlan['name'].upper() != 'OOB':
                        result.warn("Cross-sheet",
                                    f"mgmt_subnet {mnet} overlaps with "
                                    f"VLAN {vlan['id']} ({vlan['name']}) subnet {vlan['network']}")


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------

def validate_excel(xlsx_path):
    """Run all validation checks on an Excel file. Returns ValidationResult."""
    result = ValidationResult()

    path = Path(xlsx_path).resolve()
    if not path.exists():
        result.error("File", f"Not found: {path}")
        return result
    if path.suffix.lower() not in ('.xlsx', '.xlsm'):
        result.error("File", f"Not an Excel file: {path.name}")
        return result

    print(f"Validating: {path.name}")
    print(f"{'='*60}")

    try:
        wb = openpyxl.load_workbook(path, data_only=True)
    except Exception as e:
        result.error("File", f"Cannot open workbook: {e}")
        return result

    # 1. Sheet existence
    print("  Checking sheets...")
    validate_sheets(wb, result)

    # 2. Settings
    if 'Settings' in wb.sheetnames:
        print("  Checking Settings...")
        settings = validate_settings(wb['Settings'], result)
    else:
        settings = {}

    # 3. Nodes
    parsed_nodes = []
    if 'Nodes' in wb.sheetnames:
        print("  Checking Nodes...")
        parsed_nodes = validate_nodes(wb['Nodes'], result, settings=settings)
        print(f"    {len(parsed_nodes)} nodes found")

    # 4. VLANs & Profiles
    parsed_vlans = []
    if 'VLANs & Profiles' in wb.sheetnames:
        print("  Checking VLANs & Profiles...")
        parsed_vlans = validate_vlans(wb['VLANs & Profiles'], result)
        print(f"    {len(parsed_vlans)} VLANs found: {[v['id'] for v in parsed_vlans]}")

    # 5. Wire Map — port validation and duplicate detection
    wm_ports = {}
    if 'Wire Map' in wb.sheetnames:
        print("  Checking Wire Map...")
        wm_ports = validate_wire_map(wb['Wire Map'], result, "Wire Map")
        wm_rows = wb['Wire Map'].max_row - 1
        print(f"    {wm_rows} rows, {len(wm_ports)} unique switch port assignments")

    # 6. Air_Only
    air_ports = {}
    if 'Air_Only' in wb.sheetnames:
        print("  Checking Air_Only...")
        air_ports = validate_wire_map(wb['Air_Only'], result, "Air_Only")
        air_rows = wb['Air_Only'].max_row - 1
        print(f"    {air_rows} rows, {len(air_ports)} unique switch port assignments")

    # 7. Cross-sheet port conflict check
    if wm_ports and air_ports:
        print("  Checking cross-sheet port conflicts...")
        validate_cross_sheet_ports(wm_ports, air_ports, result)

    # 8. Cross-sheet data validation (IPs within subnets, overlaps)
    if settings or parsed_nodes or parsed_vlans:
        print("  Checking cross-sheet data consistency...")
        validate_cross_sheet_data(settings, parsed_nodes, parsed_vlans, result)

    wb.close()
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Validate an ERA Excel configuration file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('excel', metavar='EXCEL', help="Path to the Excel file to validate")
    args = parser.parse_args()

    result = validate_excel(args.excel)
    print(result.summary())

    return 0 if result.ok else 1


if __name__ == '__main__':
    sys.exit(main())
