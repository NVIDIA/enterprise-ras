# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Regression guard for GitLab #77: validate-ping-matrix must fail closed.

At SU32 (136 servers) the collect phase fanned out 136 concurrent SSH
sessions from one jump host; the tail of the loop timed out, was folded into
NODATA, and the playbook — which had no failure condition at all — exited 0
with 38/136 servers unmeasured. The Makefile target then discarded the
playbook's exit status as well.

These tests exercise the tally/fail expressions from the playbook against a
synthetic collect_results (with the Ansible filters/tests they use shimmed on
plain Jinja2, so no ansible install is needed) and assert the structural
markers: batched collection, FETCHFAIL vs NODATA, a fail task, and a Makefile
that propagates the exit code.
"""
import re
from pathlib import Path

import jinja2
import yaml

REPO = Path(__file__).resolve().parent.parent
PLAYBOOK = REPO / "playbooks" / "validate-ping-matrix.yml"


def _env():
    env = jinja2.Environment()
    env.tests["match"] = lambda v, p: re.match(p, v) is not None
    env.tests["search"] = lambda v, p: re.search(p, v) is not None
    env.filters["split"] = lambda s, sep=None: s.split(sep)
    # Ansible's `difference` is set-based and returns an arbitrary order —
    # sort here so a test can never encode an ordering the real filter does
    # not promise (verified against ansible-core 2.21.4rc1).
    env.filters["difference"] = lambda a, b: sorted(set(a) - set(b))
    return env


def _tasks():
    return yaml.safe_load(PLAYBOOK.read_text())[0]["tasks"]


def _task(prefix):
    matches = [t for t in _tasks() if t["name"].startswith(prefix)]
    assert matches, f"no task starting with {prefix!r}"
    return matches[0]


def _tally(stdout_lines, server_groups):
    env = _env()
    ctx = {
        "server_groups": server_groups,
        "local_report": "/tmp/r.txt",
        "collect_results": {"stdout_lines": stdout_lines},
    }
    for t in _tasks():
        if t["name"].startswith("Tally"):
            for key, expr in t["set_fact"].items():
                body = expr.strip()
                assert body.startswith("{{") and body.endswith("}}")
                ctx[key] = env.compile_expression(body[2:-2])(**ctx)
    fail = _task("Fail if")
    ctx["_fails"] = env.compile_expression(fail["when"])(**ctx)
    ctx["_msg"] = env.from_string(fail["fail"]["msg"]).render(**ctx)
    return ctx


LINES = [
    "FROM:a|PASS|bond0(1.1.1.1)|b|1.1.1.2|INBAND",
    "FROM:a|FAIL|bond0(1.1.1.1)|c|1.1.1.3|CROSS-VRF",   # expected
    "FROM:a|FAIL|bond0(1.1.1.1)|d|1.1.1.4|INBAND",      # unexpected
    "FROM:b|PASS|bond0(1.1.1.2)|c|1.1.1.3|CROSS-VRF",   # VRF leak
    "COLLECT|c|FETCHFAIL|timeout after 15s",
    "COLLECT|d|NODATA|no results file (script never ran or was not fired)",
]


def test_tally_distinguishes_fetchfail_from_nodata_and_fails():
    ctx = _tally(LINES, ["a", "b", "c", "d", "e"])
    assert ctx["pm_fetchfail"] == ["c"]
    assert ctx["pm_reported"] == ["a", "b"]
    # c (fetch failed), d (no DONE) and e (never even echoed a line) all count.
    assert sorted(ctx["pm_unreported"]) == ["c", "d", "e"]
    assert ctx["pm_unexpected"] == [LINES[2], LINES[3]]
    assert ctx["_fails"] is True
    assert "3/5 server(s) did not report" in ctx["_msg"]
    assert "1 fetch failures" in ctx["_msg"]


def test_clean_run_does_not_fail():
    lines = [
        "FROM:a|PASS|bond0(1.1.1.1)|b|1.1.1.2|INBAND",
        "FROM:a|FAIL|bond0(1.1.1.1)|c|1.1.1.3|CROSS-VRF",
        "FROM:b|PASS|bond0(1.1.1.2)|a|1.1.1.1|INBAND",
        "FROM:c|PASS|bond0(1.1.1.3)|a|1.1.1.1|INBAND",
    ]
    ctx = _tally(lines, ["a", "b", "c"])
    assert ctx["pm_unreported"] == []
    assert ctx["pm_unexpected"] == []
    assert ctx["_fails"] is False


def test_single_nodata_fails_even_when_everything_else_passes():
    lines = [
        "FROM:a|PASS|bond0(1.1.1.1)|b|1.1.1.2|INBAND",
        "COLLECT|b|NODATA|no results file (script never ran or was not fired)",
    ]
    ctx = _tally(lines, ["a", "b"])
    assert ctx["_fails"] is True


def test_collect_is_batched():
    env = _env()
    shell = _task("Collect results")["shell"]
    n = 70
    servers = [f"s{i}" for i in range(n)]
    out = env.from_string(shell).render(
        server_groups=servers,
        hostvars={s: {"ansible_host": "10.0.0.1"} for s in servers},
        server_ansible_password="x",  # pragma: allowlist secret
        collect_batch_size=32,
        pm_run_token="TOKEN",
    )
    assert len(re.findall(r"^collect '.+' '.+' &$", out, re.M)) == n
    assert out.count("collect() {") == 1, "the body must be emitted once"
    # A wait after each full batch of 32 (2 for 70 servers) plus the final one.
    assert len(re.findall(r"^\s*wait\s*$", out, re.M)) == 3
    # Every non-result outcome is named, so the report can say which it was.
    assert "FETCHFAIL|timeout after 15s" in out
    assert "FETCHFAIL|ssh rc=255 (connection failed)" in out
    assert "FETCHFAIL|sshpass rc=$RC" in out
    assert "NODATA|no results file" in out
    assert "NODATA|no marker for this run" in out


def test_rendered_collect_script_fits_in_one_exec_argument():
    """The collect body is emitted once, not per server.

    Ansible hands `shell:` to `/bin/sh -c <script>` as a single argv entry,
    and Linux caps one entry at MAX_ARG_STRLEN (128 KB). Inlining the
    classification per server rendered 157 KB at SU32 and execve refused the
    whole task with "[Errno 7] Argument list too long" before one server was
    contacted — a failure no smaller arch reaches. Budget generously: at 136
    servers the function form is ~7 KB.
    """
    MAX_ARG_STRLEN = 128 * 1024
    servers = [f"su-{i // 4 + 1:02d}-node-{i % 4 + 1:02d}" for i in range(136)]
    rendered = _env().from_string(_task("Collect results")["shell"]).render(
        server_groups=servers,
        hostvars={s: {"ansible_host": f"192.168.200.{89 + i}"}
                  for i, s in enumerate(servers)},
        server_ansible_password="x", collect_batch_size=32,  # pragma: allowlist secret
        pm_run_token="TOKEN",
    )
    assert len(rendered) < MAX_ARG_STRLEN // 4, (
        f"{len(rendered)} bytes for 136 servers — the per-server cost has "
        "grown; keep the body in the collect() function, not the loop")


def test_collector_requires_this_runs_done_marker():
    """A results file left by an earlier run must not pass as evidence."""
    shell = _task("Collect results")["shell"]
    fire_task = _task("Push and fire")["ansible.builtin.shell"]
    fire = fire_task["cmd"] + fire_task["stdin"]
    assert 'echo "DONE {{ pm_run_token }}" >> $R' in fire
    assert 'grep -qx "DONE {{ pm_run_token }}"' in shell
    # The token is fixed once via set_fact, before the fire phase.
    names = [t["name"] for t in _tasks()]
    assert names.index("Generate run token") < names.index("Push and fire ping scripts (parallel)")


def test_expected_isolation_uses_the_fast_probe():
    """A CROSS-VRF target is meant to be unreachable — don't pay for proof.

    `_p` is warm-up (3s) then measure (5s); on a target that is supposed to
    fail that is ~8s of pure timeout, 128 times on a support node — ~17 of
    the ~26 minutes it took at SU32, which is why `support-*` was in #77's
    NODATA set and has never been collected in time. A VRF leak replies
    immediately, so a 1s probe still catches the case that matters.
    """
    fire_task = _task("Push and fire")["ansible.builtin.shell"]
    fire = fire_task["cmd"] + fire_task["stdin"]
    assert '_px() { ping -c 1 -W 1' in fire
    # The warm-up must short-circuit: no `;` chaining the two pings.
    assert '_p() { ping -c 1 -W 3 "$1" -I "$2" >/dev/null 2>&1 || ping' in fire
    # Every CROSS-VRF-labelled call site uses the fast probe.
    for line in fire.splitlines():
        if "CROSS-VRF" in line and ("_p " in line or "_px " in line):
            assert "_px " in line or "{{ _probe }}" in line, line


def test_wait_polls_for_this_runs_marker_instead_of_sleeping():
    """A flat sleep is wrong at every scale but one.

    At SU32 the fire phase alone takes 6m21s and each server's run takes
    minutes, so `pause: 120` expired mid-run and collect read 84/136 as
    NODATA. The wait must poll for THIS run's marker, and must not itself
    be the verdict - the fail task at the end of the play is.
    """
    names = [t["name"] for t in _tasks()]
    assert not any("pause" in t for t in _tasks()), "the fixed pause must be gone"
    wait = _task("Wait for every server to finish pinging")
    assert "grep -qx 'DONE {{ pm_run_token }}'" in wait["shell"]
    assert "server_groups | length" in wait["until"]
    assert wait["failed_when"] is False, (
        "exhausting retries must not abort before the report is generated")
    # It has to run after the fire and before the collect.
    assert (names.index("Push and fire ping scripts (parallel)")
            < names.index("Wait for every server to finish pinging")
            < names.index("Collect results from all servers (parallel, batched)"))


def test_wait_bound_is_generous_enough_for_su32():
    play = yaml.safe_load(PLAYBOOK.read_text())[0]
    cap = int(play["vars"]["ping_wait_retries"]) * int(play["vars"]["ping_wait_interval"])
    # SU32 measured ~3 min of server run time after a 6m21s staggered fire.
    assert cap >= 480, f"{cap}s is under the measured SU32 requirement"


def test_batch_size_is_asserted_positive():
    a = _task("Ensure collect_batch_size")["assert"]
    assert any("> 0" in c for c in a["that"])


def test_default_batch_size_is_bounded():
    play = yaml.safe_load(PLAYBOOK.read_text())[0]
    assert 0 < int(play["vars"]["collect_batch_size"]) <= 64


def test_makefile_propagates_playbook_exit_status():
    mk = (REPO / "Makefile").read_text()
    start = mk.index("\nvalidate-ping-matrix:")
    end = mk.index("\nvalidate-all:", start)
    recipe = mk[start:end]
    assert "_AP=$$?" in recipe, "exit status of ansible-playbook must be captured"
    assert recipe.rstrip().endswith("exit $$_AP"), "recipe must exit with the playbook's status"
    # The report must still be printed on failure, so it can't be gated on &&.
    assert "ping-matrix-report.txt\"}' && " not in recipe


def test_makefile_clears_stale_report_before_running():
    """Only a report this invocation fetched may be printed or uploaded.

    `cat`/upload became unconditional so a failing run still shows its
    report — which would otherwise resurrect the previous run's file when
    the play dies before fetching a new one.
    """
    mk = (REPO / "Makefile").read_text()
    start = mk.index("\nvalidate-ping-matrix:")
    end = mk.index("\nvalidate-all:", start)
    recipe = mk[start:end]
    rm = recipe.index('rm -f "$(REPORT_DIR)/ping-matrix-report.txt"')
    assert rm < recipe.index("$(ANSIBLE_PLAYBOOK)"), \
        "the stale report must be removed before the playbook runs"


def test_report_names_why_a_server_produced_no_results():
    """FETCHFAIL/NODATA reach the operator with their reason, not bare."""
    report = _task("Generate ping matrix report")["copy"]["content"]
    assert "fetchfail_line[0].split('|')[3]" in report
    assert "nodata_line[0].split('|')[3]" in report
    assert "harness failure, not a data-plane result" in report


# ── The collect phase, executed ────────────────────────────────────────────
# Everything above asserts the *shape* of the change. This runs the real
# rendered collect script under real bash against stub SSH hosts, which is
# the only offline way to prove the bound actually bounds and that each
# failure class lands in the right bucket. The `timeout 15` case is left to
# the Air run — reproducing it here would cost 15 s of wall clock.

_STUB = r"""#!/bin/bash
for a in "$@"; do case "$a" in ubuntu@*) T=${a#ubuntu@};; esac; done
OCT=${T##*.}
echo "S $(date +%s%N)" >> "$EVENTS"
finish() { echo "E $(date +%s%N)" >> "$EVENTS"; }
case "$OCT" in
  102) finish; exit 255 ;;                         # ssh transport failure
  103) finish; exit 5 ;;                           # sshpass auth failure
  104) finish; exit 0 ;;                           # no results file
  105) echo "PASS|bond0(1.1.1.5)|x|1.1.1.9|INBAND" # a previous run's file
       echo "DONE STALE"; finish; exit 0 ;;
  *)   sleep 0.5
       echo "PASS|bond0(1.1.1.$OCT)|x|1.1.1.9|INBAND"
       echo "DONE THIS-RUN"; finish; exit 0 ;;
