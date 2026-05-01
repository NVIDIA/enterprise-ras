# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Tests for the ERA topology generator.

Tests parse_wiremap_excel(), parse_swp_port(), TopologyGenerator, MAC generation
consistency, duplicate endpoint detection, and output JSON structure using
in-memory openpyxl workbooks written to tmp_path.
"""
import json
import re
import sys
from pathlib import Path

import openpyxl
import pytest

# Add scripts/ to path so we can import the modules
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from utils import generate_mac, reset_mac_registry
from topology_generator import (
    parse_swp_port,
    parse_wiremap_excel,
    parse_air_only_sheet,
    parse_version_image_map,
    parse_switch_versions,
    TopologyGenerator,
    WiremapRow,
    SWITCH_MODELS,
    SWITCH_OS_FALLBACK,
    SERVER_OS,
    NODE_DEFAULTS,
)


@pytest.fixture(autouse=True)
def _reset_mac_reg():
    """Reset MAC registry between tests to avoid cross-test collision errors."""
    reset_mac_registry()
    yield
    reset_mac_registry()


# ---------------------------------------------------------------------------
# Helper: build minimal Excel files on disk (TopologyGenerator needs file paths)
# ---------------------------------------------------------------------------

def _build_wiremap_workbook(rows=None, settings=None, air_only_rows=None):
    """Create an openpyxl Workbook with Wire Map (and optionally Air_Only/Settings)."""
    wb = openpyxl.Workbook()

    # Remove default sheet
    wb.remove(wb.active)

    # Settings sheet
    ws_settings = wb.create_sheet("Settings")
    if settings:
        for key, value in settings:
            ws_settings.append([key, value])

    # Wire Map sheet with 13 columns
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
            padded = list(row) + [None] * (13 - len(row))
            ws.append(padded[:13])

    # Air_Only sheet (optional, new format)
    if air_only_rows is not None:
        ws_air = wb.create_sheet("Air_Only")
        air_header = [
            "Display in Air", "System Role", "System Name", "NIC/Port",
            "Network Profile", "Switch Role", "Switch Name", "Switch Port",
        ]
        ws_air.append(air_header)
        for row in air_only_rows:
            padded = list(row) + [None] * (8 - len(row))
            ws_air.append(padded[:8])

    return wb


def _write_workbook(wb, tmp_path, arch="2-8-5-200"):
    """Write a workbook to the expected path for TopologyGenerator."""
    input_dir = tmp_path / "input" / arch / "default"
    input_dir.mkdir(parents=True, exist_ok=True)
    excel_path = input_dir / f"{arch}.xlsx"
    wb.save(str(excel_path))
    return excel_path


# ---------------------------------------------------------------------------
# parse_swp_port
# ---------------------------------------------------------------------------

class TestParseSwpPort:
    """Tests for parse_swp_port() which extracts port numbers."""

    def test_simple_port(self):
        assert parse_swp_port("swp49") == (49, None)

    def test_subport(self):
        assert parse_swp_port("swp49s3") == (49, 3)

    def test_bare_number(self):
        assert parse_swp_port("50") == (50, None)

    def test_invalid_string(self):
        assert parse_swp_port("eth0") is None

    def test_empty_string(self):
        assert parse_swp_port("") is None

    def test_port_with_prefix_noise(self):
        """Strings that don't match the pattern return None."""
        assert parse_swp_port("bond1s0") is None

    def test_zero_port(self):
        assert parse_swp_port("swp0") == (0, None)


# ---------------------------------------------------------------------------
# parse_wiremap_excel (file-based)
# ---------------------------------------------------------------------------

