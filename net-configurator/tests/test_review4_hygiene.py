# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Release review #4 F12, F13, F16 (GitLab #107 / ERA-164).

F12: every YAML file opens with `---` and carries its SPDX header on the two
lines after it (AGENTS.md "Licensing Requirements"), including the group_vars
the generator writes and the secrets template it copies.
F13: NOTICE names every package a user installs through `make setup`, and
certifi, which README tells macOS users to install.
F16: no unused role, airlib API function or `validate_*` check is shipped.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import inventory_defaults  # noqa: E402

# REUSE-IgnoreStart
SPDX = [
    "# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.",
    "# SPDX-License-Identifier: MIT",
]
# REUSE-IgnoreEnd


def _tracked(*patterns):
    proc = subprocess.run(["git", "ls-files", "-z", "--", *patterns],
                          cwd=REPO, capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode()
    return sorted(p for p in proc.stdout.decode().split("\0") if p)


YAML = _tracked("*.yml", "*.yaml", "*.yml.example")


def _yaml_head_problem(text):
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return "line 1 is not '---'"
    if any("SPDX-" in line for line in lines[:12]) and lines[1:3] != SPDX:
        return "SPDX header is not on lines 2-3"
    return None


def test_yaml_inventory_is_what_we_expect():
    assert len(YAML) > 400, len(YAML)
    assert "inventories/secrets.yml" in YAML
    assert "output/2-8-9-800/default/inventory/group_vars/servers.yml" in YAML


def test_every_yaml_file_opens_with_document_marker_then_spdx():
    bad = {}
    for rel in YAML:
        problem = _yaml_head_problem((REPO / rel).read_text(encoding="utf-8"))
        if problem:
            bad[rel] = problem
    assert not bad, "\n".join(f"{k}: {v}" for k, v in sorted(bad.items()))


@pytest.mark.parametrize("name", ["SWITCHES_GROUP_VARS", "SERVERS_GROUP_VARS"])
def test_generator_group_vars_open_with_document_marker(name):
    assert _yaml_head_problem(vars(inventory_defaults)[name]) is None


@pytest.mark.parametrize("text, problem", [
    ("\n".join(SPDX) + "\nkey: 1\n", "line 1 is not '---'"),
    ("\n".join(SPDX) + "\n---\nkey: 1\n", "line 1 is not '---'"),
    ("---\n# comment\n" + "\n".join(SPDX) + "\n", "SPDX header is not on lines 2-3"),
    ("---\n" + "\n".join(SPDX) + "\nkey: 1\n", None),
    ("---\nkey: 1\n", None),
])
def test_yaml_head_check_discriminates(text, problem):
    assert _yaml_head_problem(text) == problem


def _requirement_names(path):
    names = set()
    for line in (REPO / path).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            names.add(re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0].lower())
    return names


NOTICE_ENTRY = re.compile(r"^ {4}(\S+) +(\S+)$", re.MULTILINE)


def test_notice_lists_every_installed_package_with_a_license():
    listed = {m.group(1).lower(): m.group(2)
              for m in NOTICE_ENTRY.finditer((REPO / "NOTICE").read_text())}
    wanted = (_requirement_names("requirements.txt")
              | _requirement_names("tests/requirements.txt"))
    assert "yamllint" in wanted and "flake8" in wanted
    assert sorted(wanted - listed.keys()) == []
    assert listed["yamllint"] == "GPL-3.0-or-later"


def test_notice_lists_certifi_while_readme_recommends_it():
    if "pip install certifi" in (REPO / "README.md").read_text():
        assert re.search(r"^ {4}certifi +MPL-2\.0$",
                         (REPO / "NOTICE").read_text(), re.MULTILINE)


def test_make_setup_installs_the_test_requirements_notice_covers():
    assert "-r tests/requirements.txt" in (REPO / "Makefile").read_text()


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


ROLE_ACTIONS = {"include_role", "import_role",
                "ansible.builtin.include_role", "ansible.builtin.import_role"}
ROLE_PATH = re.compile(r"roles/([A-Za-z0-9_.-]+)/")


