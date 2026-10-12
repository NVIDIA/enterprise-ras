# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""End-to-end: an explicit Loopbacks `ASN` value overrides the derived
per-node BGP ASN in the generated inventory + config, and nothing else changes.

Runs against a throwaway copy of the tool tree (never the live repo), mirroring
test_seedless_generation.py.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import workbook_access  # noqa: E402

NC = Path(__file__).resolve().parent.parent  # net-configurator/
ARCH = "2-8-9-800"
SWITCH = "oob-switch-01"
OVERRIDE = 4260394838  # base(4260394788)+50 — distinct, valid, OOB singleton

_COPY_IGNORE = shutil.ignore_patterns(
    "output", "archive", ".git", ".venv*", "__pycache__", "*.pyc",
    ".pytest_cache", ".era-secrets", "legacy",
)


def _inject_asn(xlsx: Path, switch: str, asn: int):
    """Set `switch`'s ASN, overriding just that one switch."""
    wb = openpyxl.load_workbook(xlsx)
    assert workbook_access.set_switch_asn(wb, switch, asn), f"no {switch} row"
    wb.save(xlsx)


def test_asn_override_flows_to_config(tmp_path):
    src_xlsx = NC / "input" / ARCH / "default" / f"{ARCH}.xlsx"
    if not src_xlsx.exists():
        pytest.skip(f"no committed default workbook for {ARCH}")

    dst = tmp_path / "nc"
    shutil.copytree(NC, dst, ignore=_COPY_IGNORE)
    _inject_asn(dst / "input" / ARCH / "default" / f"{ARCH}.xlsx", SWITCH, OVERRIDE)

    r = subprocess.run(
        [sys.executable, "scripts/excel_parser.py", "--arch", ARCH,
         "--site", "default", "--skip-validate"],
        cwd=dst, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"parser failed:\n{r.stderr[-2000:]}"

    # The parser generates inventory (host_vars); the NVUE .sh render is a later
    # ansible step (covered by the byte-identical make-generate gate + Air).
    hv_dir = dst / "output" / ARCH / "default" / "inventory" / "host_vars"
    hv = hv_dir / f"{SWITCH}.yml"
    assert hv.exists(), "override switch host_vars missing"
    assert f"bgp_asn: {OVERRIDE}" in hv.read_text(), \
        f"override ASN not in {SWITCH} host_vars"

    # a non-overridden OOB switch keeps its derived ASN (base+idx), not the override
    other = hv_dir / "oob-switch-02.yml"
    assert f"bgp_asn: {OVERRIDE}" not in other.read_text(), \
        "override leaked to a switch that was not overridden"
    assert "bgp_asn: 4260394790" in other.read_text(), \
        "non-overridden OOB switch lost its derived ASN"
