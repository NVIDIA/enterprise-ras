#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""The one rule for turning a site name into the directory name used on disk.

Shared by `import-excel.py` (workbook cell / `--site`) and the Makefile (a
command-line `SITE=`), so import, generate and deploy always agree:

    python3 scripts/_site_name.py 'lab--2.x'   ->   lab-2-x

Standard library only: the Makefile runs this at parse time, before any venv
is guaranteed.
"""
import re
import sys

# Characters not allowed in site directory names
_INVALID_SITE_CHARS = re.compile(r'[^\w\-]')


def safe_site_name(raw: str) -> str:
    """Sanitize a site name for use as a directory name.

    Case is PRESERVED. This used to `.lower()`, and nothing downstream did: the
    Makefile uses `$(SITE)` verbatim and `make generate` reads
    `input/<arch>/$(SITE)/<arch>.xlsx`, so import wrote one directory and
    generate read another whenever the site name contained an uppercase letter.

    Surfaced by the first e2e run of `2-8-9-400-SP` — the only arch whose NAME
    carries uppercase, so `SITE=ci-<id>-2-8-9-400-SP-noztp` landed on disk as
    `...-2-8-9-400-sp-noztp` and generate failed with a bare `[File] Not found`.
    Not CI-only: any operator using a mixed-case site name hit it.

    Sanitisation of genuinely unsafe characters is unchanged — the output still
    matches the Makefile's SITE guard charset, `[A-Za-z0-9._-]`.
    """
    sanitized = _INVALID_SITE_CHARS.sub('-', raw.strip())
    sanitized = re.sub(r'-+', '-', sanitized).strip('-')
    return sanitized or "default"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(2)
    print(safe_site_name(sys.argv[1]))
