#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Present an intake-form workbook to the parser in the shapes it expects.

ERA-109 Phase 1. `process_excel_template` reads `settings` and `nodes` from
whichever format it detects, but everything BELOW that branch point still
reads four legacy sheets directly:

    VLANs & Profiles   x8   VLANs, VRFs, DHCP relay, port-profile hardware
    Air_Only           x3   version -> Air image map, Air management subnet
    Wire Map           x1   the physical link table
    Loopbacks & ASNs   x1   per-switch loopback overrides AND the BGP ASN base

Rather than rewrite those thirteen call sites -- thirteen chances to change
legacy behaviour, against a pipeline whose correctness is defined as
byte-identical output -- this module builds the four sheets IN MEMORY from
the intake sheets that already carry the same data, and hands the parser a
workbook it can read unchanged.

That makes byte-identical configs the DEFAULT rather than something to be
re-established call site by call site: identical inputs reach identical code.
The five ERA override sheets need nothing here; `convert_workbook` already
carries them across verbatim.

This is a view, not a conversion. Nothing is written to disk, the intake
sheets are left untouched, and the legacy reading path is not modified.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from intake_reader import (  # noqa: E402
    column_map, find_section, header_row,
)
from intake_layout import host_row_groups  # noqa: E402

# Legacy `Wire Map` header row, in order.
WIRE_MAP_HEADERS = [
    "Display in Air", "System Name (A)", "Port (A)", "Port Side (A)",
    "Cable Split (A)", "System Name (B)", "Port (B)", "Port Side (B)",
    "Cable Split (B)", "Network Profile",
]

# Legacy `Wire Map` column -> intake `Wiremap` column. The inverse of
# convert_workbook.WIREMAP_COLUMN_MAP; kept as its own literal because the
# two are read in opposite directions and a shared dict inverted at import
# time reads worse than saying it once in each direction.
_WIRE_MAP_FROM_INTAKE = {
    "Display in Air": "display in air",
    "System Name (A)": "system name (a)",
    "Port (A)": "port (a)",
    "Port Side (A)": "port side (a)",
    "Cable Split (A)": "cable split (a)",
    "System Name (B)": "system name (z)",
    "Port (B)": "port (z)",
    "Port Side (B)": "port side (z)",
    "Cable Split (B)": "cable split (z)",
    "Network Profile": "network profile",
}

# Legacy `VLANs` section header row, in order.
VLAN_HEADERS = [
    "VLAN ID", "Name", "Purpose", "Subnet", "Gateway", "VRF", "VNI",
    "DHCP Relay Client",
]

# Legacy `VLANs` column -> intake `Network Data` column (normalised).
_VLAN_FROM_INTAKE = {
    "VLAN ID": "vlan",
    "Name": "fabric name",
    "Purpose": "use",
    "Subnet": "ip subnet",
    "Gateway": "gateway addr",
    "VRF": "vrf",
    "VNI": "vni(d)",
    "DHCP Relay Client": "dhcp relay client",
}

# Sub-tables that `convert_workbook` copied into `Network Data` verbatim and
# that are copied back the same way.
_STACKED_SECTIONS = ["VRFs", "Port Profiles", "DHCP Relay"]

LOOPBACK_HEADERS = ["Switch", "Default", "OOB", "INBAND", "EXIT", "GPU",
                    "STORAGE", "ASN"]

# Legacy `Loopbacks & ASNs` column -> intake `Switch Data` column.
_LOOPBACK_FROM_SWITCH_DATA = {
    "Switch": "name",
    "Default": "loopback ip",
    "OOB": "oob lo",
    "INBAND": "inband (n-s) lo",
    "EXIT": "exit lo",
    "GPU": "gpu lo",
    "STORAGE": "storage lo",
    "ASN": "asn",
}

AIR_SUBNET_KEY = "Air Management Subnet"


