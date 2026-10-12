# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""`push-switch-configs` stages the rendered script privately and removes it (GitLab #103, F7).

The rendered `<host>-config.sh` carries the LDAP bind password when LDAP is on.
It used to be copied to a fixed `/tmp/<host>-config.sh` with mode 0755 and left
on the switch after the push.

This runs the playbook's real "Push config and apply" play with Ansible against
localhost (`connection: local`), with `nv` stubbed on PATH. The config script
records the path and mode it was run from, so the assertions are about what
Ansible actually did, not about the YAML text.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

NC = Path(__file__).resolve().parent.parent
PLAYBOOK = NC / "playbooks" / "push-switch-configs.yml"
PLAY = "Push config and apply (with confirm)"
ANSIBLE = Path(sys.executable).parent / "ansible-playbook"
if not ANSIBLE.exists():
    ANSIBLE = Path(shutil.which("ansible-playbook") or "ansible-playbook")


def _play():
    plays = yaml.safe_load(PLAYBOOK.read_text())
    return next(p for p in plays if p["name"] == PLAY)


def _run(tmp_path, script_rc):
    host = "leaf01"
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    rec = tmp_path / "ran-from"
    (cfg_dir / f"{host}-config.sh").write_text(
        "#!/bin/bash\n"
        f"printf '%s %s\\n' \"$0\" \"$(stat -c %a \"$0\")\" > {rec}\n"
        f"exit {script_rc}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "nv").write_text("#!/bin/bash\nexit 0\n")
    (bin_dir / "nv").chmod(0o755)

    play = _play()
    play["hosts"] = "localhost"
    play["connection"] = "local"
    play["vars"] = {**play.get("vars", {}), "config_output_dir": str(cfg_dir),
                    "hostname": host, "switch_ansible_password": "pw",  # pragma: allowlist secret
                    "ansible_python_interpreter": sys.executable}
    pb = tmp_path / "play.yml"
    pb.write_text(yaml.safe_dump([play], sort_keys=False))
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-local"),
           "ANSIBLE_REMOTE_TEMP": str(tmp_path / "ansible-remote"),
           "ANSIBLE_NOCOLOR": "1"}
    p = subprocess.run([str(ANSIBLE), "-i", "localhost,", str(pb)], cwd=str(NC),
                       capture_output=True, text=True, env=env, timeout=300)
    return p, rec


def test_script_runs_from_a_private_unique_file_that_is_removed(tmp_path):
    p, rec = _run(tmp_path, 0)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    path, mode = rec.read_text().split()
    assert mode == "600", mode
    assert Path(path).name != "leaf01-config.sh"
    assert Path(path).name.endswith("-config.sh")
    assert not Path(path).exists(), f"{path} left behind"


def test_script_is_removed_when_it_fails(tmp_path):
    p, rec = _run(tmp_path, 3)
    assert p.returncode != 0
    path, mode = rec.read_text().split()
    assert mode == "600"
    assert not Path(path).exists(), f"{path} left behind after a failed run"
