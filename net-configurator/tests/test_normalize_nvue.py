#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Tests for scripts/normalize_nvue.py — the normalizer validate-config runs.

This module had NO direct coverage. tests/test_parser_functions.py tests a
same-named `_expand_iface_token` in the INTERNAL release/qa-scripts
compare_excel_inventory_and_configs.py, which is a different implementation with
a different signature (returns a comma-joined string, not a list) and which
`playbooks/validate-config.yml` does not use. The playbook copies THIS file to
the ZTP server and pipes both configs through it, so a gap here fails every
switch in validate-config while looking covered.

Regression driver: Cumulus 5.18.0's `nv config show -o commands` collapses port
ranges that carry a subport suffix — `nv set interface swp1-33s0 ...` where
5.16.1 emitted swp1s0, swp2s0, … individually. `_expand_iface_token` did not
expand that form, so every member of the range counted as BOTH missing (from
the expanded generated config) and extra (from the collapsed running config).
Result: 76/76 switches MISMATCH on a fabric that was provably converged
(5504/5504 BGP established), and validate-all halted at its phase-2 canary.

Evidence: internal-docs/validation-evidence/
2026-08-11-cumulus-518-air-minimum-resources.md
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from normalize_nvue import (  # noqa: E402
    _expand_iface_token,
    _is_iface_spec,
    normalize_and_expand,
)


class TestSubportRangeExpansion:
    """`swpA-Bsn` means swpAsn..swpBsn — the 5.18.0 collapsed form."""

    def test_simple_two_port_range(self):
        assert _expand_iface_token("swp59-60s2") == ["swp59s2", "swp60s2"]

    def test_wide_range(self):
        got = _expand_iface_token("swp1-33s0")
        assert got == [f"swp{i}s0" for i in range(1, 34)]
        assert len(got) == 33

    def test_range_keeps_its_subport_index(self):
        """s1 must stay s1 across the whole range — not collapse to s0."""
        got = _expand_iface_token("swp18-33s1")
        assert got == [f"swp{i}s1" for i in range(18, 34)]
        assert all(i.endswith("s1") for i in got)

    def test_recognised_as_an_interface_spec(self):
        assert _is_iface_spec("swp1-33s0")

    @pytest.mark.parametrize("token,first,last,count", [
        ("swp59-64s0", "swp59s0", "swp64s0", 6),
        ("swp61-64s3", "swp61s3", "swp64s3", 4),
        ("swp1-2s0", "swp1s0", "swp2s0", 2),
    ])
    def test_observed_forms(self, token, first, last, count):
        got = _expand_iface_token(token)
        assert (got[0], got[-1], len(got)) == (first, last, count)


class TestTwoDimensionalRange:
    """`swpA-BsC-D` = ports A..B X subports C..D — what 5.18.0 really emits.

    This is the form that actually appears in captured 5.18.0 output
    (`swp1-33s0-1`, `swp61-64s0-3`). It is the dangerous one: the ORIGINAL
    generic pattern silently half-expanded it, reading `swp1-33s0-1` as prefix
    `swp1-33s` over range 0..1 and yielding ['swp1-33s0', 'swp1-33s1'] — the
    subport dimension expanded, the PORT range left intact and unexpanded.

    A half-expansion is worse than none: it produces plausible-looking tokens
    that no longer match anything, which is exactly why validate-config showed
    598 unexplained missing lines on a switch whose config was correct.
    """

    def test_ports_times_subports(self):
        assert _expand_iface_token("swp1-3s0-1") == [
            "swp1s0", "swp1s1", "swp2s0", "swp2s1", "swp3s0", "swp3s1",
        ]

    def test_four_by_four(self):
        got = _expand_iface_token("swp61-64s0-3")
        assert len(got) == 16
        assert got[0] == "swp61s0" and got[-1] == "swp64s3"

    def test_wide_real_form(self):
        """`swp1-33s0-1` — 33 ports x 2 subports, from real 5.18.0 output."""
        got = _expand_iface_token("swp1-33s0-1")
        assert len(got) == 66
        assert "swp1s0" in got and "swp33s1" in got

    def test_never_half_expands(self):
        """Regression: no output token may still contain a range."""
        for token in ("swp1-33s0-1", "swp18-33s0-1", "swp61-64s0-3"):
            for out in _expand_iface_token(token):
                assert "-" not in out, (
                    f"{token} half-expanded to {out}: port range left intact"
                )


