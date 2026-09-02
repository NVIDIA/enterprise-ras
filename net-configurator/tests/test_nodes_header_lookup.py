# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-81: the Nodes sheet must be read by header name, never by position.

ADR-0028 inserted an `OOB VLAN` column at index 2, shifting `Type` from index 2
to index 3. `_switch_function` hardcoded `row[3] == 'switch'`, so on any
pre-ADR-0028 workbook it resolved ZERO switches and returned '' for every name.

That is worse than no check. `validate_isl_matches_arch_model` filters ISL ends
by switch function, so an empty map drops every end and the check reports
"Wire Map wires 0" against a fabric that wires 142 — a fabricated under-cabling
finding. It surfaced on an OEM 2-8-9-800 endorsement submission that had already
passed a full 5-phase validate-all with zero config drift on 25 switches.

Both column layouts must resolve identically.
"""
import sys
from pathlib import Path

import openpyxl
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_excel import _nodes_switch_functions, _switch_function  # noqa: E402

# The two schemas, and where `Type` lands in each.
PRE_ADR_0028 = ["Function", "Name", "Type", "MAC Address for ZTP",
                "Mgmt IP Address", "Prefix", "Gateway", "ZTP", "Enabled", "Notes"]
POST_ADR_0028 = ["Function", "Name", "OOB VLAN", "Type", "MAC Address for ZTP",
                 "Mgmt IP Address", "Prefix", "Gateway", "ZTP", "Enabled", "Notes"]

ROWS = [
    ("csl", "csl-01", "switch"),
    ("csl", "csl-02", "switch"),
    ("oob-switch", "oob-switch-01", "switch"),
    ("gpu", "su-01-node-01", "server"),
]


def _book(header):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Nodes"
    ws.append(header)
    oob_vlan = "OOB VLAN" in header
    for fn, name, typ in ROWS:
        row = [fn, name] + ([200] if oob_vlan else []) + [typ]
        row += [None] * (len(header) - len(row))
        ws.append(row)
    return wb


EXPECTED = {"csl-01": "csl", "csl-02": "csl", "oob-switch-01": "oob-switch"}


@pytest.mark.parametrize("label,header", [("pre-ADR-0028", PRE_ADR_0028),
                                          ("post-ADR-0028", POST_ADR_0028)])
def test_switch_functions_resolve_on_both_column_layouts(label, header):
    """Both schemas must yield the same switch->function map."""
    got = _nodes_switch_functions(_book(header))
    assert got == EXPECTED, f"{label}: resolved {got}, expected {EXPECTED}"


@pytest.mark.parametrize("label,header", [("pre-ADR-0028", PRE_ADR_0028),
                                          ("post-ADR-0028", POST_ADR_0028)])
def test_servers_are_not_classified_as_switches(label, header):
    """Only `Type == switch` rows are switches, on either layout."""
    assert "su-01-node-01" not in _nodes_switch_functions(_book(header)), label


@pytest.mark.parametrize("label,header", [("pre-ADR-0028", PRE_ADR_0028),
                                          ("post-ADR-0028", POST_ADR_0028)])
def test_switch_function_lookup_is_non_empty(label, header):
    """The regression itself: `_switch_function` returned '' for everything.

    An empty result is what let the ISL link count report 0 ends, so assert the
    lookup resolves rather than merely that the map is well-formed.
    """
    wb = _book(header)
    assert _switch_function(wb, "csl-01") == "csl", label
    assert _switch_function(wb, "oob-switch-01") == "oob-switch", label


def test_unknown_name_is_empty_string_not_error():
    assert _switch_function(_book(POST_ADR_0028), "does-not-exist") == ""


def test_missing_type_column_still_maps_names():
    """A workbook with no recognisable Type column must not resolve to nothing.

    Degrading to "classify every named row" keeps the ISL filter working; the
    silent alternative is the exact failure ERA-81 records.
    """
    header = ["Function", "Name", "Mgmt IP Address"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Nodes"
    ws.append(header)
    ws.append(["csl", "csl-01", "10.0.0.1"])
    assert _nodes_switch_functions(wb).get("csl-01") == "csl"
