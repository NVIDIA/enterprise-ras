# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-144 (Air finding F4): LDAP AAA is rendered on every switch role.

Only core_nvue_cli.j2 carried the `nv set system aaa ldap ...` block; with
`ldap_enabled = Yes` the OOB/GL/spine switches booted without LDAP and
rejected the directory user that the cores accepted. Offline evidence
only: the rendered scripts carry the commands; the login behaviour on
Cumulus needs an Air re-run.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from excel_parser import process_excel_template  # noqa: E402

TEMPLATES = {
    "core": REPO / "roles/core/templates/core_nvue_cli.j2",
    "oob": REPO / "roles/oob-switch/templates/oob_nvue_cli.j2",
    "gl": REPO / "roles/gl/templates/gl_nvue_cli.j2",
    "spine": REPO / "roles/spine/templates/spine_nvue_cli.j2",
}
LDAP_LINES = (
    "nv set system aaa authentication order local ldap",
    "nv set system aaa ldap vrf mgmt",
    "nv set system aaa ldap base-dn ",
    "nv set system aaa ldap bind-dn ",
    "nv set system aaa ldap secret ",
    "nv set system aaa ldap server ",
)


@pytest.mark.parametrize("role", sorted(TEMPLATES))
def test_every_switch_template_carries_the_ldap_block(role):
    src = TEMPLATES[role].read_text()
    assert "ldap.enabled | default(false)" in src
    for line in LDAP_LINES:
        assert line in src, f"{role}: missing {line!r}"
    # if/else on the authentication order: exactly one local-only fallback
    assert src.count("nv set system aaa authentication order local\n") == 1


def test_ldap_blocks_are_identical_across_roles():
    """The core block is the reference; drift between roles is how F4
    happened. Compare the LDAP-guarded region verbatim."""
    def block(path):
        src = path.read_text()
        m = re.search(r"\{% if ldap is defined and ldap\.enabled \| default\(false\) %\}\n"
                      r"nv set system aaa ldap vrf mgmt\n.*?\n\{% endif %\}\n\{% endif %\}\n",
                      src, re.S)
        assert m, path
        return m.group(0)
    ref = block(TEMPLATES["core"])
    for role, path in TEMPLATES.items():
        assert block(path) == ref, role


# ── end-to-end: workbook → inventory → rendered switch scripts ───────────

def _workbook(tmp_path, arch, ldap_enabled):
    src = REPO / "input" / arch / "default" / f"{arch}.xlsx"
    if not src.exists():
        pytest.skip(f"{src} not generated")
    dst = tmp_path / f"{arch}.xlsx"
    shutil.copy(src, dst)
    wb = openpyxl.load_workbook(dst)
    hit = False
    for row in wb["Deployment"].iter_rows(min_row=1):
        if row[0].value == "ldap_enabled":
            row[1].value = ldap_enabled
            hit = True
    assert hit
    wb.save(dst)
    return dst


def _render_site(tmp_path, arch, ldap_enabled):
    if not shutil.which("ansible-playbook"):
        pytest.skip("ansible-playbook required")
    site = f"audit-ldap-{ldap_enabled.lower()}"
    inv = tmp_path / "output" / arch / site / "inventory"
    cfg = tmp_path / "output" / arch / site / "configs"
    process_excel_template(_workbook(tmp_path, arch, ldap_enabled), inv, site=site)
    cfg.mkdir(parents=True)
    env = {**os.environ, "ANSIBLE_LOCALHOST_WARNING": "false"}
    res = subprocess.run(
        ["ansible-playbook", str(REPO / "playbooks" / "generate-cli-configs.yml"),
         "-i", str(inv / "hosts"), "-e", f"config_output_dir={cfg}"],
        capture_output=True, text=True, env=env, cwd=REPO, timeout=900)
    assert res.returncode == 0, res.stdout[-4000:] + res.stderr[-2000:]
    scripts = sorted(p for p in cfg.glob("*-config.sh")
                     if not p.name.startswith("cust-net-edge-"))
    assert scripts
    return scripts


@pytest.mark.parametrize("arch,roles", [
    ("2-4-3-200", ("core-", "oob-switch-")),
    ("2-8-9-800", ("csl-", "gsl-plane", "oob-switch-")),
])
def test_ldap_enabled_renders_aaa_ldap_on_every_switch(tmp_path, arch, roles):
    scripts = _render_site(tmp_path, arch, "Yes")
    seen = set()
    for p in scripts:
        text = p.read_text()
        for line in LDAP_LINES:
            assert line in text, f"{p.name}: missing {line!r}"
        assert "nv set system aaa ldap server 172.20.0.78" in text, p.name
        seen.update(r for r in roles if p.name.startswith(r))
    assert seen == set(roles), f"roles rendered: {seen}"


def test_ldap_disabled_renders_no_ldap_anywhere(tmp_path):
    for p in _render_site(tmp_path, "2-4-3-200", "No"):
        text = p.read_text()
        assert "aaa ldap" not in text, p.name
        assert "nv set system aaa authentication order local\n" in text, p.name
