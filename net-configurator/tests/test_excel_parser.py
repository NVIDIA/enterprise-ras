# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Edge case tests for the ERA Excel parser.

Tests parse_settings(), parse_nodes(), parse_vlans(), and wiremap-related
functions with in-memory openpyxl workbooks to verify error handling,
empty data, and valid complete input.
"""
import sys
from pathlib import Path

import openpyxl
import pytest

# Add scripts/ to path so we can import the modules
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from utils import reset_mac_registry
from excel_parser import (
    parse_settings,
    parse_nodes,
    parse_vlans,
    parse_vrfs,
    parse_versions,
    parse_oob_switch_configs,
    build_devices,
    classify_host_role,
    _build_wiremap_row_list,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal workbooks for testing
# ---------------------------------------------------------------------------

def _make_settings_sheet(wb, data=None):
    """Add a Settings sheet with optional key-value rows."""
    ws = wb.create_sheet("Settings")
    if data:
        for key, value in data:
            ws.append([key, value])
    return ws


def _make_nodes_sheet(wb, headers=None, rows=None):
    """Add a Nodes sheet with headers and data rows."""
    ws = wb.create_sheet("Nodes")
    if headers is None:
        headers = ["Function", "Name", "MAC Address for ZTP", "Mgmt IP Address",
                    "Prefix", "Gateway"]
    ws.append(headers)
    if rows:
        for row in rows:
            ws.append(row)
    return ws


def _make_vlans_sheet(wb, vlans=None):
    """Add a VLANs & Profiles sheet with headers and data rows.

    Row 1 = section title, Row 2 = column headers, Row 3+ = data.
    """
    ws = wb.create_sheet("VLANs & Profiles")
    ws.append(["VLANs"])  # row 1: section label
    ws.append(["VLAN_ID", "Name", "Purpose", "Subnet", "VRF"])  # row 2: headers
    if vlans:
        for vlan in vlans:
            ws.append(vlan)
    return ws


def _make_wiremap_sheet(wb, rows=None):
    """Add a Wire Map sheet with 13-column header and data rows."""
    ws = wb.create_sheet("Wire Map")
    header = [
        "Display in Air", "System Role", "System Name", "NIC/Port",
        "Speed", "Description", "Network Profile",
        "Disabled by Neighbor", "Speed2", "Description2",
        "Switch Role", "Switch Name", "Switch Port",
    ]
    ws.append(header)
    if rows:
        for row in rows:
            # Pad short rows
            padded = list(row) + [None] * (13 - len(row))
            ws.append(padded[:13])
    return ws


@pytest.fixture(autouse=True)
def _reset_mac_reg():
    """Reset MAC registry between tests to avoid cross-test collision errors."""
    reset_mac_registry()
    yield
    reset_mac_registry()


# ---------------------------------------------------------------------------
# parse_settings
# ---------------------------------------------------------------------------

class TestParseSettings:
    """Tests for parse_settings() edge cases."""

    def test_empty_sheet(self):
        """Empty Settings sheet returns empty dict."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Settings"
        result = parse_settings(ws)
        assert result == {}

    def test_valid_settings(self):
        """Key-value pairs are correctly parsed and snake_cased."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Settings"
        ws.append(["Site Name", "test-site"])
        ws.append(["Domain Name", "example.com"])
        ws.append(["Mgmt Subnets", "192.168.200.0/24"])

        result = parse_settings(ws)
        assert result["site_name"] == "test-site"
        assert result["domain_name"] == "example.com"
        assert result["mgmt_subnets"] == "192.168.200.0/24"

    def test_none_value_skipped(self):
        """Rows with None values are skipped."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Settings"
        ws.append(["Valid Key", "some_value"])
        ws.append(["Missing Value", None])

        result = parse_settings(ws)
        assert "valid_key" in result
        assert "missing_value" not in result

    def test_none_key_skipped(self):
        """Rows with None keys are skipped."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Settings"
        ws.append([None, "orphan_value"])
        ws.append(["Good Key", "good_value"])

        result = parse_settings(ws)
        assert len(result) == 1
        assert "good_key" in result

    def test_key_normalization(self):
        """Keys with spaces and hyphens become snake_case."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Settings"
        ws.append(["Air URL", "https://air.nvidia.com"])
        ws.append(["NTP-Server", "pool.ntp.org"])

        result = parse_settings(ws)
        assert "air_url" in result
        assert "ntp_server" in result

    def test_numeric_values_preserved(self):
        """Numeric values are preserved (not stringified by parse_settings)."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Settings"
        ws.append(["VLAN Count", 10])

        result = parse_settings(ws)
        assert result["vlan_count"] == 10


# ---------------------------------------------------------------------------
# parse_nodes
# ---------------------------------------------------------------------------

class TestParseNodes:
    """Tests for parse_nodes() edge cases."""

    def test_empty_nodes_sheet(self):
        """Nodes sheet with only header returns empty list."""
        wb = openpyxl.Workbook()
        ws = _make_nodes_sheet(wb)
        result = parse_nodes(ws)
        assert result == []

    def test_valid_nodes(self):
        """Complete rows are parsed correctly."""
        wb = openpyxl.Workbook()
        ws = _make_nodes_sheet(wb, rows=[
            ["core-01", "core-01", "48:b0:2d:aa:bb:cc", "192.168.200.2", 24, "192.168.200.1"],
            ["su-01-node-01", "su-01-node-01", "", "192.168.200.11", 24, "192.168.200.1"],
        ])

        result = parse_nodes(ws)
        assert len(result) == 2
        assert result[0]["role"] == "core-01"
        assert result[0]["name"] == "core-01"
        assert result[0]["mac_address"] == "48:b0:2d:aa:bb:cc"
        assert result[0]["mgmt_ip"] == "192.168.200.2"

    def test_missing_mac_empty_string(self):
        """Missing MAC is returned as empty string, not None."""
        wb = openpyxl.Workbook()
        ws = _make_nodes_sheet(wb, rows=[
            ["core-02", "core-02", None, "192.168.200.3", 24, "192.168.200.1"],
        ])

        result = parse_nodes(ws)
        assert result[0]["mac_address"] == ""

    def test_missing_name_falls_back_to_role(self):
        """If Name column is empty, it falls back to the Function column."""
        wb = openpyxl.Workbook()
        ws = _make_nodes_sheet(wb, rows=[
            ["core-01", None, "", "192.168.200.2", 24, "192.168.200.1"],
        ])

        result = parse_nodes(ws)
        assert result[0]["name"] == "core-01"

    def test_skip_rows_without_function(self):
        """Rows with no Function value are skipped."""
        wb = openpyxl.Workbook()
        ws = _make_nodes_sheet(wb, rows=[
            [None, "orphan-name", "", "10.0.0.1", 24, "10.0.0.1"],
            ["core-01", "core-01", "", "192.168.200.2", 24, "192.168.200.1"],
        ])

        result = parse_nodes(ws)
        assert len(result) == 1
        assert result[0]["role"] == "core-01"

    def test_default_prefix(self):
        """Missing prefix defaults to 24."""
        wb = openpyxl.Workbook()
        ws = _make_nodes_sheet(wb, rows=[
            ["core-01", "core-01", "", "192.168.200.2", None, "192.168.200.1"],
        ])

        result = parse_nodes(ws)
        assert result[0]["prefix"] == 24

    def test_enabled_column_respected(self):
        """Nodes with 'No' in Enabled column are marked Disabled."""
        wb = openpyxl.Workbook()
        headers = ["Function", "Name", "MAC Address for ZTP", "Mgmt IP Address",
                    "Prefix", "Gateway", "Enabled"]
        ws = _make_nodes_sheet(wb, headers=headers, rows=[
            ["core-01", "core-01", "", "192.168.200.2", 24, "192.168.200.1", "Yes"],
            ["core-02", "core-02", "", "192.168.200.3", 24, "192.168.200.1", "No"],
        ])

        result = parse_nodes(ws)
        assert result[0]["status"] == "Active"
        assert result[1]["status"] == "Disabled"

    def test_duplicate_node_names_both_returned(self):
        """Duplicate names are not deduplicated by parse_nodes itself."""
        wb = openpyxl.Workbook()
        ws = _make_nodes_sheet(wb, rows=[
            ["core-01", "core-01", "", "192.168.200.2", 24, "192.168.200.1"],
            ["core-01", "core-01", "", "192.168.200.3", 24, "192.168.200.1"],
        ])

        result = parse_nodes(ws)
        assert len(result) == 2

    def test_missing_column_headers_uses_defaults(self):
        """If headers don't match known names, fallback column indices are used."""
        wb = openpyxl.Workbook()
        # Use completely non-standard headers -- parser falls back to default columns
        ws = _make_nodes_sheet(wb, headers=[
            "Col_A", "Col_B", "Col_C", "Col_D", "Col_E", "Col_F",
        ], rows=[
            ["core-01", "core-01", "48:b0:2d:11:22:33", "192.168.200.2", 24, "192.168.200.1"],
        ])

        result = parse_nodes(ws)
        # Still parsed because default column indices 1-6 match the data layout
        assert len(result) == 1


