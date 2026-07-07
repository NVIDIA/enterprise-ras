# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
#33: `make import` must not let an Excel's `site_name` cell silently override
the folder the file already lives in. An Excel at input/<arch>/customer-x/ with
site_name=sample should route to customer-x (the folder), not sample.
"""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_import_excel():
    spec = importlib.util.spec_from_file_location("import_excel_mod",
                                                  SCRIPTS / "import-excel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ie = _load_import_excel()
INPUT_DIR = ie.INPUT_DIR


def test_path_site_under_arch_site_dir():
    p = INPUT_DIR / "2-4-3-200" / "customer-x" / "2-4-3-200.xlsx"
    assert ie._path_derived_site(p, "2-4-3-200") == "customer-x"


def test_path_site_sanitized():
    p = INPUT_DIR / "2-4-3-200" / "Customer X!" / "2-4-3-200.xlsx"
    # _safe_site_name lowercases + replaces invalid chars with hyphens
    assert ie._path_derived_site(p, "2-4-3-200") == "customer-x"


def test_no_site_when_directly_under_arch():
    # input/<arch>/<arch>.xlsx — no site subdir → fall back to Excel cell
    p = INPUT_DIR / "2-4-3-200" / "2-4-3-200.xlsx"
    assert ie._path_derived_site(p, "2-4-3-200") is None


def test_no_site_when_outside_input(tmp_path):
    p = tmp_path / "downloads" / "2-4-3-200.xlsx"
    assert ie._path_derived_site(p, "2-4-3-200") is None


def test_no_site_when_wrong_arch_dir():
    # File under a different arch's tree → no match for this arch
    p = INPUT_DIR / "2-8-9-800" / "lab" / "2-8-9-800.xlsx"
    assert ie._path_derived_site(p, "2-4-3-200") is None
