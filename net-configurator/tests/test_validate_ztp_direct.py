# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""H4 / GitLab #92: `make validate-ztp-direct` reports the playbook's verdict.

The recipe piped ansible-playbook through three `grep -v` filters with no
`PIPESTATUS`, so the target exited with the last grep's status: a failed
playbook that printed anything passed, and a clean run that printed nothing
failed. The playbook also counted a switch as passed on SSH reachability alone,
so a switch with the wrong hostname or no applied NVUE config still passed.

The Makefile cases run the real recipe against a stub ``ANSIBLE_PLAYBOOK``. The
playbook cases run the real playbook against one local host with stub
``hostname``/``nv`` commands on PATH.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
MAKEFILE = Path(os.environ.get("ERA_VALIDATE_ZTP_DIRECT_MAKEFILE", NC / "Makefile"))
PLAYBOOK = Path(os.environ.get("ERA_VALIDATE_ZTP_DIRECT_PLAYBOOK",
                               NC / "playbooks" / "validate-ztp-direct.yml"))
ARCH = "2-4-3-200"
STARTUP = "/etc/nvue.d/startup.yaml"


def _stub(path, body):
    path.write_text("#!/bin/bash\n" + body)
    path.chmod(0o755)


def _make(tmp_path, stub_body):
    (tmp_path / "input" / ARCH).mkdir(parents=True)
    (tmp_path / "scripts").symlink_to(NC / "scripts")
    _stub(tmp_path / "ansible-playbook-stub", stub_body)
    return subprocess.run(
        ["make", "-f", str(MAKEFILE), "validate-ztp-direct", f"ARCH={ARCH}",
         "SITE=default", f"ANSIBLE_PLAYBOOK={tmp_path / 'ansible-playbook-stub'}"],
        cwd=tmp_path, capture_output=True, text=True, timeout=120)


def test_failed_playbook_fails_the_target_even_when_it_prints(tmp_path):
    r = _make(tmp_path, 'echo "fatal: [core-01]: UNREACHABLE!"\nexit 2\n')
    assert r.returncode != 0, r.stdout + r.stderr
    assert "UNREACHABLE" in r.stdout


def test_successful_playbook_passes_the_target_even_when_filtered_silent(tmp_path):
    r = _make(tmp_path, 'echo "[WARNING] filtered"\necho\nexit 0\n')
    assert r.returncode == 0, r.stdout + r.stderr


def test_report_is_still_printed_when_the_playbook_fails(tmp_path):
    reports = tmp_path / "output" / ARCH / "default" / "reports"
    reports.mkdir(parents=True)
    (reports / "ztp-validation.txt").write_text("SUMMARY:  0/1 switches passed\nRAW COMMAND OUTPUT\nraw\n")
    r = _make(tmp_path, "exit 2\n")
    assert r.returncode != 0
    assert "0/1 switches passed" in r.stdout
    assert "raw" not in r.stdout.split("RAW COMMAND OUTPUT")[0].splitlines()


needs_ansible = pytest.mark.skipif(not shutil.which("ansible-playbook"),
                                   reason="ansible-playbook required")


def _run_playbook(tmp_path, reported_hostname, nvue_hostname, startup_present):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir / "hostname", f"echo {reported_hostname}\n")
    _stub(bin_dir / "nv", "echo '%s'\n" % json.dumps({"system": {"hostname": nvue_hostname}}))
    # A switch ships jq; CI images may not. Answer the one query the playbook's
    # applied-config check makes, so the result does not depend on the runner.
    jq = bin_dir / "jq"
    jq.write_text(f"#!{sys.executable}\nimport json, sys\n"
                  "assert sys.argv[1:] == ['-r', '.system.hostname'], sys.argv\n"
                  "print(json.load(sys.stdin)['system']['hostname'])\n")
    jq.chmod(0o755)
    startup = tmp_path / "startup.yaml"
    if startup_present:
        startup.write_text("- set: {}\n")
    text = PLAYBOOK.read_text()
    assert text.count(STARTUP) == 1
    (tmp_path / "play.yml").write_text(text.replace(STARTUP, str(startup)))
    (tmp_path / "hosts").write_text(
        "[oob_switch]\n"
        f"oob-switch-01 ansible_host=127.0.0.1 ansible_connection=local "
        f"ansible_python_interpreter={sys.executable} hostname=oob-switch-01\n"
        "[switches:children]\noob_switch\n")
    report = tmp_path / "report.txt"
    env = {"PATH": f"{bin_dir}:{Path(sys.executable).parent}:/usr/bin:/bin",
           "HOME": str(tmp_path), "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-tmp")}
    r = subprocess.run(["ansible-playbook", "-i", str(tmp_path / "hosts"), str(tmp_path / "play.yml"),
                        "-e", json.dumps({"report_file": str(report)})],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300)
    return r, report.read_text() if report.exists() else ""


@needs_ansible
def test_switch_with_its_hostname_and_applied_config_passes(tmp_path):
    r, report = _run_playbook(tmp_path, "oob-switch-01", "oob-switch-01", True)
    assert r.returncode == 0, r.stdout[-3000:]
    assert "1/1 switches passed" in report
    assert "Status:                   PASSED" in report


@needs_ansible
@pytest.mark.parametrize("reported,nvue,startup,reason", [
    ("cumulus", "oob-switch-01", True, "hostname mismatch"),
    ("oob-switch-01", "oob-switch-01", False, "NVUE config not applied"),
    ("oob-switch-01", "cumulus", True, "NVUE config not applied"),
], ids=["wrong-hostname", "no-startup-config", "config-not-applied"])
def test_reachable_switch_without_its_config_fails(tmp_path, reported, nvue, startup, reason):
    r, report = _run_playbook(tmp_path, reported, nvue, startup)
    assert r.returncode != 0, r.stdout[-3000:]
    assert "0/1 switches passed" in report
    assert f"FAILED — {reason}" in report
