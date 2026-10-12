#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Read a shipped workbook's data without knowing its sheet layout.

The shipped workbooks are the intake form (ADR-0064). Tests that want "the
VLANs" or "the settings" previously opened `VLANs & Profiles` or `Settings`
directly, so the layout was restated in 27 files and every one of them broke
on the format change.

These accessors read the intake sheets natively -- no legacy views -- so the
layout lives in one place. `scripts/intake_reader.py` owns the sheet-level
reading; this is the test-facing shape on top of it.
"""
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import intake_reader  # noqa: E402
from intake_layout import HOST_MGMT_INTERFACE as MGMT_INTERFACE  # noqa: E402


def _norm(value):
    return " ".join(str(value or "").split()).lower()


def vlan_rows(wb):
    """-> [{vlan, subnet, vrf, name, vni, purpose, dhcp_relay_client}]."""
    ws = wb["Network Data"]
    cols = intake_reader.column_map(ws)
    want = {"vlan": "vlan", "ip subnet": "subnet", "vrf": "vrf",
            "fabric name": "name", "vni(d)": "vni", "use": "purpose",
            "dhcp relay client": "dhcp_relay_client"}
    header = intake_reader.header_row(ws)
    out = []
    for r in range(header + 1, ws.max_row + 1):
        row = {key: ws.cell(r, cols[name]).value
               for name, key in want.items() if name in cols}
        if row.get("vlan") in (None, ""):
            break                      # the VLAN table ends before the stacked sections
        out.append(row)
    return out


def settings(wb):
    """-> {name: value} from `Deployment`, section banners skipped."""
    return intake_reader.read_deployment(wb["Deployment"])


def wiremap_rows(wb):
    """-> [{a_name, a_port, z_name, z_port, profile, display_in_air}]."""
    ws = wb["Wiremap"]
    cols = intake_reader.column_map(ws)
    want = {"system name (a)": "a_name", "port (a)": "a_port",
            "system name (z)": "z_name", "port (z)": "z_port",
            "network profile": "profile", "display in air": "display_in_air",
            "cable split (a)": "a_split", "cable split (z)": "z_split"}
    header = intake_reader.header_row(ws)
    out = []
    for r in range(header + 1, ws.max_row + 1):
        row = {key: ws.cell(r, cols[name]).value
               for name, key in want.items() if name in cols}
        if not row.get("a_name"):
            continue
        out.append(row)
    return out


def node_rows(wb):
    """-> [{name, function, type, mgmt_ip, ...}] across Switch Data + Host Data.

    One list, because the legacy `Nodes` tab was one list and the split into
    switches and hosts is a presentation choice, not a change of meaning.
    """
    out = []
    for sheet, name_col, fn_col in (("Switch Data", "name", "function"),
                                    ("Host Data", "system name", "function")):
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        cols = intake_reader.column_map(ws)
        header = intake_reader.header_row(ws)
        for r in range(header + 1, ws.max_row + 1):
            name = ws.cell(r, cols[name_col]).value if name_col in cols else None
            if not name:
                continue
            row = {"name": name,
                   "function": ws.cell(r, cols[fn_col]).value if fn_col in cols else None,
                   "is_switch": sheet == "Switch Data"}
            for label, key in (("mgmt ip", "mgmt_ip"), ("ip", "mgmt_ip"),
                               ("type", "type"), ("oob vlan", "oob_vlan"),
                               ("enabled", "enabled"), ("ztp", "ztp"),
                               ("asn", "asn"), ("loopback ip", "loopback_ip")):
                if label in cols:
                    row.setdefault(key, ws.cell(r, cols[label]).value)
            out.append(row)
    return out


def set_vlan_subnet(wb, want_vrf, new_subnet):
    """Move the first VLAN in `want_vrf` onto `new_subnet`. -> its VLAN id.

    Negative tests need to break a workbook on purpose, which means writing as
    well as reading. Both live here so a layout change lands in one file
    instead of every test that doctors a workbook.
    """
    ws = wb["Network Data"]
    cols = intake_reader.column_map(ws)
    header = intake_reader.header_row(ws)
    for r in range(header + 1, ws.max_row + 1):
        vlan = ws.cell(r, cols["vlan"]).value
        if vlan in (None, ""):
            break
        if _norm(ws.cell(r, cols["vrf"]).value).upper() == str(want_vrf).upper():
            ws.cell(r, cols["ip subnet"]).value = new_subnet
            return vlan
    return None


def retag_first_vlan(wb, want_vrf, new_vrf, new_subnet):
    """Retag the first VLAN in `want_vrf` onto `new_vrf` / `new_subnet`.

    -> True if one was retagged. Negative tests use this to invent a VRF the
    tool has never seen, or to move a VLAN between routing domains.
    """
    ws = wb["Network Data"]
    cols = intake_reader.column_map(ws)
    header = intake_reader.header_row(ws)
    for r in range(header + 1, ws.max_row + 1):
        if ws.cell(r, cols["vlan"]).value in (None, ""):
            break
        if _norm(ws.cell(r, cols["vrf"]).value).upper() == str(want_vrf).upper():
            ws.cell(r, cols["vrf"]).value = new_vrf
            ws.cell(r, cols["ip subnet"]).value = new_subnet
            return True
    return False


def derived(wb):
    """-> {setting: value} from the read-only `Derived` sheet.

    ADR-0064 D3 makes topology settings derived rather than declared, so
    `gpu_planes` and `convergence` are NOT in `Deployment`. Reading them from
    settings returns nothing and a `or 1` fallback then silently answers
    "one plane" for a dual-plane fabric.
    """
    if "Derived" not in wb.sheetnames:
        return {}
    ws = wb["Derived"]
    out = {}
    for r in range(2, ws.max_row + 1):
        name, value = ws.cell(r, 1).value, ws.cell(r, 2).value
        if name and not str(name).startswith("These values"):
            out[str(name).strip()] = value
    return out


def rename_node(wb, old, new):
    """Rename a node everywhere it is named. -> number of cells rewritten.

    A node's name appears on `Wiremap` (both endpoints) and on whichever of
    `Switch Data` / `Host Data` owns it. Renaming one and not the other leaves
    a workbook that is broken in a way the test did not intend.
    """
    hits = 0
    ws = wb["Wiremap"]
    cols = intake_reader.column_map(ws)
    header = intake_reader.header_row(ws)
    for label in ("system name (a)", "system name (z)"):
        if label not in cols:
            continue
        for r in range(header + 1, ws.max_row + 1):
            if str(ws.cell(r, cols[label]).value or "").strip() == old:
                ws.cell(r, cols[label]).value = new
                hits += 1
    for sheet, label in (("Switch Data", "name"), ("Host Data", "system name")):
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        cols = intake_reader.column_map(ws)
        if label not in cols:
            continue
        header = intake_reader.header_row(ws)
        for r in range(header + 1, ws.max_row + 1):
            if str(ws.cell(r, cols[label]).value or "").strip() == old:
                ws.cell(r, cols[label]).value = new
                hits += 1
    return hits


def set_setting(wb, name, value):
    """Set a `Deployment` setting, inserting it below the header if absent."""
    ws = wb["Deployment"]
    want = _norm(name)
    for r in range(1, ws.max_row + 1):
        if _norm(ws.cell(r, 1).value) == want:
            ws.cell(r, 2).value = value
            return r
    header = next((r for r in range(1, ws.max_row + 1)
                   if _norm(ws.cell(r, 1).value) == "setting"), 1)
    ws.insert_rows(header + 1)
    ws.cell(header + 1, 1).value = name
    ws.cell(header + 1, 2).value = value
    return header + 1


def set_vlan_network(wb, want_vrf, subnet, gateway):
    """Move every VLAN in `want_vrf` onto `subnet`/`gateway`. -> rows changed."""
    ws = wb["Network Data"]
    cols = intake_reader.column_map(ws)
    header = intake_reader.header_row(ws)
    hits = 0
    for r in range(header + 1, ws.max_row + 1):
        if ws.cell(r, cols["vlan"]).value in (None, ""):
            break
        if _norm(ws.cell(r, cols["vrf"]).value).upper() == str(want_vrf).upper():
            ws.cell(r, cols["ip subnet"]).value = subnet
            ws.cell(r, cols["gateway addr"]).value = gateway
            hits += 1
    return hits


def set_node_mgmt_ip(wb, name, ip):
    """Set one node's management address. -> True if the node was found.

    Switches carry it as `Mgmt IP` on `Switch Data`, hosts as `IP` on
    `Host Data`; the caller should not have to know which a name is. A host
    may have a row per physical interface, so the management row is picked by
    interface rather than by being first.
    """
    for sheet, name_col, ip_col in (("Switch Data", "name", "mgmt ip"),
                                    ("Host Data", "system name", "ip")):
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        cols = intake_reader.column_map(ws)
        if name_col not in cols or ip_col not in cols:
            continue
        header = intake_reader.header_row(ws)
        iface = cols.get("physical interface")
        first = None
        for r in range(header + 1, ws.max_row + 1):
            if str(ws.cell(r, cols[name_col]).value or "").strip() != name:
                continue
            first = first or r
            if iface is None or _norm(ws.cell(r, iface).value) == MGMT_INTERFACE:
                ws.cell(r, cols[ip_col]).value = ip
                return True
        if first:
            ws.cell(first, cols[ip_col]).value = ip
            return True
    return False


def sheet_table(wb, name):
    """-> (ws, {normalised header: column}, first data row) for a sheet.

    For tests that mutate one named column and need the cells, not dicts.
    Only the header geometry -- banded vs plain -- is shared; the column name
    is the test's own business.
    """
    ws = wb[name]
    return ws, intake_reader.column_map(ws), intake_reader.header_row(ws) + 1


def set_loopback_ip(wb, switch, value):
    """Override one switch's loopback address. -> True if it was found."""
    ws, cols, first = sheet_table(wb, "Switch Data")
    for r in range(first, ws.max_row + 1):
        if str(ws.cell(r, cols["name"]).value or "").strip() == switch:
            ws.cell(r, cols["loopback ip"]).value = value
            return True
    return False


