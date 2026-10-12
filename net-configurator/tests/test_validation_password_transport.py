# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""H2 / GitLab #90 (ADR-0090): validation playbooks deliver passwords as data.

Each fan-out task used to splice the password into shell text
(``export SSHPASS='{{ pw }}'`` or a positional probe argument). A quote broke
out of the literal, ``$(...)`` ran on the jump, and the password sat in the argv
of ``/bin/sh -c`` where any local user could read it with ``ps``.

The tasks now take the password on the shell task's ``stdin`` (``read`` into
``SSHPASS``) and call ``sshpass -e``; switch probes that need ``sudo`` get it on
the ssh stdin stream, ahead of the probe. These tests EXECUTE the real tasks
through ansible-playbook against stub ``timeout``/``sshpass``/``ssh`` on PATH
and check: exact password bytes in ``SSHPASS``, the password in no process argv
(each stub snapshots ``ps``), no command-substitution side effect, and nothing
in Ansible's output (``no_log``).
"""
import json
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

NC = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not shutil.which("ansible-playbook"),
                                reason="ansible-playbook required")

STUB_TIMEOUT = """#!/bin/bash
shift
exec "$@"
"""
STUB_SSHPASS = """#!/bin/bash
f="$STUB_LOG/sshpass.$$.$RANDOM"
printf '%s\\0' "$@" > "$f.argv"
printf '%s' "$SSHPASS" > "$f.env"
ps -eo args > "$f.ps"
[ "$1" = "-e" ] && shift
exec "$@"
"""
STUB_SSH = """#!/bin/bash
f="$STUB_LOG/ssh.$$.$RANDOM"
printf '%s\\0' "$@" > "$f.argv"
cat > "$f.stdin"
remote="${@: -1}"
if [ "$remote" = "bash -s" ] && [ -n "$STUB_REMOTE_EXEC" ]; then
  PATH="$STUB_REMOTE_BIN:$PATH" bash -s < "$f.stdin"
else
  echo ok