class TestParseWiremapExcel:
    """Tests for parse_wiremap_excel() which reads Wire Map from an xlsx file."""

    def test_empty_wiremap(self, tmp_path):
        """Wire Map with only header returns empty list."""
        wb = _build_wiremap_workbook()
        path = _write_workbook(wb, tmp_path)
        result = parse_wiremap_excel(path)
        assert result == []

    def test_valid_rows(self, tmp_path):
        """Data rows are parsed into WiremapRow objects."""
        wb = _build_wiremap_workbook(rows=[
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ])
        path = _write_workbook(wb, tmp_path)

        result = parse_wiremap_excel(path)
        assert len(result) == 1
        assert isinstance(result[0], WiremapRow)
        assert result[0].system_role == "su-01-node-01"
        assert result[0].switch_port == "swp1s0"
        assert result[0].display_in_air is True

    def test_missing_wiremap_sheet_raises(self, tmp_path):
        """Workbook without Wire Map sheet raises ValueError."""
        wb = openpyxl.Workbook()
        wb.active.title = "Not Wire Map"
        path = tmp_path / "test.xlsx"
        wb.save(str(path))

        with pytest.raises(ValueError, match="Wire Map"):
            parse_wiremap_excel(path)

    def test_skip_empty_system_role(self, tmp_path):
        """Rows with empty System Role are skipped."""
        wb = _build_wiremap_workbook(rows=[
            ["Yes", "", "", "NIC1", None, None, "CPU", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ])
        path = _write_workbook(wb, tmp_path)

        result = parse_wiremap_excel(path)
        assert result == []


# ---------------------------------------------------------------------------
# parse_air_only_sheet
# ---------------------------------------------------------------------------

class TestParseAirOnlySheet:
    """Tests for parse_air_only_sheet() which reads the Air_Only sheet."""

    def test_no_air_only_sheet(self):
        """Workbook without Air_Only returns empty list."""
        wb = openpyxl.Workbook()
        result = parse_air_only_sheet(wb)
        assert result == []

    def test_valid_air_only_rows(self):
        """Air_Only rows are correctly parsed."""
        wb = openpyxl.Workbook()
        ws = wb.create_sheet("Air_Only")
        ws.append(["Display in Air", "System Role", "System Name", "NIC/Port",
                    "Network Profile", "Switch Role", "Switch Name", "Switch Port"])
        ws.append(["Yes", "dhcp-oob", "dhcp-oob", "eth1",
                    "Air - Management", "oob-switch-01", "oob-switch-01", "swp44"])

        result = parse_air_only_sheet(wb)
        assert len(result) == 1
        assert result[0].system_role == "dhcp-oob"
        assert result[0].switch_port == "swp44"
        assert result[0].display_in_air is True


# ---------------------------------------------------------------------------
# parse_version_image_map
# ---------------------------------------------------------------------------

class TestParseVersionImageMap:
    """Tests for parse_version_image_map() from Air_Only sheet."""

    def test_no_air_only_sheet(self):
        """Workbook without Air_Only returns empty dict."""
        wb = openpyxl.Workbook()
        result = parse_version_image_map(wb)
        assert result == {}

    def test_valid_version_map(self):
        """Version table is correctly parsed."""
        wb = openpyxl.Workbook()
        ws = wb.create_sheet("Air_Only")
        # Some data rows first (8+ columns, will be skipped by the version parser
        # because col1 won't be 'Friendly Version')
        ws.append(["Display in Air", "System Role", "System Name", "NIC/Port",
                    "Network Profile", "Switch Role", "Switch Name", "Switch Port"])
        ws.append(["Yes", "dhcp-oob", "dhcp-oob", "eth1",
                    "Air - Management", "oob-switch-01", "oob-switch-01", "swp44"])
        # Version table
        ws.append(["Friendly Version", "Air Image Name"])
        ws.append(["5.16.1", "cumulus-linux-vx-amd64-5.16.1.0008.qcow2"])
        ws.append(["5.15.1", "cumulus-linux-vx-amd64-5.15.1.qcow2"])

        result = parse_version_image_map(wb)
        assert result["5.16.1"] == "cumulus-linux-vx-amd64-5.16.1.0008.qcow2"
        assert result["5.15.1"] == "cumulus-linux-vx-amd64-5.15.1.qcow2"


# ---------------------------------------------------------------------------
# parse_switch_versions
# ---------------------------------------------------------------------------

class TestParseSwitchVersions:
    """Tests for parse_switch_versions() from Settings sheet."""

    def test_no_settings_sheet(self):
        """Workbook without Settings returns empty dict."""
        wb = openpyxl.Workbook()
        wb.active.title = "Other"
        result = parse_switch_versions(wb)
        assert result == {}

    def test_valid_versions(self):
        wb = openpyxl.Workbook()
        ws = wb.create_sheet("Settings")
        ws.append(["Switch Function", "Cumulus Version"])
        ws.append(["core", "5.16.1"])
        ws.append(["oob", "5.15.1"])

        result = parse_switch_versions(wb)
        assert result == {"core": "5.16.1", "oob": "5.15.1"}


# ---------------------------------------------------------------------------
# TopologyGenerator — integration with tmp_path Excel files
# ---------------------------------------------------------------------------

class TestTopologyGenerator:
    """Tests for the TopologyGenerator class."""

    def _make_minimal_topology(self, tmp_path, wiremap_rows, settings=None,
                               air_only_rows=None, arch="2-8-5-200"):
        """Helper: write workbook and instantiate TopologyGenerator."""
        wb = _build_wiremap_workbook(
            rows=wiremap_rows,
            settings=settings,
            air_only_rows=air_only_rows,
        )
        path = _write_workbook(wb, tmp_path, arch=arch)
        return TopologyGenerator(path, arch)

    def test_empty_topology(self, tmp_path):
        """Empty wiremap produces topology with no nodes or links."""
        gen = self._make_minimal_topology(tmp_path, [])
        topo = gen.generate()

        assert "content" in topo
        assert "nodes" in topo["content"]
        assert "links" in topo["content"]
        assert topo["content"]["oob"] is False

    def test_basic_node_creation(self, tmp_path):
        """Nodes from wiremap are created in the topology."""
        rows = [
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)
        topo = gen.generate()

        nodes = topo["content"]["nodes"]
        assert "su-01-node-01" in nodes
        assert "core-01" in nodes

    def test_node_os_assignment(self, tmp_path):
        """Switches get Cumulus OS, servers get Ubuntu OS."""
        rows = [
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)
        topo = gen.generate()

        nodes = topo["content"]["nodes"]
        assert nodes["core-01"]["os"] == SWITCH_OS_FALLBACK
        assert nodes["su-01-node-01"]["os"] == SERVER_OS

    def test_link_creation(self, tmp_path):
        """Links are created from wiremap connections."""
        rows = [
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)
        topo = gen.generate()

        links = topo["content"]["links"]
        # Should have at least one connected link plus unconnected stubs
        connected_links = [l for l in links if isinstance(l[1], dict)]
        assert len(connected_links) >= 1

        # Check the connected link endpoints
        link = connected_links[0]
        node_names = {link[0]["node"], link[1]["node"]}
        assert node_names == {"su-01-node-01", "core-01"}

    def test_display_in_air_no_skipped(self, tmp_path):
        """Rows with Display in Air = No do not create their specific nodes.

        Note: air-oob-switch and infra nodes (dhcp-oob, oob-server-01) may still
        be injected by _inject_air_oob_switch(), but wiremap-derived nodes should
        not appear.
        """
        rows = [
            ["No", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)
        topo = gen.generate()

        nodes = topo["content"]["nodes"]
        # The wiremap nodes should NOT be present
        assert "su-01-node-01" not in nodes
        assert "core-01" not in nodes

    def test_duplicate_endpoints_deduped(self, tmp_path):
        """Duplicate (node, interface) pairs keep only the first occurrence."""
        rows = [
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
            # Same switch port, different system — this should be deduped
            ["Yes", "su-01-node-02", "su-01-node-02", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)
        topo = gen.generate()

        # core-01:swp1s0 should only appear in one connected link
        connected_links = [l for l in topo["content"]["links"] if isinstance(l[1], dict)]
        core_swp1s0_count = sum(
            1 for link in connected_links
            for ep in [link[0], link[1]]
            if ep["node"] == "core-01" and ep["interface"] == "swp1s0"
        )
        assert core_swp1s0_count == 1

    def test_outbound_link(self, tmp_path):
        """Rows with switch_role 'outbound' create outbound links."""
        rows = [
            ["Yes", "dhcp-oob", "dhcp-oob", "eth0", None, None,
             "outbound", None, None, None,
             "outbound", "", ""],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)
        topo = gen.generate()

        outbound_links = [l for l in topo["content"]["links"]
                          if isinstance(l[1], str) and l[1] == "outbound"]
        assert len(outbound_links) >= 1
        assert outbound_links[0][0]["node"] == "dhcp-oob"

    def test_mac_in_links(self, tmp_path):
        """Link endpoints include deterministic MAC addresses."""
        rows = [
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)
        topo = gen.generate()

        connected_links = [l for l in topo["content"]["links"] if isinstance(l[1], dict)]
        assert len(connected_links) >= 1
        for ep in [connected_links[0][0], connected_links[0][1]]:
            assert "mac" in ep
            assert re.match(r'^48:b0:2d:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}$', ep["mac"])

    def test_topology_json_structure(self, tmp_path):
        """Generated topology has all required top-level keys."""
        rows = [
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)
        topo = gen.generate()

        # Top-level structure
        assert topo["format"] == "JSON"
        assert "title" in topo
        assert "content" in topo
        assert topo["ztp"] is None

        # Content structure
        content = topo["content"]
        assert "nodes" in content
        assert "links" in content
        assert content["oob"] is False

    def test_node_structure(self, tmp_path):
        """Each node has all required fields."""
        rows = [
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)
        topo = gen.generate()

        node = topo["content"]["nodes"]["core-01"]
        required_fields = ["cpu", "memory", "storage", "positioning", "os",
                           "features", "pxehost", "secureboot", "oob",
                           "emulation_type", "network_pci"]
        for field in required_fields:
            assert field in node, f"Missing field: {field}"
        assert isinstance(node["positioning"], dict)
        assert "x" in node["positioning"]
        assert "y" in node["positioning"]

    def test_unconnected_stubs_generated(self, tmp_path):
        """Switches get unconnected stubs for ports without connections."""
        rows = [
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)
        topo = gen.generate()

        unconnected_links = [l for l in topo["content"]["links"]
                             if isinstance(l[1], str) and l[1] == "unconnected"]
        # core-01 is SN5610 with 64 ports — most should be unconnected
        assert len(unconnected_links) > 0

    def test_write_to_file(self, tmp_path):
        """TopologyGenerator.write() creates a valid JSON file."""
        rows = [
            ["Yes", "su-01-node-01", "su-01-node-01", "NIC1_P1", None, None,
             "CPU/In-Band Network", None, None, None,
             "core-01", "core-01", "swp1s0"],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)

        output_path = tmp_path / "output" / "topology.json"
        gen.write(output_path)

        assert output_path.exists()
        with open(output_path) as f:
            data = json.load(f)
        assert data["format"] == "JSON"

    def test_invalid_hostname_skipped(self, tmp_path):
        """Rows with invalid hostnames (spaces) are not included."""
        rows = [
            ["Yes", "SPARE ISL", "SPARE ISL", "swp60", None, None,
             "ISL", None, None, None,
             "core-02", "core-02", "swp60"],
        ]
        gen = self._make_minimal_topology(tmp_path, rows)
        topo = gen.generate()

        nodes = topo["content"]["nodes"]
        assert "SPARE ISL" not in nodes


# ---------------------------------------------------------------------------
# MAC consistency between topology_generator and excel_parser
# ---------------------------------------------------------------------------

class TestMacConsistency:
    """Verify MACs are deterministic and consistent across generators."""

    def test_mac_format(self):
        """All MACs start with 48:b0:2d: prefix."""
        mac = generate_mac("core-01", "swp1")
        assert mac.startswith("48:b0:2d:")

    def test_mac_deterministic(self):
        """Same inputs produce same MAC."""
        mac1 = generate_mac("core-01", "swp1")
        reset_mac_registry()
        mac2 = generate_mac("core-01", "swp1")
        assert mac1 == mac2

    def test_mac_unique_per_interface(self):
        """Different interfaces produce different MACs."""
        mac1 = generate_mac("core-01", "swp1")
        mac2 = generate_mac("core-01", "swp2")
        assert mac1 != mac2

    def test_mac_unique_per_node(self):
        """Different nodes produce different MACs."""
        mac1 = generate_mac("core-01", "eth0")
        mac2 = generate_mac("core-02", "eth0")
        assert mac1 != mac2


# ---------------------------------------------------------------------------
# NODE_DEFAULTS and SWITCH_MODELS constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify topology generator constants are well-formed."""

    def test_switch_models_have_required_keys(self):
        for role, model in SWITCH_MODELS.items():
            assert "model" in model
            assert "ports" in model
            assert isinstance(model["ports"], int)
            assert model["ports"] > 0

    def test_node_defaults_have_required_keys(self):
        for role, defaults in NODE_DEFAULTS.items():
            assert "cpu" in defaults
            assert "memory" in defaults
            assert "storage" in defaults
            assert defaults["cpu"] > 0
            assert defaults["memory"] > 0

    def test_core_switch_is_sn5610(self):
        assert SWITCH_MODELS["core"]["model"] == "SN5610"
        assert SWITCH_MODELS["core"]["ports"] == 64

    def test_oob_switch_is_sn2201(self):
        assert SWITCH_MODELS["oob"]["model"] == "SN2201"
        assert SWITCH_MODELS["oob"]["ports"] == 48