def _roles_used_by_playbooks():
    used = set()
    for path in sorted((REPO / "playbooks").glob("*.yml")):
        for node in _walk(yaml.safe_load(path.read_text(encoding="utf-8"))):
            for entry in node.get("roles") or []:
                used.add(entry if isinstance(entry, str)
                         else entry.get("role") or entry.get("name"))
            for action in ROLE_ACTIONS & node.keys():
                used.add(node[action]["name"])
            for value in node.values():
                if isinstance(value, str):
                    used.update(ROLE_PATH.findall(value))
    return used


def test_role_usage_scan_ignores_task_names_and_comments():
    assert _roles_used_by_playbooks() >= {"ldap", "ztp-server", "core", "nodes"}
    play = yaml.safe_load(
        "- hosts: all\n  tasks:\n    - name: core\n      debug: {msg: x}\n")
    assert not any("roles" in n or ROLE_ACTIONS & n.keys() for n in _walk(play))


@pytest.mark.parametrize("role", sorted(
    p.name for p in (REPO / "roles").iterdir() if p.is_dir()))
def test_every_role_is_used(role):
    assert role in _roles_used_by_playbooks(), (
        f"roles/{role} is not declared, included or templated by any playbook")


def _top_level_defs(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))
            and not n.name.startswith("_")}


def _code_refs(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Name):
            yield node.id, node.lineno
        elif isinstance(node, ast.Attribute):
            yield node.attr, node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                yield alias.name, node.lineno


SCRIPTS_PY = sorted(REPO.glob("scripts/**/*.py"))


def _used_outside_own_body(name, def_path, def_node, sources=SCRIPTS_PY):
    """True when code (not comments, strings or the definition itself)
    names *name* somewhere in *sources*."""
    own = range(def_node.lineno, def_node.end_lineno + 1)
    return any(ref == name and not (path == def_path and line in own)
               for path in sources for ref, line in _code_refs(path))


def test_usage_scan_ignores_self_references_comments_and_strings(tmp_path):
    src = tmp_path / "m.py"
    src.write_text(
        "class K:\n"
        "    @classmethod\n"
        "    def make(cls) -> 'K':\n"
        "        return cls()\n"
        "def f():\n"
        "    return f\n"
        "# K and f are mentioned here\n"
        "DOC = 'K f'\n"
        "def g():\n"
        "    return K\n")
    defs = _top_level_defs(src)
    assert not _used_outside_own_body("f", src, defs["f"], [src])
    assert _used_outside_own_body("K", src, defs["K"], [src])
    assert not _used_outside_own_body("g", src, defs["g"], [src])


AIR_API = REPO / "scripts" / "airlib" / "api.py"
AIR_API_DEFS = _top_level_defs(AIR_API)
# The user-config (cloud-init) writer is covered by tests and kept for the
# first-boot wait-online work; air-destroy already cleans up what it creates.
AIR_API_PENDING_ADOPTION = {"create_userconfig", "assign_node_userconfigs"}


@pytest.mark.parametrize("name", sorted(AIR_API_DEFS.keys() - AIR_API_PENDING_ADOPTION))
def test_every_airlib_api_name_is_used(name):
    assert _used_outside_own_body(name, AIR_API, AIR_API_DEFS[name]), (
        f"airlib.api.{name} is never called")


VALIDATOR = REPO / "scripts" / "validate_excel.py"
VALIDATOR_DEFS = _top_level_defs(VALIDATOR)


@pytest.mark.parametrize("name", sorted(
    n for n in VALIDATOR_DEFS if n.startswith("validate_")))
def test_every_validator_check_is_called(name):
    assert _used_outside_own_body(name, VALIDATOR, VALIDATOR_DEFS[name]), (
        f"{name} is defined but never called")


def test_no_if_false_dead_branches_in_scripts():
    hits = [f"{p.relative_to(REPO)}:{i}"
            for p in REPO.glob("scripts/**/*.py")
            for i, line in enumerate(p.read_text().splitlines(), 1)
            if re.search(r"\bif False\b", line)]
    assert hits == []