class Origins:
    """Where each legacy-view cell came from on the intake form.

    The validators read the legacy views, so their findings name legacy
    sheets and rows. An operator only has the intake workbook; this maps a
    legacy (sheet, row, column) back to the intake (sheet, row, column) the
    value was copied from, so a finding can name a cell the operator can find.
    """

    def __init__(self):
        self._rows = {}

    def add(self, legacy_sheet, legacy_row, intake_sheet, intake_row, cols=None):
        """Record one copied row. `cols` maps legacy column -> intake column;
        None means the columns were copied in place."""
        self._rows[(legacy_sheet, legacy_row)] = (intake_sheet, intake_row, cols)

    def row(self, legacy_sheet, legacy_row):
        """(intake sheet, intake row) for a legacy row, or None."""
        origin = self._rows.get((legacy_sheet, legacy_row))
        return None if origin is None else origin[:2]

    def cell(self, legacy_sheet, legacy_row, legacy_col):
        """(intake sheet, intake row, intake column) for a legacy cell, or None.

        The column is None when the legacy column has no intake counterpart.
        """
        origin = self._rows.get((legacy_sheet, legacy_row))
        if origin is None:
            return None
        sheet, row, cols = origin
        col = legacy_col if cols is None else cols.get(legacy_col)
        return sheet, row, col


def _record(origins, *args, **kwargs):
    if origins is not None:
        origins.add(*args, **kwargs)


def is_intake_workbook(wb):
    """True when the workbook is in the intake form format (ADR-0064).

    Detected by sheet names. `Wiremap` (one word) is the intake form;
    `Wire Map` (two words) is the legacy layout. Requires BOTH intake
    markers present AND every legacy-required sheet absent, so a legacy
    workbook that has picked up a stray `Wiremap`/`Deployment` tab (e.g.
    scratch notes) cannot flip onto the intake path and be refused there.
    The converter's own output is exactly ['Read Me', 'Wiremap', 'Network
    Data', 'Switch Data', 'Host Data', 'Deployment', 'Derived'] (no legacy
    sheets), and none of the shipped workbooks carry both `Wiremap` and
    `Settings`.

    The single definition: the parser, the validator, the loader below and
    the OEM audit all call this one. They had drifted into two rules --
    this strict one and a looser `Wiremap and Deployment` -- which disagree
    on exactly the stray-tab case the strict rule exists to catch.
    """
    has_intake_markers = "Wiremap" in wb.sheetnames and "Deployment" in wb.sheetnames
    has_legacy_sheets = any(
        s in wb.sheetnames
        for s in ("Settings", "Nodes", "VLANs & Profiles", "Wire Map"))
    return has_intake_markers and not has_legacy_sheets


def _rows_below(ws, first_row, key_col=1):
    """Row indices from `first_row` while column `key_col` has a value."""
    out = []
    for r in range(first_row, ws.max_row + 1):
        if ws.cell(r, key_col).value in (None, ""):
            break
        out.append(r)
    return out


def _build_wire_map(wb, origins=None):
    src = wb["Wiremap"]
    cols = column_map(src)
    start = header_row(src) + 1
    col_origin = {c: cols.get(_WIRE_MAP_FROM_INTAKE[name])
                  for c, name in enumerate(WIRE_MAP_HEADERS, start=1)}

    dst = wb.create_sheet("Wire Map")
    for c, name in enumerate(WIRE_MAP_HEADERS, start=1):
        dst.cell(1, c, name)

    out_row = 2
    for r in range(start, src.max_row + 1):
        a_col = cols.get("system name (a)")
        if not a_col or not src.cell(r, a_col).value:
            continue                      # not a link — same rule as the converter
        for c, legacy_name in enumerate(WIRE_MAP_HEADERS, start=1):
            src_col = cols.get(_WIRE_MAP_FROM_INTAKE[legacy_name])
            if src_col:
                dst.cell(out_row, c, src.cell(r, src_col).value)
        _record(origins, "Wire Map", out_row, "Wiremap", r, col_origin)
        out_row += 1
    return dst


