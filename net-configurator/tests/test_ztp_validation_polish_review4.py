# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Release review #4 F8-F10 (GitLab #105).

F8: ``make validate-topology`` warned ``Extra node: ext-storage-0N`` on the
    shipped default sites. The generator makes a node for every valid A-side
    hostname; the validator only counted A-sides that had a System Role, and
    ext-storage rows have none.
F9: ``validate-ztp-direct`` collected BGP/EVPN on gl/gs/cl/cs switches, but the
    report printed those lines only for core/csl/gsl.
F10: the ztp-server role hard-coded the ``netadmin`` account and its home path.
"""
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

NC = Path(__file__).resolve().parent.parent
SCRIPTS = NC / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _valid_archs import VALID_ARCHS  # noqa: E402
from topology_generator import TopologyGenerator, TopologyValidator  # noqa: E402

PLAYBOOK = NC / "playbooks" / "validate-ztp-direct.yml"
ROLE = NC / "roles" / "ztp-server"
STARTUP = "/etc/nvue.d/startup.yaml"

needs_ansible = pytest.mark.skipif(not shutil.which("ansible-playbook"),
                                   reason="ansible-playbook required")


# --- F8 ---------------------------------------------------------------------

@pytest.mark.parametrize("arch", VALID_ARCHS)
def test_shipped_default_site_topology_validates_without_warnings(tmp_path, arch):
    excel = NC / "input" / arch / "default" / f"{arch}.xlsx"
    topo_path = tmp_path / "topology.json"
    topo_path.write_text(json.dumps(TopologyGenerator(excel, arch).generate()))
    validator = TopologyValidator(excel, topo_path, arch)
    assert validator.validate() is True, validator.errors
    assert validator.warnings == []


def test_ext_storage_rows_are_expected_nodes():
    excel = NC / "input" / "2-8-5-200" / "default" / "2-8-5-200.xlsx"
    topo = TopologyGenerator(excel, "2-8-5-200").generate()
    ext = {n for n in topo["content"]["nodes"] if n.startswith("ext-storage-")}
    assert ext == {"ext-storage-01", "ext-storage-02"}


@pytest.mark.parametrize("role,expected", [("NA", False), ("OUTBOUND", False), ("", True)])
def test_validator_b_side_rule_matches_generator(tmp_path, role, expected):
    excel = NC / "input" / "2-8-5-200" / "default" / "2-8-5-200.xlsx"
    gen = TopologyGenerator(excel, "2-8-5-200")
    extra = copy.copy(next(r for r in gen.rows if r.enabled and r.display_in_air))
    extra.switch_name, extra.switch_role = "edge-peer-01", role
    gen.rows.append(extra)
    nodes = gen._build_nodes()
    assert ("edge-peer-01" in nodes) is expected
    topo_path = tmp_path / "topology.json"
    topo_path.write_text(json.dumps(gen.generate()))
    validator = TopologyValidator(excel, topo_path, "2-8-5-200")
    validator.rows.append(extra)
    validator._check_nodes(nodes)
    assert not [m for m in validator.errors + validator.warnings if "edge-peer-01" in m]


# --- F9 ---------------------------------------------------------------------

def _stub(path, body):
    path.write_text(body)
    path.chmod(0o755)


def _run_direct_validation(tmp_path, hostname, group, parent=None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir / "hostname", f"#!/bin/bash\necho {hostname}\n")
    _stub(bin_dir / "nv", "#!/bin/bash\n"
          'case "$*" in\n'
          "  *'router bgp'*) printf 'state                  Established\\n"
          "configured-neighbors   4\\nestablished-neighbors  4\\n' ;;\n"
          "  *'show evpn --output json'*) echo '{\"l2vni-count\": 3, \"l3vni-count\": 1}' ;;\n"
          "  *'config show'*) echo '%s' ;;\n"
          "  *) : ;;\n"
          "esac\n" % json.dumps({"system": {"hostname": hostname}}))
    _stub(bin_dir / "jq", f"#!{sys.executable}\nimport json, sys\n"
          "doc = json.load(sys.stdin)\n"
          "if sys.argv[1:] == ['-r', '.system.hostname']:\n"
          "    print(doc['system']['hostname'])\n"
          "else:\n"
          "    print(doc.get('l2vni-count', 0)); print(doc.get('l3vni-count', 0))\n")
    startup = tmp_path / "startup.yaml"
    startup.write_text("- set: {}\n")
    text = PLAYBOOK.read_text()
    assert text.count(STARTUP) == 1
    (tmp_path / "play.yml").write_text(text.replace(STARTUP, str(startup)))
    hosts = (f"[{group}]\n{hostname} ansible_host=127.0.0.1 ansible_connection=local "
             f"ansible_python_interpreter={sys.executable} hostname={hostname}\n")
    top = group
    if parent:
        hosts += f"[{parent}:children]\n{group}\n"
        top = parent
    hosts += f"[switches:children]\n{top}\n"
    (tmp_path / "hosts").write_text(hosts)
    report = tmp_path / "report.txt"
    env = {"PATH": f"{bin_dir}:{Path(sys.executable).parent}:/usr/bin:/bin",
           "HOME": str(tmp_path), "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-tmp")}
    r = subprocess.run(["ansible-playbook", "-i", str(tmp_path / "hosts"), str(tmp_path / "play.yml"),
                        "-e", json.dumps({"report_file": str(report)})],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:]
    return report.read_text()


@needs_ansible
@pytest.mark.parametrize("hostname,group,parent", [
    ("gl-plane1-01", "gl_plane1", "gl"),
    ("gs-plane2-01", "gs_plane2", None),
    ("gsl-plane1-01", "gsl_plane1", "gsl"),
    ("core-01", "core", None),
    ("csl-01", "csl", None),
], ids=["gl", "gs", "gsl", "core", "csl"])
def test_report_shows_bgp_and_evpn_for_every_routed_role(tmp_path, hostname, group, parent):
    report = _run_direct_validation(tmp_path, hostname, group, parent)
    assert "BGP State:                Established" in report
    assert "BGP Established Neighbors:4" in report
    assert "EVPN L2 VNIs:             3" in report
    assert "EVPN L3 VNIs:             1" in report


@needs_ansible
def test_report_has_no_bgp_lines_for_oob_switch(tmp_path):
    report = _run_direct_validation(tmp_path, "oob-switch-01", "oob_switch")
    assert "Status:                   PASSED" in report
    assert "BGP State" not in report


def test_routed_group_list_covers_every_generated_switch_group():
    play = yaml.safe_load(PLAYBOOK.read_text())[0]
    groups = set(play["vars"]["l3_switch_groups"])
    assert {"core", "csl", "gsl", "gsl_plane1", "gsl_plane2", "gl", "gl_plane1",
            "gl_plane2", "gs", "gs_plane1", "gs_plane2", "cl", "cs"} <= groups
    assert "oob_switch" not in groups and "oob" not in groups


# --- F10 --------------------------------------------------------------------

def _role_tasks():
    return yaml.safe_load((ROLE / "tasks" / "main.yml").read_text())


def test_ztp_server_user_is_a_role_default():
    defaults = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text())
    assert defaults["ztp_server_user"] == "netadmin"


def test_role_tasks_do_not_hard_code_the_account():
    text = (ROLE / "tasks" / "main.yml").read_text()
    assert "netadmin" not in text
    tasks = _role_tasks()
    user_task = next(t for t in tasks if "user" in t and t["user"].get("generate_ssh_key"))
    assert user_task["user"]["name"] == "{{ ztp_server_user }}"
    slurp = next(t for t in tasks if "slurp" in t and t.get("register") == "ztp_server_pubkey")
    assert slurp["slurp"]["src"].startswith("{{ " + user_task["register"] + ".ssh_key_file | default(")
    assert "ztp_server_user" in slurp["slurp"]["src"]


def _run_user_check(tmp_path, value):
    check = next(t for t in _role_tasks() if t.get("name") == "Check the ZTP server user name")
    (tmp_path / "play.yml").write_text(yaml.safe_dump(
        [{"hosts": "localhost", "gather_facts": False, "tasks": [check]}]))
    env = {"PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin", "HOME": str(tmp_path),
           "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-tmp")}
    return subprocess.run(
        ["ansible-playbook", "-i", "localhost,", "-c", "local", str(tmp_path / "play.yml"),
         "-e", json.dumps({"ztp_server_user": value,
                           "ansible_python_interpreter": sys.executable})],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


@needs_ansible
@pytest.mark.parametrize("value", ["netadmin", "ztp_ops", "_svc-1"])
def test_valid_ztp_server_user_is_accepted(tmp_path, value):
    r = _run_user_check(tmp_path, value)
    assert r.returncode == 0, r.stdout[-2000:]


@needs_ansible
@pytest.mark.parametrize("value", ["", "NetAdmin", "1ops", "ops;id", "../root", "a" * 33, "ops admin"])
def test_invalid_ztp_server_user_is_refused(tmp_path, value):
    r = _run_user_check(tmp_path, value)
    assert r.returncode != 0
    assert "not a valid Linux user name" in r.stdout
