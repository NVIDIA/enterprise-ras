# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-141 (Air finding F2): L2 sites get the customer-side Node Instructions
and the switch-health probe judges BGP against the switch's own config.

Offline evidence only -- the Air runtime effect (EXIT peers Established,
health gate green) needs a live re-run.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
from excel_parser import process_excel_template  # noqa: E402
PROBE = SCRIPTS / "switch_health_probe.sh"


def _load_air_deploy():
    spec = importlib.util.spec_from_file_location("air_deploy", SCRIPTS / "air-deploy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


air_deploy = _load_air_deploy()


def _link(a, ai, b, bi):
    return [{"node": a, "interface": ai}, {"node": b, "interface": bi}]


def _l2_topology(ext_storage_eth0=False):
    nodes = {n: {} for n in (
        "core-01", "core-02", "cust-net-edge-01", "cust-net-edge-02",
        "ext-storage-01", "ext-storage-02", "air-oob-switch", "dhcp-oob")}
    links = [
        _link("cust-net-edge-01", "swp1", "core-01", "swp64s0"),
        _link("cust-net-edge-02", "swp1", "core-02", "swp64s0"),
        _link("ext-storage-01", "eth1", "core-01", "swp62s0"),
        _link("ext-storage-02", "eth1", "core-02", "swp62s0"),
        _link("cust-net-edge-01", "eth0", "air-oob-switch", "swp3"),
        _link("cust-net-edge-02", "eth0", "air-oob-switch", "swp4"),
    ]
    if ext_storage_eth0:
        links += [_link("ext-storage-01", "eth0", "air-oob-switch", "swp5"),
                  _link("ext-storage-02", "eth0", "air-oob-switch", "swp6")]
    return {"content": {"nodes": nodes, "links": links, "oob": False},
            "_oob_uplink_mode": "l2"}


@pytest.fixture
def calls(monkeypatch, tmp_path):
    seen = {"edge": [], "ext": []}
    monkeypatch.setattr(air_deploy, "load_switch_password", lambda inv: "pw")  # pragma: allowlist secret
    monkeypatch.setattr(
        air_deploy, "_inject_cust_net_edge_instructions",
        lambda *a, **k: seen["edge"].append((a[4], k)) or 1)
    monkeypatch.setattr(
        air_deploy, "_inject_ext_storage_instructions",
        lambda *a, **k: seen["ext"].append(a[4]) or 1)
    inv = tmp_path / "inventory"
    (inv / "group_vars" / "all").mkdir(parents=True)
    (inv / "group_vars" / "all" / "main.yml").write_text(
        "common:\n  site: audit-l2\n  arch: 2-4-3-200\n")
    seen["inv"] = inv
    return seen


def _run(calls, topo):
    air_deploy._inject_customer_side_instructions(
        None, "https://air", "tok", "sim", calls["inv"], topo)


def test_l2_topology_gets_cust_net_edge_ni(calls):
    _run(calls, _l2_topology())
    assert len(calls["edge"]) == 1
    topo, kw = calls["edge"][0]
    assert kw["switch_password"] == "pw"  # pragma: allowlist secret
    assert kw["common"]["site"] == "audit-l2"
    assert "cust-net-edge-02" in topo["content"]["nodes"]


def test_ext_storage_without_mgmt_eth0_is_skipped_not_queued(calls, capsys):
    _run(calls, _l2_topology(ext_storage_eth0=False))
    assert calls["ext"] == []
    out = capsys.readouterr().out
    assert "ext-storage-01, ext-storage-02" in out
    assert "STORAGE VRF" in out


def test_ext_storage_with_mgmt_eth0_gets_frr_ni(calls):
    _run(calls, _l2_topology(ext_storage_eth0=True))
    assert len(calls["ext"]) == 1
    nodes = calls["ext"][0]["content"]["nodes"]
    assert {"ext-storage-01", "ext-storage-02"} <= set(nodes)


def test_only_reachable_ext_storage_is_passed_on(calls):
    topo = _l2_topology(ext_storage_eth0=False)
    topo["content"]["links"].append(
        _link("ext-storage-01", "eth0", "air-oob-switch", "swp5"))
    _run(calls, topo)
    nodes = calls["ext"][0]["content"]["nodes"]
    assert "ext-storage-01" in nodes
    assert "ext-storage-02" not in nodes
    assert "core-01" in nodes  # non-ext-storage nodes untouched


def test_no_customer_side_nodes_is_a_noop(calls):
    topo = {"content": {"nodes": {"core-01": {}}, "links": []}}
    _run(calls, topo)
    assert calls["edge"] == [] and calls["ext"] == []


def test_main_calls_helper_in_both_oob_modes():
    """Structural guard: the L2 branch and the L3 branch of main() both
    queue the customer-side NIs, and in L2 the call is not nested under the
    air-oob-switch presence check (a bridge-less L2 topology still peers)."""
    src = (SCRIPTS / "air-deploy.py").read_text()
    start = src.index('if infra["mode"] != "l3":')
    l3 = src.index("            else:", start)
    nxt = src.index("_inject_external_conn_nat_ni(", l3)
    l2_branch, l3_branch = src[start:l3], src[l3:nxt]
    assert "_inject_customer_side_instructions(" in l2_branch
    assert "_inject_customer_side_instructions(" in l3_branch
    call = l2_branch.index("_inject_customer_side_instructions(")
    line = l2_branch.rfind("\n", 0, call) + 1
    bridge_if = l2_branch.index('if infra["air_bridge"]')
    if_indent = len(l2_branch[l2_branch.rfind("\n", 0, bridge_if) + 1:bridge_if])
    assert len(l2_branch[line:call]) == if_indent, "L2 NI call must be a sibling of the air_bridge check"


# --- switch_health_probe.sh: BGP expectation from the switch's own config ---

def _bgp_python(exp_bgp: str, summary: str, tmp_path: Path) -> str:
    """Run the probe's embedded BGP Python block against a canned summary."""
    src = PROBE.read_text()
    m = re.search(r'EXP_BGP="\$exp_bgp" python3 - <<\'PY\'\n(.*?)\nPY\n', src, re.S)
    assert m, "probe BGP python block not found"
    (tmp_path / "_sh_bgp.json").write_text(summary)
    code = m.group(1).replace("/tmp/_sh_bgp.json", str(tmp_path / "_sh_bgp.json"))
    r = subprocess.run(["python3", "-"], input=code, text=True, capture_output=True,
                       env={"EXP_BGP": exp_bgp, "PATH": "/usr/bin:/bin"})
    return r.stdout


def _summary(*peers):
    return '{"default": {"ipv4Unicast": {"peers": {%s}}}}' % ",".join(
        '"%s": {"state": "%s"}' % p for p in peers)


def test_l2_oob_switch_with_no_bgp_configured_passes(tmp_path):
    out = _bgp_python("0", "{}", tmp_path)
    assert "CHECK|bgp|PASS|no BGP neighbors configured" in out


def test_l2_oob_switch_unparseable_summary_passes_when_unconfigured(tmp_path):
    out = _bgp_python("0", "not json", tmp_path)
    assert "CHECK|bgp|PASS|" in out


def test_configured_neighbors_but_none_at_runtime_fails(tmp_path):
    out = _bgp_python("4", "{}", tmp_path)
    assert "CHECK|bgp|FAIL|no BGP neighbors found (4 configured)" in out


def test_missing_config_capture_still_requires_neighbors(tmp_path):
    """An empty `nv config show` capture is not evidence of an L2 switch:
    EXP_BGP="" keeps the historical must-have-neighbors behaviour."""
    out = _bgp_python("", "{}", tmp_path)
    assert "CHECK|bgp|FAIL|no BGP neighbors found" in out
    assert "configured" not in out


def test_configured_neighbor_idle_still_fails(tmp_path):
    # Numbered peer: not subject to the unnumbered no-carrier benign skip.
    out = _bgp_python("2", _summary(("10.0.0.2", "Idle"), ("swp1s0", "Established")), tmp_path)
    assert "CHECK|bgp|FAIL|established=1/2" in out


def test_all_established_passes(tmp_path):
    out = _bgp_python("2", _summary(("swp1s0", "Established"), ("swp1s1", "Established")), tmp_path)
    assert "CHECK|bgp|PASS|neighbors=2 established=2" in out


def _render_l2_site(tmp_path):
    """Import the shipped 2-4-3-200 workbook with oob_uplink_mode=L2 and render
    its switch scripts into tmp_path (no dependency on a pre-generated site)."""
    if not shutil.which("ansible-playbook"):
        pytest.skip("ansible-playbook required")
    src = REPO / "input" / "2-4-3-200" / "default" / "2-4-3-200.xlsx"
    if not src.exists():
        pytest.skip(f"{src} not generated")
    xlsx = tmp_path / "2-4-3-200.xlsx"
    shutil.copy(src, xlsx)
    wb = openpyxl.load_workbook(xlsx)
    hit = False
    for row in wb["Deployment"].iter_rows(min_row=1):
        if row[0].value == "oob_uplink_mode":
            row[1].value = "L2"
            hit = True
    assert hit
    wb.save(xlsx)
    inv = tmp_path / "output" / "2-4-3-200" / "audit-l2" / "inventory"
    cfg = tmp_path / "output" / "2-4-3-200" / "audit-l2" / "configs"
    process_excel_template(xlsx, inv, site="audit-l2")
    cfg.mkdir(parents=True)
    res = subprocess.run(
        ["ansible-playbook", str(REPO / "playbooks" / "generate-cli-configs.yml"),
         "-i", str(inv / "hosts"), "-e", f"config_output_dir={cfg}"],
        capture_output=True, text=True, cwd=REPO, timeout=900,
        env={**os.environ, "ANSIBLE_LOCALHOST_WARNING": "false"})
    assert res.returncode == 0, res.stdout[-4000:] + res.stderr[-2000:]
    return cfg


def test_generated_l2_oob_config_has_no_bgp_neighbors(tmp_path):
    """The probe's `router bgp neighbor` grep sees zero lines on a rendered
    L2 oob-switch config (and >0 on a core), so the expectation is real."""
    cfg = _render_l2_site(tmp_path)
    oob = (cfg / "oob-switch-01-config.sh").read_text()
    core = (cfg / "core-01-config.sh").read_text()
    assert len(re.findall(r"router bgp neighbor ", oob)) == 0
    assert len(re.findall(r"router bgp neighbor ", core)) > 0