def _build_vlans_and_profiles(wb, origins=None):
    src = wb["Network Data"]
    dst = wb.create_sheet("VLANs & Profiles")

    dst.cell(1, 1, "VLANs")
    for c, name in enumerate(VLAN_HEADERS, start=1):
        dst.cell(2, c, name)

    cols = column_map(src)
    vlan_cols = {c: cols.get(_VLAN_FROM_INTAKE[name])
                 for c, name in enumerate(VLAN_HEADERS, start=1)}
    _record(origins, "VLANs & Profiles", 2, "Network Data", header_row(src), vlan_cols)
    out_row = 3
    for r in _rows_below(src, header_row(src) + 1):
        for c, legacy_name in enumerate(VLAN_HEADERS, start=1):
            src_col = cols.get(_VLAN_FROM_INTAKE[legacy_name])
            if src_col:
                dst.cell(out_row, c, src.cell(r, src_col).value)
        _record(origins, "VLANs & Profiles", out_row, "Network Data", r, vlan_cols)
        out_row += 1

    # The stacked sub-tables went across verbatim; they come back the same
    # way, including their own header rows, so the legacy readers that scan
    # for each section title find exactly what they expect.
    for title in _STACKED_SECTIONS:
        try:
            title_row = find_section(src, title)
        except (ValueError, KeyError):
            continue                      # optional section, absent here
        out_row += 1                      # blank separator row
        dst.cell(out_row, 1, title)
        _record(origins, "VLANs & Profiles", out_row, "Network Data", title_row)
        out_row += 1
        end = title_row + 1
        while end + 1 <= src.max_row and src.cell(end + 1, 1).value:
            end += 1
        for r in range(title_row + 1, end + 1):
            for c in range(1, src.max_column + 1):
                value = src.cell(r, c).value
                if value is not None:
                    dst.cell(out_row, c, value)
            _record(origins, "VLANs & Profiles", out_row, "Network Data", r)
            out_row += 1
    return dst


def _build_loopbacks(wb, origins=None):
    src = wb["Switch Data"]
    cols = column_map(src)
    start = header_row(src) + 1
    col_origin = {c: cols.get(_LOOPBACK_FROM_SWITCH_DATA[name])
                  for c, name in enumerate(LOOPBACK_HEADERS, start=1)}

    dst = wb.create_sheet("Loopbacks & ASNs")
    dst.cell(1, 1, "Per-switch / per-VRF loopback overrides. Blank cells "
                   "fall back to Settings.loopback_base. See docs/LOOPBACKS.md.")
    for c, name in enumerate(LOOPBACK_HEADERS, start=1):
        dst.cell(2, c, name)

    out_row = 3
    name_col = cols.get("name")
    for r in range(start, src.max_row + 1):
        if not name_col or not src.cell(r, name_col).value:
            continue
        for c, legacy_name in enumerate(LOOPBACK_HEADERS, start=1):
            src_col = cols.get(_LOOPBACK_FROM_SWITCH_DATA[legacy_name])
            if src_col:
                dst.cell(out_row, c, src.cell(r, src_col).value)
        _record(origins, "Loopbacks & ASNs", out_row, "Switch Data", r, col_origin)
        out_row += 1
    return dst


def _build_air_only(wb, version_images, air_subnet):
    dst = wb.create_sheet("Air_Only")
    dst.cell(1, 1, "Friendly Version")
    dst.cell(1, 2, "Air Image")
    row = 2
    for version, image in version_images:
        dst.cell(row, 1, version)
        dst.cell(row, 2, image)
        row += 1
    row += 1                              # blank separator, as in the legacy sheet
    dst.cell(row, 1, AIR_SUBNET_KEY)
    dst.cell(row, 2, air_subnet)
    return dst


# Legacy `Nodes` header row, in order.
NODES_HEADERS = [
    "Function", "Name", "OOB VLAN", "Type", "MAC Address for ZTP",
    "Mgmt IP Address", "Prefix", "Gateway", "ZTP", "Enabled", "Notes",
]

# Legacy `Nodes` column -> intake `Switch Data` column (normalised).
_NODES_FROM_SWITCH_DATA = {
    "Function": "function", "Name": "name", "OOB VLAN": "oob vlan",
    "Type": None,                          # switches are Type=switch
    "MAC Address for ZTP": "ztp mac address",
    "Mgmt IP Address": "mgmt ip", "Prefix": "prefix",
    "Gateway": "mgmt gateway", "ZTP": "ztp", "Enabled": "enabled",
    "Notes": "notes",
}

