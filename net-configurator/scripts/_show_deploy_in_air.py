#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Print `yes` or `no`: the `deploy_in_air` setting of an intake workbook.

Reads the Deployment sheet, so it answers before any inventory exists. A
missing file, sheet or row prints `yes`, the parser's default. Used by Makefile
macros that must not touch Air for a physical (`Deploy in Air = No`) site.

Usage:
    python3 scripts/_show_deploy_in_air.py input/2-4-3-200/default/2-4-3-200.xlsx
"""
import sys
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import openpyxl  # noqa: E402

from intake_reader import read_deployment  # noqa: E402


def deploy_in_air(xlsx):
    path = Path(xlsx)
    if not path.is_file():
        return True
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        if 'Deployment' not in wb.sheetnames:
            return True
        value = read_deployment(wb['Deployment']).get('deploy_in_air', 'Yes')
    finally:
        wb.close()
    return str(value if value is not None else 'Yes').strip().lower() in ('yes', 'true', '1')


def main() -> int:
    print('yes' if len(sys.argv) < 2 or deploy_in_air(sys.argv[1]) else 'no')
    return 0


if __name__ == '__main__':
    sys.exit(main())
