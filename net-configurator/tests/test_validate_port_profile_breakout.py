# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
validate_port_profiles must reject a non-numeric Breakout/Lanes cell with an
actionable error. excel_parser does a bare int() on these columns, so a
non-numeric value would otherwise crash `make generate` with an uncaught
ValueError (spiteful-OEM "garbage in -> ugly crash" path).
"""
import sys
from pathlib import Path

import openpyxl

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_excel import validate_port_profiles, ValidationResult


def _sheet(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "VLANs & Profiles"
    for r in rows:
        ws.append(r)
    return ws


HEADER = ["Profile", "Port Mode", "Breakout", "Lanes"]


def _run(profile_row):
    ws = _sheet([["Port Profiles"], HEADER, profile_row, [None]])
    result = ValidationResult()
    validate_port_profiles(ws, result)
    return result


def test_non_numeric_breakout_errors():
    result = _run(["GPU Access", "access", "4x", None])
    assert not result.ok
    assert any("Breakout" in e and "positive whole number" in e for e in result.errors)


def test_non_numeric_lanes_errors():
    result = _run(["GPU Access", "access", None, "two"])
    assert not result.ok
    assert any("Lanes" in e for e in result.errors)


def test_numeric_breakout_ok():
    result = _run(["GPU Access", "access", 4, 8])
    assert result.ok, result.errors


def test_blank_breakout_ok():
    result = _run(["GPU Access", "access", None, None])
    assert result.ok, result.errors
