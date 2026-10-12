#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Load plaintext or whole-file Ansible Vault secrets.

Use ``load_secrets(path)`` to obtain a mapping and ``resolve_secret`` to read
one actionable, plaintext value from it. The loader accepts per-variable
``!vault`` values for compatibility with the existing secrets checker, but
callers that need a concrete secret must use a fully decryptable file.
"""

import os
import re
import subprocess
from pathlib import Path

import yaml

import check_secrets as cs

VAULT_PASS_ENV = "ANSIBLE_VAULT_PASSWORD_FILE"
SHARED_VAULT_DIRNAME = ".era-secrets"
SHARED_VAULT_PASS_FILENAME = "vault-pass"
DEFAULT_SWITCH_PASSWORD = "Cumu1usLinux!"  # pragma: allowlist secret
_VAULT_CONFIG_RE = re.compile(
    r"^[ \t]*vault_(password_file|identity_list)[ \t]*=",
    re.MULTILINE,
)


class SecretsError(Exception):
    """Actionable message; callers print and exit non-zero."""


def default_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def find_vault_password_file(project_root=None, environ=None) -> Path | None:
    """Return the configured vault password file, if one exists."""
    root = default_project_root() if project_root is None else Path(project_root)
    env = os.environ if environ is None else environ
    env_path = env.get(VAULT_PASS_ENV)
    if env_path:
        path = Path(env_path).expanduser()
        if path.exists():
            return path
    saved = root / SHARED_VAULT_DIRNAME / SHARED_VAULT_PASS_FILENAME
    return saved if saved.exists() else None


def effective_ansible_config(environ=None) -> Path | None:
    """Return Ansible's first existing configuration candidate."""
    env = os.environ if environ is None else environ
    candidates = []
    if env.get("ANSIBLE_CONFIG"):
        candidates.append(Path(env["ANSIBLE_CONFIG"]).expanduser())
    candidates.append(Path("ansible.cfg"))
    home = env.get("HOME")
    candidates.append(
        (Path(home) if home else Path("/")) / ".ansible.cfg"
    )
    candidates.append(Path("/etc/ansible/ansible.cfg"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def has_native_vault_source(environ=None) -> bool:
    """Return whether Ansible itself can resolve a vault source."""
    return _has_native_vault_source(environ)


def _has_native_vault_source(environ=None) -> bool:
    env = os.environ if environ is None else environ
    if "ANSIBLE_VAULT_IDENTITY_LIST" in env:
        return True
    if env.get("DEFAULT_VAULT_PASSWORD_FILE"):
        return True
    config = effective_ansible_config(env)
    if config is None:
        return False
    try:
        return _VAULT_CONFIG_RE.search(config.read_text(encoding="utf-8")) is not None
    except OSError:
        return False


def _missing_password_message(path: Path) -> str:
    return (
        f"{path} is vault-encrypted but no vault password source was found. "
        "Provide one of: make secrets, .era-secrets/vault-pass, or "
        "export ANSIBLE_VAULT_PASSWORD_FILE=/path/to/password-file."
    )


def load_secrets(path: Path, project_root=None, environ=None) -> dict:
    """Read a secrets mapping, decrypting whole-file Vault data when needed."""
    path = Path(path)
    if not path.exists():
        raise SecretsError(f"{path} not found; create it with make secrets")

    encrypted = cs.is_vault_encrypted(path)
    if encrypted:
        env = os.environ if environ is None else environ
        env_password_file = env.get(VAULT_PASS_ENV)
        password_file = (
            Path(env_password_file).expanduser()
            if env_password_file and Path(env_password_file).expanduser().exists()
            else None
        )
        native_source = False
        if password_file is not None:
            command = [
                "ansible-vault", "view", str(path),
                "--vault-password-file", str(password_file),
            ]
            command_env = dict(env)
            command_env.pop(VAULT_PASS_ENV, None)
        elif _has_native_vault_source(env):
            command = ["ansible-vault", "view", str(path)]
            command_env = dict(env)
            native_source = True
        else:
            password_file = find_vault_password_file(project_root, env)
            if password_file is None:
                raise SecretsError(_missing_password_message(path))
            command = [
                "ansible-vault", "view", str(path),
                "--vault-password-file", str(password_file),
            ]
            command_env = dict(env)
            command_env.pop(VAULT_PASS_ENV, None)
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=60,
                env=command_env,
            )
        except FileNotFoundError as exc:
            raise SecretsError(
                "ansible-vault not found in PATH (pip install ansible-core)"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SecretsError(f"ansible-vault timed out while decrypting {path}") from exc
        if result.returncode != 0:
            detail = ""
            if native_source and result.stderr.strip():
                detail = f": {result.stderr.strip().splitlines()[-1]}"
            if password_file is None:
                raise SecretsError(
                    f"ansible-vault could not decrypt {path}{detail}"
                )
            raise SecretsError(
                f"ansible-vault could not decrypt {path} "
                f"(wrong vault password in {password_file}?)"
            )
        text = result.stdout
    else:
        text = path.read_text(encoding="utf-8")

    try:
        data = yaml.load(
            text,
            Loader=cs._SecretsLoader,
        )
    except yaml.YAMLError as exc:
        if encrypted:
            raise SecretsError(
                f"decrypted content of {path} is not valid YAML"
            ) from exc
        raise SecretsError(f"{path} is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SecretsError(
            f"{path} does not contain a mapping (got {type(data).__name__})"
        )
    return data


def resolve_secret(
    secrets: dict, key: str, *, default=None, path="secrets.yml"
) -> str:
    """Resolve one concrete, non-empty string secret from a mapping."""
    if key not in secrets:
        if default is not None:
            return default
        raise SecretsError(f"{key} is not set in {path}")
    value, reason = cs.resolve_value(secrets, key)
    if reason:
        raise SecretsError(
            f"{key} in {path} {reason}; it cannot be resolved here — "
            "set a plaintext value or decrypt the whole file with ansible-vault "
            "instead of per-variable !vault"
        )
    if not isinstance(value, str) or not value:
        raise SecretsError(
            f"{key} in {path} must be a string, got {type(value).__name__}"
        )
    return value


def load_switch_password(
    inventory_dir: Path, project_root=None, environ=None
) -> str:
    """Load the switch password, using the documented development fallback."""
    path = Path(inventory_dir) / "group_vars" / "all" / "secrets.yml"
    if not path.exists():
        return DEFAULT_SWITCH_PASSWORD
    secrets = load_secrets(path, project_root, environ)
    return resolve_secret(
        secrets, "switch_password", default=DEFAULT_SWITCH_PASSWORD, path=path
    )


def load_server_password(
    inventory_dir: Path, project_root=None, environ=None
) -> str:
    """Load the required server Ansible password."""
    path = Path(inventory_dir) / "group_vars" / "all" / "secrets.yml"
    secrets = load_secrets(path, project_root, environ)
    return resolve_secret(secrets, "server_ansible_password", path=path)