def section_table(wb, sheet, title):
    """-> (ws, {normalised header: column}, first data row) for a stacked section.

    `Network Data` carries the VLAN table plus `VRFs`, `Port Profiles` and
    `DHCP Relay` stacked below it, each under its own banner and header row.
    """
    ws = wb[sheet]
    start = intake_reader.find_section(ws, title)
    if start is None:
        raise KeyError(f"{sheet}: no {title!r} section")
    cols = {_norm(ws.cell(start + 1, c).value): c
            for c in range(1, ws.max_column + 1)
            if ws.cell(start + 1, c).value}
    return ws, cols, start + 2


def port_profile_rows(wb):
    """-> [{normalised header: value}] for the Port Profiles section."""
    ws, cols, first = section_table(wb, "Network Data", "Port Profiles")
    out = []
    for r in range(first, ws.max_row + 1):
        if ws.cell(r, cols["profile"]).value is None:
            break
        out.append({name: ws.cell(r, c).value for name, c in cols.items()})
    return out


def port_profile_row(wb, profile):
    """-> (ws, cols, row) for one Port Profiles entry, or raise."""
    ws, cols, first = section_table(wb, "Network Data", "Port Profiles")
    for r in range(first, ws.max_row + 1):
        name = ws.cell(r, cols["profile"]).value
        if name is None:
            break
        if _norm(name) == _norm(profile):
            return ws, cols, r
    raise KeyError(f"no {profile!r} port profile")


