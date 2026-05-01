#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Interactive onboarding wizard for NVIDIA Air credentials.

Creates ``<project_root>/.era-secrets/air-secrets.yml`` (vault-encrypted) with the
user's NGC API key, optional username, and SSH key path. Optionally saves the
vault password to ``<project_root>/.era-secrets/vault-pass`` so future
``make air-*`` commands can decrypt without prompting.

Run once per checkout -- every arch/site under this repo reads from the
one shared vault. The ``.era-secrets/`` directory is gitignored.

Usage:
    # Interactive
    python3 scripts/air-setup.py

    # Non-interactive (for testing/CI)
    python3 scripts/air-setup.py --non-interactive \\
        --api-key nvapi-xxxx \\
        --username "" \\
        --ssh-key ~/.ssh/id_ed25519 \\
        --vault-password hunter2 \\
        --save-password
"""

import argparse
import getpass
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

# Match airlib.env.py
SHARED_VAULT_DIRNAME = ".era-secrets"
SHARED_VAULT_FILENAME = "air-secrets.yml"
SHARED_VAULT_PASS_FILENAME = "vault-pass"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

NGC_API_KEY_URL = "https://org.ngc.nvidia.com/account/api-keys"
SSH_KEY_NAMES = ("id_ed25519", "id_rsa", "id_ecdsa")


# ---------- output helpers ----------

def banner(text: str) -> None:
    print()
    print(f"━━━ {text} ━━━")
    print()


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def warn(msg: str) -> None:
    print(f"  ⚠️  {msg}")


def err(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)


def mask(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return "*" * len(value)
    # Show enough of a nvapi-/sk- style prefix to reassure users it's the right key,
    # then mask the secret portion and reveal the last 4 chars.
    return f"{value[:6]}****...{value[-4:]}"


# ---------- path helpers ----------

def shared_config_dir() -> Path:
    """Repo-local shared config dir (<project_root>/.era-secrets)."""
    return PROJECT_ROOT / SHARED_VAULT_DIRNAME


def find_existing_vault() -> Path | None:
    """Return the path to the shared Air vault, or None if not present."""
    candidate = shared_config_dir() / SHARED_VAULT_FILENAME
    return candidate if candidate.exists() else None


# ---------- prerequisite checks ----------

def ensure_ansible_vault(non_interactive: bool) -> None:
    """Verify ansible-vault is available. If missing, notify and ask to install."""
    if shutil.which("ansible-vault"):
        ok("ansible-vault found")
        return

    err("ansible-vault not found in PATH.")
    print()
    print("  ansible-vault is required to encrypt your credentials.")
    print("  Install with:  pip install ansible-core")
    print()
    if non_interactive:
        sys.exit(2)
    resp = input("  Attempt 'pip install ansible-core' now? [y/N]: ").strip().lower()
    if resp != "y":
        print("  Aborted. Install ansible-core, then re-run `make air-setup`.")
        sys.exit(2)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "ansible-core"],
            check=True,
        )
    except subprocess.CalledProcessError:
        err("pip install failed. Install ansible-core manually.")
        sys.exit(2)
    if not shutil.which("ansible-vault"):
        err("ansible-vault still not on PATH after install. Check your Python environment.")
        sys.exit(2)
    ok("ansible-vault installed")


# ---------- SSH key detection ----------

def detect_ssh_keys() -> list[Path]:
    """Return existing SSH private keys from ~/.ssh/ in preferred order."""
    ssh_dir = Path.home() / ".ssh"
    found: list[Path] = []
    if not ssh_dir.exists():
        return found
    for name in SSH_KEY_NAMES:
        key = ssh_dir / name
        if key.exists() and key.is_file():
            found.append(key)
    return found


def generate_ed25519_key(path: Path) -> None:
    """Generate a new ed25519 SSH key at ``path`` with no passphrase."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(path), "-N", "", "-q"],
            check=True,
        )
    except FileNotFoundError:
        err("ssh-keygen not found in PATH.")
        sys.exit(2)
    except subprocess.CalledProcessError as exc:
        err(f"ssh-keygen failed: {exc}")
        sys.exit(2)
    ok(f"generated {path}")


