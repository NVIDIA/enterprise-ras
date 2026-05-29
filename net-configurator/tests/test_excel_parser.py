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
import yaml

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
    generate_group_vars,
)


def _expand_port_range(range_str):
    """Expand a port range string like 'swp1-3,swp5' into a set of port names."""
    ports = set()
    for token in (range_str or "").split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            prefix = token.split("-")[0].rstrip("0123456789")
            start = int(token.split("-")[0][len(prefix):])
            end = int(token.split("-")[1])
            for n in range(start, end + 1):
                ports.add(f"{prefix}{n}")
        else:
            ports.add(token)
    return ports


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


class TestGenerateGroupVars:
    """Tests for generated group_vars behavior across source-inventory merges."""

    def test_source_inventory_link_state_is_not_inherited(self, tmp_path):
        """Source inventory must not silently inject link-state defaults."""
        settings = {"architecture": "2-8-5-200"}
        vlans = [
            {
                "id": 200,
                "name": "OOB",
                "subnet": "192.168.200.0/24",
                "vrf": "OOB",
                "vni": 4200,
            },
            {
                "id": 300,
                "name": "CPU/In-Band",
                "subnet": "172.16.178.0/24",
                "vrf": "INBAND",
                "vni": 4300,
            },
        ]
        vrfs = {
            "OOB": {"name": "OOB", "l3_vni": 5001},
            "INBAND": {"name": "INBAND", "l3_vni": 5002},
        }
        output_dir = tmp_path / "inventory"
        output_dir.mkdir()

        generate_group_vars(
            settings=settings,
            vlans=vlans,
            vrfs=vrfs,
            output_dir=output_dir,
            arch="2-8-5-200",
        )

        core_vars = yaml.safe_load((output_dir / "group_vars" / "core.yml").read_text())
        assert "interfaces_up" not in core_vars
        assert "interfaces_down" not in core_vars

    def test_l3_oob_uplink_mode_rewrites_default_vrf_bgp(self, tmp_path):
        """L3 OOB mode should emit direct uplink intent, not bond-based OOB defaults."""
        settings = {
            "architecture": "2-8-9-800",
            "oob_uplink_mode": "L3",
        }
        vlans = [
            {"id": 200, "name": "OOB", "subnet": "10.187.5.0/25", "vrf": "OOB", "vni": 289200},
            {"id": 300, "name": "CPU/In-Band", "subnet": "10.187.5.128/25", "vrf": "INBAND", "vni": 289300},
            {"id": 400, "name": "Support", "subnet": "10.187.4.0/27", "vrf": "INBAND", "vni": 289400},
        ]
        vrfs = {
            "OOB": {"name": "OOB", "l3_vni": 289001},
            "INBAND": {"name": "INBAND", "l3_vni": 289002},
            "EXIT": {"name": "EXIT", "l3_vni": 289004},
        }
        port_config = {
            "oob_uplink_interfaces": {
                "ports": [59],
                "breakout": 8,
                "lanes": 1,
                "port_overrides": {59: {"subports": [0, 1]}},
            },
            "isl_interfaces": {
                "ports": [56, 57, 58],
                "breakout": 2,
                "lanes": 4,
                "port_overrides": {58: {"subports": [0]}},
            },
        }
        nodes = [
            {"role": "oob-switch", "name": "mg-01"},
            {"role": "oob-switch", "name": "mg-02"},
        ]
        loopback_overrides = {
            "mg-01": {"lo": "10.187.4.35/32"},
            "mg-02": {"lo": "10.187.4.36/32"},
        }
        output_dir = tmp_path / "inventory"
        output_dir.mkdir()

        generate_group_vars(
            settings=settings,
            vlans=vlans,
            vrfs=vrfs,
            output_dir=output_dir,
            arch="2-8-9-800",
            nodes=nodes,
            port_config=port_config,
            loopback_overrides=loopback_overrides,
        )

        core_vars = yaml.safe_load((output_dir / "group_vars" / "core.yml").read_text())
        assert "oob_uplink_interfaces" in core_vars
        neighbors = core_vars["default_vrf_bgp"]["neighbors"]
        peer_groups = {pg["id"]: pg for pg in core_vars["default_vrf_bgp"]["peer_groups"]}
        assert any(n["interfaces"] == "isl" and n["peer_group"] == "internal-isl" for n in neighbors)
        assert any(n["interfaces"] == "oob_uplink" and n["peer_group"] == "underlay" for n in neighbors)
        assert any(n["interfaces"] == ["10.187.4.35", "10.187.4.36"] and n["peer_group"] == "overlay"
                   for n in neighbors)
        assert peer_groups["internal-isl"]["remote_as"] == "internal"
        assert peer_groups["underlay"]["remote_as"] == "external"
        assert peer_groups["overlay"]["update_source"] == "lo"

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
        assert "swp1" in _expand_port_range(cfg["access_ports"])
        assert "swp49" in _expand_port_range(cfg["uplink_ports"])
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
        # access_ports is a range string (e.g. "swp1-2") that includes both
        # the explicitly-wired port (swp2) and the auto-allocated air-oob
        # backdoor (first unused port, here swp1). Expand and check membership.
        assert "swp2" in _expand_port_range(cfg["access_ports"])
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