def add_vlan(wb, **fields):
    """Append a row to the VLAN table on `Network Data`. -> its row.

    `fields` are keyed by normalised header, e.g. `vlan=201, vrf="OOB"`.
    """
    ws = wb["Network Data"]
    cols = intake_reader.column_map(ws)
    header = intake_reader.header_row(ws)
    last = header
    while ws.cell(last + 1, cols["vlan"]).value not in (None, ""):
        last += 1
    ws.insert_rows(last + 1)
    for name, value in fields.items():
        ws.cell(last + 1, cols[_norm(name)]).value = value
    return last + 1


def set_node_oob_vlan(wb, name, vlan):
    """Move one node onto a different OOB VLAN. -> True if it was found."""
    for sheet, name_col in (("Switch Data", "name"), ("Host Data", "system name")):
        if sheet not in wb.sheetnames:
            continue
        ws, cols, first = sheet_table(wb, sheet)
        if name_col not in cols or "oob vlan" not in cols:
            continue
        hit = False
        for r in range(first, ws.max_row + 1):
            if str(ws.cell(r, cols[name_col]).value or "").strip() == name:
                ws.cell(r, cols["oob vlan"]).value = vlan
                hit = True
        if hit:
            return True
    return False


def add_port_profile(wb, **fields):
    """Insert a Port Profiles row at the top of the section. -> its row."""
    ws, cols, first = section_table(wb, "Network Data", "Port Profiles")
    ws.insert_rows(first)
    for name, value in fields.items():
        ws.cell(first, cols[_norm(name)]).value = value
    return first


def add_host(wb, **fields):
    """Append a row to `Host Data`. -> its row."""
    ws, cols, _first = sheet_table(wb, "Host Data")
    r = ws.max_row + 1
    for name, value in fields.items():
        ws.cell(r, cols[_norm(name)]).value = value
    return r


def add_wiremap_row(wb, **fields):
    """Append a link to `Wiremap`. -> its row."""
    ws, cols, _first = sheet_table(wb, "Wiremap")
    r = ws.max_row + 1
    for name, value in fields.items():
        ws.cell(r, cols[_norm(name)]).value = value
    return r


def vlan_row(wb, want_vrf):
    """-> (ws, cols, row) for the first VLAN in `want_vrf`, or raise."""
    ws = wb["Network Data"]
    cols = intake_reader.column_map(ws)
    header = intake_reader.header_row(ws)
    for r in range(header + 1, ws.max_row + 1):
        if ws.cell(r, cols["vlan"]).value in (None, ""):
            break
        if _norm(ws.cell(r, cols["vrf"]).value).upper() == str(want_vrf).upper():
            return ws, cols, r
    raise KeyError(f"no VLAN with VRF {want_vrf!r}")


def set_switch_asn(wb, switch, asn):
    """Override one switch's BGP ASN. -> True if it was found."""
    ws, cols, first = sheet_table(wb, "Switch Data")
    for r in range(first, ws.max_row + 1):
        if str(ws.cell(r, cols["name"]).value or "").strip() == switch:
            ws.cell(r, cols["asn"]).value = asn
            return True
    return False
