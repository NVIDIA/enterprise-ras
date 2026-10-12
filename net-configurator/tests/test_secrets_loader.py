# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Tests for the shared plaintext and Ansible Vault secrets loader."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import check_secrets as cs  # noqa: E402
import secrets_loader as sl  # noqa: E402

HAVE_VAULT = shutil.which("ansible-vault") is not None
needs_vault = pytest.mark.skipif(not HAVE_VAULT, reason="ansible-vault not installed")
GOOD = "Sw1tchPa$$word"  # pragma: allowlist secret
VAULT_PW = "unit-test-vault-pw"  # pragma: allowlist secret


def _encrypted(path, password_file):
    subprocess.run(
        ["ansible-vault", "encrypt", "--vault-password-file", str(password_file), str(path)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_find_vault_password_file_precedence(tmp_path):
    saved = tmp_path / ".era-secrets" / "vault-pass"
    saved.parent.mkdir()
    saved.write_text("saved\n")  # pragma: allowlist secret
    env_file = tmp_path / "env-pass"
    env_file.write_text("env\n")  # pragma: allowlist secret
    assert sl.find_vault_password_file(tmp_path, {"ANSIBLE_VAULT_PASSWORD_FILE": str(env_file)}) == env_file
    assert sl.find_vault_password_file(
        tmp_path, {"ANSIBLE_VAULT_PASSWORD_FILE": str(tmp_path / "missing")}
    ) == saved
    assert sl.find_vault_password_file(tmp_path, {}) == saved
    assert sl.find_vault_password_file(tmp_path / "none", {}) is None


def test_load_plaintext_and_per_variable_vault(tmp_path):
    plain = tmp_path / "secrets.yml"
    plain.write_text("switch_password: plain\nserver_ansible_password: server\n")
    assert sl.load_secrets(plain) == {
        "switch_password": "plain",  # pragma: allowlist secret
        "server_ansible_password": "server",  # pragma: allowlist secret
    }
    plain.write_text(
        "switch_password: !vault |\n"
        "  $ANSIBLE_VAULT;1.1;AES256\n"
        "  deadbeef\nserver_ansible_password: server\n"
    )
    data = sl.load_secrets(plain)
    assert isinstance(data["switch_password"], cs.VaultedValue)
    assert data["server_ansible_password"] == "server"  # pragma: allowlist secret


@pytest.mark.parametrize(
    "contents, message",
    [("", None), ("- one\n- two\n", "mapping"), ("hello\n", "mapping"),
     ("key: [broken\n", "valid YAML")],
)
def test_load_yaml_shapes(tmp_path, contents, message):
    path = tmp_path / "secrets.yml"
    path.write_text(contents)
    if message is None:
        assert sl.load_secrets(path) == {}
    else:
        with pytest.raises(sl.SecretsError, match=message):
            sl.load_secrets(path)


def test_missing_file_is_actionable(tmp_path):
    with pytest.raises(sl.SecretsError, match="not found"):
        sl.load_secrets(tmp_path / "missing.yml")


def test_resolve_secret_values():
    secrets = {
        "switch_password": "plain",  # pragma: allowlist secret
        "switch_ansible_password": "{{ switch_password }}",
        "vaulted": cs.VaultedValue(),
        "templated": "{{ lookup('env','X') }}",
        "integer": 1,
    }
    assert sl.resolve_secret(secrets, "switch_password") == "plain"
    assert sl.resolve_secret(secrets, "switch_ansible_password") == "plain"
    with pytest.raises(sl.SecretsError, match="cannot be resolved here"):
        sl.resolve_secret(secrets, "vaulted")
    with pytest.raises(sl.SecretsError, match="cannot be resolved here"):
        sl.resolve_secret(secrets, "templated")
    with pytest.raises(sl.SecretsError, match="must be a string"):
        sl.resolve_secret(secrets, "integer")
    assert sl.resolve_secret({}, "missing", default="fallback") == "fallback"
    with pytest.raises(sl.SecretsError, match="not set"):
        sl.resolve_secret({}, "missing")


def test_load_switch_password_defaults_only_when_file_is_absent(tmp_path):
    inventory = tmp_path / "inventory"
    assert sl.load_switch_password(inventory) == sl.DEFAULT_SWITCH_PASSWORD
    path = inventory / "group_vars" / "all" / "secrets.yml"
    path.parent.mkdir(parents=True)
    path.write_text("server_ansible_password: server\n")
    assert sl.load_switch_password(inventory) == sl.DEFAULT_SWITCH_PASSWORD


@needs_vault
def test_encrypted_loading_and_env_precedence(tmp_path):
    password_file = tmp_path / "password"
    password_file.write_text(VAULT_PW + "\n")  # pragma: allowlist secret
    saved = tmp_path / ".era-secrets" / "vault-pass"
    saved.parent.mkdir()
    saved.write_text(password_file.read_text())  # pragma: allowlist secret
    path = tmp_path / "inventory" / "group_vars" / "all" / "secrets.yml"
    path.parent.mkdir(parents=True)
    path.write_text(f'switch_password: "{GOOD}"\n')  # pragma: allowlist secret
    _encrypted(path, password_file)
    assert sl.load_secrets(path, project_root=tmp_path)["switch_password"] == GOOD
    wrong = tmp_path / "wrong-password"
    wrong.write_text("wrong\n")  # pragma: allowlist secret
    with pytest.raises(sl.SecretsError, match="could not decrypt"):
        sl.load_secrets(
            path,
            project_root=tmp_path,
            environ={"ANSIBLE_VAULT_PASSWORD_FILE": str(wrong), "PATH": os.environ["PATH"]},
        )
    assert sl.load_switch_password(path.parents[2], project_root=tmp_path) == GOOD


@needs_vault
def test_encrypted_file_without_source_is_not_defaulted(tmp_path):
    password_file = tmp_path / "password"
    password_file.write_text(VAULT_PW + "\n")  # pragma: allowlist secret
    path = tmp_path / "inventory" / "group_vars" / "all" / "secrets.yml"
    path.parent.mkdir(parents=True)
    path.write_text(f'switch_password: "{GOOD}"\n')  # pragma: allowlist secret
    _encrypted(path, password_file)
    with pytest.raises(sl.SecretsError, match="make secrets"):
        sl.load_switch_password(path.parents[2], project_root=tmp_path, environ={})


@needs_vault
def test_identity_list_is_used_without_saved_password(tmp_path):
    password_file = tmp_path / "password"
    password_file.write_text(VAULT_PW + "\n")  # pragma: allowlist secret
    path = tmp_path / "secrets.yml"
    path.write_text(f'switch_password: "{GOOD}"\n')  # pragma: allowlist secret
    _encrypted(path, password_file)
    environ = {
        "ANSIBLE_VAULT_IDENTITY_LIST": f"default@{password_file}",
        "PATH": os.environ["PATH"],
    }
    assert sl.load_secrets(path, project_root=tmp_path, environ=environ)["switch_password"] == GOOD


@needs_vault
def test_effective_config_is_used_before_saved_password(tmp_path, monkeypatch):
    password_file = tmp_path / "password"
    password_file.write_text(VAULT_PW + "\n")  # pragma: allowlist secret
    saved = tmp_path / ".era-secrets" / "vault-pass"
    saved.parent.mkdir()
    saved.write_text("wrong-password\n")  # pragma: allowlist secret
    (tmp_path / "ansible.cfg").write_text(
        f"[defaults]\nvault_password_file = {password_file}\n"
    )
    path = tmp_path / "secrets.yml"
    path.write_text(f'switch_password: "{GOOD}"\n')  # pragma: allowlist secret
    _encrypted(path, password_file)
    monkeypatch.chdir(tmp_path)
    assert sl.load_secrets(path, project_root=tmp_path)["switch_password"] == GOOD


@needs_vault
def test_identity_list_is_not_overridden_by_saved_password(tmp_path):
    password_file = tmp_path / "password"
    password_file.write_text(VAULT_PW + "\n")  # pragma: allowlist secret
    wrong = tmp_path / "wrong-password"
    wrong.write_text("wrong-password\n")  # pragma: allowlist secret
    saved = tmp_path / ".era-secrets" / "vault-pass"
    saved.parent.mkdir()
    saved.write_text(password_file.read_text())  # pragma: allowlist secret
    path = tmp_path / "secrets.yml"
    path.write_text(f'switch_password: "{GOOD}"\n')  # pragma: allowlist secret
    _encrypted(path, password_file)
    with pytest.raises(sl.SecretsError, match="could not decrypt"):
        sl.load_secrets(
            path,
            project_root=tmp_path,
            environ={
                "ANSIBLE_VAULT_IDENTITY_LIST": f"default@{wrong}",
                "PATH": os.environ["PATH"],
            },
        )


def test_preview_and_deploy_use_shared_switch_loader():
    generate = (SCRIPTS / "generate-node-instructions.py").read_text()
    deploy = (SCRIPTS / "air-deploy.py").read_text()
    assert "load_switch_password(" in generate
    assert "load_switch_password(" in deploy
    assert "yaml.safe_load" in deploy or "inventory_yaml.load" in deploy
    assert not re.search(r"(?<![\w.])yaml\.(load|unsafe_load|full_load)\(", deploy)
    main = generate[generate.index("def main()"):]
    assert main.index("load_switch_password(") < main.index("write_script(")
    for source in (generate, deploy):
        for line_no, line in enumerate(source.splitlines()):
            if "secrets.yml" in line:
                nearby = "\n".join(source.splitlines()[line_no:line_no + 5])
                assert "yaml.safe_load" not in nearby


@needs_vault
def test_regression_yaml_safe_load_of_vault_header_is_not_a_mapping(tmp_path):
    password_file = tmp_path / "password"
    password_file.write_text(VAULT_PW + "\n")  # pragma: allowlist secret
    path = tmp_path / "secrets.yml"
    path.write_text(f'switch_password: "{GOOD}"\n')  # pragma: allowlist secret
    _encrypted(path, password_file)
    assert isinstance(yaml.safe_load(path.read_text()), str)
    saved = tmp_path / ".era-secrets" / "vault-pass"
    saved.parent.mkdir()
    saved.write_text(password_file.read_text())  # pragma: allowlist secret
    assert sl.load_secrets(path, project_root=tmp_path)["switch_password"] == GOOD
