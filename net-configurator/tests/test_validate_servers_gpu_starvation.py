# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Behavioral tests for the GPU-starvation pre-flight guard in validate-servers.yml.

The guard (`Fail when any compute node is missing GPU addresses`) must:

1. Fire before the probe fan-out, so a partly-addressed cluster cannot produce
   reassuring output before the playbook halts.
2. Count GPU addresses from *both* gpu_interfaces (rail/plane modes) and gpu_ips
   (single mode). Single-mode inventories carry only gpu_ips with no
   gpu_interfaces key, so a guard that counts only gpu_interfaces returns 0 for
   every node and fires on a perfectly healthy single-mode deployment.
3. Name the short/zero hosts in its fail_msg so an operator can act without
   hand-reading the inventory.

Each behavioral test renders the guard's Jinja2 expressions directly against
synthetic data using a plain jinja2.Environment (no Ansible extensions). This
is possible — and necessary — because the guard uses only Jinja2 builtins;
any Ansible-only filter (e.g. `extract`) would break both this test and the
guard's ability to be unit-tested without running Ansible.
"""
import ast
import yaml
import jinja2
from pathlib import Path

NC = Path(__file__).resolve().parent.parent
PLAYBOOK = NC / "playbooks" / "validate-servers.yml"
GUARD_NAME = "Fail when any compute node is missing GPU addresses"


def _load_guard():
    """Return the guard task dict from the playbook."""
    plays = yaml.safe_load(PLAYBOOK.read_text())
    return next(
        t
        for play in plays
        for t in (play.get("tasks") or [])
        if t.get("name") == GUARD_NAME
    )


def _render_guard(devices, server_groups):
    """Render the guard's _gpu_counts var and assert conditions via plain Jinja2.

    Reads expression strings from the live playbook file — never a copy — so that
    changes to the playbook are exercised automatically. Returns
    (gpu_counts: list[int], guard_passes: bool, fail_msg_template: str).

    Ansible converts a vars template that renders to a Python-literal string into
    real data. ast.literal_eval mirrors that behaviour here.
    """
    task = _load_guard()
    counts_expr = task["vars"]["_gpu_counts"]
    that_conditions = task["assert"]["that"]
    fail_msg_tmpl = task["assert"]["fail_msg"]

    env = jinja2.Environment()

    # Render _gpu_counts to a Python-literal string, then parse it.
    counts_str = env.from_string(counts_expr).render(
        server_groups=server_groups,
        devices=devices,
    )
    # ast.literal_eval mirrors Ansible's own coercion of rendered list literals.
    gpu_counts = ast.literal_eval(counts_str.strip())

    context = dict(server_groups=server_groups, devices=devices, _gpu_counts=gpu_counts)
    guard_passes = all(
        env.from_string("{{ (" + cond + ") }}").render(**context) == "True"
        for cond in that_conditions
    )
    return gpu_counts, guard_passes, fail_msg_tmpl


def _render_fail_msg(devices, server_groups, gpu_counts, fail_msg_tmpl):
    """Render the fail_msg template with the given context."""
    return jinja2.Environment().from_string(fail_msg_tmpl).render(
        server_groups=server_groups,
        devices=devices,
        _gpu_counts=gpu_counts,
    )


# ── Structural tests ───────────────────────────────────────────────────────────


def test_starvation_guard_task_exists():
    plays = yaml.safe_load(PLAYBOOK.read_text())
    names = [
        t.get("name", "")
        for play in plays
        for key in ("pre_tasks", "tasks")
        for t in (play.get(key) or [])
    ]
    assert GUARD_NAME in names, (
        f"validate-servers.yml must carry a task named {GUARD_NAME!r}. "
        f"Found: {[n for n in names if n][:10]}"
    )


def test_guard_runs_before_the_probe_fanout():
    """A guard that runs after the probe reports health for a broken
    cluster before failing, which defeats the point."""
    text = PLAYBOOK.read_text()
    assert text.index(GUARD_NAME) < text.index("srvv.XXXXXX")


# ── Behavioral tests ───────────────────────────────────────────────────────────


def test_guard_healthy_rail_mode():
    """Per-rail inventory: every compute node has 9 gpu_interfaces → guard passes."""
    devices = {
        f"su-01-node-{i:02d}": {"role": "compute", "gpu_interfaces": [{}] * 9}
        for i in range(1, 5)
    }
    server_groups = list(devices.keys())
    _, guard_passes, _ = _render_guard(devices, server_groups)
    assert guard_passes


def test_guard_healthy_single_mode():
    """Regression test for Finding 1 (task brief Step 4 defect).

    Single-mode inventories carry gpu_ips with no gpu_interfaces key at all.
    A guard that only counts gpu_interfaces sees 0 for every node and fires on a
    healthy deployment. The corrected guard must count gpu_ips when gpu_interfaces
    is absent and must therefore pass here.
    """
    devices = {
        f"su-01-node-{i:02d}": {
            "role": "compute",
            "gpu_ips": ["10.0.0.1/24", "10.0.1.1/24"],
            # no gpu_interfaces key — this is the single-mode invariant
        }
        for i in range(1, 5)
    }
    server_groups = list(devices.keys())
    _, guard_passes, _ = _render_guard(devices, server_groups)
    assert guard_passes, (
        "guard must pass for a healthy single-mode (gpu_ips only) inventory; "
        "if it fires here the guard is counting only gpu_interfaces"
    )


def test_guard_partial_starvation_fails_and_names_hosts():
    """Some nodes healthy, some starved → guard fires; starved hostnames in fail_msg."""
    devices = {
        "su-01-node-01": {"role": "compute", "gpu_interfaces": [{}] * 9},
        "su-01-node-02": {"role": "compute", "gpu_interfaces": []},  # starved
        "su-01-node-03": {"role": "compute", "gpu_interfaces": [{}] * 9},
        "su-01-node-04": {"role": "compute", "gpu_interfaces": []},  # starved
    }
    server_groups = list(devices.keys())
    gpu_counts, guard_passes, fail_msg_tmpl = _render_guard(devices, server_groups)
    assert not guard_passes, "guard must fire when some nodes are starved"
    msg = _render_fail_msg(devices, server_groups, gpu_counts, fail_msg_tmpl)
    assert "su-01-node-02" in msg, f"starved host missing from fail_msg: {msg!r}"
    assert "su-01-node-04" in msg, f"starved host missing from fail_msg: {msg!r}"
    assert "=0" in msg, f"zero count missing from fail_msg: {msg!r}"


def test_guard_uniform_starvation_fails():
    """Every compute node holds zero GPU addresses → guard fires."""
    devices = {
        f"su-01-node-{i:02d}": {"role": "compute", "gpu_interfaces": []}
        for i in range(1, 4)
    }
    server_groups = list(devices.keys())
    _, guard_passes, _ = _render_guard(devices, server_groups)
    assert not guard_passes


def test_guard_no_compute_nodes_passes():
    """No compute nodes → guard passes (min of empty list must not raise)."""
    devices = {
        "su-01-storage-01": {"role": "storage", "bond_ip1": "10.0.0.1/24"},
    }
    server_groups = list(devices.keys())
    gpu_counts, guard_passes, _ = _render_guard(devices, server_groups)
    assert gpu_counts == [], f"expected empty counts list, got {gpu_counts}"
    assert guard_passes


def test_guard_short_but_nonzero_fails_and_names_host():
    """One node 8 while the rest hold 9 → guard fires; short node named in fail_msg."""
    devices = {
        "su-01-node-01": {"role": "compute", "gpu_interfaces": [{}] * 9},
        "su-01-node-02": {"role": "compute", "gpu_interfaces": [{}] * 8},  # short
        "su-01-node-03": {"role": "compute", "gpu_interfaces": [{}] * 9},
    }
    server_groups = list(devices.keys())
    gpu_counts, guard_passes, fail_msg_tmpl = _render_guard(devices, server_groups)
    assert not guard_passes, "guard must fire when counts are non-uniform"
    msg = _render_fail_msg(devices, server_groups, gpu_counts, fail_msg_tmpl)
    assert "su-01-node-02" in msg, f"short host missing from fail_msg: {msg!r}"
    assert "=8" in msg, f"short count missing from fail_msg: {msg!r}"


def test_success_msg_does_not_report_zero_when_there_are_no_compute_nodes():
    """A cluster with no compute nodes passes the guard, and the success message
    must not read like starvation. `_gpu_counts | first | default(0)` rendered
    'All compute nodes hold 0 GPU address(es).' on a healthy pass."""
    devices = {"su-01-storage-01": {"role": "storage"}}
    server_groups = list(devices.keys())
    gpu_counts, guard_passes, _ = _render_guard(devices, server_groups)
    assert guard_passes
    msg = jinja2.Environment().from_string(_load_guard()["assert"]["success_msg"]).render(
        server_groups=server_groups, devices=devices, _gpu_counts=gpu_counts
    )
    assert "hold 0" not in msg, f"success_msg reads like starvation on a pass: {msg!r}"
    assert "no compute nodes" in msg.lower(), f"unexpected success_msg: {msg!r}"


def test_guard_absent_host_no_exception():
    """A host named in server_groups but absent from devices → no exception."""
    devices = {
        "su-01-node-01": {"role": "compute", "gpu_interfaces": [{}] * 9},
    }
    # devices.get(h, {}) returns {} for the ghost host; role check excludes it.
    server_groups = ["su-01-node-01", "su-01-node-ghost"]
    _, guard_passes, _ = _render_guard(devices, server_groups)
    assert guard_passes
