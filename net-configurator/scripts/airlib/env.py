# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Environment and credential loading for Air API scripts.

Air credentials and instance URL live in a single shared vault at
``<project_root>/.era-secrets/air-secrets.yml``. The file is expected to be
vault-encrypted; run ``make air-setup`` to create it. The ``.era-secrets/``
directory is gitignored.

Precedence (higher wins):
1. Shell environment variables (``AIR_BASE_URL``, ``AIR_API_KEY``,
   ``AIR_USERNAME``, ``AIR_SSH_KEY_PATH``)
2. Shared vault at ``.era-secrets/air-secrets.yml`` (``air_url``,
   ``air_api_key``, ``air_username``, ``air_ssh_key_path``)

For decryption, the loader auto-points ``ANSIBLE_VAULT_PASSWORD_FILE`` at
``.era-secrets/vault-pass`` if that file exists and the env var is not
already set. Otherwise ``ansible-vault view`` prompts interactively.
"""

import os
import subprocess
from pathlib import Path

import yaml

from airlib.errors import AirConfigError


SHARED_VAULT_DIRNAME = ".era-secrets"
SHARED_VAULT_FILENAME = "air-secrets.yml"
SHARED_VAULT_PASS_FILENAME = "vault-pass"


def _default_project_root() -> Path:
    """Resolve the project root from this file's location."""
    return Path(__file__).resolve().parent.parent.parent


def shared_vault_dir(project_root: Path | None = None) -> Path:
    """Return the in-repo directory that holds the shared Air vault."""
    if project_root is None:
        project_root = _default_project_root()
    return project_root / SHARED_VAULT_DIRNAME


def find_shared_vault(project_root: Path | None = None) -> Path | None:
    """Return the path to the shared Air vault, or None if not found."""
    candidate = shared_vault_dir(project_root) / SHARED_VAULT_FILENAME
    return candidate if candidate.exists() else None


def find_shared_vault_pass(project_root: Path | None = None) -> Path | None:
    """Return the path to the saved vault-pass file, or None."""
    candidate = shared_vault_dir(project_root) / SHARED_VAULT_PASS_FILENAME
    return candidate if candidate.exists() else None


def _read_vault_file(path: Path, vault_pass_file: Path | None = None) -> dict:
    """Read a YAML file that may be vault-encrypted.

    If the file starts with ``$ANSIBLE_VAULT``, decrypts via ``ansible-vault view``.
    Otherwise parses as plain YAML (tolerated for dev convenience).
    """
    if not path.exists():
        return {}

    content = path.read_text()
    if not content.startswith("$ANSIBLE_VAULT"):
        try:
            return yaml.safe_load(content) or {}
        except yaml.YAMLError as exc:
            raise AirConfigError(
                f"{path} is not valid YAML:\n{exc}\n"
                "Fix the file or re-run `make air-setup` to recreate it."
            ) from exc

    cmd = ["ansible-vault", "view", str(path)]
    if vault_pass_file is None:
        env_vault_pass = os.environ.get("ANSIBLE_VAULT_PASSWORD_FILE")
        if env_vault_pass:
            vault_pass_file = Path(env_vault_pass)
    if vault_pass_file and vault_pass_file.exists():
        cmd.extend(["--vault-password-file", str(vault_pass_file)])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=30,
        )
        try:
            return yaml.safe_load(result.stdout) or {}
        except yaml.YAMLError as exc:
            raise AirConfigError(
                f"Decrypted {path} is not valid YAML:\n{exc}\n"
                "Re-run `make air-setup` to recreate the vault."
            ) from exc
    except subprocess.CalledProcessError as exc:
        raise AirConfigError(
            f"Failed to decrypt {path}:\n{exc.stderr.strip()}\n"
            "Provide the vault password by setting ANSIBLE_VAULT_PASSWORD_FILE,\n"
            "saving it to .era-secrets/vault-pass, or re-running\n"
            "`make air-setup` to reconfigure."
        ) from exc
    except FileNotFoundError as exc:
        raise AirConfigError(
            "ansible-vault not found in PATH. Install ansible-core "
            "(`pip install ansible-core`) or run `make air-setup` for guidance."
        ) from exc


