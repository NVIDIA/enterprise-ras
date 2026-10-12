#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""The intake form's layout: sheet names, column order, section titles.

Owned here rather than in `convert_workbook.py` because that converter is
transitional and is removed at nc-v10 (ADR-0064 decision 2) -- the layout
outlives it. Two producers share this module: the converter, which fills the
layout from a legacy workbook, and `generate_arch_excel.py`, which fills it
from the arch models. A second copy of these constants would drift, and the
sunset would delete the surviving one.

`scripts/intake_reader.py` is the read-side counterpart; this is the write
side. Changing a header here changes what both producers emit -- check the
reader's `column_map` / `read_section` callers before editing.
"""

from intake_reader import column_map, header_row

# Row 1 (group labels) / row 2 (real headers), 23 columns — mirrors the
# shipped intake template (see tests/intake_fixtures.WIREMAP_HEADERS,
# Task 1).
WIREMAP_HEADERS = [
    "DC Location (A)", "Rack (A)", "RU (A)", "System Name (A)",
    "Interface Type (A)", "Port (A)", "Transceiver (A)", "Port Side (A)",
    "Cable Split (A)",
    "DC Location (Z)", "Rack (Z)", "RU (Z)", "System Name (Z)",
    "Interface Type (Z)", "Port (Z)", "Transceiver (Z)", "Port Side (Z)",
    "Cable Split (Z)",
    "Network Profile", "Cable Length (m)", "Cable Type", "Cable SKU",
    "Display in Air",
]


# Legacy `Wire Map` column name -> intake `Wiremap` column name. Physical/
# procurement columns the legacy sheet never carried (DC Location, Rack,
# RU, Interface Type, Transceiver, Cable Length/Type/SKU) are intentionally
# absent here and stay blank in the output.
WIREMAP_COLUMN_MAP = {
    "Display in Air": "Display in Air",
    "System Name (A)": "System Name (A)",
    "Port (A)": "Port (A)",
    "Port Side (A)": "Port Side (A)",
    "Cable Split (A)": "Cable Split (A)",
    "System Name (B)": "System Name (Z)",
    "Port (B)": "Port (Z)",
    "Port Side (B)": "Port Side (Z)",
    "Cable Split (B)": "Cable Split (Z)",
    "Network Profile": "Network Profile",
}


# The template's main-table columns, verified against the actual intake
# form template (2026-09-08 review) — not our legacy `VLANs` names.
NETWORK_DATA_HEADERS = [
    "Fabric Name", "Use", "VLAN", "VNI(D)", "VRF", "IP Subnet",
    "Gateway Addr", "Comments", "DHCP Relay Client",
]


# Legacy `VLANs` section column (normalised) -> template column name.
# `Comments` has no legacy source and is always blank.
_NETWORK_DATA_VLAN_COLUMN_MAP = {
    "name": "Fabric Name",
    "purpose": "Use",
    "vlan id": "VLAN",
    "vni": "VNI(D)",
    "vrf": "VRF",
    "subnet": "IP Subnet",
    "gateway": "Gateway Addr",
    "dhcp relay client": "DHCP Relay Client",
}


# Stacked sub-tables the legacy sheet also carries. `VRFs` and `DHCP Relay`
# are the template's own stacked sections (design doc); `Port Profiles` is
# not named as a template section, but nothing calls for dropping it, so
# it is preserved verbatim rather than invented or discarded.
_NETWORK_DATA_VERBATIM_SECTIONS = ["VRFs", "Port Profiles", "DHCP Relay"]


# The template's own 18 Switch Data columns, verified against the actual
# intake form template (2026-09-08 review) — not our legacy names.
SWITCH_DATA_TEMPLATE_HEADERS = [
    "Function", "Name", "ZTP MAC Address", "Mgmt IP", "Mgmt Gateway",
    "Loopback IP", "Router-ID", "ASN",
    "OOB lo", "INBAND (N-S) lo", "EXIT lo", "GPU lo", "STORAGE lo",
    "OOB in", "CPU (N-S) int", "Support int", "Storage int",
    "GPU (E-W) int",
]


# Row-1 banded group labels over the template columns above (1-based start
# column -> label). `intake_reader.header_row()` detects the banded header
# by these exact labels, so this must match its `_GROUP_LABELS` set.
# Column-to-group assignment verified against the actual template file
# (2026-09-08 review): `ZTP MAC Address` is identity, not an address, so it
# sits under `Switch`; `Loopback IP` is an address, so it sits under
# `Switch IP's` rather than `L3`.
SWITCH_DATA_GROUPS = [
    (1, "Switch"),          # Function, Name, ZTP MAC Address
    (4, "Switch IP's"),     # Mgmt IP, Mgmt Gateway, Loopback IP
    (7, "L3"),              # Router-ID, ASN, {OOB,INBAND,EXIT,GPU,STORAGE} lo
    (14, "L2"),             # OOB in, CPU (N-S) int, Support int, Storage int, GPU (E-W) int
]


# ERA extension columns: legacy `Nodes`/`Loopbacks & ASNs` fields with no
# home in the template's 18 columns. Kept under their legacy names and
# appended AFTER the template's own columns — they are ours, not the
# standard's.
SWITCH_DATA_EXTENSION_HEADERS = ["OOB VLAN", "Prefix", "ZTP", "Enabled", "Notes"]


SWITCH_DATA_HEADERS = SWITCH_DATA_TEMPLATE_HEADERS + SWITCH_DATA_EXTENSION_HEADERS


# Host Data's base standard columns (7), per the intake form spec.
HOST_DATA_BASE_HEADERS = [
    "System Name", "Physical Interface", "Logical Interface", "IP",
    "NICOSName", "Mac Address", "Profile",
]


# ERA extension columns, appended after the standard seven and keeping
# their legacy `Nodes` header names. Prefix/Gateway drive management addressing and Enabled gates
# Air-only devices, so dropping them changes generated configs. A
# conformant reader of the base standard ignores columns it does not
# recognise.
HOST_DATA_EXTENSION_HEADERS = [
    "Function", "Type", "Prefix", "Gateway", "ZTP", "Enabled", "OOB VLAN",
    "Notes",
]


HOST_DATA_HEADERS = HOST_DATA_BASE_HEADERS + HOST_DATA_EXTENSION_HEADERS


# Orientation for whoever opens the converted workbook. Names the optional
# sheets explicitly -- they are easy to miss, and the whole point of carrying
# them across is that an operator can keep using them. Points at the Excel
# guide rather than the ADR: the ADR is an internal decision record and does
# not ship, so a public workbook must not send a reader to it.
DEPLOYMENT_NOTES = [
    "# Deployment settings. One setting per row: name in column A, value in "
    "column B.",
    "#",
    "# Two settings are NOT listed here: gpu_planes and convergence. They are "
    "derived",
    "# from the wiremap rather than declared, so that a declared value can "
    "never",
    "# contradict the cabling. See the read-only 'Derived' sheet for what was "
    "derived",
    "# and from what.",
    "#",
    "# Optional override sheets, carried over from your previous workbook and "
    "still",
    "# read by the tool: Route policy, Prefix lists, ACLs, Community lists, "
    "Custom_Config.",
    "# Leave them empty unless you need them. Their column layouts are "
    "documented in",
    "# docs/EXCEL_CONFIGURATION_GUIDE.md.",
]


# The five optional override sheets. They are ERA extensions with no vendor
# template equivalent, so they are carried across VERBATIM rather than
# reshaped -- their schemas are documented in EXCEL_CONFIGURATION_GUIDE.md
# and the parser reads them directly.
#
# Dropping them was a silent data-loss bug: a customer workbook with real
# ACLs or route policy converted to a workbook with none, no warning, and
# the loss only visible by diffing sheet lists. They are nearly empty in the
# shipped workbooks, which is exactly why it went unnoticed.
OVERRIDE_SHEETS = [
    "Route policy", "Prefix lists", "ACLs", "Community lists",
    "Custom_Config",
]


# Vendor-template sheets we never author. Nothing in the arch models describes
# rack elevations or a BOM, so generating them would only add blank tabs --
# ADR-0064 D5 originally said to ship them empty; that was reversed, see the
# ADR. They are still CARRIED when a user's own workbook has filled one in,
# under the same content rule as the override sheets: we ignore empty sheets,
# we do not delete someone's data.
CARRY_IF_POPULATED_SHEETS = OVERRIDE_SHEETS + ["Rack Elevations", "High Level BOM"]


# The OOB management NIC every host's `IP` column refers to. Named rather than
# left blank because an address with no interface beside it reads as "we did
# not know" -- and we do: the server templates exclude `eth0` from bonding
# precisely because it is the management interface, and every switch sets
# `nv set interface eth0 vrf mgmt`. Only rows that actually carry an IP get
# it; the rest stay blank, since their interfaces belong in the completed
# workbook, not the blank form.
HOST_MGMT_INTERFACE = "eth0"


def host_row_groups(ws):
    """Group `Host Data` rows by host into `(mgmt_row, declared_rows)`.

    `Host Data` is one row per INTERFACE. The management row is the one whose
    `Logical Interface` is `eth0` -- or blank, for the one-row-per-host shape
    the blank form ships with. Every other row is a data-plane interface
    (`bond0`, `bond1`, `ethN`); when its `IP` cell is filled it is a declared
    address (ADR-0034). Rows without a `System Name` are ignored.

    Returns an ordered dict ``{system_name: {"mgmt": row_or_None,
    "declared": [{"row", "logical", "nic", "physical", "profile", "ip"}]}}``.
    Declared entries carry every row with a non-blank `IP` -- including a
    second `eth0`/blank-logical row, which the caller cannot bind and must
    report rather than drop; consistency between them is the caller's
    decision. A host with data-plane rows but
    no management row is reported with ``mgmt=None`` -- the caller must
    treat that as an error rather than promote a bond address to `eth0`.
    """
    cols = column_map(ws)
    name_col = cols.get("system name")
    if not name_col:
        return {}
    logical_col = cols.get("logical interface")
    ip_col = cols.get("ip")
    nic_col = cols.get("nicosname")
    phys_col = cols.get("physical interface")
    profile_col = cols.get("profile")

    def text(r, col):
        if not col:
            return ""
        return str(ws.cell(r, col).value or "").strip()

    groups = {}
    for r in range(header_row(ws) + 1, ws.max_row + 1):
        name = text(r, name_col)
        if not name:
            continue
        g = groups.setdefault(name, {"mgmt": None, "declared": []})
        logical = text(r, logical_col).lower()
        if (not logical or logical == HOST_MGMT_INTERFACE) and g["mgmt"] is None:
            g["mgmt"] = r
            continue
        ip = text(r, ip_col)
        if ip:
            g["declared"].append({
                "row": r, "logical": logical,
                "nic": text(r, nic_col).lower(),
                "physical": text(r, phys_col),
                "profile": text(r, profile_col),
                "ip": ip,
            })
    return groups


# Lives here, not in `convert_workbook`: the generator needs it to decide
# what `Deployment` carries, and that converter is deleted at nc-v10
# (ADR-0064 D2). Importing it from there would break the generator at
# exactly the moment this format becomes the only one.
# Settings that are neither derived nor declared: dropped entirely because
# they are inert. `ztp_enabled` has no consumer in the pipeline — ZTP is
# selected by which target you run, not by a Settings flag — so carrying it
# forward would relocate dead weight rather than remove it (ERA-106 /
# GitLab #80).
#
# This is now a CONVERTER concern only: the generator stopped building the
# row, so nothing it emits can be dropped here. A legacy workbook still has
# one, and conversion is where it goes. Do not delete this as dead until the
# converter does, at nc-v10.
DROPPED_SETTINGS = {
    "ztp_enabled",
}
