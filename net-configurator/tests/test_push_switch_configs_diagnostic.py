# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""A bootstrap failure must accuse the thing the evidence implicates (ADR-0052).

`push-switch-configs` probes the switch from LOCALHOST (see the playbook header),
which is correct for a physically-cabled deployment and impossible for NVIDIA Air —
Air switches live on 172.20.0.x behind the jump host, and this playbook never loads
`playbooks/vars/air_proxy.yml`.

Before this split, an unreachable switch produced:

    could not log in with switch_ansible_password after bootstrap.
    Set switch_bootstrap_password to the password currently on the switch

On 2026-08-17 that sent me chasing a credential that was never wrong, across all six
switches of an Air sim. ssh exits 255 with a connect error; a real auth failure exits
5 with "Permission denied" — the playbook has the evidence, it just has to look.
"""
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

PLAYBOOK = Path(__file__).resolve().parent.parent / "playbooks" / "push-switch-configs.yml"

# The classifier regex, kept in step with the playbook by the test below.
UNREACHABLE_RE = (r"(?i)(network is unreachable|connection timed out|no route to host"
                  r"|connection refused|could not resolve)")


def _tasks():
    doc = yaml.safe_load(PLAYBOOK.read_text())
    return [t for play in doc for t in play.get("tasks", [])]


def _task(name_fragment):
    for t in _tasks():
        if name_fragment.lower() in (t.get("name") or "").lower():
            return t
    return None


def test_both_failure_modes_have_their_own_task():
    assert _task("unreachable from the controller"), "no reachability-specific failure"
    assert _task("target password still does not work"), "no credential-specific failure"


def test_the_two_failures_are_mutually_exclusive():
    """Exactly one must fire, or the operator gets contradictory advice."""
    unreach = _task("unreachable from the controller")
    creds = _task("target password still does not work")
    u = " ".join(str(c) for c in unreach["when"])
    c = " ".join(str(x) for x in creds["when"])
    assert "_probe_unreachable" in u and "not (" in c, (
        f"guards are not complementary:\n  unreachable: {u}\n  credentials: {c}"
    )


def test_reachability_message_does_not_blame_the_password():
    msg = _task("unreachable from the controller")["ansible.builtin.fail"]["msg"]
    assert "switch_bootstrap_password" not in msg, (
        "the unreachable path must not tell the operator to change a password that "
        "was never tested"
    )
    assert "jump host" in msg and "NOZTP" in msg, (
        "it should name the actual cause and the Air-supported alternatives"
    )


def test_credential_message_states_the_switch_was_reachable():
    msg = _task("target password still does not work")["ansible.builtin.fail"]["msg"]
    assert "reachable over SSH" in msg, (
        "the credential path should say reachability was established, so the operator "
        "knows the password really is the problem"
    )


@pytest.mark.parametrize("stderr,expect_unreachable", [
    ("ssh: connect to host 172.20.0.201 port 22: Connection timed out", True),
    ("ssh: connect to host 172.20.0.201 port 22: Network is unreachable", True),
    ("ssh: connect to host sw1 port 22: No route to host", True),
    ("Permission denied, please try again.", False),
    ("cumulus@10.0.0.1: Permission denied (publickey,password).", False),
    ("", False),
])
def test_classifier_separates_real_stderr(stderr, expect_unreachable):
    """The first two strings are verbatim from the 2026-08-17 Air failure."""
    assert bool(re.search(UNREACHABLE_RE, stderr)) is expect_unreachable


def test_playbook_regex_matches_this_test():
    """If the playbook regex drifts, this test is asserting nothing."""
    text = PLAYBOOK.read_text()
    for token in ("network is unreachable", "connection timed out", "no route to host",
                  "connection refused", "could not resolve"):
        assert token in text, f"playbook classifier lost {token!r}"


def _push_play_task_names():
    doc = yaml.safe_load(PLAYBOOK.read_text())
    for play in doc:
        if play.get("name") == "Push config and apply (with confirm)":
            return [t.get("name") for t in play.get("tasks", [])]
    raise AssertionError("push play not found")


def test_password_is_staged_after_the_generated_script():
    """Generated *-config.sh sets aaa user role/name and never password.

    Staging the password first is a no-op: the script's later
    `nv set system aaa user` lines replace the user object and apply
    drops Linux SSH. Password must be the last nv set before apply.
    """
    names = _push_play_task_names()
    script_name = "Run config script (stage NVUE changes)"
    stage_name = "Stage switch password in NVUE"
    apply_name = "Apply staged config"
    for task_name in (script_name, stage_name, apply_name):
        assert task_name in names, names
    script = names.index(script_name)
    stage = names.index(stage_name)
    apply = names.index(apply_name)
    assert script < stage < apply, names


def test_confirm_play_cannot_reuse_ssh_mux():
    """ControlPersist made Play 3 look green after apply dropped the password."""
    names = _push_play_task_names()
    reset_name = "Drop SSH mux so confirm re-authenticates"
    apply_name = "Apply staged config"
    assert reset_name in names, names
    assert apply_name in names, names
    assert names.index(reset_name) > names.index(apply_name), names
