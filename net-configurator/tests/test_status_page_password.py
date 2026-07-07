# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Security review #9/#14: the status-page Basic-Auth password must NOT default to
`switch_password` — the page is served over plain HTTP (and Air forwards it
publicly), so reusing the switch credential would leak it. Both the ZTP-server
role and the standalone playbook must use the dedicated `status_page_password`
secret with the same `era-status-CHANGE_ME` placeholder default.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HTPASSWD_SOURCES = [
    REPO / "playbooks" / "setup-status-page.yml",
    REPO / "roles" / "ztp-server" / "tasks" / "main.yml",
]


@pytest.mark.parametrize("f", HTPASSWD_SOURCES, ids=lambda p: p.name)
def test_htpasswd_pass_does_not_default_to_switch_password(f):
    for line in f.read_text().splitlines():
        if "HTPASSWD_PASS:" in line:
            assert "switch_password" not in line, (
                f"{f}: status-page HTPASSWD_PASS must not fall back to "
                f"switch_password (plain-HTTP credential leak): {line.strip()}")
            assert "status_page_password" in line, line


@pytest.mark.parametrize("f", HTPASSWD_SOURCES, ids=lambda p: p.name)
def test_htpasswd_pass_uses_shared_sentinel_default(f):
    for line in f.read_text().splitlines():
        if "HTPASSWD_PASS:" in line:
            assert "era-status-CHANGE_ME" in line, (
                f"{f}: both paths should share the era-status-CHANGE_ME default: "
                f"{line.strip()}")


def test_status_page_password_seeded_in_secrets():
    """status_page_password must be present in every source secrets.yml so the
    safe default is overridable (else the placeholder always fires)."""
    for sec in sorted((REPO / "inventories").glob("*/group_vars/all/secrets.yml")):
        assert "status_page_password" in sec.read_text(), f"{sec} lacks status_page_password"
