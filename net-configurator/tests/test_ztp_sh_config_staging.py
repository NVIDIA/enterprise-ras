# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ZTP stages the downloaded switch config privately and removes it (GitLab #103, F7).

`ztp.sh` used to `wget` the config to `/tmp/<host>-config.sh`, `chmod +x` it
(world-readable, 0755) and leave it on the switch. With LDAP on, that file
holds the bind password.

This renders the real template and runs its `load_configuration` function in
bash, with `wget` and `nv` stubbed on PATH. The stub config records the path
and mode it was sourced from.
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


def _functions(tmp_path):
    env = Environment(loader=FileSystemLoader(str(TEMPLATE.parent)))
    env.filters["quote"] = lambda s: shlex.quote(str(s))
    out = env.get_template(TEMPLATE.name).render(
        switch_password="pw", switch_user="cumulus",  # pragma: allowlist secret
        cumulus_target_release="", ztp_monitoring_config="")
    funcs = []
    for name in ("log", "install_ldap_packages", "load_configuration"):
        m = re.search(rf"^function {name}\(\) ?\{{.*?^\}}$", out, re.M | re.S)
        assert m, f"function {name} not found in rendered ztp.sh"
        funcs.append(m.group(0))
    return "\n".join(funcs).replace("/tmp/config-", f"{tmp_path}/config-")


def _run(tmp_path, wget_rc=0, source_rc=0, leftover_log=False, ldap_step=""):
    work = tmp_path / "tmp"
    work.mkdir()
    rec = tmp_path / "sourced-from"
    if leftover_log:
        (tmp_path / "config-load.log").write_text("old\n")
        (tmp_path / "config-load.log").chmod(0o644)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "wget").write_text(
        "#!/bin/bash\n"
        f"[ {wget_rc} -eq 0 ] || exit {wget_rc}\n"
        "cat > \"$2\" <<'CFG'\n"
        f"printf '%s %s\\n' \"${{BASH_SOURCE[0]}}\" \"$(stat -c %a \"${{BASH_SOURCE[0]}}\")\" > {rec}\n"
        f"return {source_rc}\n"
        "CFG\n")
    (bin_dir / "nv").write_text("#!/bin/bash\nexit 0\n")
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    script = tmp_path / "funcs.sh"
    funcs = _functions(tmp_path)
    if ldap_step:
        funcs += f"\nfunction install_ldap_packages() {{\n{ldap_step}\n}}\n"
    script.write_text(funcs + "\nhostname=leaf01\nPROVISION_URL=\nload_configuration\n")  # pragma: allowlist secret
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "TMPDIR": str(work)}
    p = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env,
                       cwd=str(tmp_path), timeout=30)
    return p, rec, work


def test_config_is_sourced_from_a_private_file_that_is_removed(tmp_path):
    p, rec, work = _run(tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    path, mode = rec.read_text().split()
    assert mode == "600"
    assert Path(path).parent == work
    assert "leaf01" not in Path(path).name
    assert not Path(path).exists()
    assert list(work.iterdir()) == []


def test_load_log_is_root_only_even_if_an_old_one_was_world_readable(tmp_path):
    p, _, _ = _run(tmp_path, leftover_log=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert oct((tmp_path / "config-load.log").stat().st_mode & 0o777) == "0o600"


@pytest.mark.parametrize("case", ["download fails", "load fails"])
def test_config_is_removed_on_failure(tmp_path, case):
    kw = {"wget_rc": 4} if case == "download fails" else {"source_rc": 1}
    p, _, work = _run(tmp_path, **kw)
    assert p.returncode == 1
    assert list(work.iterdir()) == []


def test_template_no_longer_uses_a_fixed_world_readable_path():
    text = TEMPLATE.read_text()
    assert "/tmp/${hostname}-config.sh" not in text
    assert "chmod +x" not in text


def test_package_install_runs_with_the_callers_umask(tmp_path):
    """umask 077 is for the config and logs only, not for apt-get / nslcd."""
    seen = tmp_path / "umask-during-install"
    p, _, _ = _run(tmp_path, ldap_step=f"umask > {seen}")
    assert p.returncode == 0, p.stdout + p.stderr
    assert seen.read_text().strip() != "0077"


@pytest.mark.parametrize("how", ["exit", "TERM", "INT"])
def test_config_is_removed_if_ztp_stops_before_sourcing_it(tmp_path, how):
    step = "exit 3" if how == "exit" else f"kill -{how} $$; sleep 5"
    p, rec, work = _run(tmp_path, ldap_step=step)
    assert p.returncode != 0
    assert not rec.exists(), "config was sourced; the stop came too late to test cleanup"
    assert list(work.iterdir()) == []