def prompt_ssh_key(current: str | None = None) -> str:
    """Interactive SSH key selection; returns the chosen path (as a string, unexpanded)."""
    found = detect_ssh_keys()
    print()
    if found:
        print("  Found SSH keys in ~/.ssh/:")
        for i, k in enumerate(found, 1):
            tag = " (recommended)" if i == 1 else ""
            print(f"    [{i}] {k}{tag}")
        next_i = len(found) + 1
        print(f"    [{next_i}] Enter a different path")
        print(f"    [{next_i + 1}] Generate a new key (ed25519 at ~/.ssh/id_ed25519)")
        default = "1"
    else:
        print("  No SSH keys found in ~/.ssh/.")
        print("    [1] Enter a custom path")
        print("    [2] Generate a new key (ed25519 at ~/.ssh/id_ed25519)")
        next_i = 1
        default = "2"

    while True:
        raw = input(f"  Choice [{default}]: ").strip() or default
        if not raw.isdigit():
            warn("Enter a number.")
            continue
        choice = int(raw)
        if found and 1 <= choice <= len(found):
            return str(found[choice - 1]).replace(str(Path.home()), "~", 1)
        if choice == next_i:
            custom = input("  SSH private key path: ").strip()
            if not custom:
                warn("Path is required.")
                continue
            expanded = Path(custom).expanduser()
            if not expanded.exists():
                warn(f"{expanded} does not exist. Pick another option or create it first.")
                continue
            return custom
        if choice == next_i + 1:
            target = Path.home() / ".ssh" / "id_ed25519"
            if target.exists():
                warn(f"{target} already exists; using it instead of generating.")
            else:
                generate_ed25519_key(target)
            return "~/.ssh/id_ed25519"
        warn("Invalid choice.")


# ---------- vault password handling ----------

def prompt_vault_password(confirm: bool = True) -> str:
    """Prompt for a vault password with confirmation."""
    while True:
        pw = getpass.getpass("  Vault password: ")
        if not pw:
            warn("Password cannot be empty.")
            continue
        if not confirm:
            return pw
        pw2 = getpass.getpass("  Confirm:        ")
        if pw == pw2:
            return pw
        warn("Passwords do not match, try again.")


def prompt_save_password() -> bool:
    """Ask the user whether to save the vault password to a file."""
    print()
    print("  How should we remember your vault password?")
    print(f"    [1] Save to ./{SHARED_VAULT_DIRNAME}/{SHARED_VAULT_PASS_FILENAME} (convenient; default)")
    print("    [2] Prompt every time (more secure; you'll type it often)")
    while True:
        choice = input("  Choice [1]: ").strip() or "1"
        if choice == "1":
            return True
        if choice == "2":
            return False
        warn("Enter 1 or 2.")


def read_vault_pass_file(cfg_dir: Path) -> str | None:
    """Return the saved vault password, or None if not present."""
    path = cfg_dir / SHARED_VAULT_PASS_FILENAME
    if not path.exists():
        return None
    return path.read_text().strip() or None


# ---------- vault I/O ----------

def _write_password_tempfile(password: str) -> Path:
    """Write the password to a 0600 tempfile and return the path."""
    fd, tmp_path = tempfile.mkstemp(prefix="air-vault-", suffix=".pass")
    os.close(fd)
    path = Path(tmp_path)
    path.chmod(0o600)
    path.write_text(password)
    return path


