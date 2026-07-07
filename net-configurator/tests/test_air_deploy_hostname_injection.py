# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Regression test: build_server_ni_commands must shell-quote the Excel-derived
node hostname. It is interpolated into `hostnamectl set-hostname ...` and run as
shell on each Air node at first-boot provisioning, so an unquoted malicious
hostname (e.g. `n;reboot`) would execute arbitrary commands. Same class-of-bug
as the ztp.sh.j2 `| quote` and airlib/ssh.py fixes.
"""
import importlib.util
import shlex
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_air_deploy():
    spec = importlib.util.spec_from_file_location("air_deploy", SCRIPTS / "air-deploy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


air_deploy = _load_air_deploy()


def _hostname_cmd(node_name):
    cmds = air_deploy.build_server_ni_commands(
        node_name, {"eth0_ip": "192.168.200.50"}, {})
    return cmds, [c for c in cmds if c.startswith("hostnamectl set-hostname")]


def test_malicious_hostname_is_quoted():
    evil = "n;reboot $(id)"
    cmds, hn = _hostname_cmd(evil)
    assert hn, "expected a hostnamectl command"
    # Properly quoted form — the shell metacharacters are inert.
    assert hn[0] == f"hostnamectl set-hostname {shlex.quote(evil)}"
    # The raw, unquoted, injectable form must NOT appear anywhere.
    assert "hostnamectl set-hostname n;reboot" not in "\n".join(cmds)


def test_normal_hostname_still_works():
    cmds, hn = _hostname_cmd("gpu-01")
    assert hn == ["hostnamectl set-hostname gpu-01"]
