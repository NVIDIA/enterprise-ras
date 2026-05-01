#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Topology Generator - Generate and validate NVIDIA Air topology from Excel wiremap.

Reads the Wire Map sheet from the customer-filled Excel workbook
(input/<arch>/<site>/<arch>.xlsx) and produces a complete Air 2.0 topology
JSON with all switch ports represented — including unconnected stubs for
ports without connections.

Old format: Air-specific connections (dhcp-oob, oob-server-01, dhcp-edge, eth0
management) are included at the top of the Wire Map sheet with "Air - " prefixed
profiles.

New format: Air-specific connections are in a dedicated Air_Only sheet.
The Air_Only sheet also contains a version→image name mapping table used to
resolve the correct qcow2 image for each switch function.

Usage:
    # Generate topology from Excel wiremap
    python scripts/topology_generator.py generate --arch 2-8-5-200

    # Validate existing topology against wiremap
    python scripts/topology_generator.py validate --arch 2-8-5-200
    python scripts/topology_generator.py validate --arch 2-8-5-200 --topology path/to/file.json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import openpyxl

from utils import generate_mac, classify_node, is_switch, is_valid_hostname

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum physical port counts per switch model.
# The generator also scans the wiremap for higher-numbered ports and extends
# the range automatically (e.g., SN2201 swp49-52 uplinks).
SWITCH_MODELS = {
    "core":    {"model": "SN5610", "ports": 64},
    "oob":     {"model": "SN2201", "ports": 48},
    "edge":    {"model": "SN2201", "ports": 48},
    "air-oob": {"model": "SN2201", "ports": 48},
}

# Fallback OS images used when no version mapping is available in the workbook
SWITCH_OS_FALLBACK = "cumulus-linux-vx-amd64-5.16.0.qcow2"
SERVER_OS = "generic/ubuntu2204"

# Node resource defaults by role.
#
# Storage is uniformly 20 GB across all roles: public NGC Air requires
# a 20 GB minimum per node and we keep one value so Air-Inside runs use
# the same topology without per-env conditionals.
NODE_DEFAULTS = {
    "core":    {"cpu": 4, "memory": 4096, "storage": 20},
    "oob":     {"cpu": 1, "memory": 2048, "storage": 20},
    "air-oob": {"cpu": 1, "memory": 2048, "storage": 20},
    "edge":    {"cpu": 1, "memory": 2048, "storage": 20},
    "compute": {"cpu": 1, "memory": 1024, "storage": 20},
    "storage": {"cpu": 1, "memory": 1024, "storage": 20},
    "support": {"cpu": 1, "memory": 1024, "storage": 20},
    "k8s":     {"cpu": 1, "memory": 1024, "storage": 20},
    "bcme":    {"cpu": 1, "memory": 1024, "storage": 20},
    "infra":   {"cpu": 1, "memory": 1024, "storage": 20},
    "unknown": {"cpu": 1, "memory": 1024, "storage": 20},
}

# Wire Map sheet column indices (1-based, openpyxl convention)
# These are the same in both old and new format.
COL_DISPLAY_IN_AIR = 1
COL_SYSTEM_ROLE = 2
COL_SYSTEM_NAME = 3   # Actual node name (may differ from role for OEM naming)
COL_NIC_PORT = 4
COL_NET_PROFILE = 7
COL_SWITCH_ROLE = 11
COL_SWITCH_NAME = 12  # Actual switch name (may differ from role for OEM naming)
COL_SWITCH_PORT = 13

# Air_Only sheet column indices (1-based, new format only)
AIR_ONLY_COL_DISPLAY_IN_AIR = 1
AIR_ONLY_COL_SYSTEM_ROLE = 2
AIR_ONLY_COL_SYSTEM_NAME = 3  # Actual node name (formula-computed)
AIR_ONLY_COL_NIC_PORT = 4
AIR_ONLY_COL_NET_PROFILE = 5
AIR_ONLY_COL_SWITCH_ROLE = 6
AIR_ONLY_COL_SWITCH_NAME = 7  # Actual switch name (formula-computed)
AIR_ONLY_COL_SWITCH_PORT = 8


# ---------------------------------------------------------------------------
# Data class for parsed wiremap rows
# ---------------------------------------------------------------------------

@dataclass
class WiremapRow:
    """One row from the Wire Map Excel sheet."""
    display_in_air: bool
    system_role: str       # Left-side function/role (su-01-node-01, support-07, …) — used for classification
    system_name: str       # Left-side actual node name (may differ from role for OEM naming)
    nic_port: str          # Left-side interface (swpNsM for switches, HW NIC for servers)
    net_profile: str       # Network profile / description
    switch_role: str       # Right-side device role (core-01, oob-switch-01, …) — used for classification
    switch_name: str       # Right-side actual device name (may differ from role for OEM naming)
    switch_port: str       # Right-side interface (swpN, ethNN, …)



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# classify_node(), is_switch(), generate_mac(), is_valid_hostname()
# imported from utils.py — shared with excel_parser.py


def parse_swp_port(port_str: str) -> Optional[Tuple[int, Optional[int]]]:
    """Parse a switch port string into (base_num, sub_port_or_None).

    Examples:
        'swp49'   -> (49, None)
        'swp49s3' -> (49, 3)
        '50'      -> (50, None)   (bare number for disabled ports)
    Returns None if the string doesn't match.
    """
    m = re.match(r"swp(\d+)s(\d+)$", port_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"swp(\d+)$", port_str)
    if m:
        return int(m.group(1)), None
    m = re.match(r"(\d+)$", port_str)
    if m:
        return int(m.group(1)), None
    return None


def _cell_str(ws, row: int, col: int) -> str:
    """Read a cell value as a stripped string, treating None as ''."""
    val = ws.cell(row, col).value
    if val is None:
        return ""
    return str(val).strip()


# ---------------------------------------------------------------------------
# Excel parser
# ---------------------------------------------------------------------------