# Legacy `Nodes` column -> intake `Host Data` column (normalised).
_NODES_FROM_HOST_DATA = {
    "Function": "function", "Name": "system name", "OOB VLAN": "oob vlan",
    "Type": "type", "MAC Address for ZTP": "mac address",
    "Mgmt IP Address": "ip", "Prefix": "prefix", "Gateway": "gateway",
    "ZTP": "ztp", "Enabled": "enabled", "Notes": "notes",
}


def _build_nodes(wb, origins=None):
    """Rebuild `Nodes` by re-merging Switch Data and Host Data.

    `convert_workbook` splits one `Nodes` sheet across the two, so this
    re-merges them. Switch rows carry no `Type` column of their own -- the
    split criterion is "has a row in Loopbacks & ASNs", and every such
    device is Type=switch -- so it is restored as a constant.
    """
    dst = wb.create_sheet("Nodes")
    for c, name in enumerate(NODES_HEADERS, start=1):
        dst.cell(1, c, name)

    out_row = 2
    for sheet, mapping, key, forced_type in (
            ("Switch Data", _NODES_FROM_SWITCH_DATA, "name", "switch"),
            ("Host Data", _NODES_FROM_HOST_DATA, "system name", None)):
        if sheet not in wb.sheetnames:
            continue
        src = wb[sheet]
        cols = column_map(src)
        key_col = cols.get(key)
        if not key_col:
            continue
        # `Host Data` is one row per interface; the legacy `Nodes` sheet is
        # one row per node. Only each host's management row becomes a Nodes
        # row -- the same rule the parser applies -- otherwise a completed
        # workbook's bond/GPU rows read as duplicate nodes with bogus mgmt IPs.
        col_origin = {c: (None if mapping[name] is None else cols.get(mapping[name]))
                      for c, name in enumerate(NODES_HEADERS, start=1)}
        mgmt_rows = None
        if sheet == "Host Data" and "logical interface" in cols:
            mgmt_rows = {g["mgmt"] for g in host_row_groups(src).values()
                         if g["mgmt"] is not None}
        for r in range(header_row(src) + 1, src.max_row + 1):
            if not src.cell(r, key_col).value:
                continue
            if mgmt_rows is not None and r not in mgmt_rows:
                continue
            for c, legacy_name in enumerate(NODES_HEADERS, start=1):
                intake_name = mapping[legacy_name]
                if intake_name is None:
                    dst.cell(out_row, c, forced_type)
                    continue
                src_col = cols.get(intake_name)
                if src_col:
                    dst.cell(out_row, c, src.cell(r, src_col).value)
            _record(origins, "Nodes", out_row, sheet, r, col_origin)
            out_row += 1
    return dst


def _build_settings(wb, settings_rows, version_rows, origins=None, source_rows=()):
    """Rebuild `Settings` from `Deployment`.

    `settings_rows` is (name, value) in sheet order INCLUDING the section
    banners, so the reconstructed sheet keeps the legacy grouping that
    `parse_settings` skips over. `version_rows` is (role, version), written
    under the `Switch Function` header `parse_versions` scans for.
    """
    dst = wb.create_sheet("Settings")
    dst.cell(1, 1, "Setting")
    dst.cell(1, 2, "Value")
    row = 2
    sources = dict(enumerate(source_rows))
    for i, (name, value) in enumerate(settings_rows):
        dst.cell(row, 1, name)
        dst.cell(row, 2, value)
        if sources.get(i) is not None:
            _record(origins, "Settings", row, "Deployment", sources[i])
        row += 1

    if version_rows:
        row += 1
        dst.cell(row, 1, "VERSIONS")
        row += 1
        dst.cell(row, 1, "Switch Function")
        dst.cell(row, 2, "Cumulus Version")
        row += 1
        for role, version in version_rows:
            dst.cell(row, 1, role)
            dst.cell(row, 2, version)
            row += 1
    return dst


