#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Generation must refuse to emit two switches sharing a loopback /32.

Guard for ERA-97 / GitLab #65. Three sources disagree about the N/S loopback
block map — the map declared in loopback_allocation.py, the layout the workbook
generator emits, and the blank-Loopbacks-sheet fallback in excel_parser.py.
Which is authoritative is an open owner decision (D1).

This guard is deliberately AUTHORITY-NEUTRAL: it takes no side on the block
map, and only catches the harm all three can produce — two switches sharing a
BGP router-id, which in an EVPN fabric fails silently at runtime.

Known margins when this was written: the fallback collides at 11 N/S leaves
(largest shipped fabric has 8) and the workbook path at 21 OOB switches
(largest shipped has 16).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from excel_parser import (  # noqa: E402
    _assert_no_duplicate_loopbacks,
    _record_loopback_claims,
)


def claims_for(*hosts):
    c = {}
    for name, hv in hosts:
        _record_loopback_claims(c, name, hv)
    return c


# --- must NOT fire -----------------------------------------------------------

def test_lo_ip_and_router_id_are_one_claim():
    """The same address in both keys is by design, not a collision."""
    c = claims_for(("cl-01", {"lo_ip": "172.16.176.11/32", "router_id": "172.16.176.11"}))
    _assert_no_duplicate_loopbacks(c)


def test_distinct_vrfs_on_one_switch_do_not_collide():
    c = claims_for(("cl-01", {
        "lo_ip": "172.16.176.11/32",
        "vrf_loopbacks": {"OOB": "172.16.176.151/32", "INBAND": "172.16.176.167/32",
                          "EXIT": "172.16.176.183/32", "STORAGE": "172.16.176.199/32"},
    }))
    _assert_no_duplicate_loopbacks(c)


def test_same_octet_on_different_planes_does_not_collide():
    """E/W planes live in different /24s — 10.1.1.1 and 10.2.1.1 are distinct."""
    c = claims_for(("gsl-plane1-01", {"lo_ip": "10.1.1.1/32"}),
                   ("gsl-plane2-01", {"lo_ip": "10.2.1.1/32"}))
    _assert_no_duplicate_loopbacks(c)


def test_empty_and_missing_values_are_ignored():
    c = claims_for(("x-01", {"lo_ip": None, "oob_vrf_loopback": "", "vrf_loopbacks": {}}))
    _assert_no_duplicate_loopbacks(c)


# --- must fire ---------------------------------------------------------------

def test_workbook_path_collision_at_21_oob_switches():
    """oob-switch-01's OOB-VRF is pinned to .121, inside the oob-switch lo block."""
    c = claims_for(
        ("oob-switch-01", {"lo_ip": "172.16.176.101/32", "oob_vrf_loopback": "172.16.176.121/32"}),
        ("oob-switch-21", {"lo_ip": "172.16.176.121/32"}),
    )
    with pytest.raises(ValueError, match="Duplicate switch loopback"):
        _assert_no_duplicate_loopbacks(c)


def test_fallback_path_collision_at_11_ns_leaves():
    """Blank Loopbacks sheet: leaf #11 lands on .21, where spine #1 already is."""
    c = claims_for(("cl-11", {"lo_ip": "172.16.176.21/32"}),
                   ("cs-01", {"lo_ip": "172.16.176.21/32"}))
    with pytest.raises(ValueError, match="Duplicate switch loopback"):
        _assert_no_duplicate_loopbacks(c)


def test_two_switches_sharing_a_vrf_loopback():
    c = claims_for(("cl-01", {"vrf_loopbacks": {"OOB": "172.16.176.151/32"}}),
                   ("cl-02", {"vrf_loopbacks": {"OOB": "172.16.176.151/32"}}))
    with pytest.raises(ValueError, match="Duplicate switch loopback"):
        _assert_no_duplicate_loopbacks(c)


def test_error_names_every_owner_and_slot():
    """The operator must be able to see which switches and which slots clashed."""
    c = claims_for(
        ("oob-switch-01", {"oob_vrf_loopback": "172.16.176.121/32"}),
        ("oob-switch-21", {"lo_ip": "172.16.176.121/32"}),
    )
    with pytest.raises(ValueError) as exc:
        _assert_no_duplicate_loopbacks(c)
    msg = str(exc.value)
    for expected in ("172.16.176.121", "oob-switch-01", "oob-switch-21",
                     "vrf:OOB", "(lo)", "router-id", "Loopbacks & ASNs"):
        assert expected in msg, f"error message omits {expected!r}:\n{msg}"


def test_mask_is_ignored_when_comparing():
    """A bare address and a /32 of the same address are the same claim."""
    c = claims_for(("a-01", {"lo_ip": "10.0.0.1/32"}), ("b-01", {"router_id": "10.0.0.1"}))
    with pytest.raises(ValueError):
        _assert_no_duplicate_loopbacks(c)


def test_divergent_router_id_is_still_checked():
    """A router_id that differs from lo_ip must not escape the guard.

    Regression for the coalescing blind spot Greptile flagged on MR !261:
    `add('lo', lo_ip or router_id)` stopped looking at router_id the moment
    lo_ip was set, so a shared router-id -- the exact failure this guard
    exists to catch -- would go unreported if the two ever diverged.
    """
    c = claims_for(
        ("cl-01", {"lo_ip": "172.16.176.11/32", "router_id": "172.16.176.99"}),
        ("cl-02", {"lo_ip": "172.16.176.12/32", "router_id": "172.16.176.99"}),
    )
    with pytest.raises(ValueError, match="Duplicate switch loopback") as exc:
        _assert_no_duplicate_loopbacks(c)
    assert "172.16.176.99" in str(exc.value)


def test_matching_lo_ip_and_router_id_is_not_a_self_collision():
    """Recording both must not make a host collide with itself (the common case)."""
    c = claims_for(("cl-01", {"lo_ip": "172.16.176.11/32",
                              "router_id": "172.16.176.11"}))
    _assert_no_duplicate_loopbacks(c)