# ---------------------------------------------------------------------------
# parse_dhcp_relay_table + parse_vlans DHCP Relay Client column
# ---------------------------------------------------------------------------

from excel_parser import parse_dhcp_relay_table


def _make_vlans_profiles_with_dhcp(wb, vlans=None, dhcp_relay_rows=None,
                                   add_relay_client_col=True):
    """Build a minimal VLANs & Profiles sheet with optional DHCP Relay table
    and per-VLAN DHCP Relay Client column.

    vlans: list of (id, name, purpose, subnet, gateway, vrf, vni, relay_client).
    dhcp_relay_rows: list of (server_ip_raw, vrf, upstream_interface).
    """
    ws = wb.create_sheet("VLANs & Profiles")
    ws.append(["VLANs"])
    header = ["VLAN ID", "Name", "Purpose", "Subnet", "Gateway", "VRF", "VNI"]
    if add_relay_client_col:
        header.append("DHCP Relay Client")
    ws.append(header)
    for v in (vlans or []):
        ws.append(list(v))
    # Empty row gap
    ws.append([])
    if dhcp_relay_rows is not None:
        ws.append(["DHCP Relay"])
        ws.append(["Server IP", "VRF", "Upstream Interface"])
        for row in dhcp_relay_rows:
            ws.append(list(row))
    return ws


class TestParseDhcpRelayTable:
    """parse_dhcp_relay_table() reads the DHCP Relay table from VLANs & Profiles."""

    def test_no_section(self):
        wb = openpyxl.Workbook()
        ws = _make_vlans_profiles_with_dhcp(wb, dhcp_relay_rows=None)
        assert parse_dhcp_relay_table(ws) == []

    def test_empty_table(self):
        wb = openpyxl.Workbook()
        ws = _make_vlans_profiles_with_dhcp(wb, dhcp_relay_rows=[])
        assert parse_dhcp_relay_table(ws) == []

    def test_single_row(self):
        wb = openpyxl.Workbook()
        ws = _make_vlans_profiles_with_dhcp(
            wb, dhcp_relay_rows=[("192.168.200.252", "OOB", "vlan200")])
        result = parse_dhcp_relay_table(ws)
        assert result == [{
            'servers': ['192.168.200.252'],
            'vrf': 'OOB',
            'upstream_interfaces': ['vlan200'],
        }]

    def test_comma_separated_servers(self):
        wb = openpyxl.Workbook()
        ws = _make_vlans_profiles_with_dhcp(
            wb,
            dhcp_relay_rows=[("192.168.200.252,192.168.200.253", "OOB", "vlan200")],
        )
        result = parse_dhcp_relay_table(ws)
        assert result[0]['servers'] == ['192.168.200.252', '192.168.200.253']

    def test_comma_separated_upstream_interfaces(self):
        """NVUE supports multiple upstream-interface entries per server-group
        (deck slide 16); operator declares them comma-separated."""
        wb = openpyxl.Workbook()
        ws = _make_vlans_profiles_with_dhcp(
            wb,
            dhcp_relay_rows=[("192.168.200.252", "OOB", "swp64s0,swp64s1")],
        )
        result = parse_dhcp_relay_table(ws)
        assert result[0]['upstream_interfaces'] == ['swp64s0', 'swp64s1']

    def test_multiple_rows(self):
        wb = openpyxl.Workbook()
        ws = _make_vlans_profiles_with_dhcp(
            wb,
            dhcp_relay_rows=[
                ("192.168.200.252", "OOB", "vlan200"),
                ("10.0.0.100", "EXIT", "swp61s0"),
            ],
        )
        result = parse_dhcp_relay_table(ws)
        assert len(result) == 2
        assert result[0]['vrf'] == 'OOB'
        assert result[1]['vrf'] == 'EXIT'
        assert result[1]['upstream_interfaces'] == ['swp61s0']

    def test_vrf_normalized_uppercase(self):
        wb = openpyxl.Workbook()
        ws = _make_vlans_profiles_with_dhcp(
            wb, dhcp_relay_rows=[("192.168.200.252", "oob", "vlan200")])
        result = parse_dhcp_relay_table(ws)
        assert result[0]['vrf'] == 'OOB'


