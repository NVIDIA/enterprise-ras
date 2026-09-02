# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Hardware-limit tests replacing architecture-specific layout ranges."""

import sys
from pathlib import Path

from openpyxl import Workbook

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_excel import ValidationResult, validate_switch_hardware_ports  # noqa: E402


HEADERS = [
    "Display in Air",
    "Function (A)",
    "System Name (A)",
    "Port (A)",
    "Port Side (A)",
    "Function (B)",
    "System Name (B)",
    "Port (B)",
    "Port Side (B)",
    "Cable Split",
    "Network Profile",
]


def _validate(row, functions):
    wb = Workbook()
    ws = wb.active
    ws.title = "Wire Map"
    ws.append(HEADERS)
    ws.append(row)
    result = ValidationResult()
    validate_switch_hardware_ports(wb, {}, functions, result)
    return result


def test_oob_access_must_use_sn2201_copper_band():
    result = _validate(
        ["Yes", "gpu", "gpu-01", "eth0", "NA", "oob-switch",
         "oob-switch-01", "swp49", "NA", "1.0", "OOB"],
        {"gpu-01": "gpu", "oob-switch-01": "oob-switch"},
    )
    assert any("SN2201 copper swp1-swp48" in error for error in result.errors)


def test_fabric_port_cannot_exceed_sn5600_parent_limit():
    result = _validate(
        ["Yes", "gpu", "gpu-01", "B3240 P1", "NA", "core",
         "core-01", "swp65s0", "NA", "1.0", "CPU/In-Band Network"],
        {"gpu-01": "gpu", "core-01": "core"},
    )
    assert any("SN5600 fabric swp1-swp64" in error for error in result.errors)


def test_valid_oob_uplink_hardware_bands_pass():
    result = _validate(
        ["Yes", "oob-switch", "oob-switch-01", "swp49", "NA", "core",
         "core-01", "swp61s0", "NA", "1.0", "OOB Uplink"],
        {"oob-switch-01": "oob-switch", "core-01": "core"},
    )
    assert not result.errors
