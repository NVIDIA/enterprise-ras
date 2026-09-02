# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Every playbook must still LOAD. Nothing here checks that a playbook is correct.

The bug this exists for: an apostrophe inside a shell comment.

    # we don't need the old workdir

Ansible tokenizes a free-form module argument with `split_args()`, which tracks quote
balance and has no idea `#` started a comment. One apostrophe makes the whole task
unparseable, and the playbook fails to load *for every deployment* -- not at the task,
but before the run starts. It is invisible to review (the shell is correct), invisible
to yamllint (the YAML is valid), and invisible to the test suite (nothing imports a
playbook). It shipped once and was found only by bisecting with split_args by hand.

Two checks, because one does not cover the other:

* `--syntax-check` per playbook. Catches playbook-level tasks AND statically included
  roles (`roles:`), plus unknown modules and malformed task structure.
* `split_args` per role task file. `--syntax-check` does NOT reach a role pulled in with
  `include_role`, which is dynamic and resolved at runtime -- verified, not assumed:
  the same injected apostrophe is caught in `roles/oob-server` (static, via
  setup-oob-server.yml) and missed in `roles/ldap` (dynamic, via era-servers.yml).
  Since role tasks are where most of the shell lives, that hole is most of the risk.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PLAYBOOK_DIR = PROJECT_ROOT / "playbooks"
ROLES_DIR = PROJECT_ROOT / "roles"

# Modules whose argument may be a bare string, which is what split_args() tokenizes.
FREE_FORM = {
    "shell", "command", "raw", "script",
    "ansible.builtin.shell", "ansible.builtin.command",
    "ansible.builtin.raw", "ansible.builtin.script",
}


def _playbooks():
    return sorted(PLAYBOOK_DIR.glob("*.yml"))


def _role_task_files():
    """tasks/ and handlers/ both. A handler is a task -- `command: netplan apply` in a
    handler breaks the same way, and handlers are if anything less exercised."""
    return sorted([*ROLES_DIR.glob("*/tasks/*.yml"), *ROLES_DIR.glob("*/handlers/*.yml")])


def _require_ansible():
    """Missing ansible must not quietly turn this file into zero assertions.

    Locally that is a fair skip -- ansible is a runtime dep, not a test dep. In CI it
    means the job installed requirements.txt and got nothing, so the guard would report
    green while checking nothing. That is the failure mode this whole file exists to
    prevent, so CI fails instead.
    """
    if shutil.which("ansible-playbook"):
        return
    if os.environ.get("CI"):
        pytest.fail("ansible-playbook missing in CI -- this guard would silently no-op")
    pytest.skip("ansible-playbook not installed (it is in requirements.txt)")


def _free_form_args(node):
    """Yield every bare-string free-form module arg, recursing through block/rescue."""
    if isinstance(node, list):
        for item in node:
            yield from _free_form_args(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key in FREE_FORM and isinstance(value, str):
                yield value
            elif isinstance(value, (list, dict)):
                yield from _free_form_args(value)


@pytest.mark.parametrize("playbook", _playbooks(), ids=lambda p: p.name)
def test_playbook_passes_ansible_syntax_check(playbook):
    _require_ansible()
    # ANSIBLE_CONFIG must be explicit. Ansible refuses to auto-discover ansible.cfg from
    # a world-writable cwd, which is exactly what a GitLab runner's build dir is -- so
    # roles_path (./roles) went unset in CI and both statically-included roles failed to
    # resolve, while passing locally. Pointing at the file the tool actually uses is also
    # the more faithful check.
    env = {**os.environ, "ANSIBLE_CONFIG": str(PROJECT_ROOT / "ansible.cfg")}
    result = subprocess.run(
        ["ansible-playbook", "--syntax-check", "-i", "localhost,", str(playbook)],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, (
        f"{playbook.name} does not load:\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.parametrize("task_file", _role_task_files(),
                         ids=lambda p: f"{p.parents[1].name}/{p.parent.name}/{p.name}")
def test_role_task_args_split_cleanly(task_file):
    """Closes the include_role blind spot that --syntax-check leaves open."""
    _require_ansible()
    import yaml
    from ansible.parsing.splitter import split_args

    tasks = yaml.safe_load(task_file.read_text())
    if not tasks:
        pytest.skip(f"{task_file} is empty")

    for arg in _free_form_args(tasks):
        try:
            split_args(arg)
        except Exception as exc:  # AnsibleParserError, but do not import for one name
            first = next((ln for ln in arg.splitlines() if "'" in ln or '"' in ln), "")
            pytest.fail(
                f"{task_file.relative_to(PROJECT_ROOT)} has an unsplittable argument: "
                f"{exc}\nLikely line: {first.strip()!r}\n"
                "A lone apostrophe (often in a comment) unbalances the quote tracker.")


def test_the_gate_actually_covers_the_tree():
    """A glob that silently matches nothing is a green test that checks nothing.

    Counts come from git, not from the globs above, so narrowing a glob fails here
    instead of quietly shrinking coverage.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "playbooks/*.yml",
         "roles/*/tasks/*.yml", "roles/*/handlers/*.yml"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if tracked.returncode != 0:
        pytest.skip("not a git checkout")

    listed = {ln for ln in tracked.stdout.split() if ln}
    # git's pathspec recurses; glob("*.yml") does not. playbooks/vars/air_proxy.yml is
    # a vars file, not a play -- syntax-checking it as one is meaningless.
    expected_playbooks = {p for p in listed
                          if p.startswith("playbooks/") and p.count("/") == 1}
    expected_roles = {p for p in listed if p.startswith("roles/")}

    actual_playbooks = {str(p.relative_to(PROJECT_ROOT)) for p in _playbooks()}
    actual_roles = {str(p.relative_to(PROJECT_ROOT)) for p in _role_task_files()}

    assert actual_playbooks == expected_playbooks, "playbook coverage drifted from git"
    assert actual_roles == expected_roles, "role task coverage drifted from git"
    assert len(expected_playbooks) >= 16, "playbooks vanished -- glob or tree is wrong"