# ---------------------------------------------------------------------------
# parse_vlans
# ---------------------------------------------------------------------------

class TestParseVlans:
    """Tests for parse_vlans() edge cases."""

    def test_empty_vlans_sheet(self):
        """VLANs sheet with no data rows returns empty list."""
        wb = openpyxl.Workbook()
        ws = _make_vlans_sheet(wb)
        result = parse_vlans(ws)
        assert result == []

    def test_valid_vlans(self):
        """Standard VLANs are parsed with auto-generated VNI."""
        wb = openpyxl.Workbook()
        ws = _make_vlans_sheet(wb, vlans=[
            [100, "CPU/In-Band", "Compute traffic", "172.16.178.0/24", "default"],
            [200, "OOB", "Management", "192.168.200.0/24", "mgmt"],
        ])

        result = parse_vlans(ws)
        assert len(result) == 2
        assert result[0]["id"] == 100
        assert result[0]["name"] == "CPU/In-Band"
        assert result[0]["subnet"] == "172.16.178.0/24"
        assert result[0]["vni"] == 4100  # 100 + 4000

    def test_vlan_breaks_on_non_integer_id(self):
        """Parsing stops when a non-integer VLAN ID is encountered."""
        wb = openpyxl.Workbook()
        ws = _make_vlans_sheet(wb, vlans=[
            [100, "First", "test", "10.0.0.0/24", "default"],
            ["not-a-number", "Second", "test2", "10.0.1.0/24", "default"],
            [300, "Third", "test3", "10.0.2.0/24", "default"],
        ])

        result = parse_vlans(ws)
        assert len(result) == 1  # Stops at the non-integer row

    def test_vrf_defaults_to_default(self):
        """Missing VRF defaults to 'default'."""
        wb = openpyxl.Workbook()
        ws = _make_vlans_sheet(wb, vlans=[
            [100, "Test", "test", "10.0.0.0/24", None],
        ])

        result = parse_vlans(ws)
        assert result[0]["vrf"] == "default"

    def test_vni_column_overrides_auto(self):
        """Explicit VNI column values override the auto-calculated VNI."""
        wb = openpyxl.Workbook()
        ws = wb.create_sheet("VLANs & Profiles")
        ws.append(["VLANs"])
        ws.append(["VLAN_ID", "Name", "Purpose", "Subnet", "VRF", "VNI"])
        ws.append([100, "Test", "test", "10.0.0.0/24", "default", 99999])

        result = parse_vlans(ws)
        assert result[0]["vni"] == 99999


