# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Tests for the Air credentials loader (scripts/airlib/env.py).

Covers the precedence matrix (shell env > repo-local shared vault), vault
discovery under ``<project_root>/.era-secrets/``, and vault-password-file
auto-use.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from airlib import env as airlib_env  # noqa: E402
from airlib.errors import AirConfigError  # noqa: E402


HAS_ANSIBLE_VAULT = shutil.which("ansible-vault") is not None


@pytest.fixture
def dummy_project(tmp_path, monkeypatch):
    """Create an isolated project root. Tests populate `.era-secrets/` as needed —
    the per-deployment inventory no longer carries Air creds (see commit 419e745
    — air_url moved from Excel/main.yml to the shared vault)."""
    root = tmp_path / "project"
    root.mkdir()
    for var in ("AIR_API_KEY", "AIR_USERNAME", "AIR_SSH_KEY_PATH",
                "AIR_BASE_URL", "ANSIBLE_VAULT_PASSWORD_FILE"):
        monkeypatch.delenv(var, raising=False)
    return root


def write_plain_vault(project_root: Path,
                      api_key: str = "nvapi-test-key-longer-than-20",
                      air_url: str = "https://air.example.com",
                      username: str = "",
                      ssh_key: str = "~/.ssh/id_ed25519") -> Path:
    """Write an unencrypted YAML to the in-repo shared-vault location."""
    vault_dir = project_root / airlib_env.SHARED_VAULT_DIRNAME
    vault_dir.mkdir(parents=True, exist_ok=True)
    vault = vault_dir / airlib_env.SHARED_VAULT_FILENAME
    vault.write_text(
        f"air_api_key: '{api_key}'\n"
        f"air_url: '{air_url}'\n"
        f"air_username: '{username}'\n"
        f"air_ssh_key_path: '{ssh_key}'\n"
    )
    return vault


def write_encrypted_vault(project_root: Path, password: str, api_key: str) -> Path:
    """Encrypt a YAML via ansible-vault and place it under .era-secrets/."""
    vault_dir = project_root / airlib_env.SHARED_VAULT_DIRNAME
    vault_dir.mkdir(parents=True, exist_ok=True)

    plain = vault_dir / "plain.yml"
    plain.write_text(
        f"air_api_key: '{api_key}'\n"
        f"air_username: ''\n"
        f"air_ssh_key_path: '~/.ssh/id_ed25519'\n"
    )

    pass_file = vault_dir / "_enc_pass"
    pass_file.write_text(password)
    pass_file.chmod(0o600)

    vault = vault_dir / airlib_env.SHARED_VAULT_FILENAME
    if vault.exists():
        vault.unlink()
    subprocess.run(
        ["ansible-vault", "encrypt",
         "--vault-password-file", str(pass_file),
         "--output", str(vault),
         str(plain)],
        check=True, capture_output=True, text=True,
    )
    plain.unlink()
    pass_file.unlink()
    return vault


def write_password_file(project_root: Path, password: str) -> Path:
    vault_dir = project_root / airlib_env.SHARED_VAULT_DIRNAME
    vault_dir.mkdir(parents=True, exist_ok=True)
    pass_file = vault_dir / airlib_env.SHARED_VAULT_PASS_FILENAME
    pass_file.write_text(password + "\n")
    pass_file.chmod(0o600)
    return pass_file


# ---------- precedence (no encryption) ----------

def test_no_vault_no_env_raises(dummy_project):
    config = airlib_env.load_air_config("2-8-5-200", project_root=dummy_project)
    assert "api_key" not in config
    with pytest.raises(AirConfigError):
        airlib_env.require_config(config, "base_url", "api_key")


def test_shared_vault_provides_creds(dummy_project):
    write_plain_vault(dummy_project, api_key="nvapi-from-vault-xxxx",
                      air_url="https://air.example.com")
    config = airlib_env.load_air_config("2-8-5-200", project_root=dummy_project)
    assert config["api_key"] == "nvapi-from-vault-xxxx"
    assert config["base_url"] == "https://air.example.com"


def test_shell_env_overrides_vault(dummy_project, monkeypatch):
    write_plain_vault(dummy_project, api_key="nvapi-from-vault-xxxx")
    monkeypatch.setenv("AIR_API_KEY", "nvapi-env-override-xxxx")
    config = airlib_env.load_air_config("2-8-5-200", project_root=dummy_project)
    assert config["api_key"] == "nvapi-env-override-xxxx"


