# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""F15 (review #4): the probe scripts' output contracts, executed.

`server_validate_probe.sh` emits a `RESULT|` line that `validate-servers.yml`
splits by position, and `oob_bgp_probe.sh` dumps JSON that the jump-side
`oob_bgp_classify.py` turns into an `OOB_BGP|` verdict. Both used to get only
`bash -n`. These tests run the real scripts against stub commands on PATH and
check the fields land where the playbooks read them.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
SERVER_PROBE = NC / "scripts" / "server_validate_probe.sh"
OOB_PROBE = NC / "scripts" / "oob_bgp_probe.sh"
OOB_CLASSIFY = NC / "scripts" / "oob_bgp_classify.py"
SERVERS_PLAYBOOK = NC / "playbooks" / "validate-servers.yml"

# Probe variable -> playbook key, in the order the playbook documents.
PROBE_VAR_TO_KEY = {
    "NAME": "name", "OK": "status", "HOST": "ip", "HOSTNAME": "hostname",
    "ETH0_IP": "eth0_ip", "BOND_MODE": "bond_mode", "BOND_ACTIVE": "bond_active",
    "VLAN_IFACES": "vlan_ifaces", "LLDPD": "lldpd", "GW_PING": "gw_ping",
    "OOB_PING": "oob_ping", "INET_PING": "inet_ping", "ROLE": "role",
    "ALL_IPS": "all_ips",
}


def _probe_fields():
    """Field names of the OK `RESULT|` line, as the probe writes them."""
    m = re.search(r'^echo "RESULT\|(\$NAME\|OK\|[^"]+)"$', SERVER_PROBE.read_text(), re.M)
    assert m, "OK RESULT| line not found in server_validate_probe.sh"
    return ["RESULT"] + [f.lstrip("$") for f in m.group(1).split("|")]


def _playbook_index():
    """Playbook key -> position it reads from the split RESULT line."""
    pairs = re.findall(r"'(\w+)': _f\[(\d+)\]", SERVERS_PLAYBOOK.read_text())
    assert pairs, "RESULT| field mapping not found in validate-servers.yml"
    return {key: int(i) for key, i in pairs}


def _parse(stdout):
    """What `Parse and display results` does: the RESULT line, split on '|'."""
    line = next((ln for ln in stdout.splitlines() if re.match(r"^RESULT\|", ln)), "")
    f = line.split("|")
    return {key: (f[i] if i < len(f) else "") for key, i in _playbook_index().items()}, f


def test_playbook_reads_every_probe_field_at_its_position():
    fields = _probe_fields()
    index = _playbook_index()
    assert len(fields) == 15, fields
    read = {fields[i]: key for key, i in index.items()}
    assert read == PROBE_VAR_TO_KEY, (
        "validate-servers.yml reads RESULT| fields at positions the probe does not "
        f"write them:\n  probe:    {fields}\n  playbook: {sorted(index.items(), key=lambda kv: kv[1])}")


def _stub(bindir, name, body):
    p = bindir / name
    p.write_text("#!/bin/bash\n" + body)
    p.chmod(0o755)


@pytest.fixture
def server_stubs(tmp_path):
    """A fake server behind a fake sshpass: the remote heredoc runs locally."""
    b = tmp_path / "bin"
    b.mkdir()
    log = tmp_path / "log"
    log.mkdir()
    # sshpass -e ssh <opts...> ubuntu@IP "bash -s -- 'NAME' ..."  -> run the last arg.
    _stub(b, "sshpass", f'printf "%s\\n" "$@" > {log}/sshpass.argv\n'
                        '[ -n "$STUB_DOWN" ] && exit 255\n'
                        'eval "${@: -1}"\n')
    _stub(b, "hostname", 'echo gpu-01\n')
    _stub(b, "systemctl", 'echo active\n')
    _stub(b, "sudo", 'exit 0\n')
    _stub(b, "ip", r'''case "$*" in
  "-4 addr show eth0") echo "    inet 192.168.200.21/24 brd 192.168.200.255 scope global eth0";;
  "-4 -br addr show") printf 'lo UNKNOWN 127.0.0.1/8\neth0 UP 192.168.200.21/24\nbond0.20@bond0 UP 172.16.20.21/24\n';;
  "-br link show type vlan") echo "bond0.20@bond0 UP";;
  "-o route get"*) echo "172.16.20.1 from 172.16.20.21 dev bond0.20 uid 0";;
  *) echo "ip-raw $*";;
esac
''')
    # ping fails only for the address in STUB_PING_FAIL.
    _stub(b, "ping", 'for a in "$@"; do [ -n "$STUB_PING_FAIL" ] && [ "$a" = "$STUB_PING_FAIL" ] && exit 1; done\n'
                     'echo "64 bytes from stub: icmp_seq=1"\n')
    env = {**os.environ, "PATH": f"{b}:{os.environ['PATH']}", "SSHPASS": "pw-not-in-argv"}
    return env, log


