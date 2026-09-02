# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
ERA-93 — every shipped workbook pre-fills `ldap_servers = 172.20.0.78` (the
`utility` jump on the DEFAULT air-mgmt plane). Move `air_mgmt_subnet` and that
pre-fill silently points at an address the deployment does not have. It is a
syntactically valid IP, so nothing else complains.

Inert while `ldap_enabled` is No — which is why it has never bitten — so the
gate fires only when both conditions hold.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_excel import validate_ldap_servers_plane  # noqa: E402


class _Result:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, sheet, msg):
        self.errors.append((sheet, msg))

    def warn(self, sheet, msg):
        self.warnings.append((sheet, msg))


def _check(**settings):
    r = _Result()
    validate_ldap_servers_plane(settings, r)
    return r


class TestLdapServersPlane:
    def test_stale_prefill_on_a_moved_plane_is_an_error(self):
        r = _check(ldap_enabled="Yes", ldap_servers="172.20.0.78",
                   air_mgmt_subnet="10.78.255.0/24")
        assert len(r.errors) == 1
        assert "172.20.0.78" in r.errors[0][1]
        assert "10.78.255.0/24" in r.errors[0][1]

    def test_silent_when_ldap_is_disabled(self):
        # The trap is inert here; reporting it would be noise on every workbook.
        r = _check(ldap_enabled="No", ldap_servers="172.20.0.78",
                   air_mgmt_subnet="10.78.255.0/24")
        assert r.errors == []

    def test_silent_on_the_default_plane(self):
        r = _check(ldap_enabled="Yes", ldap_servers="172.20.0.78",
                   air_mgmt_subnet="172.20.0.0/24")
        assert r.errors == []

    def test_silent_when_no_plane_is_declared(self):
        r = _check(ldap_enabled="Yes", ldap_servers="172.20.0.78")
        assert r.errors == []

    def test_an_ldap_server_on_the_moved_plane_is_fine(self):
        r = _check(ldap_enabled="Yes", ldap_servers="10.78.255.78",
                   air_mgmt_subnet="10.78.255.0/24")
        assert r.errors == []

    def test_an_unrelated_external_ldap_server_is_not_flagged(self):
        # Only the DEFAULT-plane pre-fill is unambiguous; a real external
        # server reachable by routing must not be second-guessed.
        r = _check(ldap_enabled="Yes", ldap_servers="10.20.30.40",
                   air_mgmt_subnet="10.78.255.0/24")
        assert r.errors == []

    def test_each_stale_entry_in_a_csv_is_reported(self):
        r = _check(ldap_enabled="Yes",
                   ldap_servers="172.20.0.78, 10.78.255.79, 172.20.0.79",
                   air_mgmt_subnet="10.78.255.0/24")
        assert len(r.errors) == 2

    def test_malformed_plane_is_left_to_its_own_gate(self):
        r = _check(ldap_enabled="Yes", ldap_servers="172.20.0.78",
                   air_mgmt_subnet="not-a-cidr")
        assert r.errors == []
