# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
The Air API may send an optional `nv-ngc-org` header (GitLab #28). It must be:
  - OMITTED when no org is configured (historical bearer-only behavior the
    air-inside gateway currently accepts — sending empty/wrong could 400), and
  - PRESENT with the configured value when set.
Sourced from config (vault air_org / AIR_NGC_ORG env) via load_air_config ->
api.set_ngc_org, so every air-* script gets it without per-script wiring.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from airlib import api
from airlib.env import load_air_config


@pytest.fixture(autouse=True)
def _reset_org():
    api.set_ngc_org(None)
    yield
    api.set_ngc_org(None)


def test_header_omitted_by_default():
    h = api._headers("nvapi-xyz")
    assert h["Authorization"] == "Bearer nvapi-xyz"
    assert "nv-ngc-org" not in h


def test_header_present_when_set():
    api.set_ngc_org("my-ngc-org")
    h = api._headers("nvapi-xyz")
    assert h["nv-ngc-org"] == "my-ngc-org"


def test_set_org_blank_disables():
    api.set_ngc_org("  ")
    assert "nv-ngc-org" not in api._headers("t")
    api.set_ngc_org("org")
    api.set_ngc_org("")
    assert "nv-ngc-org" not in api._headers("t")


def test_load_air_config_wires_org_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AIR_NGC_ORG", "env-org")
    cfg = load_air_config("2-4-3-200", "default", tmp_path)  # empty root -> no vault
    assert cfg["org"] == "env-org"
    # load_air_config also pushed it onto the api module for all callers.
    assert api._headers("t").get("nv-ngc-org") == "env-org"


def test_load_air_config_org_empty_when_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("AIR_NGC_ORG", raising=False)
    cfg = load_air_config("2-4-3-200", "default", tmp_path)
    assert cfg["org"] == ""
    assert "nv-ngc-org" not in api._headers("t")
