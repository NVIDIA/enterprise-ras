# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
A malformed (hand-edited) plaintext Air credentials file must surface a typed
AirConfigError with remediation guidance, not a raw yaml.YAMLError traceback.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from airlib.env import _read_vault_file
from airlib.errors import AirConfigError


def test_malformed_plaintext_vault_raises_airconfigerror(tmp_path):
    bad = tmp_path / "air-secrets.yml"
    # Invalid YAML (unterminated flow mapping / bad indentation).
    bad.write_text("air_api_key: nvapi-x\n  : : : broken\n\tmore: [unclosed\n")
    with pytest.raises(AirConfigError) as exc:
        _read_vault_file(bad)
    assert "not valid YAML" in str(exc.value)


def test_valid_plaintext_vault_still_loads(tmp_path):
    good = tmp_path / "air-secrets.yml"
    good.write_text("air_api_key: nvapi-x\nair_username: u\n")
    assert _read_vault_file(good) == {"air_api_key": "nvapi-x", "air_username": "u"}


def test_missing_vault_returns_empty(tmp_path):
    assert _read_vault_file(tmp_path / "nope.yml") == {}
