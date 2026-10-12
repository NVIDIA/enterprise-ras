# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Every `wget` in ztp.sh runs with `-q` (Cumulus issue 3878394).

Cumulus 5.18 lists 3878394 as open: ZTP can fail with a Unicode decoding
error on `wget` output, and the workaround is `wget -q`. `load_configuration`
already used `-qO`; `add_topo` and `add_ssh_keys` used plain `wget -O`.

The runtime tests render the real template and run `add_topo` /
`add_ssh_keys` in bash under the script's own `trap error ERR`, with `wget`,
`chown` and `logger` stubbed on PATH. The `wget` stub records its arguments
and, like 3878394, fails when it is called without `-q`.
"""
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

NC = Path(__file__).resolve().parent.parent
TEMPLATE = NC / "roles" / "ztp-server" / "templates" / "ztp.sh.j2"


def _rendered():
    env = Environment(loader=FileSystemLoader(str(TEMPLATE.parent)))
    env.filters["quote"] = lambda s: shlex.quote(str(s))
    return env.get_template(TEMPLATE.name).render(
        switch_password="pw", switch_user="cumulus",  # pragma: allowlist secret
        cumulus_target_release="", ztp_monitoring_config="")


def _wget_calls(text):
    """Lines that run wget as a command (not log text that mentions it)."""
    return [line.strip() for line in text.splitlines()
            if re.match(r"\s*(?:if\s+!\s*)?wget\s", line)]


def _has_quiet(call):
    args = shlex.split(call.split("wget", 1)[1].split("||", 1)[0].split(";", 1)[0])
    return any(a == "-q" or a == "--quiet" or re.fullmatch(r"-[A-Za-z]*q[A-Za-z]*", a)
               for a in args)


def test_every_rendered_wget_is_quiet():
    calls = _wget_calls(_rendered())
    assert len(calls) >= 3, calls
    assert [c for c in calls if not _has_quiet(c)] == []


def _run(tmp_path, func, wget_rc=0):
    home = tmp_path / "home" / "cumulus"
    ptm = tmp_path / "ptm.d"
    ptm.mkdir()
    rec = tmp_path / "wget-args"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "wget").write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' \"$@\" > {shlex.quote(str(rec))}\n"
        "quiet=0; for a in \"$@\"; do case \"$a\" in -q|--quiet|-q?*) quiet=1;; esac; done\n"
        "[ $quiet -eq 1 ] || { echo \"UnicodeDecodeError\" >&2; exit 1; }\n"
        f"[ {wget_rc} -eq 0 ] || exit {wget_rc}\n"
        "while [ $# -gt 0 ]; do [ \"$1\" = -O ] && { echo payload > \"$2\"; shift; }; shift; done\n")
    (bin_dir / "chown").write_text("#!/bin/bash\nexit 0\n")
    (bin_dir / "logger").write_text("#!/bin/bash\nexit 0\n")
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    out = _rendered()
    funcs = []
    for name in ("error", "log", func):
        m = re.search(rf"^function {name}\(\) ?\{{.*?^\}}$", out, re.M | re.S)
        assert m, f"function {name} not found in rendered ztp.sh"
        funcs.append(m.group(0))
    body = ("\n".join(funcs)
            .replace("/home/cumulus", str(home))
            .replace("/etc/ptm.d", str(ptm)))
    script = tmp_path / "funcs.sh"
    script.write_text(
        body + "\ntrap error ERR\nPROVISION_URL=\n"
        "TOPO_URL=http://ztp.example/topology/leaf01.dot\n"
        "SSH_URL=http://ztp.example/authorized_keys\n"
        f"{func}\necho ZTP-CONTINUED\n")
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    p = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env,
                       cwd=str(tmp_path), timeout=30)
    args = rec.read_text().split("\n") if rec.exists() else []
    target = ptm / "topology.dot" if func == "add_topo" else home / ".ssh" / "authorized_keys"
    return p, args, target


@pytest.mark.parametrize("func", ["add_topo", "add_ssh_keys"])
def test_download_runs_quiet_and_succeeds(tmp_path, func):
    p, args, target = _run(tmp_path, func)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "-q" in args
    assert target.read_text() == "payload\n"
    assert "successfully" in p.stdout
    assert "WARNING" not in p.stdout
    if func == "add_ssh_keys":
        assert oct(target.stat().st_mode & 0o777) == "0o600"


@pytest.mark.parametrize("func", ["add_topo", "add_ssh_keys"])
def test_failed_download_still_warns_and_ztp_continues(tmp_path, func):
    p, args, _ = _run(tmp_path, func, wget_rc=8)
    assert "-q" in args
    assert p.returncode == 0, p.stdout + p.stderr
    assert "WARNING: Failed to download" in p.stdout
    assert "(wget exit 8)" in p.stdout
    assert "successfully" not in p.stdout
    assert "ZTP-CONTINUED" in p.stdout
