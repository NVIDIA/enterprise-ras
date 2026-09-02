# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Unit tests for the optional control-plane ACL override (ADR-0030):
parse_acls_sheet / generate_acls (mirroring the prefix-list override) plus the
validate_acls charset/protocol/port backstop and suppress-security warning.
"""
import sys
from pathlib import Path

import openpyxl

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from excel_parser import (  # noqa: E402
    generate_acls,
    parse_acls_sheet,
    OVERRIDABLE_ACLS,
    SECURITY_DEFAULT_ACLS,
)
from validate_excel import ValidationResult, validate_acls  # noqa: E402

HEADER = ["ACL name", "Rule id", "Protocol", "Dest port", "Action"]


def _sheet(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    return ws


class TestParseAclsSheet:
    """Locked interface: parse_acls_sheet(ws) ->
    {'acls': {name: [rule, ...]}, 'suppress': set()}. Set-agnostic — override
    vs add is decided in generate_acls."""

    def test_blank_action_collects_rule(self):
        ws = _sheet([["acl-default-whitelist", "201", "tcp", "9000", ""]])
        d = parse_acls_sheet(ws)
        assert d["acls"]["acl-default-whitelist"] == [
            {"id": "201", "protocol": "tcp", "dest_port": "9000"}
        ]
        assert d["suppress"] == set()

    def test_new_acl_added(self):
        ws = _sheet([["mgmt-allow", "10", "tcp", "22", ""]])
        d = parse_acls_sheet(ws)
        assert d["acls"]["mgmt-allow"] == [
            {"id": "10", "protocol": "tcp", "dest_port": "22"}
        ]

    def test_suppress_wins_over_rule_rows(self):
        ws = _sheet([
            ["acl-default-dos", "5", "tcp", "80", ""],
            ["acl-default-dos", None, None, None, "suppress"],
        ])
        d = parse_acls_sheet(ws)
        assert "acl-default-dos" in d["suppress"]
        assert "acl-default-dos" not in d["acls"]

    def test_empty_sheet_is_noop(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(HEADER)  # header only, no data rows
        d = parse_acls_sheet(ws)
        assert d == {"acls": {}, "suppress": set()}

    def test_row_missing_protocol_or_port_skipped(self):
        ws = _sheet([
            ["acl-default-whitelist", "201", "tcp", "", ""],   # no port
            ["acl-default-whitelist", "202", "", "9000", ""],  # no protocol
        ])
        d = parse_acls_sheet(ws)
        assert d["acls"] == {}


class TestGenerateAcls:
    def test_non_spine_defaults_bindings_only(self):
        acls = generate_acls("csl")
        ids = [a["id"] for a in acls]
        assert ids == ["acl-default-dos", "acl-default-whitelist"]
        assert all(a["control_plane_inbound"] for a in acls)
        assert all(a["rule"] == [] for a in acls)
        assert all(a["type"] is None for a in acls)

    def test_spine_defines_whitelist_rule_200(self):
        for cat in ("cs", "gs-plane1", "gs-plane2"):
            acls = generate_acls(cat)
            wl = next(a for a in acls if a["id"] == "acl-default-whitelist")
            assert wl["type"] == "ipv4"
            assert wl["rule"] == [
                {"id": "200", "protocol": "tcp", "dest_port": "8251"}
            ]

    def test_collapsed_gsl_plane_is_not_spine(self):
        # collapsed GPU planes render the gl template (bindings only)
        acls = generate_acls("gsl-plane1")
        wl = next(a for a in acls if a["id"] == "acl-default-whitelist")
        assert wl["rule"] == [] and wl["type"] is None

    def test_none_directives_equals_omitted(self):
        assert generate_acls("cs", None) == generate_acls("cs")

    def test_override_replaces_whitelist_rules(self):
        directives = {"acls": {"acl-default-whitelist":
                     [{"id": "201", "protocol": "tcp", "dest_port": "9000"}]},
                     "suppress": set()}
        acls = generate_acls("csl", directives)
        wl = next(a for a in acls if a["id"] == "acl-default-whitelist")
        assert wl["rule"] == [{"id": "201", "protocol": "tcp", "dest_port": "9000"}]
        assert wl["type"] == "ipv4"  # a rule set implies ipv4

    def test_add_new_acl_bound_inbound(self):
        directives = {"acls": {"mgmt-allow":
                     [{"id": "10", "protocol": "tcp", "dest_port": "22"}]},
                     "suppress": set()}
        acls = generate_acls("csl", directives)
        new = next(a for a in acls if a["id"] == "mgmt-allow")
        assert new["control_plane_inbound"] is True
        assert new["rule"] == [{"id": "10", "protocol": "tcp", "dest_port": "22"}]

    def test_suppress_removes_acl(self):
        directives = {"acls": {}, "suppress": {"acl-default-dos"}}
        acls = generate_acls("cs", directives)
        assert "acl-default-dos" not in [a["id"] for a in acls]

    def test_security_default_set_membership(self):
        assert SECURITY_DEFAULT_ACLS == {"acl-default-dos", "acl-default-whitelist"}
        assert OVERRIDABLE_ACLS == {"acl-default-dos", "acl-default-whitelist"}


class TestValidateAcls:
    def test_clean_sheet_no_errors(self):
        ws = _sheet([["acl-default-whitelist", "201", "tcp", "9000", ""]])
        r = ValidationResult()
        validate_acls(ws, r)
        assert r.errors == []

    def test_bad_name_errors(self):
        ws = _sheet([["bad name; rm -rf", "1", "tcp", "80", ""]])
        r = ValidationResult()
        validate_acls(ws, r)
        assert any("ACL name" in e for e in r.errors)

    def test_bad_protocol_errors(self):
        ws = _sheet([["mgmt-allow", "1", "sctp", "80", ""]])
        r = ValidationResult()
        validate_acls(ws, r)
        assert any("protocol" in e for e in r.errors)

    def test_bad_port_errors(self):
        ws = _sheet([["mgmt-allow", "1", "tcp", "70000", ""]])
        r = ValidationResult()
        validate_acls(ws, r)
        assert any("dest port" in e for e in r.errors)

    def test_suppress_security_default_warns(self):
        ws = _sheet([["acl-default-dos", None, None, None, "suppress"]])
        r = ValidationResult()
        validate_acls(ws, r)
        assert r.errors == []
        assert any("baseline" in w for w in r.warnings)
