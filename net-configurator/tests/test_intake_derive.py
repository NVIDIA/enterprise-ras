# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Derivation must be evidence-based and must refuse to guess.

Ambiguity is an error, never a default — a silently defaulted topology
generates cleanly and is wrong, which is the worst failure mode we have.

Absence of GPU-plane switches is *not* ambiguity, though: four of the
seven shipped architectures are converged (switches named `core-N`, no
plane switches at all) and legitimately derive to a single collapsed
plane. Ambiguity is reserved for input that genuinely cannot be resolved.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from intake_derive import DerivationError, derive_convergence, derive_gpu_planes


def _links(*names):
    return [{"system_name_a": n, "system_name_z": "core-01"} for n in names]


def test_gpu_planes_counted_from_plane_named_systems():
    links = _links("gsl-plane1-01", "gsl-plane1-02", "gsl-plane2-01")
    assert derive_gpu_planes(links) == 2


def test_single_plane_is_one():
    assert derive_gpu_planes(_links("gsl-plane1-01")) == 1


def test_gpu_planes_matches_gl_name_family_too():
    # 2-4-5-800 names its GPU leaves `gl-planeN-`, not `gsl-planeN-`. A
    # regex matching only one family is a bug this repo has shipped
    # before (three switch-name families once caused 8 of 14 topologies
    # to silently no-op).
    links = _links("gl-plane1-01", "gl-plane1-02", "gl-plane2-01")
    assert derive_gpu_planes(links) == 2


def test_no_gpu_switches_derives_to_one_converged_plane():
    # Converged architectures (core-N only, no plane switches) legitimately
    # ship gpu_planes=1 — absence of plane switches is a topology, not
    # ambiguity, so this must derive cleanly rather than raise.
    assert derive_gpu_planes(_links("csl-01", "csl-02")) == 1


def test_convergence_is_dedicated_when_gsl_distinct_from_csl():
    links = _links("gsl-plane1-01", "csl-01")
    assert derive_convergence(links) == "dedicated_gpu"


def test_convergence_is_dedicated_for_gl_name_family_too():
    links = _links("gl-plane1-01", "csl-01")
    assert derive_convergence(links) == "dedicated_gpu"


def test_convergence_is_full_without_plane_switches():
    # "full" is the literal value shipped in the converged archs' Settings
    # sheets — not "collapsed".
    assert derive_convergence(_links("csl-01", "csl-02")) == "full"


def test_derivation_error_is_a_value_error():
    # Reserved for genuinely undecidable input — none of the seven shipped
    # architectures hit it today, but the class stays exported for callers
    # that need to handle it.
    assert issubclass(DerivationError, ValueError)


def test_gpu_planes_raises_on_empty_links_rather_than_guessing_one():
    # An empty links list is ambiguous, not converged -- it means nothing
    # describes the fabric at all (e.g. a Wiremap read that silently found
    # zero links because a required column was missing upstream). Distinct
    # from test_no_gpu_switches_derives_to_one_converged_plane() above,
    # whose links are non-empty and simply don't match PLANE_RE.
    with pytest.raises(DerivationError):
        derive_gpu_planes([])


def test_convergence_raises_on_empty_links_rather_than_guessing_full():
    with pytest.raises(DerivationError):
        derive_convergence([])
