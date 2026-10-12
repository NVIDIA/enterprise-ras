# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Locks in stacked sub-table handling.

The critical property: sections are found by SCANNING for their title, so
adding rows to the table above them does not break the parser. Fixed row
offsets would pass on the blank template and fail on a real workbook.
"""
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from intake_reader import find_section, read_section


def _sheet(extra_main_rows=0):
    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Network Data")
    ws["A3"] = "Fabric Name"
    ws["B3"] = "Use"
    ws["C3"] = "VLAN"
    row = 4
    for i in range(extra_main_rows):
        ws.cell(row, 1, f"fabric-{i}")
        row += 1
    row += 1                      # blank gap — NOT a terminator
    ws.cell(row, 1, "VRFs")
    ws.cell(row + 1, 1, "VRF Name")
    ws.cell(row + 1, 2, "Description")
    ws.cell(row + 2, 1, "GPU")
    ws.cell(row + 2, 2, "gpu fabric")
    return ws


def test_section_found_regardless_of_rows_above():
    assert find_section(_sheet(0), "VRFs") == 5
    assert find_section(_sheet(9), "VRFs") == 14


def test_read_section_returns_rows_below_its_header():
    rows = read_section(_sheet(9), "VRFs", ["vrf name", "description"])
    assert rows == [{"vrf name": "GPU", "description": "gpu fabric"}]


def test_missing_section_returns_none_not_an_exception():
    assert find_section(_sheet(0), "Nonexistent") is None


def _sheet_with_two_adjacent_sections():
    """Two stacked sections whose first data column both live in column A.

    This is the shape that defeats a break condition comparing the title
    cell against `values[columns[0]]`: when the section's first mapped
    column *is* column A, that comparison is really "cell == itself" and
    can never be true, so the reader never recognizes the next section's
    title row and keeps consuming rows past the boundary.
    """
    wb = openpyxl.Workbook()
    ws = wb.create_sheet("Network Data")
    ws.cell(1, 1, "VRFs")
    ws.cell(2, 1, "VRF Name")
    ws.cell(2, 2, "Description")
    ws.cell(3, 1, "GPU")
    ws.cell(3, 2, "gpu fabric")
    ws.cell(4, 1, "Storage")
    ws.cell(4, 2, "storage fabric")
    # blank gap between sections, per the template's own layout
    ws.cell(6, 1, "DHCP Relay")
    ws.cell(7, 1, "Relay IP")
    ws.cell(7, 2, "VLAN")
    ws.cell(8, 1, "10.0.0.1")
    ws.cell(8, 2, 500)
    return ws


def test_read_section_stops_before_the_next_stacked_section():
    """Locks in the fix: reading one section must never swallow the next.

    Regression test for a defective break condition that compared the
    title cell to `values[columns[0]]` — when the section's own header
    maps its first column to column A (as VRFs' "VRF Name" does here),
    that comparison is a cell against itself and is always equal, so the
    loop never breaks and swallows the next section's title, header, and
    data rows as if they belonged to the first section.
    """
    ws = _sheet_with_two_adjacent_sections()
    rows = read_section(ws, "VRFs", ["vrf name", "description"])
    assert rows == [
        {"vrf name": "GPU", "description": "gpu fabric"},
        {"vrf name": "Storage", "description": "storage fabric"},
    ]
    titles = {row["vrf name"] for row in rows}
    assert "DHCP Relay" not in titles
    assert "Relay IP" not in titles
    assert "10.0.0.1" not in titles


def test_read_section_accepts_un_normalised_column_names():
    """Caller-supplied column names are normalised like the sheet's own.

    Sheet headers go through `_norm`, so a caller passing "VRF Name" rather
    than "vrf name" matched nothing and got back zero rows -- a silent empty
    result, not an error. Every existing caller happens to pass lowercase,
    which made the contract implicit rather than safe. (Greptile P2)
    """
    import openpyxl
    from intake_reader import read_section

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["VRFs"])
    ws.append(["VRF Name", "Description"])
    ws.append(["OOB", "Out-of-Band"])
    ws.append(["GPU", "East-West"])

    lower = read_section(ws, "VRFs", ["vrf name", "description"])
    mixed = read_section(ws, "VRFs", ["VRF Name", "  Description  "])

    assert len(lower) == 2, f"baseline read failed: {lower}"
    assert mixed == lower, (
        f"un-normalised column names returned different rows: {mixed}")
