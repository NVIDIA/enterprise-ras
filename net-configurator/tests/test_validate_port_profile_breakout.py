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
    result = _run(["GPU Access", "access", 4, 2])
    assert result.ok, result.errors


def test_blank_breakout_ok():
    result = _run(["GPU Access", "access", None, None])
    assert result.ok, result.errors


# ---------------------------------------------------------------------------
# Renderable (breakout, lanes) pairs.
#
# core_nvue_cli.j2 buckets ports into 4x/2-lane, 2x/4-lane and 8x/1-lane with
# no else branch. Any other pair is dropped from the breakout section while its
# sub-ports are still emitted into `type swp` / bonds / BGP neighbors, so the
# switch rejects the config at apply time. Generation and validation both look
# clean, which is why this needs to fail HERE.
# ---------------------------------------------------------------------------

import pytest  # noqa: E402


@pytest.mark.parametrize("breakout,lanes", sorted({(2, 4), (4, 2), (8, 1)}))
def test_renderable_breakout_lane_pairs_accepted(breakout, lanes):
    result = _run(["Storage", "trunk", breakout, lanes])
    assert result.ok, result.errors


@pytest.mark.parametrize("breakout,lanes", [
    (4, 8),   # 32 lanes -- the value this test file previously asserted was OK
    (4, 4),   # 16 lanes
    (4, 1),   # 4 lanes: valid on a 400G cage, not on the SN5600 this renders for
    (2, 2),
    (8, 2),
    (2, 1),
])
def test_unrenderable_breakout_lane_pairs_rejected(breakout, lanes):
    result = _run(["Storage", "trunk", breakout, lanes])
    assert not result.ok, (
        f"breakout {breakout}x / {lanes} lanes must be rejected: the template "
        f"emits no breakout line for it and the switch fails at apply time"
    )
    assert any("not a supported combination" in e for e in result.errors), result.errors


def test_whole_port_needs_no_breakout_line():
    """breakout == 1 is 'use the whole port' -- no breakout line is correct.

    The SN2201 oob_uplink profile is 1x100G, so this must stay legal.
    """
    result = _run(["OOB Uplink", "trunk", 1, 1])
    assert result.ok, result.errors


def test_lanes_without_breakout_is_not_gated():
    """Only the PAIR is checkable; a lone Lanes value says nothing renderable."""
    result = _run(["Storage", "trunk", None, 4])
    assert result.ok, result.errors