def _deployment_rows(wb):
    """Split `Deployment` into settings, Cumulus versions and the Air block.

    Read in SHEET ORDER, banners included, so the reconstructed `Settings`
    keeps the legacy grouping. The three categories are distinguished the
    same way `_parse_intake_settings` does it, so the adapter and the parser
    cannot disagree about what a given row means.
    """
    import re
    from intake_reader import SECTION_BANNERS

    version_key = re.compile(r"^\d+\.\d+\.\d+$")
    roles = {"core", "oob", "csl", "gsl"}

    ws = wb["Deployment"]
    settings_rows, version_rows, image_rows = [], [], []
    source_rows = []
    air_subnet = None
    # A banner is held until a real setting appears under it. `Deployment`
    # carries two that head no settings at all -- `VERSIONS`, whose rows are
    # version_rows, and the trailing `AIR DEPLOYMENT`, whose rows are the
    # image map -- and legacy `Settings` has neither: the images live on
    # `Air_Only` and the VERSIONS block is rebuilt below.
    pending_banner = None
    for r in range(1, ws.max_row + 1):
        name = ws.cell(r, 1).value
        if name is None:
            continue
        text = str(name).strip()
        if not text or text.startswith("#"):
            continue
        value = ws.cell(r, 2).value
        if text.lower() == "setting" and str(value).strip().lower() == "value":
            continue
        if text == AIR_SUBNET_KEY:
            air_subnet = value
            continue
        if version_key.match(text):
            image_rows.append((text, value))
            continue
        if text.lower() in roles and value not in (None, ""):
            version_rows.append((text, value))
            continue
        if text.lower() in SECTION_BANNERS and value in (None, ""):
            pending_banner = text                    # keep the grouping
            continue
        if pending_banner is not None:
            settings_rows.append((pending_banner, None))
            source_rows.append(None)
            pending_banner = None
        settings_rows.append((text, value))
        source_rows.append(r)
    return settings_rows, version_rows, image_rows, air_subnet, source_rows


def add_legacy_views(wb, version_images=None, air_subnet=None, origins=None):
    """Add the legacy-shaped sheets the parser and validator read directly.

    Mutates `wb` in memory only. An existing sheet is never replaced, so
    this is a no-op on anything but a pure intake workbook.

    `version_images` / `air_subnet` may be passed by a caller that already
    read them; otherwise they are recovered from `Deployment` here.
    `origins`, when given, is an `Origins` filled with where each legacy row
    came from.
    """
    settings_rows, version_rows, image_rows, subnet = [], [], [], None
    source_rows = []
    if "Deployment" in wb.sheetnames:
        (settings_rows, version_rows, image_rows, subnet,
         source_rows) = _deployment_rows(wb)
    if version_images is None:
        version_images = image_rows
    if air_subnet is None:
        air_subnet = subnet

    if "Settings" not in wb.sheetnames and settings_rows:
        _build_settings(wb, settings_rows, version_rows, origins, source_rows)
    if "Wire Map" not in wb.sheetnames and "Wiremap" in wb.sheetnames:
        _build_wire_map(wb, origins)
    if "VLANs & Profiles" not in wb.sheetnames and "Network Data" in wb.sheetnames:
        _build_vlans_and_profiles(wb, origins)
    if "Loopbacks & ASNs" not in wb.sheetnames and "Switch Data" in wb.sheetnames:
        _build_loopbacks(wb, origins)
    if "Nodes" not in wb.sheetnames:
        _build_nodes(wb, origins)
    if "Air_Only" not in wb.sheetnames:
        _build_air_only(wb, version_images, air_subnet)
    return wb


def load_workbook(path, **kwargs):
    """Load a workbook, adding the legacy views if it is an intake form.

    The single entry point every script should use instead of calling
    `openpyxl.load_workbook` directly. Several tools -- the parser, the
    validator, the topology generator, the IP report -- open the workbook
    independently, and each one that bypasses this sees an intake workbook
    as a workbook with no `Wire Map` and fails.

    `read_only=True` is dropped when adapting: openpyxl read-only worksheets
    cannot have sheets added, and the adapter has to create them. Callers
    pass it as a performance hint, not a requirement.
    """
    import openpyxl

    intake = None
    probe_kwargs = dict(kwargs)
    probe_kwargs["read_only"] = True
    try:
        probe = openpyxl.load_workbook(path, **probe_kwargs)
        intake = is_intake_workbook(probe)
        probe.close()
    except Exception:                                  # noqa: BLE001
        intake = False

    if intake:
        kwargs.pop("read_only", None)
        wb = openpyxl.load_workbook(path, **kwargs)
        return add_legacy_views(wb)
    return openpyxl.load_workbook(path, **kwargs)
