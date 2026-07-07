# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
`make import` must back up an existing template before overwriting it — a
different Excel imported to a site (esp. `default`) would otherwise silently
destroy the committed reference template (violating the CLAUDE.md backup rule).
"""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("import_excel", SCRIPTS / "import-excel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


import_excel = _load()


def test_archive_backs_up_existing_template(tmp_path, monkeypatch):
    monkeypatch.setattr(import_excel, "BASE_DIR", tmp_path)
    dest = tmp_path / "input" / "2-4-3-200" / "default" / "2-4-3-200.xlsx"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"ORIGINAL TEMPLATE BYTES")

    backup = import_excel._archive_existing_template(dest, "2-4-3-200", "default")

    assert backup is not None and backup.exists()
    assert backup.read_bytes() == b"ORIGINAL TEMPLATE BYTES"
    assert (tmp_path / "archive") in backup.parents
    # The original is still in place (caller overwrites it AFTER the backup).
    assert dest.read_bytes() == b"ORIGINAL TEMPLATE BYTES"


def test_archive_noop_when_dest_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(import_excel, "BASE_DIR", tmp_path)
    dest = tmp_path / "input" / "2-4-3-200" / "newsite" / "2-4-3-200.xlsx"
    assert import_excel._archive_existing_template(dest, "2-4-3-200", "newsite") is None
