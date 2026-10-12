# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Tests for Makefile Ansible Vault password discovery."""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / "scripts" / "ansible-playbook.sh"
VENV_BIN = Path(os.environ.get("VIRTUAL_ENV", "")) / "bin" if os.environ.get("VIRTUAL_ENV") else Path()
if not VENV_BIN.is_dir():
    VENV_BIN = Path(__import__("sys").executable).parent
HAVE_VAULT = shutil.which("ansible-vault") is not None
needs_vault = pytest.mark.skipif(not HAVE_VAULT, reason="ansible-vault not installed")


def _setup(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    wrapper = scripts / WRAPPER.name
    shutil.copy2(WRAPPER, wrapper)
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    capture = tmp_path / "capture.json"
    stub = stub_dir / "ansible-playbook"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['STUB_CAPTURE'], 'w') as f:\n"
        "    json.dump({'password_file': os.environ.get('ANSIBLE_VAULT_PASSWORD_FILE', '<unset>'), 'argv': sys.argv[1:]}, f)\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env = {
        "HOME": str(tmp_path / "home"),
        "PATH": f"{stub_dir}:{VENV_BIN}:{os.environ.get('PATH', '')}",
        "STUB_CAPTURE": str(capture),
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    return wrapper, capture, env


def _run(tmp_path, args=(), env=None):
    wrapper, capture, base_env = _setup(tmp_path)
    if env:
        base_env.update(env)
    return subprocess.run(
        [str(wrapper), *args],
        cwd=tmp_path,
        env=base_env,
        text=True,
        capture_output=True,
    ), capture


def _read_capture(capture):
    return json.loads(capture.read_text())


def test_saved_vault_pass_is_exported_only_to_child(tmp_path):
    pass_file = tmp_path / ".era-secrets" / "vault-pass"
    pass_file.parent.mkdir()
    pass_file.write_text("synthetic-vault-password\n")  # pragma: allowlist secret
    result, capture = _run(tmp_path)
    assert result.returncode == 0
    assert _read_capture(capture)["password_file"] == str(pass_file)


def test_bogus_explicit_password_file_is_respected(tmp_path):
    pass_file = tmp_path / ".era-secrets" / "vault-pass"
    pass_file.parent.mkdir()
    pass_file.write_text("synthetic-vault-password\n")  # pragma: allowlist secret
    result, capture = _run(
        tmp_path,
        env={"ANSIBLE_VAULT_PASSWORD_FILE": "/nonexistent/bogus"},
    )
    assert result.returncode == 0
    assert _read_capture(capture)["password_file"] == "/nonexistent/bogus"


@pytest.mark.parametrize(
    "args, env",
    [
        (("--vault-id", "x@prompt"), {}),
        (("--vault-password-file", "/x"), {}),
        (("--ask-vault-pass",), {}),
        ((), {"ANSIBLE_ARGS": "--ask-vault-pass"}),
    ],
)
def test_explicit_sources_are_not_replaced(tmp_path, args, env):
    pass_file = tmp_path / ".era-secrets" / "vault-pass"
    pass_file.parent.mkdir()
    pass_file.write_text("synthetic-vault-password\n")  # pragma: allowlist secret
    result, capture = _run(tmp_path, args, env)
    assert result.returncode == 0
    captured = _read_capture(capture)
    assert captured["password_file"] == "<unset>"
    if env.get("ANSIBLE_ARGS"):
        assert captured["argv"] == ["--ask-vault-pass"]


def test_configured_vault_source_is_not_replaced(tmp_path):
    pass_file = tmp_path / ".era-secrets" / "vault-pass"
    pass_file.parent.mkdir()
    pass_file.write_text("synthetic-vault-password\n")  # pragma: allowlist secret
    (tmp_path / "ansible.cfg").write_text("[defaults]\nvault_password_file = /x\n")
    result, capture = _run(tmp_path)
    assert result.returncode == 0
    assert _read_capture(capture)["password_file"] == "<unset>"


def test_only_effective_config_controls_saved_password_discovery(tmp_path):
    pass_file = tmp_path / ".era-secrets" / "vault-pass"
    pass_file.parent.mkdir()
    pass_file.write_text("synthetic-vault-password\n")  # pragma: allowlist secret
    (tmp_path / "ansible.cfg").write_text("[defaults]\nretry_files_enabled = false\n")
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / ".ansible.cfg").write_text(
        "[defaults]\nvault_password_file = /nope\n"
    )
    result, capture = _run(tmp_path)
    assert result.returncode == 0
    assert _read_capture(capture)["password_file"] == str(pass_file)


def test_identity_list_environment_is_not_replaced(tmp_path):
    pass_file = tmp_path / ".era-secrets" / "vault-pass"
    pass_file.parent.mkdir()
    pass_file.write_text("synthetic-vault-password\n")  # pragma: allowlist secret
    result, capture = _run(tmp_path, env={"ANSIBLE_VAULT_IDENTITY_LIST": "x@/y"})
    assert result.returncode == 0
    assert _read_capture(capture)["password_file"] == "<unset>"


