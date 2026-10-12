# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""nc-v8 post-MR311 Air findings (ADR-0088).

1. GB300 (2-4-5-800) L2 OOB: the core seed in inventory_defaults.yml carried
   the L3-OOB default-VRF BGP intent (eBGP unnumbered on the csl OOB uplinks
   swp63s0/s1, swp64s0/s1 plus an EVPN overlay to the OOB-switch loopbacks).
   `_apply_oob_l3_uplink_mode` only rewrites that intent in L3, so in L2 the
   csl pair rendered BGP neighbours on its OOB bond members toward OOB
   switches that run no BGP, and the switch-health bgp check failed.
2. `make restart-ldap` only looped core/csl/gsl, yet every switch role
   renders the LDAP AAA block (ADR-0087), so OOB switches were never
   restarted.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from excel_parser import process_excel_template  # noqa: E402

DEFAULTS = yaml.safe_load((REPO / "scripts" / "inventory_defaults.yml").read_text())
CORE_ARCHS = sorted(DEFAULTS["core"])


@pytest.mark.parametrize("arch", CORE_ARCHS)
def test_core_seed_default_vrf_bgp_is_oob_mode_neutral(arch):
    """The seed is what an L2 site renders verbatim; OOB-facing peers are
    added only by the L3 rewrite. So the seed may peer the ISL only."""
    bgp = DEFAULTS["core"][arch].get("default_vrf_bgp") or {}
    neighbors = bgp.get("neighbors") or []
    assert [n.get("interfaces") for n in neighbors] == ["isl"], (arch, neighbors)
    assert "overlay" not in {pg["id"] for pg in bgp.get("peer_groups") or []}, arch
    underlay = [pg for pg in bgp.get("peer_groups") or []
                if pg["id"] == neighbors[0].get("peer_group")]
    assert [pg.get("remote_as") for pg in underlay] == ["internal"], arch


def _import(tmp_path, arch, mode):
    src = REPO / "input" / arch / "default" / f"{arch}.xlsx"
    if not src.exists():
        pytest.skip(f"{src} not generated")
    xlsx = tmp_path / f"{arch}.xlsx"
    shutil.copy(src, xlsx)
    wb = openpyxl.load_workbook(xlsx)
    hit = False
    for row in wb["Deployment"].iter_rows(min_row=1):
        if row[0].value == "oob_uplink_mode":
            row[1].value = mode
            hit = True
    assert hit
    wb.save(xlsx)
    inv = tmp_path / "inventory"
    process_excel_template(xlsx, inv, site=f"audit-{mode.lower()}")
    return inv


def _csl_bgp(inv):
    return yaml.safe_load((inv / "group_vars" / "csl.yml").read_text())["default_vrf_bgp"]


def test_gb300_l2_csl_peers_only_the_isl(tmp_path):
    bgp = _csl_bgp(_import(tmp_path, "2-4-5-800", "L2"))
    assert [n["interfaces"] for n in bgp["neighbors"]] == ["isl"]
    assert all(n.get("type") != "numbered" for n in bgp["neighbors"])
    groups = {pg["id"]: pg for pg in bgp["peer_groups"]}
    assert groups[bgp["neighbors"][0]["peer_group"]]["remote_as"] == "internal"


def test_gb300_l3_csl_still_gets_oob_underlay_and_overlay(tmp_path):
    bgp = _csl_bgp(_import(tmp_path, "2-4-5-800", "L3"))
    ifaces = [n["interfaces"] for n in bgp["neighbors"]]
    assert "isl" in ifaces and "oob_uplink" in ifaces
    assert any(n.get("peer_group") == "overlay" and n.get("type") == "numbered"
               for n in bgp["neighbors"])


def test_gb300_l2_rendered_csl_has_no_bgp_on_oob_bonds(tmp_path):
    if not shutil.which("ansible-playbook"):
        pytest.skip("ansible-playbook required")
    inv = _import(tmp_path, "2-4-5-800", "L2")
    cfg = tmp_path / "configs"
    cfg.mkdir()
    res = subprocess.run(
        ["ansible-playbook", str(REPO / "playbooks" / "generate-cli-configs.yml"),
         "-i", str(inv / "hosts"), "-e", f"config_output_dir={cfg}"],
        capture_output=True, text=True, cwd=REPO, timeout=900,
        env={**os.environ, "ANSIBLE_LOCALHOST_WARNING": "false"})
    assert res.returncode == 0, res.stdout[-4000:] + res.stderr[-2000:]
    for name in ("csl-01", "csl-02"):
        text = (cfg / f"{name}-config.sh").read_text()
        members = set(re.findall(r"bond member (swp\S+)", text))
        peers = set(re.findall(r"^nv set vrf default router bgp neighbor (\S+) ", text, re.M))
        assert peers, name
        assert not peers & members, (name, sorted(peers & members))
        assert all(p.startswith("swp") for p in peers), (name, sorted(peers))


def _restart_ldap_switch_expr():
    play = yaml.safe_load((REPO / "playbooks" / "restart-ldap-switches.yml").read_text())
    for task in play[0]["tasks"]:
        if "ldap_switches" in (task.get("set_fact") or {}):
            return task["set_fact"]["ldap_switches"]
    raise AssertionError("ldap_switches set_fact not found")


def test_restart_ldap_targets_every_switch(tmp_path):
    """Resolve the playbook's switch list against a real L3 inventory: it must
    contain every host in the 'switches' parent group, OOB switches included."""
    if not shutil.which("ansible"):
        pytest.skip("ansible required")
    inv = _import(tmp_path, "2-4-3-200", "L3")
    expr = _restart_ldap_switch_expr()
    res = subprocess.run(
        ["ansible", "localhost", "-i", str(inv / "hosts"), "-m", "debug",
         "-a", "msg={{ (%s) | join(',') }}|{{ groups['switches'] | join(',') }}|"
               "{{ groups['oob'] | join(',') }}" % expr.strip("{} ")],
        capture_output=True, text=True, cwd=REPO, timeout=300,
        env={**os.environ, "ANSIBLE_LOCALHOST_WARNING": "false"})
    assert res.returncode == 0, res.stdout[-3000:] + res.stderr[-2000:]
    m = re.search(r'"msg": "([^"|]*)\|([^"|]*)\|([^"|]*)"', res.stdout)
    assert m, res.stdout[-2000:]
    targets, switches, oob = (set(filter(None, g.split(","))) for g in m.groups())
    assert oob and oob <= targets, (sorted(oob), sorted(targets))
    assert switches == targets