def test_shell_env_provides_base_url(dummy_project, monkeypatch, tmp_path):
    # Point at a project without main.yml; AIR_BASE_URL should still resolve.
    blank_root = tmp_path / "blank"
    blank_root.mkdir()
    monkeypatch.setenv("AIR_BASE_URL", "https://air-env.example.com/")
    config = airlib_env.load_air_config("no-such-arch", project_root=blank_root)
    assert config["base_url"] == "https://air-env.example.com"


def test_ssh_key_path_default_when_nothing_set(dummy_project):
    config = airlib_env.load_air_config("2-8-5-200", project_root=dummy_project)
    assert config["ssh_key_path"] == "~/.ssh/id_ed25519"


# ---------- discovery ----------

def test_find_shared_vault_returns_none_when_absent(dummy_project):
    assert airlib_env.find_shared_vault(dummy_project) is None


def test_find_shared_vault_returns_path_when_present(dummy_project):
    vault = write_plain_vault(dummy_project)
    assert airlib_env.find_shared_vault(dummy_project) == vault


def test_shared_vault_dir_resolves_under_project_root(dummy_project):
    got = airlib_env.shared_vault_dir(dummy_project)
    assert got == dummy_project / ".era-secrets"


# ---------- vault-encrypted path ----------

@pytest.mark.skipif(not HAS_ANSIBLE_VAULT, reason="ansible-vault not installed")
def test_encrypted_vault_with_password_file(dummy_project):
    write_encrypted_vault(dummy_project, password="hunter2",
                          api_key="nvapi-encrypted-xxxxx")
    write_password_file(dummy_project, "hunter2")

    config = airlib_env.load_air_config("2-8-5-200", project_root=dummy_project)
    assert config["api_key"] == "nvapi-encrypted-xxxxx"


@pytest.mark.skipif(not HAS_ANSIBLE_VAULT, reason="ansible-vault not installed")
def test_encrypted_vault_wrong_password_raises(dummy_project):
    write_encrypted_vault(dummy_project, password="real",
                          api_key="nvapi-encrypted-xxxxx")
    write_password_file(dummy_project, "wrong")

    with pytest.raises(AirConfigError):
        airlib_env.load_air_config("2-8-5-200", project_root=dummy_project)


@pytest.mark.skipif(not HAS_ANSIBLE_VAULT, reason="ansible-vault not installed")
def test_existing_ansible_vault_password_file_env_respected(
    dummy_project, tmp_path, monkeypatch,
):
    """If ANSIBLE_VAULT_PASSWORD_FILE is set, don't auto-use the stored file."""
    write_encrypted_vault(dummy_project, password="real",
                          api_key="nvapi-encrypted-xxxxx")
    # Stored password file has the wrong password...
    write_password_file(dummy_project, "wrong")
    # ...but the user-provided env var points at the correct one.
    user_pass = tmp_path / "user.pass"
    user_pass.write_text("real")
    user_pass.chmod(0o600)
    monkeypatch.setenv("ANSIBLE_VAULT_PASSWORD_FILE", str(user_pass))

    config = airlib_env.load_air_config("2-8-5-200", project_root=dummy_project)
    assert config["api_key"] == "nvapi-encrypted-xxxxx"


# ---------- require_config error hints ----------

def test_require_config_mentions_air_setup(dummy_project):
    config = airlib_env.load_air_config("2-8-5-200", project_root=dummy_project)
    with pytest.raises(AirConfigError) as exc:
        airlib_env.require_config(config, "api_key")
    msg = str(exc.value)
    assert "make air-setup" in msg
    assert ".era-secrets" in msg


def test_require_config_mentions_air_setup_for_base_url():
    """base_url hint was rewritten in commit 419e745 — it now points at
    `make air-setup` (the wizard that stores air_url in the shared vault)
    or the AIR_BASE_URL env var, no longer at the Excel Settings tab."""
    config = {}
    with pytest.raises(AirConfigError) as exc:
        airlib_env.require_config(config, "base_url")
    msg = str(exc.value)
    assert "make air-setup" in msg
    assert "AIR_BASE_URL" in msg
