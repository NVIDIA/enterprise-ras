# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Regression guard for the "looks hung at maxscale" fix.

The long parallel switch/server collection runs as a single Ansible task that
is silent until done; combined with the Makefile's grep pipe block-buffering,
it read as a hang. The fix is two-part and easy to silently regress:

  1. Makefile: the minimal-callback validation targets must stream output
     (`PYTHONUNBUFFERED=1` on ansible-playbook + `grep --line-buffered`), or a
     pre-collection banner gets held in the pipe buffer until after the pause.
  2. Playbooks: an expectation banner before each quiet fan-out task so the
     dead air is explained, not read as a hang.

These assert the markers are present rather than re-running Ansible (the live
behavior is covered by docs/internal/validation-evidence/2026-06-29-validation-
progress.md). The deterministic buffering proof is scripts/internal/... not
required here.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Playbooks that gained an expectation banner before their quiet fan-out step.
BANNER_PLAYBOOKS = [
    "playbooks/validate-ztp.yml",
    "playbooks/validate-switch-health.yml",
    "playbooks/validate-config.yml",
    "playbooks/validate-servers.yml",
    "playbooks/validate-ping-matrix.yml",
]


def test_minimal_callback_targets_are_line_buffered():
    mk = (REPO / "Makefile").read_text()
    # Every minimal-callback validation invocation must also set PYTHONUNBUFFERED
    # so ansible's stdout streams through the Makefile pipe instead of block-
    # buffering until the long task finishes.
    minimal_lines = [l for l in mk.splitlines()
                     if "ANSIBLE_STDOUT_CALLBACK=minimal" in l and "ansible-playbook" in l]
    assert minimal_lines, "expected minimal-callback validation invocations in Makefile"
    for line in minimal_lines:
        assert "PYTHONUNBUFFERED=1" in line, f"missing PYTHONUNBUFFERED on: {line.strip()}"


def test_validation_greps_are_line_buffered():
    mk = (REPO / "Makefile").read_text()
    # Any grep filtering an ansible validation stream must be --line-buffered,
    # else it block-buffers and re-introduces the "looks hung" dead air.
    for line in mk.splitlines():
        if re.search(r"grep .*-v '\^\\\[WARNING", line) or "Callback dispatch" in line:
            assert "--line-buffered" in line, f"grep not line-buffered: {line.strip()}"


def test_each_fanout_playbook_has_expectation_banner():
    for rel in BANNER_PLAYBOOKS:
        text = (REPO / rel).read_text()
        assert "Progress —" in text, f"{rel}: missing 'Progress —' banner task"
        # The banner must set the expectation that silence is normal.
        assert re.search(r"not a hang", text), f"{rel}: banner missing 'not a hang' reassurance"
        assert "{{" in text and "| length" in text, f"{rel}: banner should state the count"
