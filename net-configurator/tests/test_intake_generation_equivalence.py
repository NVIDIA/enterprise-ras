#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Entry points that have to keep working on an intake workbook.

The legacy-vs-intake generation comparison that used to live here is gone
with the legacy read path (ADR-0064 D1) -- there is no longer a legacy
branch to generate from. Its successor is the `generate` matrix in
.gitlab-ci.yml: all seven archs x both shipped sites, each regenerated and
diffed against the committed snapshot. That covers fourteen cells where
this covered one.

Runs the real scripts as subprocesses, so it exercises the same path the
Makefile does rather than a reconstruction of it.
"""
import subprocess
import sys
from pathlib import Path

NC = Path(__file__).resolve().parent.parent
ARCH = "2-8-9-800"
# The frozen legacy sample -- see conftest. Both tests below convert a legacy
# workbook, so one has to come from somewhere now that the shipped ones are
# the intake form.
sys.path.insert(0, str(Path(__file__).parent))
from conftest import LEGACY_SAMPLE  # noqa: E402

LEGACY_SRC = LEGACY_SAMPLE


def _run(*args):
    return subprocess.run([sys.executable, *args], cwd=NC,
                          capture_output=True, text=True)


def test_import_excel_reads_architecture_from_an_intake_workbook(tmp_path):
    """`make import` must work on an intake workbook.

    Regression: `import-excel.py` loaded the workbook through
    `load_workbook_safe`, which does not build the legacy views, so an intake
    workbook validated successfully and then failed one step later with
    "'architecture' key not found in Settings tab" -- on a file the rest of
    the pipeline handles fine. Found by a user running `make import`, not by
    this suite, because nothing here had exercised that entry point.
    """
    sys.path.insert(0, str(NC / "scripts"))
    import importlib.util

    intake = tmp_path / "intake.xlsx"
    conv = _run("scripts/convert_workbook.py", str(LEGACY_SRC), str(intake))
    assert conv.returncode == 0, conv.stderr

    spec = importlib.util.spec_from_file_location(
        "import_excel_mod", NC / "scripts" / "import-excel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    settings = mod.read_excel_settings(intake)
    assert settings.get("architecture"), (
        "'architecture' missing -- import-excel is not building the legacy "
        f"views for an intake workbook; got keys: {sorted(settings)[:12]}")
    assert settings["architecture"].strip() == ARCH


def test_converting_an_already_converted_workbook_is_refused(tmp_path):
    """Running the converter twice must not produce a raw traceback.

    `make convert-workbook` twice, or pointing it at its own output, is an
    easy mistake. It used to die on `legacy_wb["Wire Map"]` with a bare
    KeyError three frames down.
    """
    once = tmp_path / "once.xlsx"
    assert _run("scripts/convert_workbook.py", str(LEGACY_SRC),
                str(once)).returncode == 0

    again = _run("scripts/convert_workbook.py", str(once),
                 str(tmp_path / "twice.xlsx"))
    assert again.returncode != 0, "second conversion should fail, not succeed"
    combined = (again.stdout + again.stderr).lower()
    assert "already an intake-form workbook" in combined, (
        f"expected a clear refusal, got: {combined[-400:]}")
    assert "traceback" not in combined, "raw traceback leaked to the user"
