# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Unit tests for the shared BGP ASN allocation helper.

Covers the per-tier formulas (golden values that must reproduce the historical
derivation) and the ASN-group partition used by validate_excel.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import asn_allocation as a

BASE = 4200100001  # 2-4-5-800 base


# ── per-tier formulas (golden) ─────────────────────────────────────────────

def test_converged_core_is_base():
    assert a.converged_core_asn(BASE) == BASE


def test_oob_is_base_plus_index():
    assert a.oob_asn(BASE, 1) == BASE + 1
    assert a.oob_asn(BASE, 2) == BASE + 2


def test_csl_leaf_block():
    assert a.csl_leaf_asn(BASE, 1) == BASE + 400 + 1
    assert a.csl_leaf_asn(BASE, 7) == BASE + 400 + 7


def test_csl_spine_block():
    assert a.csl_spine_asn(BASE, 1) == BASE + 500 + 1


def test_gsl_leaf_collapsed_plane_mates_share():
    # <=2 leaves in the plane -> the per-leaf offset is NOT applied; mates share.
    assert a.gsl_leaf_asn(BASE, 1, 1, 2) == a.gsl_leaf_asn(BASE, 1, 2, 2)
    assert a.gsl_leaf_asn(BASE, 1, 1, 2) == BASE + 1100
    assert a.gsl_leaf_asn(BASE, 2, 1, 2) == BASE + 1100 + 1000


def test_gsl_leaf_spined_plane_unique():
    # >2 leaves -> each leaf gets a unique ASN via (plane_idx-1).
    vals = [a.gsl_leaf_asn(BASE, 1, i, 4) for i in (1, 2, 3, 4)]
    assert vals == [BASE + 1100, BASE + 1101, BASE + 1102, BASE + 1103]
    assert len(set(vals)) == 4


def test_gsl_spine_pair_shares_and_is_below_leaf():
    assert a.gsl_spine_asn(BASE, 1) == BASE + 1099
    assert a.gsl_spine_asn(BASE, 2) == BASE + 1099 + 1000
    # one below the per-plane leaf base -> eBGP, no collision
    assert a.gsl_spine_asn(BASE, 1) == a.gsl_leaf_asn(BASE, 1, 1, 4) - 1


def test_blocks_are_non_overlapping():
    got = {
        a.converged_core_asn(BASE),
        a.oob_asn(BASE, 1),
        a.csl_leaf_asn(BASE, 1),
        a.csl_spine_asn(BASE, 1),
        a.gsl_spine_asn(BASE, 1),
        a.gsl_leaf_asn(BASE, 1, 1, 4),
    }
    assert len(got) == 6  # all distinct


# ── partition_asn_groups ───────────────────────────────────────────────────

def _groupset(names, ns_tiers=1):
    return {frozenset(g) for g in a.partition_asn_groups(names, ns_tiers)}


def test_converged_core_and_oob_singletons():
    g = _groupset(["core-01", "core-02", "oob-switch-01", "oob-switch-02"])
    assert frozenset({"core-01", "core-02"}) in g          # converged core shares
    assert frozenset({"oob-switch-01"}) in g               # OOB singleton
    assert frozenset({"oob-switch-02"}) in g


def test_collapsed_gpu_planes_pair_and_csl_converged():
    names = ["csl-01", "csl-02",
             "gsl-plane1-01", "gsl-plane1-02",
             "gsl-plane2-01", "gsl-plane2-02"]
    g = _groupset(names, ns_tiers=1)
    assert frozenset({"csl-01", "csl-02"}) in g            # converged csl
    assert frozenset({"gsl-plane1-01", "gsl-plane1-02"}) in g   # collapsed plane1
    assert frozenset({"gsl-plane2-01", "gsl-plane2-02"}) in g   # collapsed plane2


def test_spined_gpu_leaves_singletons_and_gs_pair():
    names = [f"gl-plane1-{i:02d}" for i in range(1, 5)] + ["gs-plane1-01", "gs-plane1-02"]
    g = _groupset(names)
    # 4 leaves in the plane -> each its own group
    for i in range(1, 5):
        assert frozenset({f"gl-plane1-{i:02d}"}) in g
    # gs spine pair shares
    assert frozenset({"gs-plane1-01", "gs-plane1-02"}) in g


def test_dedicated_ns_tiers_csl_are_singletons():
    g = _groupset(["csl-01", "csl-02", "cs-01"], ns_tiers=2)
    assert frozenset({"csl-01"}) in g
    assert frozenset({"csl-02"}) in g
    assert frozenset({"cs-01"}) in g


def test_cl_names_converged_at_ns_tiers_1():
    # some workbooks name the converged nodes cl-*; at ns_tiers==1 they share
    # the base (iBGP), so they must land in ONE group, not per-node singletons.
    g = _groupset(["cl-01", "cl-02"], ns_tiers=1)
    assert frozenset({"cl-01", "cl-02"}) in g


def test_cl_names_singletons_at_ns_tiers_2():
    g = _groupset(["cl-01", "cl-02"], ns_tiers=2)
    assert frozenset({"cl-01"}) in g and frozenset({"cl-02"}) in g