class TestPreExistingFormsStillWork:
    """The 5.18.0 fix must not regress the forms 5.16.1 emitted."""

    def test_plain_port_range(self):
        assert _expand_iface_token("swp1-3") == ["swp1", "swp2", "swp3"]

    def test_bond_subport_range(self):
        """`bond1s0-3` is a SUBPORT range on one bond — not a port range."""
        assert _expand_iface_token("bond1s0-3") == [
            "bond1s0", "bond1s1", "bond1s2", "bond1s3",
        ]

    def test_single_interface_unchanged(self):
        assert _expand_iface_token("swp10s0") == ["swp10s0"]
        assert _expand_iface_token("swp1") == ["swp1"]

    def test_comma_list(self):
        assert _expand_iface_token("swp49,swp50") == ["swp49", "swp50"]

    def test_named_interface_untouched(self):
        assert _expand_iface_token("spine_bond") == ["spine_bond"]


class TestFullLineExpansion:
    """End-to-end through normalize_and_expand(), as the playbook calls it."""

    def test_collapsed_range_line_expands_to_one_line_per_port(self):
        got = normalize_and_expand(
            "nv set interface swp59-60s0 vrf STORAGE"
        )
        assert sorted(got) == sorted([
            "nv set interface swp59s0 vrf STORAGE",
            "nv set interface swp60s0 vrf STORAGE",
        ])

    def test_collapsed_and_expanded_forms_agree(self):
        """The whole point: running (collapsed) must normalize to the same set
        as generated (expanded), or every port counts as missing AND extra."""
        collapsed = normalize_and_expand(
            "nv set interface swp1-3s0 link speed 400G"
        )
        expanded = []
        for i in (1, 2, 3):
            expanded += normalize_and_expand(
                f"nv set interface swp{i}s0 link speed 400G"
            )
        assert sorted(collapsed) == sorted(expanded)

    def test_real_518_telemetry_line(self):
        got = normalize_and_expand(
            "nv set interface swp18-33s1 evpn multihoming uplink enabled"
        )
        assert len(got) == 16
        assert "nv set interface swp18s1 evpn multihoming uplink enabled" in got
        assert "nv set interface swp33s1 evpn multihoming uplink enabled" in got


class TestAgainstRealCapturedConfigs:
    """End-to-end against real 5.18.0 captures, if the fixtures are present.

    Fixtures: internal-docs/validation-evidence/
    2026-08-11-cumulus-518-running-configs/ — captured from the live 32-SU sim
    before teardown. They are INTERNAL (not shipped in net-configurator/), so
    the test skips cleanly in the public tree.

    Guards the property that actually matters: after normalization, every
    command in our generated config must be present in the running config.
    """

    FIXTURES = (
        Path(__file__).resolve().parents[2]
        / "internal-docs" / "validation-evidence"
        / "2026-08-11-cumulus-518-running-configs"
    )

    @pytest.mark.parametrize("switch", [
        "cl-01", "gl-plane1-01", "cs-01", "oob-switch-01",
    ])
    def test_no_generated_command_goes_missing(self, switch):
        gen = self.FIXTURES / f"{switch}-generated.txt"
        run = self.FIXTURES / f"{switch}-running-config.txt"
        if not (gen.exists() and run.exists()):
            pytest.skip("internal 5.18.0 capture fixtures not present")

        def norm(path):
            out = set()
            for line in path.read_text().splitlines():
                line = line.strip()
                if line.startswith("nv "):
                    out.update(normalize_and_expand(line))
            return out

        missing = norm(gen) - norm(run)
        assert not missing, (
            f"{switch}: {len(missing)} generated command(s) absent from the "
            f"running config after normalization, e.g. {sorted(missing)[:5]}"
        )
