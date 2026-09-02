# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""`validate_air_oob_single_cable` is Air-only and must respect `deploy_in_air`.

The rule exists because Air's plain-Ubuntu nodes cannot bond two OOB links. It
reads `Display in Air`, a column whose every consumer lives in `utils.py` /
`topology_generator.py` — it reaches neither the switch configs nor the Ansible
inventory. On a physical deployment two OOB NICs per node are ordinary cabling
(host management port + separate BMC/LOM), so the warning was advice about a
simulation the operator is not building.

Observed on a submission where seven site-prefixed nodes each drew the warning
with `deploy_in_air = No`.
"""
import sys
from pathlib import Path

import openpyxl
import pytest

NC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NC / "scripts"))

import validate_excel as ve  # noqa: E402


class _Result:
    def __init__(self):
        self.warnings = []

    def warn(self, where, msg):
        self.warnings.append((where, msg))


def _sheet(node_names):
    """A real openpyxl worksheet — `build_wiremap_column_map` reads it directly,
    so a hand-rolled fake only proves the fake works."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Wire Map"
    ws.append(["Display in Air", "System Name (A)", "Port (A)", "Port Side (A)",
               "Cable Split (A)", "System Name (B)", "Port (B)", "Port Side (B)",
               "Cable Split (B)", "Network Profile"])
    for n in node_names:
        for port in ("swp1", "swp2"):
            ws.append(["Yes", n, "eth0", "", "", "oob-switch-01", port, "", "",
                       "OOB / IPMI"])
    return ws


NODES = [{"name": "site-prefixed-gpu-01", "function": "GPU", "enabled": True},
         {"name": "site-prefixed-k8s-01", "function": "K8s", "enabled": True}]


def _run(settings):
    res = _Result()
    ve.validate_air_oob_single_cable(_sheet([n["name"] for n in NODES]),
                                     NODES, res, settings)
    return res.warnings


@pytest.mark.parametrize("value", ["No", "no", "NO", "False", "0", ""])
def test_silent_when_not_deploying_in_air(value):
    assert _run({"deploy_in_air": value}) == []


@pytest.mark.parametrize("value", ["Yes", "yes", "TRUE", "1"])
def test_still_warns_when_deploying_in_air(value):
    assert len(_run({"deploy_in_air": value})) == 2


def test_absent_key_keeps_todays_behaviour():
    """Defaults to Yes, so a workbook predating the key is unchanged."""
    assert len(_run({})) == 2


def test_settings_none_keeps_todays_behaviour():
    """Callers that pass no settings must not be silently disarmed."""
    res = _Result()
    ve.validate_air_oob_single_cable(_sheet([n["name"] for n in NODES]), NODES, res)
    assert len(res.warnings) == 2


def test_remedy_text_does_not_contradict_itself():
    """The old text said 'Display=No on all but the BMC row' while the docstring
    said real-HW LOM/iLO rows are Display=No — iLO IS the BMC, so the two
    disagreed about which row survives."""
    msg = _run({"deploy_in_air": "Yes"})[0][1]
    assert "all but the BMC row" not in msg
    assert "OOB management port" in msg
    assert "deploy_in_air=No" in msg