# ---------------------------------------------------------------------------
# parse_versions
# ---------------------------------------------------------------------------

class TestParseVersions:
    """Tests for parse_versions() which reads the VERSIONS table from Settings."""

    def test_empty_settings(self):
        """Settings sheet without VERSIONS table returns empty dict."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Settings"
        ws.append(["Site Name", "test"])

        result = parse_versions(ws)
        assert result == {}

    def test_valid_versions(self):
        """VERSIONS table is correctly parsed."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Settings"
        ws.append(["Site Name", "test"])
        ws.append(["Switch Function", "Cumulus Version"])
        ws.append(["core", "5.16.1"])
        ws.append(["oob", "5.15.1"])

        result = parse_versions(ws)
        assert result == {"core": "5.16.1", "oob": "5.15.1"}

    def test_versions_stops_at_empty_key_string(self):
        """Parsing stops at a row with empty (non-None) key string."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Settings"
        ws.append(["Switch Function", "Cumulus Version"])
        ws.append(["core", "5.16.1"])
        ws.append(["", None])  # empty string key → stops parsing
        ws.append(["edge", "5.16.0"])  # should NOT be included

        result = parse_versions(ws)
        assert result == {"core": "5.16.1"}

    def test_versions_skips_none_key_rows(self):
        """None-key rows inside the version table are skipped (continue, not break)."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Settings"
        ws.append(["Switch Function", "Cumulus Version"])
        ws.append(["core", "5.16.1"])
        ws.append([None, None])  # None key → continue (skip)
        ws.append(["edge", "5.16.0"])  # still parsed

        result = parse_versions(ws)
        assert result == {"core": "5.16.1", "edge": "5.16.0"}


# ---------------------------------------------------------------------------
# _build_wiremap_row_list
# ---------------------------------------------------------------------------