def _load_shared_air_vault(project_root: Path | None = None) -> dict:
    """Read the shared Air vault from ``<project_root>/.era-secrets/``.

    Auto-uses ``.era-secrets/vault-pass`` if present and
    ``ANSIBLE_VAULT_PASSWORD_FILE`` is not already set. Returns an empty
    dict if no shared vault exists.
    """
    vault_path = find_shared_vault(project_root)
    if vault_path is None:
        return {}

    pass_path: Path | None = None
    if not os.environ.get("ANSIBLE_VAULT_PASSWORD_FILE"):
        pass_path = find_shared_vault_pass(project_root)

    return _read_vault_file(vault_path, vault_pass_file=pass_path)


def load_air_config(
    arch: str,
    site: str = "default",
    project_root: Path | None = None,
) -> dict[str, str]:
    """Load Air API configuration.

    Returns dict with keys: base_url, username, api_key, ssh_key_path, org.

    ``org`` is the NGC organization id sent as the ``nv-ngc-org`` header. It is
    OPTIONAL — empty/unset means no header (the current air-inside gateway
    accepts bearer-only requests); set it to future-proof for a gateway that
    requires the org.

    Precedence (higher wins):
    1. Shell environment variables (AIR_BASE_URL, AIR_API_KEY, AIR_USERNAME, AIR_SSH_KEY_PATH, AIR_NGC_ORG)
    2. Shared vault at <project_root>/.era-secrets/air-secrets.yml

    ``arch`` and ``site`` are accepted for interface compatibility but are no
    longer consulted — per-deployment inventory does not carry Air credentials.
    """
    if project_root is None:
        project_root = _default_project_root()

    config: dict[str, str] = {}

    vault = _load_shared_air_vault(project_root)
    if vault.get("air_api_key"):
        config["api_key"] = str(vault["air_api_key"])
    if vault.get("air_url"):
        config["base_url"] = str(vault["air_url"]).rstrip("/")
    if vault.get("air_username"):
        config["username"] = str(vault["air_username"])
    if vault.get("air_ssh_key_path"):
        config["ssh_key_path"] = str(vault["air_ssh_key_path"])
    if vault.get("air_org"):
        config["org"] = str(vault["air_org"]).strip()

    for env_key, config_key in [
        ("AIR_BASE_URL", "base_url"),
        ("AIR_API_KEY", "api_key"),
        ("AIR_USERNAME", "username"),
        ("AIR_SSH_KEY_PATH", "ssh_key_path"),
        ("AIR_NGC_ORG", "org"),
    ]:
        val = os.environ.get(env_key)
        if val:
            config[config_key] = val.rstrip("/") if config_key == "base_url" else val

    config.setdefault("username", "")
    config.setdefault("ssh_key_path", "~/.ssh/id_ed25519")
    config.setdefault("org", "")

    # Configure the NGC org header for every Air API call from the resolved
    # config — done here (the single config chokepoint all air-* scripts call)
    # so no individual script can forget to set it. Local import avoids a hard
    # dependency for callers that only need config (no api/httpx).
    try:
        from airlib.api import set_ngc_org
        set_ngc_org(config.get("org"))
    except Exception:
        pass  # api/httpx not importable in this context — header stays disabled

    return config


def require_config(config: dict[str, str], *keys: str) -> None:
    """Raise AirConfigError if any keys are missing or empty."""
    missing = [k for k in keys if not config.get(k)]
    if missing:
        hints = []
        if "base_url" in missing:
            hints.append(
                "  base_url: Run `make air-setup` to pick an Air instance (public\n"
                "            NGC Air vs internal air-inside) and store it in the\n"
                "            shared vault, or export AIR_BASE_URL for one-off use."
            )
        if "api_key" in missing:
            hints.append(
                "  api_key:  Run `make air-setup` to create the shared Air vault\n"
                "            at .era-secrets/air-secrets.yml (in this repo),\n"
                "            or export AIR_API_KEY for one-off use."
            )
        hint_block = "\n".join(hints)
        raise AirConfigError(
            f"Missing required Air configuration: {', '.join(missing)}\n"
            f"{hint_block}"
        )
