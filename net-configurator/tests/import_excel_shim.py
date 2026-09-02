# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""`import-excel.py` has a hyphen in its name, so it cannot be imported directly."""
import importlib.util
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "scripts" / "import-excel.py"
_spec = importlib.util.spec_from_file_location("import_excel", _MOD)
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)

_safe_site_name = _m._safe_site_name
