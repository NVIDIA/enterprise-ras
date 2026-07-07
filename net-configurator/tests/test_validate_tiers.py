# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Validator coverage for the split ns_tiers/ew_tiers consistency declaration.

`ns_tiers` (compute/North-South) and `ew_tiers` (GPU/East-West) declare the
expected tier count of each fabric (1 = converged, 2 = split). The validator
checks the declared count matches the spine roles actually present. A bare
legacy `tiers` seeds both.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_excel import validate_tiers_consistency  # new function


def test_ew_tiers_2_requires_gpu_spine():
    errs = validate_tiers_consistency({"ew_tiers": 2}, {"gl-plane1"})  # no gs spine
    assert any("ew_tiers" in e for e in errs)


def test_ew_tiers_1_forbids_gpu_spine():
    errs = validate_tiers_consistency({"ew_tiers": 1}, {"gsl-plane1", "gs-plane1"})
    assert any("ew_tiers" in e for e in errs)


def test_ns_tiers_2_requires_compute_spine():
    errs = validate_tiers_consistency({"ns_tiers": 2}, {"cl"})  # no cs
    assert any("ns_tiers" in e for e in errs)


def test_consistent_passes():
    assert validate_tiers_consistency({"ns_tiers": 1, "ew_tiers": 2},
                                      {"csl", "gl-plane1", "gs-plane1"}) == []


def test_legacy_tiers_seeds_both():
    # bare `tiers` (no ns/ew) seeds both; tiers=1 with a gs spine present is inconsistent
    errs = validate_tiers_consistency({"tiers": 1}, {"gsl-plane1", "gs-plane1"})
    assert any("ew_tiers" in e for e in errs)