def decrypt_vault(vault_path: Path, password: str) -> dict:
    """Decrypt an existing vault file and return its contents as a dict."""
    pass_file = _write_password_tempfile(password)
    try:
        result = subprocess.run(
            ["ansible-vault", "view", str(vault_path),
             "--vault-password-file", str(pass_file)],
            capture_output=True, text=True, check=True, timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        err(f"Failed to decrypt existing vault:\n{exc.stderr.strip()}")
        sys.exit(1)
    finally:
        try:
            pass_file.unlink()
        except OSError:
            pass
    return yaml.safe_load(result.stdout) or {}


def write_encrypted_vault(vault_path: Path, data: dict, password: str) -> None:
    """Write ``data`` as vault-encrypted YAML to ``vault_path`` (mode 0600)."""
    vault_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    plaintext_fd, plaintext_tmp = tempfile.mkstemp(
        prefix="air-secrets-", suffix=".yml", dir=vault_path.parent,
    )
    plaintext_path = Path(plaintext_tmp)
    try:
        with os.fdopen(plaintext_fd, "w") as f:
            f.write("---\n")
            f.write("# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.\n")
            f.write("# SPDX-License-Identifier: MIT\n")
            f.write("# NVIDIA Air shared credentials.\n")
            f.write("# Managed by `make air-setup` -- edit with `ansible-vault edit`.\n")
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        plaintext_path.chmod(0o600)

        pass_file = _write_password_tempfile(password)
        try:
            if vault_path.exists():
                vault_path.unlink()
            subprocess.run(
                ["ansible-vault", "encrypt",
                 "--vault-password-file", str(pass_file),
                 "--output", str(vault_path),
                 str(plaintext_path)],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            err(f"ansible-vault encrypt failed:\n{exc.stderr.strip()}")
            sys.exit(1)
        finally:
            try:
                pass_file.unlink()
            except OSError:
                pass
    finally:
        if plaintext_path.exists():
            plaintext_path.unlink()

    vault_path.chmod(0o600)


def write_password_file(cfg_dir: Path, password: str) -> Path:
    """Write the vault password to cfg_dir/vault-pass with 0600 perms."""
    cfg_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    pass_path = cfg_dir / SHARED_VAULT_PASS_FILENAME
    pass_path.write_text(password + "\n")
    pass_path.chmod(0o600)
    return pass_path


def remove_password_file(cfg_dir: Path) -> None:
    pass_path = cfg_dir / SHARED_VAULT_PASS_FILENAME
    if pass_path.exists():
        pass_path.unlink()


# ---------- field prompts ----------

def prompt_api_key() -> str:
    print(f"  Generate one at: {NGC_API_KEY_URL}")
    print()
    print("  1. Check the top-right account selector and make sure you're on the")
    print("     correct NGC account before generating the key.")
    print("  2. Click 'Generate Personal Key'.")
    print("  3. Copy the value -- it should start with 'nvapi-'.")
    print("     (NGC only shows the key once; copy it before leaving the page.)")
    print()
    print("  Note: these steps are for a Personal Key. If you need a Service Key")
    print("  (shared/CI use), the NGC flow is similar but the exact buttons and")
    print("  key format may differ -- see your NGC org admin or the NGC docs.")
    print()
    while True:
        key = getpass.getpass("  NGC API key: ")
        if len(key) < 20:
            warn("That seems too short for an NGC API key -- try again.")
            continue
        if not key.startswith("nvapi-"):
            warn("NGC Personal Keys start with 'nvapi-'. Continue anyway? [y/N]")
            if input("  > ").strip().lower() != "y":
                continue
        confirm = getpass.getpass("  Confirm:     ")
        if key != confirm:
            warn("Values do not match, try again.")
            continue
        return key


def prompt_username(current: str | None = None) -> str:
    print("  For NGC Air 2.0 (air.nvidia.com), leave empty and press Enter.")
    print("  For legacy Air instances, enter your email address.")
    default = f" [{current}]" if current else ""
    val = input(f"  Air username (blank for NGC){default}: ").strip()
    if not val and current is not None:
        return current
    return val


AIR_INSTANCES = {
    "1": ("Public NGC Air", "https://air-ngc.nvidia.com"),
    "2": ("Internal (air-inside)", "https://ngc.air-inside.nvidia.com"),
}


def prompt_air_url(current: str | None = None) -> str:
    """Pick an Air instance URL. Returns the chosen URL (stripped of trailing /)."""
    print("  Which NVIDIA Air instance are you deploying against?")
    for k, (name, url) in AIR_INSTANCES.items():
        print(f"    [{k}] {name:24} ({url})")
    print(f"    [3] Custom URL")
    if current:
        # Pre-select the matching option so [Enter] keeps the current value.
        default = next(
            (k for k, (_, url) in AIR_INSTANCES.items() if url == current.rstrip("/")),
            "3",
        )
        print(f"  Current: {current}")
    else:
        default = "1"
    while True:
        raw = input(f"  Choice [{default}]: ").strip() or default
        if raw in AIR_INSTANCES:
            return AIR_INSTANCES[raw][1]
        if raw == "3":
            val = input(f"  Custom Air URL{' [' + current + ']' if current else ''}: ").strip()
            if not val and current:
                return current.rstrip("/")
            if not val:
                warn("URL is required.")
                continue
            if not val.startswith(("http://", "https://")):
                warn("URL must start with http:// or https://")
                continue
            return val.rstrip("/")
        warn("Enter 1, 2, or 3.")


# ---------- update picker ----------

def choose_fields_to_update(existing: dict) -> list[str]:
    """Ask the user which fields to update. Returns the list of field names."""
    print()
    print("  Current values:")
    print(f"    air_api_key:       {mask(existing.get('air_api_key', ''))}")
    print(f"    air_url:           {existing.get('air_url') or '(none)'}")
    print(f"    air_username:      {existing.get('air_username') or '(empty)'}")
    print(f"    air_ssh_key_path:  {existing.get('air_ssh_key_path') or '(none)'}")
    print()
    print("  Which fields do you want to update?")
    print("    [1] All")
    print("    [2] api_key")
    print("    [3] air_url (Air instance)")
    print("    [4] username")
    print("    [5] ssh_key")
    print("    [6] Nothing (exit)")
    while True:
        raw = input("  Choice [1]: ").strip() or "1"
        mapping = {
            "1": ["api_key", "air_url", "username", "ssh_key"],
            "2": ["api_key"],
            "3": ["air_url"],
            "4": ["username"],
            "5": ["ssh_key"],
            "6": [],
        }
        if raw in mapping:
            return mapping[raw]
        warn("Enter 1-6.")


# ---------- main wizard ----------

def run_interactive() -> int:
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  NVIDIA Air Credentials Setup")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print("  This wizard collects your NVIDIA Air API credentials and saves")
    print("  them encrypted so every `make air-*` command can use them.")
    print()
    print(f"  Storage:  {shared_config_dir() / SHARED_VAULT_FILENAME}")
    print()

    cfg_dir = shared_config_dir()
    ensure_ansible_vault(non_interactive=False)

    existing_path = find_existing_vault()
    existing_data: dict = {}
    existing_password: str | None = None
    fields_to_update: list[str] = ["api_key", "air_url", "username", "ssh_key"]

    if existing_path is not None:
        banner("Existing vault detected")
        print(f"  Found: {existing_path}")
        print()
        saved_pass = read_vault_pass_file(cfg_dir)
        if saved_pass:
            ok("using saved vault password")
            existing_password = saved_pass
        else:
            print("  Enter the vault password to decrypt existing values:")
            existing_password = prompt_vault_password(confirm=False)
        existing_data = decrypt_vault(existing_path, existing_password)
        fields_to_update = choose_fields_to_update(existing_data)
        if not fields_to_update:
            print()
            ok("nothing to update -- goodbye.")
            return 0

    new_data = dict(existing_data)

    if "api_key" in fields_to_update:
        banner("NGC API Key")
        new_data["air_api_key"] = prompt_api_key()

    if "air_url" in fields_to_update:
        banner("Air Instance")
        new_data["air_url"] = prompt_air_url(existing_data.get("air_url"))

    if "username" in fields_to_update:
        banner("Air Username")
        new_data["air_username"] = prompt_username(existing_data.get("air_username"))

    if "ssh_key" in fields_to_update:
        banner("SSH Key")
        new_data["air_ssh_key_path"] = prompt_ssh_key(existing_data.get("air_ssh_key_path"))

    for k in ("air_api_key", "air_url", "air_username", "air_ssh_key_path"):
        new_data.setdefault(k, existing_data.get(k, ""))

    banner("Vault Password")
    if existing_password is not None:
        reuse = input("  Keep existing vault password? [Y/n]: ").strip().lower()
        if reuse in ("", "y", "yes"):
            password = existing_password
        else:
            password = prompt_vault_password(confirm=True)
    else:
        password = prompt_vault_password(confirm=True)

    save_pw = prompt_save_password()

    banner("Writing vault")
    vault_path = existing_path or (cfg_dir / SHARED_VAULT_FILENAME)
    write_encrypted_vault(vault_path, new_data, password)
    ok(f"wrote {vault_path} (mode 0600)")

    if save_pw:
        pass_path = write_password_file(cfg_dir, password)
        ok(f"saved vault password to {pass_path} (mode 0600)")
    else:
        remove_password_file(cfg_dir)
        ok("vault password not saved -- you'll be prompted each run")

    print()
    ok("setup complete. All `make air-*` commands are ready to use.")
    print()
    return 0


def run_non_interactive(args: argparse.Namespace) -> int:
    ensure_ansible_vault(non_interactive=True)

    if not args.api_key:
        err("--api-key is required in non-interactive mode")
        return 2
    if not args.vault_password:
        err("--vault-password is required in non-interactive mode")
        return 2
    if not args.ssh_key:
        args.ssh_key = "~/.ssh/id_ed25519"

    cfg_dir = shared_config_dir()
    vault_path = find_existing_vault() or (cfg_dir / SHARED_VAULT_FILENAME)

    data = {
        "air_api_key": args.api_key,
        "air_url": (args.air_url or "").rstrip("/"),
        "air_username": args.username or "",
        "air_ssh_key_path": args.ssh_key,
    }

    write_encrypted_vault(vault_path, data, args.vault_password)
    ok(f"wrote {vault_path}")

    if args.save_password:
        write_password_file(cfg_dir, args.vault_password)
        ok("saved vault password")
    else:
        remove_password_file(cfg_dir)

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Onboarding wizard for NVIDIA Air credentials.",
    )
    ap.add_argument("--non-interactive", action="store_true",
                    help=argparse.SUPPRESS)
    ap.add_argument("--api-key", help=argparse.SUPPRESS)
    ap.add_argument("--air-url", help=argparse.SUPPRESS)
    ap.add_argument("--username", help=argparse.SUPPRESS)
    ap.add_argument("--ssh-key", help=argparse.SUPPRESS)
    ap.add_argument("--vault-password", help=argparse.SUPPRESS)
    ap.add_argument("--save-password", action="store_true",
                    help=argparse.SUPPRESS)
    args = ap.parse_args()

    try:
        if args.non_interactive:
            return run_non_interactive(args)
        return run_interactive()
    except KeyboardInterrupt:
        print()
        print("  Aborted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
