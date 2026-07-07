# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Regression guard: `make deploy-switches-only EXCEL=... IMPORT_SITE=<x>` must
deploy to <x>, not to the Excel's site_name. The recipe imported to IMPORT_SITE
but then re-derived the deploy site from the Excel via _excel_context.py, so the
air-deploy step landed on site=default (dirtying the tracked default inventory).
"""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _recipe(target):
    """Return the lines of a Makefile target's recipe (tab-indented block)."""
    text = (REPO / "Makefile").read_text().splitlines()
    out, in_target = [], False
    for line in text:
        if re.match(rf"^{re.escape(target)}:", line):
            in_target = True
            continue
        if in_target:
            if line and not line.startswith(("\t", " ")) and ":" in line:
                break  # next target
            out.append(line)
    return "\n".join(out)


def test_deploy_switches_only_prefers_import_site():
    recipe = _recipe("deploy-switches-only")
    # IMPORT_SITE is used as the deploy site, falling back to the Excel site.
    assert '_DEPLOY_SITE="$(IMPORT_SITE)"' in recipe
    assert 'air-deploy-switches-only ARCH=$$_ARCH SITE=$$_DEPLOY_SITE' in recipe


def test_deploy_site_override_logic():
    # Mirror the recipe's selection: IMPORT_SITE wins when set, else Excel site.
    script = (
        '_DEPLOY_SITE="$IMPORT_SITE"; '
        '[ -n "$_DEPLOY_SITE" ] || _DEPLOY_SITE="$_SITE"; '
        'echo "$_DEPLOY_SITE"'
    )
    def run(env):
        return subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, env=env).stdout.strip()
    assert run({"IMPORT_SITE": "my-lab", "_SITE": "default"}) == "my-lab"
    assert run({"IMPORT_SITE": "", "_SITE": "default"}) == "default"
