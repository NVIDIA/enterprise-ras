#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Derive topology settings from intake-form data.

Pure functions. No Excel, no file I/O, no ERA imports — so every arch can
be covered by cheap unit tests.

Design rule: ambiguity raises. A defaulted value produces a wrong fabric
that generates cleanly, which is the failure mode this project exists to
avoid. Absence of GPU-plane switches is *not* ambiguity, though: five of
the eight shipped architectures are converged (switches named `core-N`,
no plane switches at all) and legitimately ship a single collapsed plane.
"""
import re

# Matches both shipped GPU-leaf name families: `gsl-planeN-` (2-8-9-400-SP,
# 2-8-9-800) and `gl-planeN-` (2-4-5-800). A regex that knows only one
# family is a bug this repo has shipped before (three switch-name families
# once caused 8 of 14 topologies to silently no-op).
PLANE_RE = re.compile(r"gs?l-plane(\d+)-", re.IGNORECASE)


class DerivationError(ValueError):
    """Raised when the data does not determine a value.

    Reserved for genuinely undecidable input. None of the seven shipped
    architectures hit this today — a converged fabric with no GPU-plane
    switches is a known, valid topology, not an ambiguous one. An *empty*
    links list is different from that: it means nothing describes the
    fabric at all (e.g. a Wiremap read that silently found zero links
    because a required column was missing or renamed upstream), which is
    ambiguous and must raise rather than guess a converged default.
    """


# The setting names this module's derive_* functions actually produce
# today. `convert_workbook.DERIVED_SETTINGS` names 14 settings as safe to
# strip from the intake form's `Deployment` sheet on the theory that the
# parser reconstructs them from the data — this is the ground truth for
# how many of those 14 it actually can. Grown by adding a name here (and
# a derive_<name>() function) as Phase 1 ships each one.
DERIVABLE_SETTINGS = frozenset({"gpu_planes", "convergence"})


def _names(links):
    for link in links:
        for key in ("system_name_a", "system_name_z"):
            name = link.get(key)
            if name:
                yield str(name)


def derive_gpu_planes(links):
    """Number of distinct GPU planes, from `g(s)l-planeN-*` system names.

    Converged architectures have *links* whose names simply don't match
    `PLANE_RE` — that derives to a single collapsed plane rather than
    raising, since it's a real, legitimate topology (four of the seven
    shipped architectures). An *empty* `links` list is a different case:
    it means there is nothing to derive from at all, which must raise
    rather than silently guess the converged default — see
    DerivationError's docstring.
    """
    if not links:
        raise DerivationError(
            "derive_gpu_planes() got an empty links list -- there is "
            "nothing to derive a GPU-plane count from. This is different "
            "from a converged fabric (which has links, just none matching "
            "the plane-name pattern); an empty list must not silently "
            "default to a single collapsed plane.")
    planes = {int(m.group(1)) for name in _names(links)
              if (m := PLANE_RE.match(name))}
    return len(planes) if planes else 1


def derive_convergence(links):
    """'dedicated_gpu' when GPU-plane switches exist, else 'full'.

    See derive_gpu_planes() for why an empty `links` list raises rather
    than defaulting to 'full'.
    """
    if not links:
        raise DerivationError(
            "derive_convergence() got an empty links list -- there is "
            "nothing to derive convergence from. See derive_gpu_planes() "
            "for why this raises rather than defaulting to 'full'.")
    has_plane = any(PLANE_RE.match(name) for name in _names(links))
    return "dedicated_gpu" if has_plane else "full"
