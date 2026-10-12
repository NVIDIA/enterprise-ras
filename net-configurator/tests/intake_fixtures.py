# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Build intake-form worksheets in memory for tests.

Mirrors the shipped template exactly: `Wiremap` and `Switch Data` carry a
two-row header (row 1 groups, row 2 real column names); `Network Data`
stacks several tables vertically with gaps between them.
"""

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


def build_wiremap_sheet(wb, rows):
    ws = wb.create_sheet("Wiremap")
    ws["A1"] = "Source"
    ws["J1"] = "Destination"
    for col, name in enumerate(WIREMAP_HEADERS, start=1):
        ws.cell(row=2, column=col, value=name)
    for r, row in enumerate(rows, start=3):
        for col, value in enumerate(row, start=1):
            ws.cell(row=r, column=col, value=value)
    return ws