class TestBuildWiremapRowList:
    """Tests for _build_wiremap_row_list() which reads Wire Map into dicts."""

    def test_empty_wiremap(self):
        """Wire Map with only header returns empty list."""
        wb = openpyxl.Workbook()
        ws = _make_wiremap_sheet(wb)
        result = _build_wiremap_row_list(ws)
        assert result == []

    def test_valid_wiremap_rows(self):
        """Data rows are parsed into dicts with correct keys."""
        wb = openpyxl.Workbook()
        ws = _make_wiremap_sheet(wb, rows=[
            # display, sys_role, sys_name, nic, speed, desc, profile,
            # disabled, speed2, desc2, sw_role, sw_name, sw_port
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ])

        result = _build_wiremap_row_list(ws)
        assert len(result) == 1
        assert result[0]["system_role"] == "su-01-node-01"
        assert result[0]["system_name"] == "su-01-node-01"
        assert result[0]["switch_role"] == "core-01"
        assert result[0]["switch_port"] == "swp1s0"
        assert result[0]["display_in_air"] is True
        assert result[0]["net_profile"] == "CPU/In-Band Network"

    def test_skip_rows_without_system_role(self):
        """Rows with empty System Role are skipped."""
        wb = openpyxl.Workbook()
        ws = _make_wiremap_sheet(wb, rows=[
            ["Yes", "", "", "NIC1", None, None, "CPU", None, None, None,
             "core-01", "core-01", "swp1s0"],
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1", None, None, "CPU",
             None, None, None, "core-01", "core-01", "swp2s0"],
        ])

        result = _build_wiremap_row_list(ws)
        assert len(result) == 1

    def test_display_in_air_flag(self):
        """Display in Air 'No' rows are parsed but with display_in_air=False."""
        wb = openpyxl.Workbook()
        ws = _make_wiremap_sheet(wb, rows=[
            ["No", "su-01-node-01", "su-01-node-01", "NIC1", None, None, "CPU",
             None, None, None, "core-01", "core-01", "swp1s0"],
        ])

        result = _build_wiremap_row_list(ws)
        assert len(result) == 1
        assert result[0]["display_in_air"] is False

    def test_system_name_falls_back_to_role(self):
        """Empty System Name falls back to System Role."""
        wb = openpyxl.Workbook()
        ws = _make_wiremap_sheet(wb, rows=[
            ["Yes", "core-01", "", "swp49s0", None, None, "ISL",
             None, None, None, "core-02", "core-02", "swp49s0"],
        ])

        result = _build_wiremap_row_list(ws)
        assert result[0]["system_name"] == "core-01"


# ---------------------------------------------------------------------------
# parse_oob_switch_configs
# ---------------------------------------------------------------------------

class TestParseOobSwitchConfigs:
    """Tests for parse_oob_switch_configs() which derives OOB switch port configs."""

    def test_empty_wiremap(self):
        """Empty Wire Map returns empty dict."""
        wb = openpyxl.Workbook()
        ws = _make_wiremap_sheet(wb)
        result = parse_oob_switch_configs(ws)
        assert result == {}

    def test_access_and_uplink_classification(self):
        """Non-core connections are access, core non-eth0 connections are uplinks."""
        wb = openpyxl.Workbook()
        ws = _make_wiremap_sheet(wb, rows=[
            # su-01-node-01 connected to oob-switch-01 swp1 = access
            ["Yes", "su-01-node-01", "su-01-node-01", "eth0", None, None,
             "OOB / IPMI", None, None, None,
             "oob-switch-01", "oob-switch-01", "swp1"],
            # core-01 swp49 connected to oob-switch-01 swp49 = uplink
            ["Yes", "core-01", "core-01", "swp49s0", None, None,
             "OOB Uplink", None, None, None,
             "oob-switch-01", "oob-switch-01", "swp49"],
        ])

        result = parse_oob_switch_configs(ws)
        assert "oob-switch-01" in result
        cfg = result["oob-switch-01"]
        assert "swp1" in cfg["access_ports"]
        assert "swp49" in cfg["uplink_ports"]
        assert "swp49" in cfg["spine_bond_members"]

    def test_core_eth0_is_access(self):
        """Core eth0 connection to OOB switch is classified as access, not uplink."""
        wb = openpyxl.Workbook()
        ws = _make_wiremap_sheet(wb, rows=[
            ["Yes", "core-01", "core-01", "eth0", None, None,
             "OOB / IPMI", None, None, None,
             "oob-switch-01", "oob-switch-01", "swp2"],
        ])

        result = parse_oob_switch_configs(ws)
        cfg = result["oob-switch-01"]
        assert "swp2" in cfg["access_ports"]
        assert cfg["spine_bond_members"] == []

    def test_dhcp_oob_port_tracked(self):
        """Port connected to dhcp-oob is tracked in dhcp_oob_port."""
        wb = openpyxl.Workbook()
        ws = _make_wiremap_sheet(wb, rows=[
            ["Yes", "dhcp-oob", "dhcp-oob", "eth1", None, None,
             "Air - Management", None, None, None,
             "oob-switch-01", "oob-switch-01", "swp44"],
        ])

        result = parse_oob_switch_configs(ws)
        assert result["oob-switch-01"]["dhcp_oob_port"] == "swp44"


