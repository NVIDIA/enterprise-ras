# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""The public `make help` lists only targets that work in the public tree (GitLab #102 / H14).

`validate-requirements` / `extract-requirements` ran scripts that moved to
the internal `data-models/`, so in both trees they printed "Internal-only ...
Skipping" and exited 0. `.PHONY` also named `ztp`, `oob` and `check-arch`,
which had no rule.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
RULES = set(re.findall(r"^([A-Za-z0-9_.%-]+)\s*:(?!=)", MAKEFILE, re.MULTILINE))
HELPED = re.findall(r"^([a-zA-Z_-]+):.*?## ", MAKEFILE, re.MULTILINE)
REMOVED = ("validate-requirements", "extract-requirements", "ztp", "oob", "check-arch")
MAJOR = ("help", "setup", "test", "lint", "use", "show-context", "import",
         "convert-workbook", "validate-excel", "generate", "deploy",
         "air-full-deploy", "switch-ztp-deploy", "push-switch-configs",
         "validate-ztp-direct", "validate-all")


def _phony():
    names = set()
    for m in re.finditer(r"^\.PHONY:((?:.*\\\n)*.*)$", MAKEFILE, re.MULTILINE):
        names |= set(m.group(1).replace("\\\n", " ").split())
    return names


def _recipe(target):
    m = re.search(rf"^{re.escape(target)}:.*\n((?:\t.*\n|\n)*)", MAKEFILE, re.MULTILINE)
    return m.group(1) if m else ""


def test_every_phony_name_has_a_rule():
    assert _phony() - RULES == set()


@pytest.mark.parametrize("name", REMOVED)
def test_dead_targets_are_gone(name):
    assert name not in RULES and name not in _phony()


def test_no_help_entry_is_an_internal_only_stub():
    stubs = [t for t in HELPED if "Internal-only" in _recipe(t)]
    assert stubs == []


@pytest.mark.parametrize("name", MAJOR)
def test_major_commands_have_help(name):
    assert name in HELPED


def test_make_help_lists_public_targets_and_no_dead_ones():
    out = subprocess.run(["make", "--no-print-directory", "help"], cwd=ROOT,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    listed = set(re.findall(r"^\x1b\[36m(\S+)", out.stdout, re.MULTILINE))
    assert set(HELPED) <= listed
    assert not listed & set(REMOVED)
