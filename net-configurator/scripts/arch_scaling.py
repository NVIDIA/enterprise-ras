#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA architecture scaling tables — single-tier deployments only.

This module captures the maximum *single-tier* SU count and the switch
fan-out per SU range for each ERA architecture, extracted from the
official architecture PDFs in `architectural_docs/`. We intentionally
do NOT model multi-tier (super-spine / GSL-spine) scaling — building
that needs new role definitions in the parser and topology generator,
and is deferred to a follow-on release.

Used by:
  - scripts/validate_excel.py     — flags over-max SU configurations
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ScalingTier:
    """One row in an arch's single-tier fan-out table.

    A given SU count falls into the tier with the smallest max_su that's
    >= the requested count. Switch counts and notes describe the cluster
    at that scale.
    """
    min_su: int
    max_su: int
    core_or_csl_leaves: int    # 2 for every documented single-tier deployment
    gsl_leaves_per_plane: Optional[int]  # None for non-dedicated-GPU arches
    oob_switches: int
    notes: str = ""


# Source: agent extraction from architectural_docs/ERA-000{08,10,11,16}-*.pdf
# Each arch's list MUST be ordered ascending by max_su. The single-tier
# max for an arch is the last tier's max_su.
ARCH_SCALING = {
    "2-4-3-200": [
        # ERA-00008-001 v03, Table 10 (p26). Collapsed E/W+N/S design.
        ScalingTier(min_su=1, max_su=4, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=None, oob_switches=2,
                    notes="Collapsed (E/W+N/S in one fabric)"),
        ScalingTier(min_su=5, max_su=6, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=None, oob_switches=3,
                    notes="3rd OOB switch added"),
        ScalingTier(min_su=7, max_su=8, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=None, oob_switches=4,
                    notes="4th OOB switch added; ISL ports active"),
    ],
    "2-8-5-200": [
        # ERA-00016-001 (v03 on file). SU6-8 single-tier split modeled here;
        # the Table 13/14 reference was attributed to a draft v04 that is not on
        # file — treat the split as modeled, pending spec-table confirmation.
        # SU1-SU5 are converged/collapsed; SU6-SU8 remain single-tier but
        # split into a dedicated E/W GSL pair and a dedicated N/S CSL pair.
        ScalingTier(min_su=1, max_su=4, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=None, oob_switches=2,
                    notes="Converged collapsed core"),
        ScalingTier(min_su=5, max_su=5, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=None, oob_switches=3,
                    notes="Converged collapsed core; 3rd OOB switch at 17-20 nodes"),
        ScalingTier(min_su=6, max_su=6, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=2, oob_switches=3,
                    notes="Split single-tier: CSL N/S pair + GSL plane-1 E/W pair"),
        ScalingTier(min_su=7, max_su=8, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=2, oob_switches=4,
                    notes="Split single-tier: CSL N/S pair + GSL plane-1 E/W pair"),
    ],
    "2-8-9-400": [
        # ERA-00010-001 v03, Table 10 (p28) + narrative p29. Narrative
        # treats SU>=4 as multi-tier; we follow the stricter narrative.
        ScalingTier(min_su=1, max_su=2, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=None, oob_switches=2,
                    notes="Collapsed"),
        ScalingTier(min_su=3, max_su=3, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=None, oob_switches=3,
                    notes="3rd OOB switch at 9-12 nodes"),
    ],
    "2-8-9-800": [
        # ERA-00011-001 v04, Table 15 (p44) + narrative p29. Dual-plane.
        # Role-separated leaves from SU=1; no spine through SU=4.
        #
        # NOTE: gsl_leaves_per_plane=2 is the doc-stated architectural
        # max for single-tier, but the *default Excel template* ships
        # only enough GSL fan-out for SU<=2 (the two plane-02 leaves'
        # high-port range is consumed by plane1↔plane2 ISLs). Scaling
        # past SU=2 in practice requires either rebalancing the ISL
        # allocation or adding more GSL leaves. The validator's
        # tier-mismatch warning surfaces this gap to operators.
        ScalingTier(min_su=1, max_su=4, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=2, oob_switches=2,
                    notes="Dual-plane, 2 leaves per plane, no spine"),
    ],
}


def get_tier(arch: str, su_count: int) -> Optional[ScalingTier]:
    """Return the scaling tier that covers `su_count` for `arch`.

    Returns None if su_count exceeds the arch's single-tier max
    (caller should treat that as a multi-tier-deployment ask).
    """
    tiers = ARCH_SCALING.get(arch)
    if not tiers or su_count < 1:
        return None
    for tier in tiers:
        if tier.min_su <= su_count <= tier.max_su:
            return tier
    return None


def max_single_tier_su(arch: str) -> Optional[int]:
    """Return the largest SU count that stays single-tier for `arch`."""
    tiers = ARCH_SCALING.get(arch)
    if not tiers:
        return None
    return tiers[-1].max_su


def is_supported_single_tier(arch: str, su_count: int) -> bool:
    """True iff the SU count fits this arch's single-tier max."""
    cap = max_single_tier_su(arch)
    return cap is not None and 1 <= su_count <= cap


# Largest SU count validated/shipped per architecture, single- OR multi-tier.
# Used to accept the shipped largescale example workbooks when the internal
# generator models (scripts/models/) aren't present — i.e. in the public
# distribution. Matches the "largescale" column in docs/ARCH_SUPPORT_MATRIX.md.
MAX_SUPPORTED_SU = {
    '2-4-3-200': 8,
    '2-8-5-200': 8,
    '2-8-9-400': 16,
    '2-4-5-800': 8,
    '2-8-9-800': 32,
    '2-8-9-400-SP': 32,
}


def max_supported_su(arch: str) -> Optional[int]:
    """Largest SU count validated/shipped for `arch` (single- or multi-tier)."""
    return MAX_SUPPORTED_SU.get(arch)


def node_name_to_su(name: str) -> Optional[int]:
    """Map a compute-node name to its SU index, across arch conventions.

    Recognized patterns:
      - 'su-NN-node-MM' (2-4-3-200, 2-8-5-200, 2-8-9-400) → NN
      - 'gpu-NN'        (2-8-9-800 dual-plane B300, 4 per SU) → ceil(NN/4)

    Returns None for non-compute / non-matching names.
    """
    name = str(name).strip()
    m = re.match(r"su-(\d+)-node-\d+", name)
    if m:
        return int(m.group(1))
    m = re.match(r"gpu-(\d+)$", name)
    if m:
        return (int(m.group(1)) + 3) // 4
    return None