def parse_wiremap_excel(excel_path: Path) -> List[WiremapRow]:
    """Read the Wire Map sheet from the Excel workbook.

    Returns a list of WiremapRow for every data row (skips the header).
    """
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    if "Wire Map" not in wb.sheetnames:
        raise ValueError(f"Sheet 'Wire Map' not found in {excel_path}")

    ws = wb["Wire Map"]
    rows: List[WiremapRow] = []

    for row_idx in range(2, ws.max_row + 1):
        display_raw = _cell_str(ws, row_idx, COL_DISPLAY_IN_AIR).lower()
        system_role = _cell_str(ws, row_idx, COL_SYSTEM_ROLE)
        system_name = _cell_str(ws, row_idx, COL_SYSTEM_NAME) or system_role
        nic_port = _cell_str(ws, row_idx, COL_NIC_PORT)
        net_profile = _cell_str(ws, row_idx, COL_NET_PROFILE)
        switch_role = _cell_str(ws, row_idx, COL_SWITCH_ROLE)
        switch_name = _cell_str(ws, row_idx, COL_SWITCH_NAME) or switch_role
        switch_port = _cell_str(ws, row_idx, COL_SWITCH_PORT)

        if not system_role:
            continue

        rows.append(WiremapRow(
            display_in_air=(display_raw == "yes"),
            system_role=system_role,
            system_name=system_name,
            nic_port=nic_port,
            net_profile=net_profile,
            switch_role=switch_role,
            switch_name=switch_name,
            switch_port=switch_port,
        ))

    wb.close()
    return rows


def parse_air_only_sheet(wb) -> List[WiremapRow]:
    """Read the Air_Only sheet from a workbook (new format).

    Air_Only columns (1-based):
      1 = Display in Air
      2 = System Role
      3 = System Name (formula — computed value via data_only)
      4 = NIC/Port
      5 = Network Profile
      6 = Switch Role
      7 = Switch Name (formula — computed value via data_only)
      8 = Switch Port

    Returns WiremapRow list compatible with Wire Map rows.
    """
    if "Air_Only" not in wb.sheetnames:
        return []

    ws = wb["Air_Only"]
    rows: List[WiremapRow] = []

    for row_idx in range(2, ws.max_row + 1):
        display_raw = _cell_str(ws, row_idx, 1).lower()
        system_role = _cell_str(ws, row_idx, 2)
        system_name = _cell_str(ws, row_idx, 3) or system_role
        nic_port    = _cell_str(ws, row_idx, 4)
        net_profile = _cell_str(ws, row_idx, 5)
        switch_role = _cell_str(ws, row_idx, 6)
        switch_name = _cell_str(ws, row_idx, 7) or switch_role
        switch_port = _cell_str(ws, row_idx, 8)

        if not system_role:
            continue

        rows.append(WiremapRow(
            display_in_air=(display_raw == "yes"),
            system_role=system_role,
            system_name=system_name,
            nic_port=nic_port,
            net_profile=net_profile,
            switch_role=switch_role,
            switch_name=switch_name,
            switch_port=switch_port,
        ))

    return rows


def parse_version_image_map(wb) -> dict:
    """Read the version→Air image mapping table from the Air_Only sheet.

    The table starts after the connection rows, identified by a row where
    col 1 = 'Friendly Version' (or similar) followed by data rows.

    Returns dict: {'5.16.1': 'cumulus-linux-vx-amd64-5.16.1.0008.qcow2', ...}
    """
    if "Air_Only" not in wb.sheetnames:
        return {}

    ws = wb["Air_Only"]
    image_map = {}
    in_table = False

    for row_idx in range(1, ws.max_row + 1):
        col1 = _cell_str(ws, row_idx, 1)
        col2 = _cell_str(ws, row_idx, 2)
        if col1.lower() in ('friendly version', 'version'):
            in_table = True
            continue
        if in_table:
            if not col1:
                break
            image_map[col1] = col2
    return image_map


def parse_air_settings(wb) -> dict:
    """Read key-value settings from the Air_Only sheet.

    Scans for rows where col1 is a known setting name (e.g., 'Air Management Subnet').
    Returns dict: {'air_mgmt_subnet': '172.20.0.0/24', ...}
    """
    if "Air_Only" not in wb.sheetnames:
        return {}

    ws = wb["Air_Only"]
    settings = {}
    _KNOWN_KEYS = {
        'air management subnet': 'air_mgmt_subnet',
    }

    for row_idx in range(1, ws.max_row + 1):
        col1 = _cell_str(ws, row_idx, 1).lower()
        col2 = _cell_str(ws, row_idx, 2)
        if col1 in _KNOWN_KEYS and col2:
            settings[_KNOWN_KEYS[col1]] = col2
    return settings


