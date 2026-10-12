# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
ERA-142 / ERA-143 — ext-storage nodes on a custom air-mgmt subnet and the
`make fix-ext-storage` vault source.

Live Air (2-4-3-200, air_mgmt 172.20.0.128/26): `make generate` passed but
`make air-deploy` aborted with `ext-storage-01 eth0 172.20.0.207 is not a
usable host of air-mgmt subnet 172.20.0.128/26`. The shipped workbooks name
ext-storage-* only on the Wiremap, so the planner's Nodes-derived ext-storage
claim list was always empty and `infra_addresses.air_mgmt` never seated them;
the builder then fell back to network+79, outside a /26.

The same run showed a bare `make fix-ext-storage` failing with rc=4 on an
encrypted inventory because the ad-hoc `ansible` child never received the
saved `.era-secrets/vault-pass` the playbook wrapper exports.
"""
import importlib.util
import ipaddress
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl
import yaml

REPO = Path(__file__).parent.parent
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import excel_parser  # noqa: E402
from excel_parser import plan_infra_addresses, process_excel_template  # noqa: E402
from airlib.ext_storage_config import discover_ext_storage_targets  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "fix_ext_storage_frr", SCRIPTS / "fix-ext-storage-frr.py")
fix = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fix)

ARCH = "2-4-3-200"
WORKBOOK = REPO / "input" / ARCH / "default" / f"{ARCH}.xlsx"
AIR26 = "172.20.0.128/26"


def _hosts(cidr):
    return set(ipaddress.IPv4Network(cidr).hosts())


def _workbook_with_air_mgmt(tmp_path, subnet):
    wb_path = tmp_path / f"{ARCH}.xlsx"
    shutil.copy(WORKBOOK, wb_path)
    wb = openpyxl.load_workbook(wb_path)
    hit = False
    for row in wb["Deployment"].iter_rows(min_row=1):
        if row[0].value == "Air Management Subnet":
            row[1].value = subnet
            hit = True
    assert hit, "Deployment sheet has no 'Air Management Subnet' row"
    wb.save(wb_path)
    return wb_path


def _generate(tmp_path, wb_path, site):
    out = tmp_path / "output" / ARCH / site / "inventory"
    process_excel_template(wb_path, out, site=site)
    main = yaml.safe_load((out / "group_vars" / "all" / "main.yml").read_text())
    return out, main


# ── ERA-142: planner sees the Wiremap's ext-storage nodes ─────────────────

def test_air_ext_storage_names_come_from_wiremap_rows():
    rows = [
        {"display_in_air": True, "system_name": "ext-storage-02"},
        {"display_in_air": True, "system_name": "ext-storage-01"},
        {"display_in_air": True, "system_name": "ext-storage-01"},   # 3 uplinks
        {"display_in_air": False, "system_name": "ext-storage-09"},  # not in Air
        {"display_in_air": True, "system_name": "gpu-01"},
    ]
    assert excel_parser.air_ext_storage_names([], rows) == ["ext-storage-01", "ext-storage-02"]


def test_air_ext_storage_names_drop_nodes_disabled_entries():
    """A Nodes row marked Disabled wins over its Wiremap rows, so validate-excel
    (which passes parsed nodes) and the generator count the same claimants."""
    rows = [{"display_in_air": True, "system_name": "ext-storage-01"},
            {"display_in_air": True, "system_name": "ext-storage-02"}]
    nodes = [{"name": "ext-storage-02", "category": "ext-storage", "status": "Disabled"}]
    assert excel_parser.air_ext_storage_names(nodes, rows) == ["ext-storage-01"]


def test_planner_claims_wiremap_ext_storage_without_nodes_rows():
    settings = {"oob_mode": "L2", "air_mgmt_subnet": AIR26}
    vlans = [{"name": "oob", "id": 200, "vrf": "OOB",
              "subnet": "192.168.200.0/24", "gateway": "192.168.200.1"}]
    nodes = [{"role": "oob-switch", "name": "oob-switch-01", "category": "oob-switch",
              "index": 0, "status": "Active", "mgmt_ip": "", "prefix": 24,
              "gateway": "192.168.200.1", "oob_vlan": "200"}]
    plan = plan_infra_addresses(settings, vlans, nodes, {"air_mgmt_subnet": AIR26},
                                ext_storage_names=["ext-storage-01", "ext-storage-02"])
    infra = plan["air_mgmt"]["infra"]
    assert {"ext-storage-01", "ext-storage-02"} <= set(infra)
    assert all(ipaddress.IPv4Address(infra[k]) in _hosts(AIR26)
               for k in ("ext-storage-01", "ext-storage-02"))


def test_shipped_workbook_default_slash24_seats_ext_storage_at_79_80(tmp_path):
    """Every shipped workbook carries ext-storage on the Wiremap; the /24
    plan must name them at the historical .79/.80 so air-deploy and the
    builder agree."""
    out, main = _generate(tmp_path, WORKBOOK, "audit-ext24")
    air = main["infra_addresses"]["air_mgmt"]
    assert air["ext-storage-01"] == "172.20.0.79"
    assert air["ext-storage-02"] == "172.20.0.80"


def test_custom_slash26_air_mgmt_seats_ext_storage_inside_subnet(tmp_path):
    wb_path = _workbook_with_air_mgmt(tmp_path, AIR26)
    out, main = _generate(tmp_path, wb_path, "audit-air26")
    air = main["infra_addresses"]["air_mgmt"]
    assert air["subnet"] == AIR26
    for name in ("ext-storage-01", "ext-storage-02"):
        assert name in air, f"{name} missing from infra_addresses.air_mgmt: {air}"
        assert ipaddress.IPv4Address(air[name]) in _hosts(AIR26)
    addrs = [v for k, v in air.items() if k != "subnet"]
    assert len(set(addrs)) == len(addrs), f"duplicate air-mgmt address: {air}"

    # The exact seam air-deploy.py uses before injecting the ext-storage NIs.
    topo = {"content": {"nodes": {"ext-storage-01": {}, "ext-storage-02": {}},
                        "links": []}}
    targets = discover_ext_storage_targets(topo, air_mgmt_subnet=AIR26, eth0_ips=air)
    assert sorted(t["node_name"] for t in targets) == ["ext-storage-01", "ext-storage-02"]
    assert all(ipaddress.IPv4Address(t["eth0_ip"]) in _hosts(AIR26) for t in targets)


def test_validate_excel_accepts_custom_slash26_workbook(tmp_path):
    """The gate must still pass (the /26 has room) — and run the planner with
    the ext-storage claimants, so a subnet that cannot seat them fails here
    rather than in air-deploy."""
    wb_path = _workbook_with_air_mgmt(tmp_path, AIR26)
    r = subprocess.run([sys.executable, str(SCRIPTS / "validate_excel.py"), str(wb_path)],
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stdout + r.stderr


def _workbook_with_disabled_ext_storage(tmp_path, arch, subnet):
    src = REPO / "input" / arch / "default" / f"{arch}.xlsx"
    wb_path = tmp_path / f"{arch}.xlsx"
    shutil.copy(src, wb_path)
    wb = openpyxl.load_workbook(wb_path)
    for row in wb["Deployment"].iter_rows(min_row=1):
        if row[0].value == "Air Management Subnet":
            row[1].value = subnet
    ws = wb["Host Data"]
    header = [c.value for c in ws[1]]
    name_col, en_col = header.index("System Name"), header.index("Enabled")
    flipped = 0
    for row in ws.iter_rows(min_row=2):
        if str(row[name_col].value or "").startswith("ext-storage-"):
            row[en_col].value = "No"
            flipped += 1
    assert flipped == 2, header
    wb.save(wb_path)
    return wb_path


def test_validate_excel_and_generator_agree_on_host_data_disabled_ext_storage(tmp_path):
    """Host Data `Enabled=No` on both ext-storage rows: the generator seats
    nobody for them, so validate-excel must not count them either. A /28
    (14 usable) has room for the plan only without the two nodes — the
    validator counting them raised a false capacity error (MR 311 review)."""
    arch = "2-8-9-800"
    wb_path = _workbook_with_disabled_ext_storage(tmp_path, arch, "172.20.0.128/28")
    r = subprocess.run([sys.executable, str(SCRIPTS / "validate_excel.py"), str(wb_path)],
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stdout + r.stderr
    out = tmp_path / "output" / arch / "audit-disabled-ext" / "inventory"
    process_excel_template(wb_path, out, site="audit-disabled-ext")
    main = yaml.safe_load((out / "group_vars" / "all" / "main.yml").read_text())
    air = main["infra_addresses"]["air_mgmt"]
    assert not [k for k in air if k.startswith("ext-storage-")], air


# ── ERA-143: fix-ext-storage passes the saved vault password to ansible ───

def test_ansible_child_env_exports_saved_vault_pass(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / ".era-secrets").mkdir(parents=True)
    vp = root / ".era-secrets" / "vault-pass"
    vp.write_text("x\n")
    monkeypatch.chdir(tmp_path)  # no ansible.cfg in cwd -> no native source
    env = fix.ansible_child_env(environ={"PATH": "/usr/bin", "HOME": str(tmp_path)},
                                project_root=root)
    assert env["ANSIBLE_VAULT_PASSWORD_FILE"] == str(vp)
    assert env["PATH"] == "/usr/bin"


def test_ansible_child_env_respects_explicit_vault_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    explicit = tmp_path / "mine"
    explicit.write_text("y\n")
    env = fix.ansible_child_env(
        environ={"ANSIBLE_VAULT_PASSWORD_FILE": str(explicit), "HOME": str(tmp_path)},
        project_root=tmp_path / "nowhere")
    assert env["ANSIBLE_VAULT_PASSWORD_FILE"] == str(explicit)


def test_ansible_child_env_unchanged_without_any_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env = fix.ansible_child_env(environ={"HOME": str(tmp_path)},
                                project_root=tmp_path / "nowhere")
    assert "ANSIBLE_VAULT_PASSWORD_FILE" not in env


def test_run_via_jump_uses_child_env(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["env"] = kw.get("env")

        class P:
            returncode = 0
            stdout = "FIX|ext-storage-01|OK|x"
            stderr = ""
        return P()

    monkeypatch.setattr(fix.subprocess, "run", fake_run)
    monkeypatch.setattr(fix, "ansible_child_env",
                        lambda: {"ANSIBLE_VAULT_PASSWORD_FILE": "/vp"})
    rc, out = fix._run_via_jump(tmp_path / "hosts", "pw", "172.20.0.79", "true")
    assert rc == 0 and "FIX|" in out
    assert seen["cmd"][0] == "ansible"
    assert seen["env"] == {"ANSIBLE_VAULT_PASSWORD_FILE": "/vp"}


def test_validate_excel_rejects_air_mgmt_too_small_for_ext_storage(tmp_path):
    """A /29 cannot seat gateway + dhcp + utility + two ext-storage nodes;
    the gate must say so up front instead of letting air-deploy discover it."""
    wb_path = _workbook_with_air_mgmt(tmp_path, "172.20.0.128/29")
    r = subprocess.run([sys.executable, str(SCRIPTS / "validate_excel.py"), str(wb_path)],
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode != 0
    assert "172.20.0.128/29" in r.stdout and "usable addresses" in r.stdout