def test_plaintext_inventory_passes_through(tmp_path):
    secrets = tmp_path / "inv" / "group_vars" / "all" / "secrets.yml"
    secrets.parent.mkdir(parents=True)
    secrets.write_text("switch_password: plain\n")
    (tmp_path / "inv" / "hosts").write_text("localhost\n")
    result, capture = _run(tmp_path, ("-i", "inv/hosts"))
    assert result.returncode == 0
    assert _read_capture(capture)["password_file"] == "<unset>"


@pytest.mark.parametrize("inventory", ("inv/hosts", "inv"))
def test_encrypted_inventory_without_source_fails_before_exec(tmp_path, inventory):
    secrets = tmp_path / "inv" / "group_vars" / "all" / "secrets.yml"
    secrets.parent.mkdir(parents=True)
    secrets.write_text("$ANSIBLE_VAULT;1.1;AES256\nnot-real\n")
    (tmp_path / "inv" / "hosts").write_text("localhost\n")
    result, capture = _run(tmp_path, ("-i", inventory))
    assert result.returncode == 1
    assert "vault-encrypted" in result.stderr
    assert "make secrets" in result.stderr
    assert "ANSIBLE_VAULT_PASSWORD_FILE" in result.stderr
    assert "ansible.cfg" in result.stderr
    assert "playbook-only" in result.stderr
    assert not capture.exists()


@needs_vault
def test_real_vault_round_trip_uses_saved_password(tmp_path):
    pass_file = tmp_path / "vault-password"
    pass_file.write_text("unit-test-vault-pw\n")  # pragma: allowlist secret
    saved = tmp_path / ".era-secrets" / "vault-pass"
    saved.parent.mkdir()
    saved.write_text(pass_file.read_text())  # pragma: allowlist secret
    secrets = tmp_path / "inv" / "group_vars" / "all" / "secrets.yml"
    secrets.parent.mkdir(parents=True)
    secrets.write_text('switch_password: "Sw1tchPa$$word"\n')  # pragma: allowlist secret
    subprocess.run(
        ["ansible-vault", "encrypt", "--vault-password-file", str(pass_file), str(secrets)],
        cwd=tmp_path,
        env={"PATH": f"{VENV_BIN}:{os.environ.get('PATH', '')}"},
        check=True,
        capture_output=True,
        text=True,
    )
    playbook = tmp_path / "show.yml"
    playbook.write_text(
        "---\n- hosts: localhost\n  gather_facts: false\n  connection: local\n"
        "  vars_files:\n    - inv/group_vars/all/secrets.yml\n"
        "  tasks:\n    - debug:\n        msg: \"{{ switch_password }}\"\n"
    )
    (tmp_path / "inv" / "hosts").write_text("localhost\n")
    wrapper, _capture, env = _setup(tmp_path)
    env["PATH"] = f"{VENV_BIN}:{os.environ.get('PATH', '')}"
    result = subprocess.run(
        [str(wrapper), "-i", "inv/hosts", str(playbook)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Sw1tchPa$$word" in result.stdout  # pragma: allowlist secret


@needs_vault
def test_real_vault_without_source_shows_guidance(tmp_path):
    pass_file = tmp_path / "vault-password"
    pass_file.write_text("unit-test-vault-pw\n")  # pragma: allowlist secret
    secrets = tmp_path / "inv" / "group_vars" / "all" / "secrets.yml"
    secrets.parent.mkdir(parents=True)
    secrets.write_text('switch_password: "Sw1tchPa$$word"\n')  # pragma: allowlist secret
    subprocess.run(
        ["ansible-vault", "encrypt", "--vault-password-file", str(pass_file), str(secrets)],
        cwd=tmp_path,
        env={"PATH": f"{VENV_BIN}:{os.environ.get('PATH', '')}"},
        check=True,
        capture_output=True,
        text=True,
    )
    (tmp_path / "inv" / "hosts").write_text("localhost\n")
    result, capture = _run(tmp_path, ("-i", "inv/hosts"))
    assert result.returncode != 0
    assert "make secrets" in result.stderr
    assert not capture.exists()


def test_makefile_routes_recipe_invocations_through_wrapper():
    makefile = (ROOT / "Makefile").read_text()
    assert "ANSIBLE_PLAYBOOK := scripts/ansible-playbook.sh" in makefile
    for line in makefile.splitlines():
        if line.startswith("\t") and "ansible-playbook " in line:
            assert "echo" in line, line
            assert "$(ANSIBLE_PLAYBOOK)" not in line or "echo" in line


def test_make_dry_run_uses_wrapper():
    if shutil.which("make") is None:
        pytest.skip("make not installed")
    result = subprocess.run(
        ["make", "-n", "generate", "ARCH=2-8-9-800", "SITE=default",
         "GENERATE_SKIP_VALIDATE=1"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "scripts/ansible-playbook.sh playbooks/generate-cli-configs.yml" in result.stdout