def _run_server_probe(env, *extra_env):
    env = {**env, **dict(extra_env)}
    return subprocess.run(
        ["bash", str(SERVER_PROBE), "172.20.0.21", "gpu-01", "172.16.20.21",
         "172.16.20.1", "gpu", "192.168.200.1"],
        env=env, capture_output=True, text=True, timeout=60)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_server_probe_ok_line_lands_in_the_playbook_fields(server_stubs):
    env, log = server_stubs
    r = _run_server_probe(env)
    assert r.returncode == 0, r.stderr
    row, raw = _parse(r.stdout)
    assert len(raw) == 15, raw
    assert row == {
        "name": "gpu-01", "status": "OK", "ip": "172.20.0.21", "hostname": "gpu-01",
        "eth0_ip": "192.168.200.21/24", "bond_mode": "", "bond_active": "",
        "vlan_ifaces": "bond0.20@bond0", "lldpd": "active", "gw_ping": "PASS",
        "oob_ping": "PASS", "inet_ping": "PASS", "role": "gpu",
        "all_ips": "eth0=192.168.200.21/24 bond0.20@bond0=172.16.20.21/24 ",
    }
    # The RAW blocks follow the RESULT line; the playbook writes them per server.
    assert r.stdout.splitlines()[0].startswith("RESULT|")
    for block in ("ip_brief", "routes", "ping_gw", "ping_oob", "ping_inet"):
        assert f"---RAW:{block}---" in r.stdout
    # One ssh session, password never on its command line.
    argv = (log / "sshpass.argv").read_text()
    assert argv.splitlines()[0] == "-e" and "ubuntu@172.20.0.21" in argv
    assert "pw-not-in-argv" not in argv


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_server_probe_internet_ping_waits_on_oob(server_stubs):
    env, _ = server_stubs
    r = _run_server_probe(env, ("STUB_PING_FAIL", "192.168.200.1"))
    row, _ = _parse(r.stdout)
    assert (row["gw_ping"], row["oob_ping"], row["inet_ping"]) == ("PASS", "FAIL", "SKIP")


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_server_probe_unreachable_line_parses_to_an_unreachable_row(server_stubs):
    env, _ = server_stubs
    r = _run_server_probe(env, ("STUB_DOWN", "1"))
    assert r.returncode == 0
    assert r.stdout.strip() == "RESULT|gpu-01|UNREACHABLE|172.20.0.21||||||||"
    row, _ = _parse(r.stdout)
    assert (row["name"], row["status"], row["ip"]) == ("gpu-01", "UNREACHABLE", "172.20.0.21")
    assert not any(v for k, v in row.items() if k not in ("name", "status", "ip"))


def test_server_probe_refuses_to_run_without_sshpass_env(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "SSHPASS"}
    r = subprocess.run(["bash", str(SERVER_PROBE), "10.0.0.1", "n"], env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode != 0 and "SSHPASS must be set" in r.stderr


BGP_UP = {"default": {"ipv4Unicast": {"peers": {
    "swp51": {"state": "Established"}, "10.10.10.1": {"state": "Established"}}}}}
BGP_DOWN = {"default": {"ipv4Unicast": {"peers": {
    "swp51": {"state": "Established"}, "swp52": {"state": "Active"}}}}}


def _oob_round_trip(tmp_path, bgp_json, password="s3cr3t pw"):  # pragma: allowlist secret
    """Stream the probe exactly as validate-oob-bgp.yml does, then classify."""
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    _stub(b, "sudo", f'printf "%s\\n" "$@" > {tmp_path}/sudo.argv\n'
                     f'IFS= read -r p; printf "%s" "$p" > {tmp_path}/sudo.stdin\n'
                     'while [ "${1:0:1}" = "-" ]; do [ "$1" = "-p" ] && shift; shift; done\n'
                     'exec "$@"\n')
    if bgp_json is None:
        _stub(b, "vtysh", "exit 1\n")
    else:
        (tmp_path / "bgp.json").write_text(json.dumps(bgp_json))
        _stub(b, "vtysh", f'[ "$*" = "-c show bgp vrf all summary json" ] && cat {tmp_path}/bgp.json\n')
    env = {**os.environ, "PATH": f"{b}:{os.environ['PATH']}"}
    stream = f"IFS= read -r PW\n{password}\n" + OOB_PROBE.read_text()
    dump = subprocess.run(["bash", "-s"], input=stream, env=env,
                          capture_output=True, text=True, timeout=30)
    verdict = subprocess.run([sys.executable, str(OOB_CLASSIFY)], input=dump.stdout,
                             capture_output=True, text=True, timeout=30)
    return dump, verdict


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_oob_probe_dump_classifies_pass(tmp_path):
    dump, verdict = _oob_round_trip(tmp_path, BGP_UP)
    assert json.loads(dump.stdout) == BGP_UP
    assert verdict.returncode == 0
    assert verdict.stdout.strip() == "OOB_BGP|PASS|neighbors=2 established=2"
    # sudo gets the password on stdin, never in its argv.
    assert (tmp_path / "sudo.stdin").read_text() == "s3cr3t pw"
    assert "s3cr3t" not in (tmp_path / "sudo.argv").read_text()


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_oob_probe_down_peer_is_a_counted_fail(tmp_path):
    _, verdict = _oob_round_trip(tmp_path, BGP_DOWN)
    assert verdict.returncode == 1
    line = verdict.stdout.strip()
    assert line == "OOB_BGP|FAIL|established=1/2 down=default/ipv4Unicast/swp52=Active"
    # The playbook's FAIL tally searches for exactly this prefix.
    assert re.search(r"OOB_BGP\|FAIL\|", line)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_oob_probe_without_vtysh_output_fails_closed(tmp_path):
    dump, verdict = _oob_round_trip(tmp_path, None)
    assert dump.stdout == ""
    assert verdict.returncode == 1
    assert verdict.stdout.startswith("OOB_BGP|FAIL|cannot parse")
