# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""H5 / GitLab #93: a `Deploy in Air = No` site never runs air-connect.

`check_air_connection` (used by `oob-setup` and `switch-ztp-deploy`) ran
`scripts/air-connect.py` whenever the Air vnode host_vars were missing or still
`CHANGE_ME` -- which on a physical site they always are. The macro now reads the
workbook's `deploy_in_air` first, so it answers before any inventory exists.

The Make cases run the real recipe in a scratch tool root whose `air-connect.py`
is a stub that records being called.
"""
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import workbook_access  # noqa: E402

NC = Path(__file__).resolve().parent.parent
ARCH = "2-4-3-200"
sys.path.insert(0, str(NC / "scripts"))
from _show_deploy_in_air import deploy_in_air  # noqa: E402


def _workbook(dst, value):
    src = NC / "input" / ARCH / "default" / f"{ARCH}.xlsx"
    wb = openpyxl.load_workbook(src)
    if value is not None:
        workbook_access.set_setting(wb, "deploy_in_air", value)
    dst.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dst)
    return dst


@pytest.mark.parametrize("value,expected", [
    ("No", False), ("no", False), ("Yes", True), (None, True)])
def test_helper_reads_the_workbook_setting(tmp_path, value, expected):
    assert deploy_in_air(_workbook(tmp_path / "w.xlsx", value)) is expected


def test_helper_defaults_to_air_when_there_is_no_workbook(tmp_path):
    assert deploy_in_air(tmp_path / "missing.xlsx") is True


def _oob_setup(tmp_path, value, corrupt=False):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for f in (NC / "scripts").iterdir():
        if f.name != "air-connect.py":
            (scripts / f.name).symlink_to(f)
    marker = tmp_path / "air-connect-called"
    (scripts / "air-connect.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('called')\n")
    wb = _workbook(tmp_path / "input" / ARCH / "default" / f"{ARCH}.xlsx", value)
    if corrupt:
        wb.write_bytes(b"not a workbook")
    stub = tmp_path / "ansible-playbook-stub"
    stub.write_text("#!/bin/bash\nexit 0\n")
    stub.chmod(0o755)
    r = subprocess.run(
        ["make", "-f", str(NC / "Makefile"), "oob-setup", f"ARCH={ARCH}", "SITE=default",
         f"ANSIBLE_PLAYBOOK={stub}"],
        cwd=tmp_path, capture_output=True, text=True, timeout=120)
    return r, marker.exists()


def test_physical_site_does_not_run_air_connect(tmp_path):
    r, called = _oob_setup(tmp_path, "No")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not called, r.stdout
    assert "skipping air-connect" in r.stdout


def test_air_site_without_connection_details_still_runs_air_connect(tmp_path):
    r, called = _oob_setup(tmp_path, "Yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert called, r.stdout


def test_unreadable_workbook_stops_before_air_connect(tmp_path):
    r, called = _oob_setup(tmp_path, "No", corrupt=True)
    assert r.returncode != 0, r.stdout + r.stderr
    assert not called, r.stdout
    assert "Cannot read 'Deploy in Air'" in r.stdout