esac
"""


def _peak_concurrency(events):
    deltas = sorted((int(ts), 1 if kind == "S" else -1)
                    for kind, ts in (l.split() for l in events if l.strip()))
    live = peak = 0
    for _, d in deltas:
        live += d
        peak = max(peak, live)
    return peak


def test_collect_script_classifies_each_failure_and_honours_the_bound(tmp_path):
    import os
    import shutil
    import subprocess

    if not shutil.which("bash"):
        import pytest
        pytest.skip("bash required")

    play = yaml.safe_load(PLAYBOOK.read_text())[0]
    batch = int(play["vars"]["collect_batch_size"])
    n = batch * 2 + 6                      # enough hosts to fill three batches
    servers = [f"s{i:03d}" for i in range(n)]
    # The stub keys its behaviour off the last octet, so s002..s005 (=> .102
    # ..105) are the fault hosts and everything else is healthy. Keep n large
    # enough that those indices exist.
    hostvars = {s: {"ansible_host": f"10.0.0.{100 + i}"}
                for i, s in enumerate(servers)}

    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "sshpass").write_text(_STUB)
    (bindir / "sshpass").chmod(0o755)
    events = tmp_path / "events"

    script = _env().from_string(_task("Collect results")["shell"]).render(
        server_groups=servers, hostvars=hostvars,
        server_ansible_password="unused-by-stub",  # pragma: allowlist secret
        collect_batch_size=batch, pm_run_token="THIS-RUN",
    )
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}",
           "EVENTS": str(events)}
    out = subprocess.run(["bash", "-c", script], env=env, check=True,
                         capture_output=True, text=True).stdout

    collect = sorted(l for l in out.splitlines() if l.startswith("COLLECT|"))
    assert collect == [
        "COLLECT|s002|FETCHFAIL|ssh rc=255 (connection failed)",
        "COLLECT|s003|FETCHFAIL|sshpass rc=5",
        "COLLECT|s004|NODATA|no results file (script never ran or was not fired)",
        "COLLECT|s005|NODATA|no marker for this run (still running, died, or "
        "left by an earlier run)",
    ], collect
    # Every other host reported, and s005's stale file did NOT count as one.
    reported = {l.split("|")[0][len("FROM:"):]
                for l in out.splitlines() if l.startswith("FROM:")}
    assert reported == set(servers) - {"s002", "s003", "s004", "s005"}
    assert _peak_concurrency(events.read_text().splitlines()) == batch