class TestParseVlansDhcpRelayClient:
    """parse_vlans() reads the new DHCP Relay Client column."""

    def test_column_present_with_no_values(self):
        wb = openpyxl.Workbook()
        ws = _make_vlans_profiles_with_dhcp(
            wb,
            vlans=[(300, 'inband', 'CPU', '192.168.45.0/24',
                    '192.168.45.1', 'INBAND', 4300, 'No')],
        )
        vlans = parse_vlans(ws)
        assert vlans[0]['dhcp_relay_client'] == 'No'

    def test_column_present_with_oob_value(self):
        wb = openpyxl.Workbook()
        ws = _make_vlans_profiles_with_dhcp(
            wb,
            vlans=[(300, 'inband', 'CPU', '192.168.45.0/24',
                    '192.168.45.1', 'INBAND', 4300, 'OOB')],
        )
        vlans = parse_vlans(ws)
        assert vlans[0]['dhcp_relay_client'] == 'OOB'

    def test_column_absent(self):
        """Backward-compat: VLANs sheet without the column → blank value."""
        wb = openpyxl.Workbook()
        ws = _make_vlans_profiles_with_dhcp(
            wb,
            vlans=[(300, 'inband', 'CPU', '192.168.45.0/24',
                    '192.168.45.1', 'INBAND', 4300)],
            add_relay_client_col=False,
        )
        vlans = parse_vlans(ws)
        assert vlans[0]['dhcp_relay_client'] == ''


# ---------------------------------------------------------------------------
# Per-rail-per-plane GPU VLAN mode
# ---------------------------------------------------------------------------

class TestPerRailPerPlaneParser:
    """build_devices() recognizes gpu_rail<R>_plane<P> VLAN rows and
    "GPU Rail R Plane P" Wire Map profiles when gpu_vlan_mode = per_rail_per_plane."""

    def _make_test_vlans(self):
        """Standard 2 rails × 2 planes VLAN set + CPU/OOB."""
        return [
            {'id': 200, 'name': 'oob',  'subnet': '192.168.200.0/24', 'vrf': 'OOB'},
            {'id': 300, 'name': 'CPU',  'subnet': '172.16.178.0/24',  'vrf': 'INBAND'},
            # Reused VLAN IDs across planes (operator's choice)
            {'id': 901, 'name': 'gpu_rail1_plane1', 'subnet': '192.168.0.0/24',  'gateway': '192.168.0.1',  'vrf': 'GPU'},
            {'id': 902, 'name': 'gpu_rail2_plane1', 'subnet': '192.168.1.0/24',  'gateway': '192.168.1.1',  'vrf': 'GPU'},
            {'id': 901, 'name': 'gpu_rail1_plane2', 'subnet': '192.168.16.0/24', 'gateway': '192.168.16.1', 'vrf': 'GPU'},
            {'id': 902, 'name': 'gpu_rail2_plane2', 'subnet': '192.168.17.0/24', 'gateway': '192.168.17.1', 'vrf': 'GPU'},
        ]

    def _make_test_wiremap(self, host='gpu-01'):
        """Wire map with 4 GPU NICs — 2 in plane 1, 2 in plane 2."""
        return [
            {'sys_role': host, 'sys_name': host, 'nic_port': 'eth3',
             'network_profile': 'GPU Rail 1 Plane 1',
             'sw_role': 'gsl-plane1', 'sw_name': 'gsl-plane1-01', 'sw_port': 'swp1s0'},
            {'sys_role': host, 'sys_name': host, 'nic_port': 'eth4',
             'network_profile': 'GPU Rail 2 Plane 1',
             'sw_role': 'gsl-plane1', 'sw_name': 'gsl-plane1-01', 'sw_port': 'swp2s0'},
            {'sys_role': host, 'sys_name': host, 'nic_port': 'eth5',
             'network_profile': 'GPU Rail 1 Plane 2',
             'sw_role': 'gsl-plane2', 'sw_name': 'gsl-plane2-01', 'sw_port': 'swp1s0'},
            {'sys_role': host, 'sys_name': host, 'nic_port': 'eth6',
             'network_profile': 'GPU Rail 2 Plane 2',
             'sw_role': 'gsl-plane2', 'sw_name': 'gsl-plane2-01', 'sw_port': 'swp2s0'},
        ]

    # NOTE: full end-to-end tests for IP allocation per (rail, plane) require a
    # built wiremap_rows list shaped by _build_wiremap_row_list (with system_role,
    # nic_port, network_profile, dst_switch, etc. populated correctly). Hand-rolled
    # dicts don't suffice. End-to-end verification is covered by smoke-running a
    # synthetic 2-8-9-800-derived Excel through `make generate` — see
    # docs/plans/2026-05-18-gpu-plane-per-rail.md.

    def test_mode_single_ignores_per_rail_plane_rows(self):
        """When mode is single, gpu_rail*_plane* rows shouldn't get used for IP allocation."""
        nodes = [{'name': 'gpu-01', 'role': 'gpu', 'mac': '', 'mgmt_ip': '192.168.200.10', 'enabled': True}]
        vlans = self._make_test_vlans()
        wiremap = self._make_test_wiremap()
        result = build_devices(nodes, vlans, [], wiremap_rows=wiremap,
                               gpu_vlan_mode='single')
        # No gpu_interfaces emitted since the per-rail-per-plane path is gated off
        gpus = result.get('gpu-01', {}).get('gpu_interfaces', [])
        assert gpus == []