# ---------------------------------------------------------------------------
# build_devices
# ---------------------------------------------------------------------------

class TestBuildDevices:
    """Tests for build_devices() which generates device dicts for dnsmasq."""

    def test_empty_nodes(self):
        """Empty nodes list returns empty devices dict."""
        result = build_devices([], [], [])
        assert result == {}

    def test_switches_excluded(self):
        """Switch nodes are not included in devices."""
        nodes = [
            {"name": "core-01", "role": "core-01", "mgmt_ip": "192.168.200.2", "enabled": True},
        ]
        result = build_devices(nodes, [], [])
        assert "core-01" not in result

    def test_infra_excluded(self):
        """Infrastructure nodes (dhcp-oob, oob-server-01) are not included."""
        nodes = [
            {"name": "dhcp-oob", "role": "dhcp-oob", "mgmt_ip": "192.168.200.252", "enabled": True},
        ]
        result = build_devices(nodes, [], [])
        assert "dhcp-oob" not in result

    def test_compute_node_included(self):
        """Compute nodes get eth0_ip and auto-generated mac."""
        nodes = [
            {"name": "su-01-node-01", "role": "su-01-node-01",
             "mgmt_ip": "192.168.200.11", "enabled": True},
        ]
        result = build_devices(nodes, [], [])
        assert "su-01-node-01" in result
        assert result["su-01-node-01"]["eth0_ip"] == "192.168.200.11"
        assert result["su-01-node-01"]["mac"].startswith("48:b0:2d:")

    def test_explicit_mac_preserved(self):
        """MAC from Excel is used when present."""
        nodes = [
            {"name": "su-01-node-01", "role": "su-01-node-01",
             "mac": "48:b0:2d:aa:bb:cc",
             "mgmt_ip": "192.168.200.11", "enabled": True},
        ]
        result = build_devices(nodes, [], [])
        assert result["su-01-node-01"]["mac"] == "48:b0:2d:aa:bb:cc"

    def test_disabled_nodes_excluded(self):
        """Nodes with enabled=False are excluded."""
        nodes = [
            {"name": "su-01-node-01", "role": "su-01-node-01",
             "mgmt_ip": "192.168.200.11", "enabled": False},
        ]
        result = build_devices(nodes, [], [])
        assert "su-01-node-01" not in result

    def test_compute_data_plane_ips(self):
        """Compute nodes get bond_ip and gpu_ips when subnets available."""
        nodes = [
            {"name": "su-01-node-01", "role": "su-01-node-01",
             "mgmt_ip": "192.168.200.11", "enabled": True},
        ]
        vlans = [
            {"name": "CPU/In-Band", "subnet": "172.16.178.0/24"},
            {"name": "GPU Network", "subnet": "172.16.179.0/24"},
        ]
        result = build_devices(nodes, vlans, [])
        dev = result["su-01-node-01"]
        assert "bond_ip" in dev
        assert dev["bond_ip"].startswith("172.16.178.")

    def test_storage_data_plane_ips(self):
        """Storage nodes get bond_ip1 and bond_ip2 when subnet available."""
        nodes = [
            {"name": "storage-01", "role": "storage-01",
             "mgmt_ip": "192.168.200.61", "enabled": True},
        ]
        vlans = [
            {"name": "Storage", "subnet": "172.16.180.0/24"},
        ]
        result = build_devices(nodes, vlans, [])
        dev = result["storage-01"]
        assert "bond_ip1" in dev
        assert dev["bond_ip1"].startswith("172.16.180.")
        assert "bond_ip2" in dev


# ---------------------------------------------------------------------------
# classify_host_role (additional edge cases)
# ---------------------------------------------------------------------------

class TestClassifyHostRoleEdgeCases:
    """Additional edge cases beyond what test_parser_functions.py covers."""

    def test_air_oob_switch_is_air_oob(self):
        """air-oob-switch is classified as 'air-oob' (not mapped to 'switch')."""
        # classify_host_role only maps core/oob/edge → switch; air-oob passes through
        assert classify_host_role("air-oob-switch") == "air-oob"

    def test_unknown_name(self):
        """Unknown names return 'unknown'."""
        assert classify_host_role("totally-weird-name") == "unknown"

    def test_k8s_not_switch(self):
        """k8s nodes are not switches."""
        assert classify_host_role("k8s-01") == "k8s"