fi
"""
STUB_SUDO = """#!/bin/bash
f="$STUB_LOG/sudo.$$.$RANDOM"
printf '%s\\0' "$@" > "$f.argv"
cat > "$f.stdin"
echo '{}'
"""

INVENTORY = """[jump]
localhost ansible_connection=local ansible_python_interpreter={py}
[core]
sw1 ansible_host=10.0.0.1
sw2 ansible_host=10.0.0.2
[oob_switch]
oob1 ansible_host=10.0.0.9
[servers]
srv1 ansible_host=10.1.0.1
srv2 ansible_host=10.1.0.2
"""

SERVER_VARS = {"server_groups": ["srv1", "srv2"], "devices": {}, "common": {},
               "collect_batch_size": 10, "pm_run_token": "tok",
               "ping_wait_retries": 0, "ping_wait_interval": 0}

# (playbook, task name, password var, extra vars, probes the task reads from /tmp)
CASES = [
    ("validate-ztp.yml", "Collect from all switches in parallel (fan-out of probe calls)",
     "switch_password", {"switch_list": ["sw1", "sw2"]}, ["ztp_collect_probe.sh"]),
    ("validate-servers.yml", "Validate all servers in parallel (fan-out of probe calls)",
     "server_ansible_password", SERVER_VARS, ["server_validate_probe.sh"]),
    ("validate-servers.yml", "Run cross-ping tests", "server_ansible_password",
     {"cross_pings": json.dumps([{"from": "srv1", "to": "srv2", "label": "L",
                                  "src_ip": "10.1.1.1", "to_ip": "10.1.1.2"}])}, []),
    ("validate-config.yml", "Pull running config from ALL switches in parallel (fan-out from jump)",
     "switch_password", {"switch_list": ["sw1", "sw2"]}, []),
    ("validate-switch-health.yml", "Run the health probe on all switches in parallel (fan-out from jump)",
     "switch_password", {"switch_list": ["sw1", "sw2"]}, ["switch_health_probe.sh"]),
    ("validate-oob-bgp.yml", "Run the OOB BGP probe on all OOB switches (fan-out from jump)",
     "switch_password", {"oob_list": ["oob1"]}, ["oob_bgp_probe.sh"]),
    ("validate-ping-matrix.yml", "Push and fire ping scripts (parallel)",
     "server_ansible_password", SERVER_VARS, []),
    ("validate-ping-matrix.yml", "Wait for every server to finish pinging",
     "server_ansible_password", SERVER_VARS, []),
    ("validate-ping-matrix.yml", "Collect results from all servers (parallel, batched)",
     "server_ansible_password", SERVER_VARS, []),
]
REMOTE_SUDO_PROBES = {"switch_health_probe.sh", "oob_bgp_probe.sh"}


def _password(tmp_path):
    """A fresh token per run, so a hit in ``ps`` can only come from this run."""
    token = secrets.token_hex(8)
    m1, m2 = tmp_path / "PWN1", tmp_path / "PWN2"
    return token, f"-{token}'q\"d$HOME $(touch {m1}) `touch {m2}`;&x y\\z", [m1, m2]


def _task(playbook, name):
    for play in yaml.safe_load((NC / "playbooks" / playbook).read_text()):
        for task in play.get("tasks", []):
            if task.get("name") == name:
                return dict(task)
    raise AssertionError(f"{playbook}: no task named {name!r}")


def _stub(bin_dir, name, body):
    path = bin_dir / name
    path.write_text(body)
    path.chmod(0o755)


def _run_task(tmp_path, playbook, name, pw_var, extra, probes, password):
    bin_dir, remote_bin, log = tmp_path / "bin", tmp_path / "rbin", tmp_path / "log"
    for d in (bin_dir, remote_bin, log):
        d.mkdir()
    _stub(bin_dir, "timeout", STUB_TIMEOUT)
    _stub(bin_dir, "sshpass", STUB_SSHPASS)
    _stub(bin_dir, "ssh", STUB_SSH)
    _stub(remote_bin, "sudo", STUB_SUDO)

    task = _task(playbook, name)
    for key in ("when", "run_once", "delegate_to"):
        task.pop(key, None)
    text = yaml.safe_dump(task, sort_keys=False)
    for probe in probes:
        copy = tmp_path / probe
        shutil.copy(NC / "scripts" / probe, copy)
        text = text.replace(f"/tmp/{probe}", str(copy))
    play = [{"hosts": "localhost", "gather_facts": False, "tasks": [yaml.safe_load(text)]}]
    (tmp_path / "play.yml").write_text(yaml.safe_dump(play, sort_keys=False))
    (tmp_path / "hosts").write_text(INVENTORY.format(py=sys.executable))
    (tmp_path / "vars.json").write_text(json.dumps({pw_var: password, **extra}))

    env = {"PATH": f"{bin_dir}:{Path(sys.executable).parent}:/usr/bin:/bin",
           "HOME": str(tmp_path), "STUB_LOG": str(log),
           "STUB_REMOTE_BIN": str(remote_bin),
           "STUB_REMOTE_EXEC": "1" if "oob_bgp_probe.sh" in probes else "",
           "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-tmp"),
           "ANSIBLE_HOST_KEY_CHECKING": "False"}
    r = subprocess.run(["ansible-playbook", "-i", str(tmp_path / "hosts"),
                        str(tmp_path / "play.yml"), "-e", f"@{tmp_path / 'vars.json'}"],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    return r, log


def _files(log, prefix, suffix):
    return sorted(log.glob(f"{prefix}.*{suffix}"))


@pytest.mark.parametrize("playbook,name,pw_var,extra,probes", CASES,
                         ids=[f"{c[0]}:{c[1][:30]}" for c in CASES])
def test_password_reaches_sshpass_as_data_only(tmp_path, playbook, name, pw_var, extra, probes):
    secret, password, markers = _password(tmp_path)
    r, log = _run_task(tmp_path, playbook, name, pw_var, extra, probes, password)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:].replace(password, "<PW>")

    envs = _files(log, "sshpass", ".env")
    assert envs, "task never called sshpass"
    for env_file in envs:
        assert env_file.read_bytes() == password.encode(), "SSHPASS is not the exact password"

    for argv in _files(log, "sshpass", ".argv") + _files(log, "ssh", ".argv"):
        assert secret not in argv.read_text(), f"password in argv: {argv.name}"
    for ps in _files(log, "sshpass", ".ps"):
        assert secret not in ps.read_text(), "password visible in the process table"
    for marker in markers:
        assert not marker.exists(), "command substitution in the password executed"
    assert secret not in r.stdout + r.stderr, "no_log did not keep the password out of output"

    if REMOTE_SUDO_PROBES & set(probes):
        prefix = f"IFS= read -r PW\n{password}\n".encode()
        streams = _files(log, "ssh", ".stdin")
        probe_streams = [s for s in streams if s.read_bytes().startswith(b"IFS= read -r PW\n")]
        assert probe_streams, "sudo password not delivered on the ssh stdin"
        for stream in probe_streams:
            assert stream.read_bytes().startswith(prefix)


def test_remote_sudo_receives_the_exact_password(tmp_path):
    """Run the streamed OOB probe as the 'switch' would: sudo -S gets exact bytes."""
    secret, password, markers = _password(tmp_path)
    r, log = _run_task(tmp_path, *CASES[5], password)
    assert r.returncode == 0
    sudo_in = _files(log, "sudo", ".stdin")
    assert sudo_in and all(f.read_bytes() == password.encode() + b"\n" for f in sudo_in)
    for argv in _files(log, "sudo", ".argv"):
        assert secret not in argv.read_text()
    for marker in markers:
        assert not marker.exists()


def _walk_tasks(tasks):
    for t in tasks or []:
        yield t
        for key in ("block", "rescue", "always"):
            yield from _walk_tasks(t.get(key))


VALIDATION_PLAYBOOKS = sorted({c[0] for c in CASES})


@pytest.mark.parametrize("playbook", VALIDATION_PLAYBOOKS)
def test_every_password_stdin_task_sets_no_log(playbook):
    plays = yaml.safe_load((NC / "playbooks" / playbook).read_text())
    missing, seen = [], 0
    for play in plays:
        for key in ("pre_tasks", "tasks", "post_tasks", "handlers"):
            for t in _walk_tasks(play.get(key)):
                mod = t.get("ansible.builtin.shell") or t.get("shell") or {}
                stdin = (mod.get("stdin", "") if isinstance(mod, dict) else "") \
                    or (t.get("args") or {}).get("stdin", "")
                if "password" in str(stdin):
                    seen += 1
                    if t.get("no_log") is not True:
                        missing.append(t.get("name"))
    assert seen, f"{playbook}: no task feeds a password on stdin"
    assert missing == [], f"{playbook}: password-on-stdin task(s) without no_log: {missing}"