def parse_switch_versions(wb) -> dict:
    """Read the VERSIONS table from the Settings sheet (new format).

    Returns dict: {'core': '5.16.1', 'oob': '5.15.1'} or {} if not present.
    """
    if "Settings" not in wb.sheetnames:
        return {}

    ws = wb["Settings"]
    versions = {}
    in_versions = False

    for row_idx in range(1, ws.max_row + 1):
        key = ws.cell(row_idx, 1).value
        if key is None:
            continue
        key_str = str(key).strip()
        if key_str.lower() == 'switch function':
            in_versions = True
            continue
        if in_versions:
            value = ws.cell(row_idx, 2).value
            if not key_str or value is None:
                break
            versions[key_str.lower()] = str(value).strip()
    return versions


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class TopologyGenerator:
    """Generate an Air 2.0 topology JSON from the Excel wiremap."""

    def __init__(self, excel_path: Path, arch: str, site: str = "default"):
        self.excel_path = excel_path
        self.arch = arch
        self.site = site

        wb = openpyxl.load_workbook(excel_path, data_only=True)
        new_format = "Air_Only" in wb.sheetnames

        # Wire Map rows — always present
        self.rows = parse_wiremap_excel(excel_path)

        if new_format:
            # New format: Air topology rows (infrastructure + outbound) are in Air_Only
            # Air_Only rows go FIRST so they take priority in dedup over Wire Map rows
            self.rows = parse_air_only_sheet(wb) + self.rows
            # Build version → OS image mapping from Air_Only and per-function versions
            image_map = parse_version_image_map(wb)
            switch_versions = parse_switch_versions(wb)
            self._switch_os: Dict[str, str] = {}
            for func, version in switch_versions.items():
                image = image_map.get(version, SWITCH_OS_FALLBACK)
                self._switch_os[func] = image
        else:
            self._switch_os = {}

        wb.close()

        # Build actual-name → function/role mapping for OEM-named devices.
        # Classification helpers (is_switch, classify_node) need the function name.
        self._name_to_role: Dict[str, str] = {}
        for r in self.rows:
            if r.system_name and r.system_name != r.system_role:
                self._name_to_role[r.system_name] = r.system_role
            if r.switch_name and r.switch_name != r.switch_role:
                self._name_to_role[r.switch_name] = r.switch_role

        # Per-server counter for sequential ethN assignment
        self._server_eth_counter: Dict[str, int] = defaultdict(int)

        # Pre-scan for explicit ethN assignments (e.g., eth0 rows from Air_Only or Wire Map)
        # so _next_eth() can skip them and avoid duplicates
        self._explicit_eth: Dict[str, Set[int]] = defaultdict(set)
        for r in self.rows:
            if r.display_in_air and not is_switch(r.system_role):
                m = re.search(r"eth(\d+)", r.nic_port or "")
                if m:
                    self._explicit_eth[r.system_name].add(int(m.group(1)))

        # Pre-scan: reserve eth0 for the first oob-switch connection per server.
        # This ensures the OOB management interface is always eth0, regardless of
        # row order in the Wire Map.  Stores (system_name, switch_name, switch_port)
        # tuples to identify the chosen row in _build_connected_links().
        self._oob_eth0: Dict[str, Tuple[str, str]] = {}  # node → (switch_name, switch_port)
        for r in self.rows:
            if not r.display_in_air or is_switch(r.system_role):
                continue
            if r.system_name in self._oob_eth0:
                continue  # already found one for this node
            peer_role = classify_node(self._name_to_role.get(r.switch_name, r.switch_role))
            if peer_role == "oob" and r.switch_port:
                self._oob_eth0[r.system_name] = (r.switch_name, r.switch_port)
                self._explicit_eth[r.system_name].add(0)  # reserve eth0

    # ---- public -----------------------------------------------------------

    def generate(self) -> dict:
        """Build the complete topology dict."""
        nodes = self._build_nodes()
        links, switch_connected = self._build_connected_links()
        nodes, links, switch_connected = self._inject_air_oob_switch(
            nodes, links, switch_connected,
        )
        links += self._build_unconnected_stubs(switch_connected)

        return {
            "format": "JSON",
            "title": f"ERA-{self.site}-{self.arch}",
            "ztp": None,
            "content": {
                "nodes": nodes,
                "links": links,
                "oob": False,
            },
            # Metadata for air-deploy.py Node Instructions
            "_air_oob": getattr(self, '_air_oob_metadata', {}),
        }

    def write(self, output_path: Path) -> None:
        """Generate and write topology JSON to *output_path*."""
        topology = self.generate()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(topology, f, indent=4)

        node_count = len(topology["content"]["nodes"])
        link_count = len(topology["content"]["links"])
        connected = sum(
            1 for lnk in topology["content"]["links"]
            if isinstance(lnk[1], dict)
        )
        unconnected = sum(
            1 for lnk in topology["content"]["links"]
            if isinstance(lnk[1], str) and lnk[1] == "unconnected"
        )
        outbound = sum(
            1 for lnk in topology["content"]["links"]
            if isinstance(lnk[1], str) and lnk[1] == "outbound"
        )

        print(f"  Topology written to {output_path}")
        print(f"  Nodes:       {node_count}")
        print(f"  Links:       {link_count}")
        print(f"    connected:   {connected}")
        print(f"    unconnected: {unconnected}")
        print(f"    outbound:    {outbound}")

    # ---- nodes ------------------------------------------------------------

    def _build_nodes(self) -> dict:
        """Collect every device that should appear as a node."""
        device_names: Set[str] = set()

        for r in self.rows:
            if not r.display_in_air:
                continue
            if r.system_role and is_valid_hostname(r.system_name):
                device_names.add(r.system_name)
            if r.switch_role and r.switch_role.upper() not in ("NA", "OUTBOUND") \
                    and is_valid_hostname(r.switch_name):
                device_names.add(r.switch_name)

        nodes = {}
        for name in sorted(device_names):
            role_name = self._name_to_role.get(name, name)
            role = classify_node(role_name)
            defaults = NODE_DEFAULTS.get(role, NODE_DEFAULTS["support"])
            nodes[name] = {
                "cpu": defaults["cpu"],
                "memory": defaults["memory"],
                "storage": defaults["storage"],
                "positioning": {"x": 0, "y": 0},
                "os": self._resolve_os(name),
                "features": {"uefi": False, "tpm": False},
                "pxehost": False,
                "secureboot": False,
                "oob": False,
                "emulation_type": None,
                "network_pci": {},
            }

        self._apply_layout(nodes)
        return nodes

    def _resolve_os(self, name: str) -> str:
        """Return the Air OS image string for a node.

        For servers always returns SERVER_OS.
        For switches, looks up per-function image from _switch_os (populated from
        the Air_Only version mapping table when using new format).
        Falls back to SWITCH_OS_FALLBACK if no mapping is available.
        """
        role_name = self._name_to_role.get(name, name)
        if not is_switch(role_name):
            return SERVER_OS
        role = classify_node(role_name)  # 'core', 'oob', 'edge', …
        if role in self._switch_os:
            return self._switch_os[role]
        # air-oob and edge switches share the same image as oob (both SN2201)
        if role in ("edge", "air-oob") and "oob" in self._switch_os:
            return self._switch_os["oob"]
        return SWITCH_OS_FALLBACK

    # ---- layout -------------------------------------------------------------

    def _apply_layout(self, nodes: dict) -> None:
        """Assign grid positions to nodes based on role.

        Uses a 275-unit grid matching NVIDIA Air visual layout conventions.
        Layout regions (left-to-right):
          - Left:   infrastructure (edge switches, OOB switches, dhcp/oob-server)
          - Center: core switches, k8s, bcme, storage columns
          - Right:  compute (su-*) nodes grouped by SU
        """
        G = 275  # grid unit (pixels)

        def _role(n: str) -> str:
            return classify_node(self._name_to_role.get(n, n))

        # Categorise nodes by role
        edges = sorted(n for n in nodes if _role(n) == "edge")
        cores = sorted(n for n in nodes if _role(n) == "core")
        oobs = sorted(n for n in nodes if _role(n) == "oob")
        infras = sorted(n for n in nodes if _role(n) == "infra")
        k8s_nodes = sorted(n for n in nodes if n.lower().startswith("k8s"))
        bcme_nodes = sorted(n for n in nodes if n.lower().startswith("bcme"))
        storage_nodes = sorted(n for n in nodes if _role(n) == "storage")
        # Support nodes that aren't k8s/bcme/storage
        support_other = sorted(
            n for n in nodes
            if _role(n) == "support"
            and n not in k8s_nodes and n not in bcme_nodes
        )
        compute = sorted(n for n in nodes if _role(n) == "compute")

        # Parse compute nodes into SU groups: { su_id: [node_names sorted] }
        su_groups: Dict[str, list] = {}
        for name in compute:
            # Extract SU identifier (e.g., "su-01" from "su-01-node-03")
            m = re.match(r"(su-\d+)", name.lower())
            su_id = m.group(1) if m else "su-00"
            su_groups.setdefault(su_id, []).append(name)

        su_ids = sorted(su_groups.keys())

        # Determine how many "server columns" we need to the right of core-01
        # Columns: k8s | bcme | storage | su-01 | su-02 | su-03 | ...
        server_col_names = []
        if k8s_nodes:
            server_col_names.append("k8s")
        if bcme_nodes:
            server_col_names.append("bcme")
        if storage_nodes:
            server_col_names.append("storage")
        if support_other:
            server_col_names.append("support")
        for su_id in su_ids:
            server_col_names.append(su_id)

        # X assignments
        # Infrastructure on the left: cols -1, 0, 1 (x = -G, 0, G)
        infra_x_base = -1  # grid col for leftmost infra

        # Core-01 starts at col 2 (x = 2*G = 550)
        core_start_col = 2
        # Server columns start at core_start_col + 1
        server_start_col = core_start_col + 1

        # Core-02 goes to the right of all server columns
        core2_col = server_start_col + len(server_col_names)

        # Map server column names to x grid columns
        server_col_x = {}
        for i, col_name in enumerate(server_col_names):
            server_col_x[col_name] = server_start_col + i

        # --- Row 0 (Y=0): edge switch #2 (top) ---
        # --- Row 1 (Y=G): edge switch #1, core-01, core-02 ---
        # --- Row 2 (Y=2G): OOB switches + first server row ---
        # --- Row 3+ : more server rows ---
        # --- Below servers: infra nodes (dhcp-edge, oob-server, dhcp-oob) ---

        # Place edge switches
        for i, name in enumerate(edges):
            if i == 0:
                nodes[name]["positioning"] = {"x": 0, "y": G}
            elif i == 1:
                nodes[name]["positioning"] = {"x": G, "y": 0}
            else:
                nodes[name]["positioning"] = {"x": i * G, "y": 0}

        # Place core switches
        if len(cores) >= 1:
            nodes[cores[0]]["positioning"] = {
                "x": core_start_col * G, "y": G,
            }
        if len(cores) >= 2:
            nodes[cores[1]]["positioning"] = {
                "x": core2_col * G, "y": G,
            }
        for i, name in enumerate(cores[2:], 2):
            nodes[name]["positioning"] = {"x": (core2_col + i - 1) * G, "y": G}

        # Place OOB switches (row 2, left side)
        for i, name in enumerate(oobs):
            nodes[name]["positioning"] = {
                "x": (infra_x_base + i) * G, "y": 2 * G,
            }

        # Place air-oob-switch (row 3, left side — between OOB switches and infra)
        if "air-oob-switch" in nodes:
            nodes["air-oob-switch"]["positioning"] = {
                "x": infra_x_base * G, "y": 3 * G,
            }

        # Determine max server rows (tallest column)
        col_heights = {
            "k8s": len(k8s_nodes),
            "bcme": len(bcme_nodes),
            "storage": len(storage_nodes),
            "support": len(support_other),
        }
        for su_id in su_ids:
            col_heights[su_id] = len(su_groups[su_id])
        max_server_rows = max(col_heights.values()) if col_heights else 0

        # Place server columns starting at row 2
        server_row_base = 2

        def _place_column(node_list: list, col_name: str) -> None:
            if col_name not in server_col_x:
                return
            x = server_col_x[col_name] * G
            for row_i, name in enumerate(node_list):
                nodes[name]["positioning"] = {
                    "x": x, "y": (server_row_base + row_i) * G,
                }

        _place_column(k8s_nodes, "k8s")
        _place_column(bcme_nodes, "bcme")
        _place_column(storage_nodes, "storage")
        _place_column(support_other, "support")
        for su_id in su_ids:
            _place_column(su_groups[su_id], su_id)

        # Place infra nodes (dhcp-edge, oob-server, dhcp-oob) below OOB switches
        # Sort: edge-related first, then oob-server in the middle, then dhcp-oob
        def _infra_sort_key(n: str) -> tuple:
            nl = n.lower()
            if "edge" in nl:
                return (0, nl)
            if "server" in nl:
                return (1, nl)
            return (2, nl)
        infras = sorted(infras, key=_infra_sort_key)

        infra_row = 4  # default position matching reference layout
        if max_server_rows > 2:
            infra_row = server_row_base + 2  # two rows below OOB switches
        for i, name in enumerate(infras):
            nodes[name]["positioning"] = {
                "x": (infra_x_base + i) * G, "y": infra_row * G,
            }

    # ---- connected links --------------------------------------------------

    def _build_connected_links(
        self,
    ) -> Tuple[list, Dict[str, Set[str]]]:
        """Build links from Display-in-Air=Yes rows.

        Air requires each (node, interface) pair to be unique across all links.
        When the wiremap maps multiple devices to the same switch port (e.g.
        BMC + LOM + iDRAC all sharing oob-switch-01:swp26), only the first
        connection is kept — duplicates are skipped with a warning.

        Handles special switch_role values:
        - "outbound": creates an outbound link (internet access for virtual nodes)
        - "NA": skipped entirely

        Returns (links_list, switch_connected_ports) where
        switch_connected_ports maps switch name -> set of port names already
        wired to something.
        """
        links: list = []
        switch_connected: Dict[str, Set[str]] = defaultdict(set)
        used_endpoints: Set[Tuple[str, str]] = set()
        skipped = 0

        for r in self.rows:
            if not r.display_in_air:
                continue
            if not r.switch_role or r.switch_role.upper() == "NA":
                continue
            # Skip rows with invalid hostnames (e.g. "SPARE ISL")
            if not is_valid_hostname(r.system_name) or not is_valid_hostname(r.switch_name):
                continue

            # Determine left-side (system) interface name
            # Switches: use wiremap port name as-is
            # OOB-switch connection reserved as eth0: use eth0
            # Servers with ethN in wiremap (Air rows): use as-is
            # Servers with HW NIC names: assign sequential ethN
            if is_switch(r.system_role):
                system_port = r.nic_port
            elif (r.system_name in self._oob_eth0
                  and self._oob_eth0[r.system_name] == (r.switch_name, r.switch_port)):
                system_port = "eth0"
            elif r.nic_port and re.search(r"eth(\d+)", r.nic_port):
                system_port = f"eth{re.search(r'eth(\d+)', r.nic_port).group(1)}"
            else:
                system_port = self._next_eth(r.system_name)

            # Handle outbound links (e.g., dhcp-oob:eth0 → outbound)
            if r.switch_role.lower() == "outbound":
                ep = (r.system_name, system_port)
                if ep in used_endpoints:
                    skipped += 1
                    continue
                used_endpoints.add(ep)

                links.append([
                    {
                        "interface": system_port,
                        "node": r.system_name,
                        "mac": generate_mac(r.system_name, system_port),
                        "network_pci": None,
                    },
                    "outbound",
                ])
                continue

            if not r.switch_port:
                continue

            # Right-side interface comes directly from the wiremap
            other_port = r.switch_port

            # Check for duplicate endpoints — Air only allows one link per port
            left_ep = (r.system_name, system_port)
            right_ep = (r.switch_name, other_port)

            if left_ep in used_endpoints or right_ep in used_endpoints:
                skipped += 1
                continue

            used_endpoints.add(left_ep)
            used_endpoints.add(right_ep)

            link = self._make_link(
                r.system_name, system_port,
                r.switch_name, other_port,
            )
            links.append(link)

            # Track connected ports on switches
            if is_switch(r.system_role):
                switch_connected[r.system_name].add(system_port)
            if is_switch(r.switch_role):
                switch_connected[r.switch_name].add(other_port)

        if skipped:
            print(f"    (skipped {skipped} duplicate port assignments)")

        return links, switch_connected

    def _parse_mgmt_subnets(self) -> List[str]:
        """Read mgmt_subnets from the Settings sheet.

        Returns list of subnet strings, e.g., ['192.168.200.0/24', '192.168.210.0/24'].
        """
        wb = openpyxl.load_workbook(self.excel_path, data_only=True)
        ws = wb["Settings"] if "Settings" in wb.sheetnames else None
        result = []
        if ws:
            for row in range(1, ws.max_row + 1):
                key = ws.cell(row=row, column=1).value
                val = ws.cell(row=row, column=2).value
                if key and str(key).lower().replace(' ', '_').replace('-', '_') == 'mgmt_subnets' and val:
                    result = [s.strip() for s in str(val).split(',') if s.strip()]
                    break
        wb.close()
        return result

    # ---- air-oob-switch injection -------------------------------------------

    def _inject_air_oob_switch(
        self,
        nodes: dict,
        links: list,
        switch_connected: Dict[str, Set[str]],
    ) -> Tuple[dict, list, Dict[str, Set[str]]]:
        """Inject a VLAN-aware air-oob-switch for OOB management.

        air-oob-switch provides:
          - air-mgmt (untagged): switch eth0s for ZTP
          - Per mgmt_subnet VLAN: uplink from each OOB switch, plus interfaces
            for oob-server-01 (gateway .1) and dhcp-oob (DHCP server)

        oob-server-01 and dhcp-oob each get:
          - eth0 → outbound (internet/SSH)
          - eth1 → air-oob-switch (air-mgmt, untagged)
          - eth2+ → air-oob-switch (one per mgmt_subnet VLAN)
        """
        AIR_OOB = "air-oob-switch"
        next_swp = 1
        air_connected: Set[str] = set()

        def _alloc_swp() -> str:
            nonlocal next_swp
            port = f"swp{next_swp}"
            next_swp += 1
            air_connected.add(port)
            return port

        # Parse mgmt_subnets from Settings tab
        mgmt_subnets = self._parse_mgmt_subnets()
        n_subnets = len(mgmt_subnets)

        # Collect OOB switch names present in the topology
        oob_switch_names = sorted(
            n for n in nodes
            if classify_node(self._name_to_role.get(n, n)) == "oob"
        )

        # --- Pass 1: Process existing links ---
        # Rewire switch eth0s to air-oob-switch, drop old infra→oob-switch links
        new_links: list = []
        oob_set = set(oob_switch_names)

        for link in links:
            if not isinstance(link[0], dict) or not isinstance(link[1], dict):
                new_links.append(link)
                continue

            ep0, ep1 = link[0], link[1]

            # Identify OOB switch endpoint
            oob_ep, other_ep = None, None
            if ep1["node"] in oob_set:
                oob_ep, other_ep = ep1, ep0
            elif ep0["node"] in oob_set:
                oob_ep, other_ep = ep0, ep1
            else:
                new_links.append(link)
                continue

            other_role = classify_node(
                self._name_to_role.get(other_ep["node"], other_ep["node"])
            )
            other_name = other_ep["node"].lower()

            # Switch eth0 → rewire to air-oob-switch
            if other_ep["interface"] == "eth0" and other_role in ("core", "oob", "edge"):
                swp = _alloc_swp()
                new_links.append(self._make_link(other_ep["node"], "eth0", AIR_OOB, swp))
                switch_connected[oob_ep["node"]].discard(oob_ep["interface"])
                continue

            # Drop dhcp-oob/oob-server links to oob-switches (rebuilt in Pass 4)
            if ("dhcp-oob" in other_name or "oob-server" in other_name) \
                    and other_ep["interface"].startswith("eth"):
                continue

            # Keep everything else (server connections, etc.)
            new_links.append(link)

        # --- Pass 2: Connect ALL switch eth0s to air-oob-switch ---
        already_on_air_oob = {
            ep["node"]
            for link in new_links
            if isinstance(link[0], dict) and isinstance(link[1], dict)
            for ep in link
            if ep.get("interface") == "eth0"
            and any(e.get("node") == AIR_OOB for e in link if isinstance(e, dict))
        }
        for sw_name in sorted(nodes):
            role = classify_node(self._name_to_role.get(sw_name, sw_name))
            if role not in ("core", "oob", "edge"):
                continue
            if sw_name in already_on_air_oob:
                continue
            swp = _alloc_swp()
            new_links.append(self._make_link(sw_name, "eth0", AIR_OOB, swp))
            switch_connected[sw_name].add("eth0")

        # --- Pass 3: OOB switch uplinks to air-oob-switch ---
        # Each OOB switch gets an uplink port to air-oob-switch (for its mgmt VLAN)
        for oob_name in oob_switch_names:
            used = switch_connected.get(oob_name, set())
            uplink_port = None
            for p in range(1, 53):
                candidate = f"swp{p}"
                if candidate not in used:
                    uplink_port = candidate
                    break
            if uplink_port:
                swp = _alloc_swp()
                new_links.append(self._make_link(oob_name, uplink_port, AIR_OOB, swp))
                switch_connected[oob_name].add(uplink_port)

        # --- Pass 4: Create dhcp-oob and oob-server-01 ---
        # Each gets: eth0 → outbound, eth1 → air-oob-switch (air-mgmt),
        #            eth2+ → air-oob-switch (one per mgmt_subnet)
        for infra_name in ["dhcp-oob", "oob-server-01"]:
            if infra_name not in nodes:
                defaults = NODE_DEFAULTS.get("infra", NODE_DEFAULTS["unknown"])
                nodes[infra_name] = {
                    "cpu": defaults["cpu"],
                    "memory": defaults["memory"],
                    "storage": defaults["storage"],
                    "positioning": {"x": 0, "y": 0},
                    "os": SERVER_OS,
                    "features": {"uefi": False, "tpm": False},
                    "pxehost": False,
                    "secureboot": False,
                    "oob": False,
                    "emulation_type": None,
                    "network_pci": {},
                }
            # eth0 → outbound
            outbound_exists = any(
                isinstance(link[0], dict) and link[0].get("node") == infra_name
                and link[1] == "outbound"
                for link in new_links
            )
            if not outbound_exists:
                new_links.append([
                    {
                        "interface": "eth0",
                        "node": infra_name,
                        "mac": generate_mac(infra_name, "eth0"),
                        "network_pci": None,
                    },
                    "outbound",
                ])
            # eth1 → air-oob-switch (air-mgmt, untagged)
            swp = _alloc_swp()
            new_links.append(self._make_link(infra_name, "eth1", AIR_OOB, swp))
            # eth2+ → air-oob-switch (one per mgmt_subnet)
            for i in range(n_subnets):
                eth_name = f"eth{2 + i}"
                swp = _alloc_swp()
                new_links.append(self._make_link(infra_name, eth_name, AIR_OOB, swp))

        # --- Create the air-oob-switch node ---
        role_defaults = NODE_DEFAULTS.get("air-oob", NODE_DEFAULTS["oob"])
        nodes[AIR_OOB] = {
            "cpu": role_defaults["cpu"],
            "memory": role_defaults["memory"],
            "storage": role_defaults["storage"],
            "positioning": {"x": 0, "y": 0},  # updated by _apply_layout
            "os": self._resolve_os(AIR_OOB),
            "features": {"uefi": False, "tpm": False},
            "pxehost": False,
            "secureboot": False,
            "oob": False,
            "emulation_type": None,
            "network_pci": {},
        }

        # Update switch_connected tracking
        switch_connected[AIR_OOB] = air_connected

        print(f"    air-oob-switch: {len(air_connected)} ports connected "
              f"(swp1-swp{next_swp - 1}), "
              f"{n_subnets} mgmt subnet{'s' if n_subnets != 1 else ''}")

        # Store metadata for Node Instructions (used by air-deploy.py)
        self._air_oob_metadata = {
            'mgmt_subnets': mgmt_subnets,
            'oob_switch_names': oob_switch_names,
            'connected_ports': sorted(air_connected, key=lambda p: int(p.replace("swp", ""))),
        }

        return nodes, new_links, switch_connected

    # ---- unconnected stubs ------------------------------------------------

    def _build_unconnected_stubs(
        self, switch_connected: Dict[str, Set[str]]
    ) -> list:
        """Add unconnected stubs for every switch port not already linked."""
        links: list = []

        # Gather all switch names from wiremap (use actual names, not function roles)
        switch_names: Set[str] = set()
        for r in self.rows:
            if is_switch(r.system_role):
                switch_names.add(r.system_name)
            if r.switch_role and is_switch(r.switch_role):
                switch_names.add(r.switch_name)

        for switch_name in sorted(switch_names):
            breakout_map, disabled_ports = self._analyze_breakouts(switch_name)
            port_count = self._effective_port_count(switch_name, breakout_map)
            connected = switch_connected.get(switch_name, set())

            for port_num in range(1, port_count + 1):
                if port_num in disabled_ports:
                    continue

                if port_num in breakout_map:
                    max_sub = breakout_map[port_num]
                    for sub in range(max_sub + 1):
                        sub_port = f"swp{port_num}s{sub}"
                        if sub_port not in connected:
                            links.append(
                                self._make_unconnected(switch_name, sub_port))
                else:
                    port_name = f"swp{port_num}"
                    if port_name not in connected:
                        links.append(
                            self._make_unconnected(switch_name, port_name))

            # eth0 management port
            if "eth0" not in connected:
                links.append(self._make_unconnected(switch_name, "eth0"))

        return links

    def _analyze_breakouts(
        self, switch_name: str
    ) -> Tuple[Dict[int, int], Set[int]]:
        """Scan ALL rows (including Display=No) for breakout/disabled info.

        Returns:
            breakout_map: {base_port_num: max_sub_port_index}
            disabled_ports: set of port numbers marked 'Port Disabled by Neighbor'
        """
        breakout_map: Dict[int, int] = {}
        disabled_ports: Set[int] = set()

        for r in self.rows:
            if r.system_name == switch_name:
                self._scan_port_info(
                    r.nic_port, r.net_profile,
                    breakout_map, disabled_ports)
            if r.switch_name == switch_name:
                self._scan_port_info(
                    r.switch_port, r.net_profile,
                    breakout_map, disabled_ports)

        return breakout_map, disabled_ports

    @staticmethod
    def _scan_port_info(
        port_str: str,
        description: str,
        breakout_map: Dict[int, int],
        disabled_ports: Set[int],
    ) -> None:
        """Update breakout_map and disabled_ports from one port entry."""
        if not port_str:
            return

        desc_lower = (description or "").lower()

        if "disabled by neighbor" in desc_lower or "port disabled" in desc_lower:
            parsed = parse_swp_port(port_str)
            if parsed:
                disabled_ports.add(parsed[0])
            return

        parsed = parse_swp_port(port_str)
        if parsed and parsed[1] is not None:
            base_num, sub_idx = parsed
            if base_num not in breakout_map or sub_idx > breakout_map[base_num]:
                breakout_map[base_num] = sub_idx

    def _effective_port_count(
        self, switch_name: str, breakout_map: Dict[int, int]
    ) -> int:
        """Base port count from the switch model.

        Ports above this count that appear in the wiremap are handled as
        connected links — they don't need unconnected stubs generated.
        We do NOT extend the range to fill gaps between the model max and
        the highest wiremap port, since those intermediate ports may not
        physically exist on the switch (e.g., SN2201 has swp1-48 + swp49-52
        uplinks, but swp53+ don't exist even though virtual connections
        may reference swp60/61).
        """
        role_name = self._name_to_role.get(switch_name, switch_name)
        role = classify_node(role_name)
        return SWITCH_MODELS.get(role, {}).get("ports", 48)

    # ---- helpers ----------------------------------------------------------

    def _next_eth(self, server_name: str) -> str:
        """Return next sequential ethN for a server node.

        Skips ethN values already used by explicit rows (e.g., eth0 from
        'Air - Management' entries) to avoid duplicate endpoints.
        """
        idx = self._server_eth_counter[server_name]
        explicit = self._explicit_eth.get(server_name, set())
        while idx in explicit:
            idx += 1
        self._server_eth_counter[server_name] = idx + 1
        return f"eth{idx}"

    def _make_link(self, node_a: str, port_a: str,
                   node_b: str, port_b: str) -> list:
        # Use the actual node name (not function/role) for MAC generation so topology
        # MACs match the dnsmasq DHCP reservations built by the Excel parser (which
        # also uses the node name).
        return [
            {
                "interface": port_a,
                "node": node_a,
                "mac": generate_mac(node_a, port_a),
                "network_pci": None,
            },
            {
                "interface": port_b,
                "node": node_b,
                "mac": generate_mac(node_b, port_b),
                "network_pci": None,
            },
        ]

    def _make_unconnected(self, node: str, port: str) -> list:
        return [
            {
                "interface": port,
                "node": node,
                "mac": generate_mac(node, port),
                "network_pci": None,
            },
            "unconnected",
        ]


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class TopologyValidator:
    """Compare an existing topology JSON against the Excel wiremap."""

    def __init__(self, excel_path: Path, topology_json: Path, arch: str):
        self.excel_path = excel_path
        self.topology_json = topology_json
        self.arch = arch
        wb = openpyxl.load_workbook(excel_path, data_only=True)
        self.rows = parse_wiremap_excel(excel_path)
        if "Air_Only" in wb.sheetnames:
            self.rows = parse_air_only_sheet(wb) + self.rows
        wb.close()
        # Build actual-name → function/role mapping
        self._name_to_role: Dict[str, str] = {}
        for r in self.rows:
            if r.system_name and r.system_name != r.system_role:
                self._name_to_role[r.system_name] = r.system_role
            if r.switch_name and r.switch_name != r.switch_role:
                self._name_to_role[r.switch_name] = r.switch_role
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self) -> bool:
        """Run all checks.  Returns True when no errors are found."""
        with open(self.topology_json, "r") as f:
            topo = json.load(f)

        nodes = topo.get("content", {}).get("nodes", {})
        links = topo.get("content", {}).get("links", [])

        self._check_nodes(nodes)
        self._check_links(links)
        self._check_os_versions(nodes)
        self._check_unconnected_stubs(links)

        self._print_results()
        return len(self.errors) == 0

    # ---- checks -----------------------------------------------------------

    def _check_nodes(self, nodes: dict) -> None:
        wiremap_devices: Set[str] = set()
        air_only_devices: Set[str] = set()
        for r in self.rows:
            if not r.display_in_air:
                continue
            # Track Air-only nodes separately (Air - prefixed network profiles)
            is_air_row = r.net_profile and r.net_profile.startswith('Air')
            if r.system_role:
                # Skip invalid hostnames — generator skips them too
                if not is_valid_hostname(r.system_name):
                    continue
                if is_air_row:
                    air_only_devices.add(r.system_name)
                else:
                    wiremap_devices.add(r.system_name)
            if r.switch_role and r.switch_role.upper() not in ("NA", "OUTBOUND"):
                if not is_valid_hostname(r.switch_name):
                    continue
                if is_air_row:
                    air_only_devices.add(r.switch_name)
                else:
                    wiremap_devices.add(r.switch_name)

        # Nodes always injected by the generator (Air infrastructure)
        auto_injected = {"air-oob-switch", "dhcp-oob", "oob-server-01"}

        # All devices the topology should contain
        all_expected = wiremap_devices | air_only_devices | auto_injected
        topo_nodes = set(nodes.keys())

        for name in sorted(wiremap_devices - topo_nodes):
            self.errors.append(
                f"Missing node: {name} (in wiremap, not in topology)")
        for name in sorted(topo_nodes - all_expected):
            self.warnings.append(
                f"Extra node: {name} (in topology, not in wiremap)")

    def _check_links(self, links: list) -> None:
        # Build lookup: switch -> set of ports present in topology
        # Node names in topology JSON are actual names; use _name_to_role for classification
        topo_switch_ports: Dict[str, Set[str]] = defaultdict(set)
        for link in links:
            node = link[0]["node"]
            if is_switch(self._name_to_role.get(node, node)):
                topo_switch_ports[node].add(link[0]["interface"])
            if isinstance(link[1], dict):
                node2 = link[1]["node"]
                if is_switch(self._name_to_role.get(node2, node2)):
                    topo_switch_ports[node2].add(link[1]["interface"])
            elif isinstance(link[1], str) and link[1] not in ("outbound", "unconnected"):
                pass  # unknown string endpoint

        for r in self.rows:
            if not r.display_in_air:
                continue
            if not r.switch_role or r.switch_role.upper() in ("NA", "OUTBOUND"):
                continue
            if not r.switch_port:
                continue

            # Check right-side switch port
            if is_switch(r.switch_role):
                if r.switch_port not in topo_switch_ports.get(r.switch_name, set()):
                    self.errors.append(
                        f"Missing link: {r.switch_name}:{r.switch_port} "
                        f"(connected to {r.system_name} in wiremap)")

            # Check left-side switch port (switch-to-switch)
            if is_switch(r.system_role) and r.nic_port:
                if r.nic_port not in topo_switch_ports.get(r.system_name, set()):
                    self.errors.append(
                        f"Missing link: {r.system_name}:{r.nic_port} "
                        f"(connected to {r.switch_name} in wiremap)")

    def _check_os_versions(self, nodes: dict) -> None:
        for name, props in sorted(nodes.items()):
            role_name = self._name_to_role.get(name, name)
            actual = props.get("os", "")
            # Switch OS may be version-mapped, so only flag if it's
            # clearly wrong (not a cumulus image for switches, not ubuntu for servers)
            if is_switch(role_name):
                if "cumulus" not in actual.lower():
                    self.warnings.append(
                        f"OS mismatch: {name} has '{actual}', expected a Cumulus image")
            elif actual != SERVER_OS:
                self.warnings.append(
                    f"OS mismatch: {name} has '{actual}', expected '{SERVER_OS}'")

    def _check_unconnected_stubs(self, links: list) -> None:
        topo_switch_ports: Dict[str, Set[str]] = defaultdict(set)
        for link in links:
            node = link[0]["node"]
            if is_switch(self._name_to_role.get(node, node)):
                topo_switch_ports[node].add(link[0]["interface"])
            if isinstance(link[1], dict):
                node2 = link[1]["node"]
                if is_switch(self._name_to_role.get(node2, node2)):
                    topo_switch_ports[node2].add(link[1]["interface"])

        switch_names: Set[str] = set()
        for r in self.rows:
            if is_switch(r.system_role):
                switch_names.add(r.system_name)
            if r.switch_role and is_switch(r.switch_role):
                switch_names.add(r.switch_name)

        for switch_name in sorted(switch_names):
            role_name = self._name_to_role.get(switch_name, switch_name)
            role = classify_node(role_name)
            model_ports = SWITCH_MODELS.get(role, {}).get("ports", 48)

            # Find max port and disabled ports from wiremap
            max_port = model_ports
            disabled_ports: Set[int] = set()
            for r in self.rows:
                port_str = None
                desc = r.net_profile
                if r.system_name == switch_name:
                    port_str = r.nic_port
                elif r.switch_name == switch_name:
                    port_str = r.switch_port
                if port_str:
                    parsed = parse_swp_port(port_str)
                    if parsed and parsed[0] > max_port:
                        max_port = parsed[0]
                    desc_lower = (desc or "").lower()
                    if parsed and ("disabled by neighbor" in desc_lower
                                   or "port disabled" in desc_lower):
                        disabled_ports.add(parsed[0])

            ports_in_topo = topo_switch_ports.get(switch_name, set())

            for port_num in range(1, max_port + 1):
                if port_num in disabled_ports:
                    continue
                port_name = f"swp{port_num}"
                has_plain = port_name in ports_in_topo
                has_sub = any(
                    p.startswith(f"swp{port_num}s") for p in ports_in_topo
                )
                if not has_plain and not has_sub:
                    self.warnings.append(
                        f"Missing port: {switch_name}:{port_name} "
                        f"(no entry in topology)")

    # ---- output -----------------------------------------------------------

    def _print_results(self) -> None:
        if not self.errors and not self.warnings:
            print("  Topology validation passed - no issues found")
            return

        if self.errors:
            print(f"\n  {len(self.errors)} error(s):")
            for err in self.errors:
                print(f"    x {err}")

        if self.warnings:
            print(f"\n  {len(self.warnings)} warning(s):")
            for warn in self.warnings:
                print(f"    ! {warn}")

        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="ERA Topology Generator & Validator")
    sub = ap.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate topology from wiremap")
    gen.add_argument("--arch", required=True,
                     help="Architecture (e.g., 2-8-5-200)")
    gen.add_argument("--site", default="default",
                     help="Site name (default: default)")

    val = sub.add_parser("validate",
                         help="Validate topology against wiremap")
    val.add_argument("--arch", required=True, help="Architecture")
    val.add_argument("--site", default="default", help="Site name")
    val.add_argument("--topology",
                     help="Path to topology JSON (default: auto-detect)")

    args = ap.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    # Locate Excel wiremap
    excel_path = (
        project_root / "input" / args.arch / args.site / f"{args.arch}.xlsx"
    )
    if not excel_path.exists():
        print(f"  Error: Excel workbook not found: {excel_path}")
        return 1

    if args.command == "generate":
        output_path = (
            project_root / "output" / args.arch / args.site
            / "topology" / f"{args.arch}-topology.json"
        )
        print(f"  Generating topology for {args.arch} (site: {args.site})")
        print(f"  Source: {excel_path}")
        generator = TopologyGenerator(excel_path, args.arch, args.site)
        generator.write(output_path)
        return 0

    elif args.command == "validate":
        if args.topology:
            topo_path = Path(args.topology)
        else:
            topo_path = (
                project_root / "output" / args.arch / args.site
                / "topology" / f"{args.arch}-topology.json"
            )

        if not topo_path.exists():
            print(f"  Error: topology not found: {topo_path}")
            return 1

        print(f"  Validating {topo_path}")
        print(f"  Against wiremap {excel_path}")
        validator = TopologyValidator(excel_path, topo_path, args.arch)
        return 0 if validator.validate() else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
