#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA architecture scaling tables.

`ARCH_SCALING` captures the maximum *single-tier* SU count and the switch
fan-out per SU range for each ERA architecture, from the ERA reference
architecture documents (ERA-00008/10/11/14/16; revisions cited per arch).
Multi-tier scales are not in those fan-out tables: `MAX_SUPPORTED_SU`
records the largest SU count shipped per arch, single- or multi-tier.

Multi-tier scales are not tier-less, though: `OOB_SWITCHES_BY_SU` carries
the OOB switch count for every generator-supported SU of every arch (single-
or multi-tier), and `ARCH_MULTI_TIER_ONLY` names the arches that have no
single-tier table *by design*. `expected_oob_switches()` consults both so a
caller can always tell "no data" from "no single-tier design".

Used by:
  - scripts/validate_excel.py     — flags over-max SU configurations
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


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


# Public, self-contained fallback derived from the internal topology_by_su
# snapshots. Source revisions: ERA-00008/10/16 v04 and ERA-00011 v04.
# Each arch's list MUST be ordered ascending by max_su. The single-tier
# max for an arch is the last tier's max_su.
ARCH_SCALING = {
    "2-4-3-200": [
        # ERA-00008-001 v04, Tables 10/11. Collapsed E/W+N/S design.
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
        # ERA-00016-001 v04, Tables 13/14.
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
        # ERA-00010-001 v04, Tables 10/11. SU4 adds a dedicated N/S leaf pair
        # but remains single-tier because neither fabric has a spine.
        ScalingTier(min_su=1, max_su=2, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=None, oob_switches=2,
                    notes="Collapsed"),
        ScalingTier(min_su=3, max_su=3, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=None, oob_switches=3,
                    notes="3rd OOB switch at 9-12 nodes"),
        ScalingTier(min_su=4, max_su=4, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=2, oob_switches=4,
                    notes="Dedicated E/W and N/S leaf pairs; no spine tier"),
    ],
    "2-8-5-400": [
        # ERA-00014-001 (2025-09-22), Tables 11/12/17/18. Single-plane
        # collapsed leaf through SU4 (dedicated N/S CSL pair from SU4); the
        # E/W leaf+spine tier activates at SU5, so SU5-SU8 are multi-tier
        # (see MAX_SUPPORTED_SU / OOB_SWITCHES_BY_SU).
        ScalingTier(min_su=1, max_su=3, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=None, oob_switches=2,
                    notes="Converged collapsed core"),
        ScalingTier(min_su=4, max_su=4, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=2, oob_switches=2,
                    notes="Dedicated E/W and N/S leaf pairs; no spine tier (SU 4 only)"),
    ],
    "2-8-9-800": [
        # ERA-00011-001 v04, Tables 8/10. Dual-plane.
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
    "2-8-9-400-SP": [
        # ERA-00011-001 v04, Tables 9/10. Single-plane variant promoted to
        # a first-class architecture; topology matches 2-8-9-800 single-plane.
        ScalingTier(min_su=1, max_su=4, core_or_csl_leaves=2,
                    gsl_leaves_per_plane=2, oob_switches=2,
                    notes="Single-plane, 2 E/W leaves + 2 N/S leaves, no spine"),
    ],
}

# 2-4-5-400 is a DEPOPULATED 2-8-5-200 (ERA-00004-001 v04): same chassis, same
# five adapters, half the GPUs. Switch counts are node/NIC-driven, so the
# scaling tiers are identical by definition — aliased rather than copied so the
# two cannot drift apart. Only the per-GPU external uplink capacity differs, and
# that is derived in data-models, not here.
ARCH_SCALING["2-4-5-400"] = ARCH_SCALING["2-8-5-200"]


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
    '2-4-5-400': 8,
    '2-8-9-400': 16,
    '2-8-5-400': 8,
    '2-4-5-800': 8,
    '2-8-9-800': 32,
    '2-8-9-400-SP': 32,
}


def max_supported_su(arch: str) -> Optional[int]:
    """Largest SU count validated/shipped for `arch` (single- or multi-tier)."""
    return MAX_SUPPORTED_SU.get(arch)


def supported_su_counts(arch: str) -> List[int]:
    """The discrete SU counts the generator supports for `arch`, ascending.

    Not every count up to `max_supported_su` is supported: 2-8-9-400 jumps
    4 -> 6 -> 8 -> 12 -> 16. Empty for an unknown arch.
    """
    return sorted(OOB_SWITCHES_BY_SU.get(arch, {}))


# Arches that have NO single-tier fan-out table on purpose (ADR-0076 D1).
# `get_tier()` returns None for them at every SU; that is a design statement,
# not a gap.
ARCH_MULTI_TIER_ONLY = {
    # ERA-00012-001 v02, Tables 6/7: GB300 NVL72 is a dedicated GPU
    # leaf-spine fabric from SU=1 (one rack per SU, 2 rack-OOB switches per
    # rack + 2 external-management SN2201s). There is no collapsed/single-
    # tier phase to tabulate.
    '2-4-5-800': "dedicated leaf-spine from SU=1 (ERA-00012-001 v02); "
                 "no single-tier phase exists",
}


# OOB switch count at every generator-supported SU, single- OR multi-tier
# (ADR-0076 D2). Public, self-contained snapshot of the internal models'
# `topology_by_su` (`oob` column incl. external-management switches); the
# internal test `test_arch_scaling_covers_every_shipped_su.py::
# test_oob_by_su_matches_generator_models` keeps it from drifting. Where a
# single-tier ScalingTier exists it agrees with this table; this table
# additionally covers the multi-tier SU counts the shipped largescale
# workbooks use.
OOB_SWITCHES_BY_SU: Dict[str, Dict[int, int]] = {
    '2-4-3-200': {1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4},
    '2-8-5-200': {1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4},
    '2-8-9-400': {1: 2, 2: 2, 3: 3, 4: 4, 6: 6, 8: 8, 12: 12, 16: 16},
    '2-8-5-400': {1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4},
    # 2 rack-OOB per SU + 2 external-management (ERA-00012-001 v02).
    '2-4-5-800': {1: 4, 2: 6, 3: 8, 4: 10, 5: 12, 6: 14, 7: 16, 8: 18},
    '2-8-9-800': {1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4,
                  12: 6, 16: 8, 24: 12, 32: 16},
    '2-8-9-400-SP': {1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4,
                     12: 6, 16: 8, 24: 12, 32: 16},
}
OOB_SWITCHES_BY_SU['2-4-5-400'] = OOB_SWITCHES_BY_SU['2-8-5-200']  # depopulated twin


def expected_oob_switches(arch: str, su_count: int) -> Optional[Tuple[int, str]]:
    """(expected OOB switch count, provenance note) for `arch` at `su_count`.

    Prefers the single-tier ScalingTier when one covers the SU; otherwise
    the per-SU snapshot (multi-tier scales, multi-tier-only arches). Returns
    None only when neither has data — an unknown arch, or an SU count the
    models do not define. Callers should say so rather than skip silently.
    """
    tier = get_tier(arch, su_count)
    if tier:
        return tier.oob_switches, tier.notes or "single-tier fan-out table"
    count = OOB_SWITCHES_BY_SU.get(arch, {}).get(su_count)
    if count is None:
        return None
    note = ARCH_MULTI_TIER_ONLY.get(arch) or "multi-tier scale snapshot"
    return count, note


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
