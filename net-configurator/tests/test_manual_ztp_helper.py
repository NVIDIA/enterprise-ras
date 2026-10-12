# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""`/opt/ztp/manual-ztp.sh` finds what the ZTP server serves and never puts a password in argv (GitLab #103, F4).

The helper looked under `/var/www/html/ztp/` for a per-switch `scripts/<switch>.sh`
and `configs/<switch>.yaml`, while the ztp-server role serves `/var/www/ztp/`
(nginx `root`) with one unified `scripts/ztp.sh` and `configs/<switch>-config.sh`,
so it never found anything. Its SSH option ran
`sshpass -p 'Cumu1usLinux!'`: the factory placeholder, ignoring secrets.yml,
and visible in `ps`. These tests run the real script against a temporary web
root with `sshpass`/`ssh` stubbed on PATH.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
SCRIPT = NC / "roles" / "ztp-server" / "files" / "manual-ztp.sh"
NGINX = NC / "roles" / "ztp-server" / "templates" / "nginx-ztp.conf.j2"


@pytest.fixture
def web_root(tmp_path):
    root = tmp_path / "www-ztp"
    (root / "scripts").mkdir(parents=True)
    (root / "configs").mkdir()
    (root / "scripts" / "ztp.sh").write_text("#!/bin/bash\n")
    (root / "configs" / "core-01-config.sh").write_text("#!/bin/bash\n")
    return root


@pytest.fixture
def stubs(tmp_path):
    """`sshpass` stub records its argv and $SSHPASS; it never connects anywhere."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    rec = tmp_path / "sshpass.rec"
    (bin_dir / "sshpass").write_text(
        "#!/bin/bash\n"
        f"printf 'ARGV=%s\\n' \"$*\" > {rec}\n"
        f"printf 'SSHPASS=%s\\n' \"${{SSHPASS:-}}\" >> {rec}\n"
        "exit 0\n")
    (bin_dir / "sshpass").chmod(0o755)
    return bin_dir, rec


def _run(web_root, stdin, bin_dir=None, sshpass=None):
    env = {k: v for k, v in os.environ.items() if k != "SSHPASS"}
    env["ZTP_WEB_ROOT"] = str(web_root)
    if bin_dir:
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
    if sshpass is not None:
        env["SSHPASS"] = sshpass
    return subprocess.run(["bash", str(SCRIPT), "core-01", "192.0.2.1"], input=stdin,
                          capture_output=True, text=True, env=env, timeout=30)


def test_default_web_root_is_what_nginx_serves():
    root = re.search(r"^\s*root\s+(\S+);", NGINX.read_text(), re.M).group(1)
    default = re.search(r'ZTP_WEB_ROOT="\$\{ZTP_WEB_ROOT:-([^}]+)\}"', SCRIPT.read_text()).group(1)
    assert default == root


def test_finds_the_served_script_and_config(web_root):
    p = _run(web_root, "n")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "ZTP script found" in p.stdout
    assert "Config file found" in p.stdout
    assert "http://192.0.2.1/scripts/ztp.sh" in p.stdout


def test_unknown_switch_lists_the_served_configs(web_root):
    p = subprocess.run(["bash", str(SCRIPT), "core-99"], input="n", capture_output=True,
                       text=True, env={**os.environ, "ZTP_WEB_ROOT": str(web_root)}, timeout=30)
    assert p.returncode == 1
    assert "core-01" in p.stdout


def test_no_password_literal_in_the_helper():
    text = SCRIPT.read_text()
    assert "Cumu1usLinux" not in text
    assert "sshpass -p" not in text


def test_ssh_option_passes_the_password_through_the_environment(web_root, stubs):
    bin_dir, rec = stubs
    p = _run(web_root, "y", bin_dir=bin_dir, sshpass="from-secrets-yml")
    assert p.returncode == 0, p.stdout + p.stderr
    got = rec.read_text()
    assert got.startswith("ARGV=-e ssh "), got
    assert "from-secrets-yml" not in got.splitlines()[0]
    assert "SSHPASS=from-secrets-yml" in got


def test_ssh_option_prompts_when_sshpass_is_unset(web_root, stubs):
    bin_dir, rec = stubs
    p = _run(web_root, "ytyped-at-prompt\n", bin_dir=bin_dir)
    assert p.returncode == 0, p.stdout + p.stderr
    got = rec.read_text()
    assert "SSHPASS=typed-at-prompt" in got
    assert "typed-at-prompt" not in got.splitlines()[0]


def test_ssh_option_refuses_an_empty_password(web_root, stubs):
    bin_dir, rec = stubs
    p = _run(web_root, "y\n", bin_dir=bin_dir)
    assert p.returncode == 1
    assert not rec.exists()


def test_without_a_server_address_it_never_points_the_switch_at_itself(web_root, stubs):
    """The switch fetches the URL; `localhost` there is the switch, not this server."""
    bin_dir, rec = stubs
    env = {**os.environ, "ZTP_WEB_ROOT": str(web_root), "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "SSHPASS": "from-secrets-yml"}  # pragma: allowlist secret
    p = subprocess.run(["bash", str(SCRIPT), "core-01"], input="y", capture_output=True,
                       text=True, env=env, timeout=30)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "localhost" not in p.stdout
    assert "http://<ztp-server-ip>/scripts/ztp.sh" in p.stdout
    assert "core-01 <ztp-server-ip>" in p.stdout
    assert not rec.exists(), "helper ran ssh without a server address the switch can reach"


def test_helper_warns_that_ztp_names_the_config_from_the_dhcp_lease(web_root):
    p = _run(web_root, "n")
    assert "DHCP" in p.stdout and "push-switch-configs" in p.stdout
