# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""The intake form's (Z) headers must resolve to the same logical columns
the legacy (B) headers do."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from excel_parser import _WM_HEADER_ALIASES


def test_z_side_headers_are_accepted_aliases():
    assert "system name (z)" in _WM_HEADER_ALIASES["switch_name"]
    assert "port (z)" in _WM_HEADER_ALIASES["switch_port"]
    # NOTE: the table has 9 logical names and no B-side "port side" entry.
    # Do not invent `switch_port_side` — verify against the live table.
    assert set(_WM_HEADER_ALIASES) == {
        "display_in_air", "system_role", "system_name", "nic_port",
        "port_side", "network_profile", "switch_role", "switch_name",
        "switch_port",
    }


def test_legacy_b_side_headers_still_work():
    assert "system name (b)" in _WM_HEADER_ALIASES["switch_name"]
    assert "port (b)" in _WM_HEADER_ALIASES["switch_port"]
