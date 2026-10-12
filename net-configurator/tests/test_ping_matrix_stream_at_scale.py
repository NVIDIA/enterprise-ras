# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Execute the real ping launcher with large payloads and a local SSH stand-in."""
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment

NC = Path(__file__).resolve().parent.parent


def _render(count):
    play = yaml.safe_load((NC / 'playbooks/validate-ping-matrix.yml').read_text())[0]
    mod = next(t for t in play['tasks']
               if t['name'] == 'Push and fire ping scripts (parallel)')['ansible.builtin.shell']
    devices = {}
    for i in range(count):
        devices[f'su-{i // 18 + 1:02d}-node-{i % 18 + 1:02d}'] = {
            'role': 'compute', 'bond_ip': f'172.16.178.{i + 10}/24',
            'interfaces': {'gpu': ['eth3', 'eth4']},
            'gpu_interfaces': [
                {'iface': 'eth3', 'plane': 'plane1', 'ip': f'192.168.0.{i + 10}/20',
                 'gateway': '192.168.0.1'},
                {'iface': 'eth4', 'plane': 'plane2', 'ip': f'192.168.16.{i + 10}/20',
                 'gateway': '192.168.16.1'}]}
    env = Environment()
    env.filters['regex_replace'] = lambda v, p, r: re.sub(p, r, str(v))
    env.filters['quote'] = lambda v: shlex.quote(str(v))
    ctx = {'server_groups': list(devices), 'devices': devices, 'item': next(iter(devices)),
           'hostvars': {h: {'ansible_host': '192.0.2.1'} for h in devices},
           'common': {'cpu_gateway': '172.16.178.1', 'support_gateway': '172.16.179.1'},
           'pm_run_token': 'THIS_RUN', 'server_ansible_password': 'test-only'}  # pragma: allowlist secret (test fixture)
    return {key: env.from_string(value).render(**ctx) for key, value in mod.items()}


def _stub(path, content):
    path.write_text('#!/bin/bash\n' + content)
    path.chmod(0o755)


def _launch(tmp_path, count, refuse=False):
    mod = _render(count)
    root = str(tmp_path)
    for key in mod:
        mod[key] = mod[key].replace('/tmp/ping-matrix', root + '/ping-matrix')
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    _stub(bin_dir / 'sshpass', 'shift; exec "$@"\n')
    _stub(bin_dir / 'ssh', '''remote="${@: -1}"
printf '%s\\n' "${#remote}" >> "$REMOTE_SIZES"
if [[ "$remote" == *"ping-matrix.sh"* && "$REJECT_UPLOAD" == 1 ]]; then exit 7; fi
exec bash -c "$remote"
''')
    _stub(bin_dir / 'ping', 'exit 0\n')
    _stub(bin_dir / 'nohup', 'bash -n "$2" && cp "$2" "$CAPTURED" && exec "$@"\n')
    captured = tmp_path / 'captured.sh'
    result = subprocess.run(['/bin/sh', '-c', mod['cmd']], input=mod['stdin'] + '\n',
                            capture_output=True, text=True, timeout=20,
                            env={**os.environ, 'PATH': str(bin_dir) + ':' + os.environ['PATH'],
                                 'CAPTURED': str(captured), 'REJECT_UPLOAD': str(int(refuse)),
                                 'REMOTE_SIZES': str(tmp_path / 'remote-sizes')})
    results = tmp_path / 'ping-matrix-results.txt'
    deadline = time.monotonic() + 10
    while not refuse and time.monotonic() < deadline:
        if results.exists() and results.read_text().endswith('DONE THIS_RUN\n'):
            break
        time.sleep(0.02)
    return result, captured, mod


@pytest.mark.parametrize('count', [32, 136, 156])
def test_large_script_reaches_server_without_large_exec_argument(tmp_path, count):
    result, captured, mod = _launch(tmp_path, count)
    assert result.returncode == 0, result.stderr
    assert '|OK' in result.stdout
    sizes = [int(n) for n in (tmp_path / 'remote-sizes').read_text().splitlines()]
    assert sizes and max(sizes) < 4096, sizes
    assert captured.exists(), 'launcher reported success but no script reached the server'
    payload = captured.read_text()
    assert 'DONE THIS_RUN' in payload
    assert f'su-{(count - 1) // 18 + 1:02d}-node-{(count - 1) % 18 + 1:02d}' in payload
    assert 'test-only' not in payload  # credential consumed, never part of the script
    assert len(mod['cmd'].encode()) < 4096
    results = (tmp_path / 'ping-matrix-results.txt').read_text().splitlines()
    assert any(line.startswith('PASS|') for line in results)
    assert results[-1] == 'DONE THIS_RUN'


def test_upload_failure_is_not_reported_as_success(tmp_path):
    result, captured, _ = _launch(tmp_path, 2, refuse=True)
    assert result.returncode != 0
    assert '|PUSH_FAILED' in result.stdout
    assert '|OK' not in result.stdout
    assert not captured.exists()
