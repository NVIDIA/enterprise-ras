# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Every Excel cell that renders into a root-executed config is guarded.

The Settings sheet has had this protection since the 2026-06-30 security review
(`SHELL_INJECTION_PRONE_KEYS`). It covered Settings ONLY, so the other
operator-supplied surfaces that reach a template verbatim were unguarded.

This docstring used to claim the guard was already complete ("every Excel cell
that renders UNQUOTED ... is guarded"). It was not, and asserting completeness is
part of why the gap survived a later 89-finding QA audit that concluded
"Excel-to-shell injection defence is thorough and tested". Four columns on the
policy sheets were in neither `_UNQUOTED_EXCEL_CELLS` nor quoted by the template
— Route policy `Rule` (col 2) and `Set value` (col 7), Prefix lists `Max prefix
length` (col 4), and Community lists `Rule` (col 2) — so a payload in any of them
validated cleanly and landed verbatim in a config that ZTP runs as root. They are
in CASES below now, and `core_nvue_cli.j2` quotes the policy values as well, so
the guard is defence-in-depth rather than validator-only.

Do not restate this as complete. State what is covered and let CASES be the list.

Two vectors were confirmed end-to-end before this check existed:

    VRF Name        `OOB; touch /tmp/x`      -> nv set vrf OOB; touch /tmp/x ...
    Auto-Negotiate  `disabled; touch /tmp/x` -> nv set interface ... link
                                                auto-negotiate disabled; touch /tmp/x

Both execute as root on every switch that receives the config.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import workbook_access  # noqa: E402

NC = Path(__file__).resolve().parent.parent
ARCH = "2-4-3-200"
ARCHS = ["2-4-3-200", "2-4-5-800", "2-8-5-200",
         "2-8-9-400", "2-8-9-400-SP", "2-8-9-800"]
_COPY_IGNORE = shutil.ignore_patterns(
    "output", "archive", ".git", ".venv*", "__pycache__", "*.pyc",
    ".pytest_cache", ".era-secrets", "legacy",
)


def _section(ws, label):
    for r in range(1, ws.max_row + 1):
        if str(ws.cell(r, 1).value or "").strip() == label:
            return r
    raise AssertionError(f"section {label!r} not found")


# (id, locator) — locator(wb) writes the payload and returns nothing.
#
# The shipped workbook is the intake form (ADR-0064): the VLAN table and the
# stacked VRFs / Port Profiles sections live on `Network Data`, and the four
# override sheets are no longer shipped at all (D6). Injection is still a
# surface for them, because a user who needs one ADDS it -- so those cases
# create the sheet first, which is exactly the path a customer takes.
def _override(wb, sheet, header, col, value):
    ws = wb[sheet] if sheet in wb.sheetnames else wb.create_sheet(sheet)
    if ws.max_row < 1 or ws.cell(1, 1).value is None:
        for c, name in enumerate(header, start=1):
            ws.cell(1, c, name)
    ws.cell(2, col, value)


CASES = [
    ("vrf-name", lambda wb, v: wb["Network Data"].cell(
        _section(wb["Network Data"], "VRF Name") + 1, 1, v)),
    # The VLAN table's name column is `Fabric Name`, and its data starts
    # immediately under the header rather than under a section banner.
    ("vlan-name", lambda wb, v: wb["Network Data"].cell(
        _section(wb["Network Data"], "Fabric Name") + 1, 1, v)),
    ("profile-vrf", lambda wb, v: wb["Network Data"].cell(
        _section(wb["Network Data"], "Profile") + 1, 6, v)),
    ("profile-speed", lambda wb, v: wb["Network Data"].cell(
        _section(wb["Network Data"], "Profile") + 1, 8, v)),
    ("profile-autoneg", lambda wb, v: wb["Network Data"].cell(
        _section(wb["Network Data"], "Profile") + 1, 11, v)),
    ("prefix-list-name", lambda wb, v: _override(
        wb, "Prefix lists", ["Name", "Seq", "Action", "Max Len"], 1, v)),
    ("prefix-list-max-len", lambda wb, v: _override(
        wb, "Prefix lists", ["Name", "Seq", "Action", "Max Len"], 4, v)),
    ("route-map-name", lambda wb, v: _override(
        wb, "Route policy", ["Name", "Rule", "Seq", "Action", "Match", "Type", "Set"], 1, v)),
    ("route-map-rule", lambda wb, v: _override(
        wb, "Route policy", ["Name", "Rule", "Seq", "Action", "Match", "Type", "Set"], 2, v)),
    ("route-map-set-value", lambda wb, v: _override(
        wb, "Route policy", ["Name", "Rule", "Seq", "Action", "Match", "Type", "Set"], 7, v)),
    ("community-list-name", lambda wb, v: _override(
        wb, "Community lists", ["Name", "Rule"], 1, v)),
    ("community-list-rule", lambda wb, v: _override(
        wb, "Community lists", ["Name", "Rule"], 2, v)),
    ("acl-name", lambda wb, v: _override(wb, "ACLs", ["Name"], 1, v)),
]

@pytest.mark.parametrize("name,writer", CASES, ids=[c[0] for c in CASES])
@pytest.mark.parametrize("payload", ["evil; touch /tmp/era_pwned",
                                     "evil`id`", "evil$(id)", "evil|nc"])
def test_shell_metacharacters_are_rejected(name, writer, payload, tmp_path):
    src = NC / "input" / ARCH / "default" / f"{ARCH}.xlsx"
    if not src.exists():
        pytest.skip(f"no default workbook for {ARCH}")
    xlsx = tmp_path / f"{ARCH}.xlsx"
    shutil.copy(src, xlsx)
    wb = openpyxl.load_workbook(xlsx)
    writer(wb, payload)
    wb.save(xlsx)

    r = subprocess.run([sys.executable, "scripts/validate_excel.py", str(xlsx)],
                       cwd=NC, capture_output=True, text=True)
    out = r.stdout + r.stderr
    assert r.returncode != 0, f"{name}: {payload!r} validated cleanly"
    assert "command injection" in out, out[-600:]


@pytest.mark.parametrize("arch", ARCHS)
@pytest.mark.parametrize("site", ["default", "largescale"])
def test_shipped_workbooks_have_no_false_positives(arch, site):
    """A guard that fires on legitimate data would be worse than none.

    Real workbooks carry values with `/`, `:`, `,`, `.`, `-` and spaces
    (subnets, communities, port lists), all of which must remain acceptable.
    """
    xlsx = NC / "input" / arch / site / f"{arch}.xlsx"
    if not xlsx.exists():
        pytest.skip(f"no {site} workbook for {arch}")
    r = subprocess.run([sys.executable, "scripts/validate_excel.py", str(xlsx)],
                       cwd=NC, capture_output=True, text=True)
    assert "command injection" not in (r.stdout + r.stderr), (
        f"{arch}/{site}: injection guard fired on a shipped workbook")


# --- node / system names ----------------------------------------------------
# Names are used three ways, all of which require a hostname charset:
#   * rendered UNQUOTED as `nv set interface <bond> description <name>`;
#   * written verbatim into the generated ansible inventory/hosts;
#   * used as NVUE object names, where a space silently truncates.
# Confirmed vector: renaming a node to `su-01-node-01; touch /tmp/x` everywhere
# it is named put it in bond_descriptions and rendered as
# `nv set interface bond1s0 description su-01-node-01; touch /tmp/x`.

_NAME_PAYLOADS = [
    "su-01-node-01; touch /tmp/era_pwned",
    "su-01-node-01`id`",
    "su-01-node-01 $(id)",
    "su-01 node-01",          # a bare space truncates the NVUE description
]


def _rename_node(xlsx, new_name):
    wb = openpyxl.load_workbook(xlsx)
    assert workbook_access.rename_node(wb, "su-01-node-01", new_name), (
        "su-01-node-01 is not in the workbook; the payload would never render")
    wb.save(xlsx)


@pytest.mark.parametrize("payload", _NAME_PAYLOADS)
def test_invalid_node_names_are_rejected(payload, tmp_path):
    src = NC / "input" / ARCH / "default" / f"{ARCH}.xlsx"
    if not src.exists():
        pytest.skip(f"no default workbook for {ARCH}")
    xlsx = tmp_path / f"{ARCH}.xlsx"
    shutil.copy(src, xlsx)
    _rename_node(xlsx, payload)
    r = subprocess.run([sys.executable, "scripts/validate_excel.py", str(xlsx)],
                       cwd=NC, capture_output=True, text=True)
    out = r.stdout + r.stderr
    assert r.returncode != 0, f"{payload!r} validated cleanly"
    assert "not a valid hostname" in out, out[-600:]


def test_legitimate_hostnames_are_accepted(tmp_path):
    """Dots, hyphens and underscores are all legal in real names."""
    src = NC / "input" / ARCH / "default" / f"{ARCH}.xlsx"
    if not src.exists():
        pytest.skip(f"no default workbook for {ARCH}")
    for name in ("su-01-node-01a", "node_01", "node.example.com", "SU-01-NODE-01"):
        xlsx = tmp_path / f"{name}.xlsx"
        shutil.copy(src, xlsx)
        _rename_node(xlsx, name)
        r = subprocess.run([sys.executable, "scripts/validate_excel.py", str(xlsx)],
                           cwd=NC, capture_output=True, text=True)
        assert "not a valid hostname" not in (r.stdout + r.stderr), (
            f"legitimate hostname {name!r} was rejected")
