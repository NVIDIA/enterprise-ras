# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Regression test for the air-setup vault write: a failed `ansible-vault encrypt`
must NOT destroy the existing vault. The old code unlinked vault_path before
encrypting, so any encrypt failure lost the credentials with nothing written.
The fix encrypts to a temp file and atomically os.replace()s on success.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_air_setup():
    spec = importlib.util.spec_from_file_location("air_setup", SCRIPTS / "air-setup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


air_setup = _load_air_setup()


def test_failed_encrypt_preserves_existing_vault(tmp_path, monkeypatch):
    vault = tmp_path / "air-secrets.yml"
    vault.write_text("ORIGINAL ENCRYPTED VAULT CONTENT\n")

    def boom(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, stderr="simulated encrypt failure")

    monkeypatch.setattr(air_setup.subprocess, "run", boom)

    with pytest.raises(SystemExit):
        air_setup.write_encrypted_vault(vault, {"air_api_key": "x"}, "pw")

    # The original vault must be intact — not deleted, not truncated.
    assert vault.exists()
    assert vault.read_text() == "ORIGINAL ENCRYPTED VAULT CONTENT\n"
    # No temp turds left behind in the secrets dir.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "air-secrets.yml"]
    assert leftovers == [], f"leftover temp files: {leftovers}"


def test_successful_encrypt_replaces_vault(tmp_path, monkeypatch):
    vault = tmp_path / "air-secrets.yml"
    vault.write_text("OLD CONTENT\n")

    # Simulate ansible-vault: write the encrypted output to the --output path.
    def fake_vault(cmd, **kwargs):
        out = cmd[cmd.index("--output") + 1]
        Path(out).write_text("$ANSIBLE_VAULT;1.1;AES256\nNEWDATA\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(air_setup.subprocess, "run", fake_vault)

    air_setup.write_encrypted_vault(vault, {"air_api_key": "x"}, "pw")

    assert vault.read_text().startswith("$ANSIBLE_VAULT")
    assert (vault.stat().st_mode & 0o777) == 0o600
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "air-secrets.yml"]
    assert leftovers == [], f"leftover temp files: {leftovers}"
