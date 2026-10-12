#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Convert a legacy ERA workbook to the intake form (ADR-0064, ERA-109).

Transitional migration aid: warns on every run and is removed at nc-v10.
Moves data across sheet boundaries without inventing anything the legacy
workbook does not already carry — physical/procurement columns the intake form adds (DC
Location, Rack, RU, Interface Type, Transceiver, Cable Length/Type/SKU) are
left blank rather than guessed.

Phase 1 groundwork, not yet load-bearing: `Network Data`, `Rack Elevations`
and `High Level BOM` are emitted into the output workbook, but nothing in
excel_parser.py reads any of them today — only `Wiremap`, `Deployment`,
`Switch Data` and `Host Data` feed the parser. Their only consumers right
now are their own tests in test_convert_workbook.py. That is intentional
groundwork, not a bug, but it means a converted workbook's Network Data
content currently has no effect on what gets generated.

Usage:
    python3 scripts/convert_workbook.py <legacy.xlsx> <intake.xlsx>
"""
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).parent))
from utils import loopbacks_sheet_name  # noqa: E402
from intake_reader import find_section, read_section  # noqa: E402
from intake_derive import DERIVABLE_SETTINGS  # noqa: E402
import intake_style  # noqa: E402

DEPRECATION = (
    "convert_workbook is a transitional migration aid and will be "
    "removed in nc-v10. Author new workbooks in the intake form directly."
)


def _header_index(ws, row=1):
    """Map header text -> 1-based column index for a single header row."""
    return {ws.cell(row, c).value: c for c in range(1, ws.max_column + 1)
            if ws.cell(row, c).value is not None}


def _find_header_row(ws, marker, col=1):
    """Scan column `col` for the row whose text equals `marker`.

    Scanning rather than a fixed offset, matching intake_reader's own
    section-location convention — a disclaimer row above the header (as
    `Loopbacks & ASNs` carries) must not need a hardcoded row number.
    """
    want = str(marker).strip().lower()
    for r in range(1, ws.max_row + 1):
        if str(ws.cell(r, col).value or "").strip().lower() == want:
            return r
    raise ValueError(
        f"could not find a {marker!r} header row in sheet {ws.title!r}")


def _copy_sheet_verbatim(src_ws, out_wb, new_name):
    """Copy a sheet under a new name, preserving what a user authored.

    Values alone are not "unchanged". These sheets are carried precisely
    BECAUSE a user may have filled them in (ADR-0064 D6), so flattening a
    hand-built rack layout into bare strings is a quieter version of the data
    loss the carry exists to prevent. Styling, number formats, merged ranges
    and column/row sizing come across too.

    Formulas are handled by the caller, which re-reads the source workbook
    without `data_only` -- the main conversion needs cached values, so the
    workbook this function usually sees has already lost them.
    """
    from copy import copy

    dst = out_wb.create_sheet(new_name)
    for row in src_ws.iter_rows():
        for cell in row:
            out = dst.cell(cell.row, cell.column)
            if cell.value is not None:
                out.value = cell.value
            if cell.has_style:
                # Copy the style OBJECTS, not `cell._style`: that is an index
                # into the source workbook's style tables, and the same index
                # means something else (or nothing) in the destination -- it
                # produces a file that opens but raises on attribute access.
                out.font = copy(cell.font)
                out.fill = copy(cell.fill)
                out.border = copy(cell.border)
                out.alignment = copy(cell.alignment)
                out.protection = copy(cell.protection)
                out.number_format = cell.number_format
    for merged in src_ws.merged_cells.ranges:
        dst.merge_cells(str(merged))
    for key, dim in src_ws.column_dimensions.items():
        dst.column_dimensions[key].width = dim.width
        dst.column_dimensions[key].hidden = dim.hidden
    for idx, dim in src_ws.row_dimensions.items():
        dst.row_dimensions[idx].height = dim.height
        dst.row_dimensions[idx].hidden = dim.hidden
    dst.freeze_panes = src_ws.freeze_panes
    return dst


# --- Wire Map -> Wiremap ------------------------------------------------

# The intake form's layout lives in `intake_layout` so the generator can
# emit the same shape from the models. This converter is deleted at
# nc-v10 (ADR-0064 D2); the layout is not.
from intake_layout import (  # noqa: E402
    DROPPED_SETTINGS,
    HOST_MGMT_INTERFACE,
    CARRY_IF_POPULATED_SHEETS,
    WIREMAP_HEADERS,
    WIREMAP_COLUMN_MAP,
    NETWORK_DATA_HEADERS,
    SWITCH_DATA_GROUPS,
    SWITCH_DATA_HEADERS,
    HOST_DATA_HEADERS,
    DEPLOYMENT_NOTES,
    _NETWORK_DATA_VLAN_COLUMN_MAP,
    _NETWORK_DATA_VERBATIM_SECTIONS,
)



def _convert_wiremap(legacy_wb, out_wb):
    src = legacy_wb["Wire Map"]
    src_cols = _header_index(src)

    dst = out_wb.create_sheet("Wiremap")
    dst.cell(1, 1, "Source")
    dst.cell(1, 10, "Destination")
    dst_cols = {}
    for col, name in enumerate(WIREMAP_HEADERS, start=1):
        dst.cell(2, col, name)
        dst_cols[name] = col

    out_row = 3
    for r in range(2, src.max_row + 1):
        # A link with no A-side system name is not a link — matches the
        # definition the equivalence test itself uses for "link count".
        if not src.cell(r, src_cols["System Name (A)"]).value:
            continue
        for legacy_name, intake_name in WIREMAP_COLUMN_MAP.items():
            value = src.cell(r, src_cols[legacy_name]).value
            dst.cell(out_row, dst_cols[intake_name], value)
        out_row += 1
    return dst


# --- VLANs & Profiles -> Network Data ------------------------------------





def _copy_sheet_range(src_ws, dst_ws, src_start_row, src_end_row, dst_start_row):
    """Copy `src_ws` rows [src_start_row, src_end_row] verbatim, starting
    at `dst_start_row` in `dst_ws`. Returns the row after the copied block."""
    for r in range(src_start_row, src_end_row + 1):
        out_r = dst_start_row + (r - src_start_row)
        for c in range(1, src_ws.max_column + 1):
            value = src_ws.cell(r, c).value
            if value is not None:
                dst_ws.cell(out_r, c, value)
    return dst_start_row + (src_end_row - src_start_row + 1)


def _convert_network_data(legacy_wb, out_wb):
    src = legacy_wb["VLANs & Profiles"]
    dst = out_wb.create_sheet("Network Data")

    for col, name in enumerate(NETWORK_DATA_HEADERS, start=1):
        dst.cell(1, col, name)

    rows = read_section(src, "VLANs", list(_NETWORK_DATA_VLAN_COLUMN_MAP))
    dst_cols = {name: c for c, name in enumerate(NETWORK_DATA_HEADERS, start=1)}
    out_row = 2
    for row in rows:
        for legacy_name, intake_name in _NETWORK_DATA_VLAN_COLUMN_MAP.items():
            dst.cell(out_row, dst_cols[intake_name], row.get(legacy_name))
        out_row += 1
    out_row += 1                      # gap before the verbatim stacked sections

    # Locate each stacked section by scanning (never a fixed offset — their
    # positions move as the table above them grows), then copy the whole
    # title/header/data block verbatim, in the order they appear in the
    # source rather than the order named above.
    starts = {t: find_section(src, t) for t in _NETWORK_DATA_VERBATIM_SECTIONS}
    ordered = sorted((r, t) for t, r in starts.items() if r is not None)
    for i, (start, _title) in enumerate(ordered):
        end = ordered[i + 1][0] - 1 if i + 1 < len(ordered) else src.max_row
        out_row = _copy_sheet_range(src, dst, start, end, out_row)
        out_row += 1                  # gap between sections
    return dst


# --- Nodes + Loopbacks & ASNs -> Switch Data / Host Data ----------------

# A device belongs in Switch Data iff it has a row in `Loopbacks & ASNs`
# (matched by name against `Nodes`). Everything else — including `edge`
# and `air-oob`, which are Type=switch but carry no loopback — goes to
# Host Data. Data-driven, not a hardcoded role list: verified across three
# dissimilar archs (see the design doc's "Host Data needs ERA extension
# columns" note).







def _switch_names(legacy_wb):
    ws = legacy_wb[loopbacks_sheet_name(legacy_wb)]
    header_row = _find_header_row(ws, "Switch")
    cols = _header_index(ws, row=header_row)
    name_col = cols["Switch"]
    names = set()
    for r in range(header_row + 1, ws.max_row + 1):
        name = ws.cell(r, name_col).value
        if name:
            names.add(str(name).strip())
    return names


# Loopback field -> its column heading on the legacy sheet. Every one is
# optional: the sheet grew columns over time (a v6-era workbook is named
# `Loopbacks` and has no `ASN` at all), and an absent column holds no data to
# carry across. `Switch` and `Default` are not here — they identify the row.
_LOOPBACK_FIELD_COLUMNS = {
    "Loopback IP": "Default",
    "OOB": "OOB",
    "INBAND": "INBAND",
    "EXIT": "EXIT",
    "GPU": "GPU",
    "STORAGE": "STORAGE",
    "ASN": "ASN",
}


def _loopback_rows(legacy_wb):
    """Name -> per-switch loopback/ASN fields, keyed as in Switch Data."""
    ws = legacy_wb[loopbacks_sheet_name(legacy_wb)]
    header_row = _find_header_row(ws, "Switch")
    cols = _header_index(ws, row=header_row)
    absent = [h for h in _LOOPBACK_FIELD_COLUMNS.values() if h not in cols]
    if absent:
        print(f"WARNING: {ws.title}: no {', '.join(absent)} column — an older "
              f"workbook predating it. Those fields convert as blank.",
              file=sys.stderr)
    rows = {}
    for r in range(header_row + 1, ws.max_row + 1):
        name = ws.cell(r, cols["Switch"]).value
        if not name:
            continue
        rows[str(name).strip()] = {
            field: ws.cell(r, cols[heading]).value if heading in cols else None
            for field, heading in _LOOPBACK_FIELD_COLUMNS.items()
        }
    return rows


def _orphaned_loopback_names(nodes, cols, switch_names):
    """`Loopbacks & ASNs` names with no matching `Nodes` row.

    `_convert_nodes` only visits `Nodes` rows, so a device with loopbacks
    but no `Nodes` entry would otherwise vanish from the output silently
    — from both `Switch Data` and `Host Data`, loopback addresses and ASN
    included, with nothing to say so. This repo has shipped exactly this
    bug class before (name-based matching where one side is silently
    smaller than the other), so it fails loud instead: a switch with
    loopbacks but no node entry is a malformed workbook, not a tolerable
    variation.
    """
    node_names = {
        str(nodes.cell(r, cols["Name"]).value).strip()
        for r in range(2, nodes.max_row + 1)
        if nodes.cell(r, cols["Name"]).value
    }
    return sorted(switch_names - node_names)


def _sole_oob_vlan(legacy_wb):
    """The OOB VLAN id when exactly one exists, else None.

    Same rule as `excel_parser.resolve_oob_vlans`: one VRF-OOB VLAN fills a
    blank, several leave it blank rather than resolve a switch onto the wrong
    OOB subnet silently.
    """
    if "VLANs & Profiles" not in legacy_wb.sheetnames:
        return None
    rows = read_section(legacy_wb["VLANs & Profiles"], "VLANs",
                        ["vlan id", "vrf"])
    oob = [r for r in rows
           if str(r.get("vrf") or "").strip().upper() == "OOB"]
    return oob[0].get("vlan id") if len(oob) == 1 else None


def _convert_nodes(legacy_wb, out_wb):
    nodes = legacy_wb["Nodes"]
    cols = _header_index(nodes)
    switch_names = _switch_names(legacy_wb)
    loopbacks = _loopback_rows(legacy_wb)

    orphans = _orphaned_loopback_names(nodes, cols, switch_names)
    if orphans:
        raise ValueError(
            f"{loopbacks_sheet_name(legacy_wb)!r} names switch(es) with no "
            f"matching row in 'Nodes' — would be silently dropped from the "
            f"converted workbook: {orphans}"
        )

    oob_vlan = _sole_oob_vlan(legacy_wb)

    switch_ws = out_wb.create_sheet("Switch Data")
    for col, label in SWITCH_DATA_GROUPS:
        switch_ws.cell(1, col, label)
    for col, name in enumerate(SWITCH_DATA_HEADERS, start=1):
        switch_ws.cell(2, col, name)

    host_ws = out_wb.create_sheet("Host Data")
    for col, name in enumerate(HOST_DATA_HEADERS, start=1):
        host_ws.cell(1, col, name)

    switch_row = 3                    # row 1 groups, row 2 headers, data from row 3
    host_row = 2
    for r in range(2, nodes.max_row + 1):
        name = nodes.cell(r, cols["Name"]).value
        if not name:
            continue
        record = {h: nodes.cell(r, c).value for h, c in cols.items()}

        if str(name).strip() in switch_names:
            loop = loopbacks.get(str(name).strip(), {})
            values = [
                record.get("Function"), record.get("Name"),
                record.get("MAC Address for ZTP"),
                record.get("Mgmt IP Address"), record.get("Gateway"),
                loop.get("Loopback IP"),
                None,                          # Router-ID: new, no legacy source
                loop.get("ASN"),
                loop.get("OOB"), loop.get("INBAND"), loop.get("EXIT"),
                loop.get("GPU"), loop.get("STORAGE"),
                None, None, None, None, None,  # OOB/CPU/Support/Storage/GPU int: no legacy source
                record.get("OOB VLAN") or oob_vlan, record.get("Prefix"),
                record.get("ZTP"), record.get("Enabled"), record.get("Notes"),
            ]
            for col, value in enumerate(values, start=1):
                switch_ws.cell(switch_row, col, value)
            switch_row += 1
        else:
            mgmt_ip = record.get("Mgmt IP Address")
            values = [
                record.get("Name"),
                HOST_MGMT_INTERFACE if mgmt_ip else None,
                None,                                   # Logical Interface: no legacy source
                mgmt_ip, None,                          # NICOSName: no legacy source
                record.get("MAC Address for ZTP"), None,  # Profile: no legacy source
                record.get("Function"), record.get("Type"),
                record.get("Prefix"), record.get("Gateway"),
                record.get("ZTP"), record.get("Enabled"),
                record.get("OOB VLAN") or (oob_vlan if mgmt_ip else None),
                record.get("Notes"),
            ]
            for col, value in enumerate(values, start=1):
                host_ws.cell(host_row, col, value)
            host_row += 1
    return switch_ws, host_ws


# --- Settings + Air_Only -> Deployment -----------------------------------

# Settings the intake form is INTENDED to derive from the wiremap/switch/
# network data instead of declaring (the intake-form design's "Derived vs
# declared" split). This is the target set, not
# what is implemented: only the subset in `intake_derive.DERIVABLE_SETTINGS`
# is actually stripped from `Deployment` below.
#
# The rest are DECLARED in `Deployment` until a derive_<name>() exists for
# them. That is the design's own rule -- derive what the data supports,
# declare what it does not -- and stripping a setting nothing reconstructs
# does not make it derived, it just destroys it. An earlier revision
# stripped all 14, which silently dropped 12 real values and put four of
# them onto wrong hardcoded fallbacks downstream. As each derivation lands,
# its name moves into DERIVABLE_SETTINGS and it stops being copied here --
# no edit to this set is needed.
DERIVED_SETTINGS = {
    "architecture", "site_name", "ns_tiers", "ew_tiers", "convergence",
    "gpu_planes", "loopback_base", "num_physical_ports", "disabled_ports",
    "gpu_vlan_mode", "oob_uplink_mode", "ztp_server", "netq_ip",
    "ldap_servers",
}

# DERIVED_SETTINGS says all 14 above are safe to strip from `Deployment`
# because the parser reconstructs them from the wiremap/switch/network
# data. `intake_derive.DERIVABLE_SETTINGS` is the ground truth for how
# many it actually can today -- computed here, not hardcoded, so this
# check cannot rot the moment someone adds a derive_<name>() function and
# forgets this module exists. Non-empty today; that is the known Phase 1
# gap, not
# a bug someone just introduced -- so this is reported, not raised. A
# Phase 1 engineer who adds one derivation function still needs to be
# told about the ones still missing, which a one-time raise would not do.
#
# These are NOT lost: each one is copied into `Deployment` as a declared
# setting and read straight back by `_parse_intake_settings`. The name is
# "not yet derived", not "dropped".
NOT_YET_DERIVED_SETTINGS = DERIVED_SETTINGS - DERIVABLE_SETTINGS

# Back-compat alias: earlier revisions stripped these, hence the old name.
UNDERIVABLE_STRIPPED_SETTINGS = NOT_YET_DERIVED_SETTINGS


# `Settings`' column-A values that are section banners or repeated
# sub-headers rather than settings, and so are never emitted as name/value
# pairs.
_SETTINGS_STRUCTURAL_ROWS = {
    "general", "air deployment", "network", "management", "telemetry",
    "advanced", "versions", "setting", "switch function",
}


def _settings_pairs(legacy_wb):
    ws = legacy_wb["Settings"]
    pairs = []
    for r in range(1, ws.max_row + 1):
        name = ws.cell(r, 1).value
        if name is None:
            continue                          # gap row
        name = str(name).strip()
        if name.lower() in ("setting", "switch function"):
            continue                          # column header, not a section
        if name.lower() in _SETTINGS_STRUCTURAL_ROWS:
            # A section banner (GENERAL / NETWORK / ...). KEEP it: it is what
            # gives `Deployment` its structure, and dropping it flattened the
            # sheet into one undifferentiated list. `read_deployment` skips
            # these by name, so carrying them costs nothing on the read side.
            pairs.append((name, None))
            continue
        if name in DERIVABLE_SETTINGS:
            continue                          # now a consequence of the data
        if name in DROPPED_SETTINGS:
            continue                          # inert — see DROPPED_SETTINGS
        pairs.append((name, ws.cell(r, 2).value))
    return pairs


def _air_only_pairs(legacy_wb):
    """Version -> Air image rows, plus the Air management subnet row."""
    # The parser itself treats this sheet as optional (`new_format =
    # 'Air_Only' in wb.sheetnames`), so a legacy workbook without one is
    # valid input. Reading it unconditionally turned that into a raw
    # KeyError -- the same failure the `Reference` guard above exists to
    # prevent. The frozen legacy fixtures all have this sheet, so they
    # alone would not exercise its absence.
    if "Air_Only" not in legacy_wb.sheetnames:
        return []
    ws = legacy_wb["Air_Only"]
    pairs = []
    for r in range(2, ws.max_row + 1):        # row 1 is the header
        name = ws.cell(r, 1).value
        if name is None:
            continue
        pairs.append((str(name).strip(), ws.cell(r, 2).value))
    return pairs




def _convert_deployment(legacy_wb, out_wb):
    dst = out_wb.create_sheet("Deployment")

    row = 1
    for note in DEPLOYMENT_NOTES:
        dst.cell(row, 1, note)
        row += 1
    row += 1

    header_row = row
    dst.cell(header_row, 1, "Setting")
    dst.cell(header_row, 2, "Value")

    row = header_row + 1
    for name, value in _settings_pairs(legacy_wb):
        dst.cell(row, 1, name)
        dst.cell(row, 2, value)
        row += 1

    row += 1                                  # gap — not a section terminator
    # A real section banner, matching the GENERAL / NETWORK / ... rows above,
    # so it folds into the same Setting/Value structure and gets the same
    # styling -- rather than floating above the sheet as a `#` comment.
    dst.cell(row, 1, "AIR DEPLOYMENT")
    row += 1
    for name, value in _air_only_pairs(legacy_wb):
        dst.cell(row, 1, name)
        dst.cell(row, 2, value)
        row += 1
    return dst


# --- Orchestration --------------------------------------------------------




def _sheet_has_content(ws):
    """True if any row below the sheet's HEADER is real data.

    Two things are deliberately not counted:

    `#`-prefixed rows are the sheet's own instructions ("HOW TO USE -- delete
    these rows before filling in"), which every shipped Custom_Config carries.

    And the header itself may not be row 1: the override sheets allow a title
    row above it. Treating everything below row 1 as data classified such a
    sheet as populated and kept it, defeating ADR-0064 D6. So find the header
    -- the first non-`#` row with two or more filled cells -- and look only
    after it.
    """
    header = None
    for row in ws.iter_rows():
        values = [c.value for c in row if c.value not in (None, "")]
        if not values or str(values[0]).lstrip().startswith("#"):
            continue
        if header is None and len(values) >= 2:
            header = row[0].row
            continue
        if header is not None and row[0].row > header:
            return True
    return False


def _carry_override_sheets(legacy_wb, out_wb, legacy_path=None):
    """Copy the optional ERA override sheets across, unless they are empty.

    ADR-0064 D6 stops shipping the five override sheets: they are header-only
    in every shipped workbook, so carrying them adds blank tabs an OEM has to
    scroll past. Dropping them unconditionally would be data loss, though --
    ADR-0030's override still works and a user may have filled one in. So the
    rule is by content, not by name: a header-only sheet is dropped, a
    populated one is carried unchanged.

    `Rack Elevations` and `High Level BOM` ride the same rule. We never author
    them, but a user who filled one in would otherwise lose it silently on
    conversion -- the exact failure this function already guards against.
    """
    carried = []
    # Re-read WITHOUT `data_only` so a user's formulas survive: the main
    # conversion needs cached values and therefore opened the file with
    # `data_only=True`, which replaces every formula with its last result.
    formula_wb = None
    if legacy_path is not None:
        try:
            formula_wb = openpyxl.load_workbook(legacy_path, data_only=False)
        except Exception:
            formula_wb = None            # fall back to the flattened copy
    for name in CARRY_IF_POPULATED_SHEETS:
        if name in legacy_wb.sheetnames and _sheet_has_content(legacy_wb[name]):
            source = legacy_wb
            if formula_wb is not None and name in formula_wb.sheetnames:
                source = formula_wb
            _copy_sheet_verbatim(source[name], out_wb, name)
            carried.append(name)
    return carried


def _add_derived_sheet(legacy_wb, out_wb):
    """A read-only `Derived` tab: what the tool worked out, and from where.

    Visibility only -- nothing reads this sheet back. It exists so a reviewer
    can see WHY a value is absent from `Deployment` without running the
    parser, which is the whole argument for deriving rather than declaring.
    """
    from intake_derive import derive_convergence, derive_gpu_planes

    ws = out_wb.create_sheet("Derived")
    ws.append(["Setting", "Derived value", "Derived from"])

    links = []
    if "Wire Map" in legacy_wb.sheetnames:
        src = legacy_wb["Wire Map"]
        cols = _header_index(src)
        a = cols.get("System Name (A)")
        z = cols.get("System Name (B)")
        for r in range(2, src.max_row + 1):
            name_a = src.cell(r, a).value if a else None
            if not name_a:
                continue
            links.append({
                "system_name_a": name_a,
                "system_name_z": src.cell(r, z).value if z else None,
            })

    if links:
        rows = [
            ("gpu_planes", derive_gpu_planes(links),
             "Wiremap: count of distinct g(s)l-planeN- system names"),
            ("convergence", derive_convergence(links),
             "Wiremap: presence of GPU-plane switches"),
        ]
    else:
        rows = [("gpu_planes", "n/a", "no Wire Map sheet to derive from"),
                ("convergence", "n/a", "no Wire Map sheet to derive from")]

    for name, value, source in rows:
        ws.append([name, value, source])

    ws.append([])
    ws.append(["These values are computed from the data and are deliberately "
               "absent from Deployment."])
    ws.append(["Editing them here has no effect -- this sheet is never read "
               "back. Change the wiremap instead."])
    return ws


def _apply_styling(out_wb):
    """Delegates: the styling is shared with the generator."""
    intake_style.style_intake_workbook(out_wb)
        # Override sheets keep the legacy workbook's own look -- they are
        # carried verbatim and have no template equivalent.


def convert(legacy_path, out_path):
    """Convert the legacy workbook at `legacy_path` to the intake form,
    writing the result to `out_path`."""
    print(f"WARNING: {DEPRECATION}", file=sys.stderr)
    if NOT_YET_DERIVED_SETTINGS:
        print(
            f"NOTE: {len(NOT_YET_DERIVED_SETTINGS)} settings are carried as "
            "DECLARED values in the Deployment sheet because no derivation "
            "exists for them yet: "
            f"{', '.join(sorted(NOT_YET_DERIVED_SETTINGS))}. They are "
            "preserved, not dropped. Deriving them is Phase 1 work.",
            file=sys.stderr)

    legacy_wb = openpyxl.load_workbook(legacy_path, data_only=True)

    # Converting an already-converted workbook is an easy mistake -- running
    # `make convert-workbook` twice, or pointing it at the output. Say so,
    # rather than dying on `legacy_wb["Wire Map"]` with a raw KeyError three
    # frames down. Conversion is one-way; there is no intake -> legacy path.
    if ("Wiremap" in legacy_wb.sheetnames
            and "Deployment" in legacy_wb.sheetnames):
        raise SystemExit(
            f"\u274c {legacy_path}: this is already an intake-form workbook "
            "(ADR-0064) -- there is nothing to convert. `convert_workbook` "
            "goes legacy -> intake only. Point it at the legacy workbook, or "
            "use this file directly: `make generate` accepts the intake form.")
    out_wb = openpyxl.Workbook()
    out_wb.remove(out_wb.active)

    # The frozen legacy workbooks carried a `Reference` sheet, but a
    # hand-authored or edited legacy workbook is not guaranteed to. Guard
    # rather than let a customer workbook without one hit a raw KeyError
    # over documentation content that isn't load-bearing data.
    if "Reference" in legacy_wb.sheetnames:
        _copy_sheet_verbatim(legacy_wb["Reference"], out_wb, "Read Me")
    else:
        out_wb.create_sheet("Read Me")
        print(f"WARNING: {legacy_path}: no 'Reference' sheet to copy into "
              "'Read Me' -- leaving 'Read Me' empty.", file=sys.stderr)
    _convert_wiremap(legacy_wb, out_wb)
    _convert_network_data(legacy_wb, out_wb)
    _convert_nodes(legacy_wb, out_wb)
    _convert_deployment(legacy_wb, out_wb)
    _add_derived_sheet(legacy_wb, out_wb)
    _carry_override_sheets(legacy_wb, out_wb, legacy_path)

    _apply_styling(out_wb)
    out_wb.save(out_path)


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/convert_workbook.py <legacy.xlsx> "
              "<intake.xlsx>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
