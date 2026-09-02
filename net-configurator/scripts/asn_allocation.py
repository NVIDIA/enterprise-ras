#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Single source of truth for BGP ASN allocation.

Historically the per-switch ASN was *derived* inside excel_parser.py as
``base + a fixed per-tier offset``. Per-node ASNs are now explicit on
the Excel Loopbacks tab: the arch generator (data-models/generate_arch_excel.py)
computes each switch's ASN with the helpers here and writes it into the tab, and
the parser reads it verbatim. Both the generator (emit) and validate_excel
(reconstruct groups) import this module so the allocation logic can never drift
between them.

The offset blocks are **NON-OVERLAPPING** by construction, so no two tiers ever
share an ASN. Changing an offset silently renumbers already-shipped arches —
keep them stable and disjoint.

    core/csl (converged) : base + 0                    (shared, iBGP)
    oob                  : base + OOB_ASN_OFFSET  + oob_idx     (1..N)
    csl-leaf (ns_tiers>1): base + CSL_LEAF_ASN_OFFSET  + core_num
    csl-spine            : base + CSL_SPINE_ASN_OFFSET + spine_idx
    gsl-leaf             : base + GSL_LEAF_ASN_OFFSET  + (plane-1)*STRIDE
                             + (plane_idx-1)  [spined planes only; collapsed share]
    gsl-spine            : base + GSL_SPINE_ASN_OFFSET + (plane-1)*STRIDE  (pair shares)
"""

# Default base ASN — the historical fallback used when no explicit base was
# supplied (matches excel_parser's prior ``settings.get('bgp_asn') or 4200100001``).
DEFAULT_BASE_ASN = 4200100001

# Per-tier offset blocks (see module docstring). NON-OVERLAPPING — do not change.
OOB_ASN_OFFSET = 0           # OOB sits just above the base (base+1, base+2, …)
CSL_LEAF_ASN_OFFSET = 400    # dedicated N/S leaves (cl), unique per leaf (ns_tiers>1)
CSL_SPINE_ASN_OFFSET = 500   # dedicated N/S spines (cs), own block clear of OOB
GSL_PLANE_ASN_STRIDE = 1000  # ASN spacing between GPU planes (leaf+spine share it)
GSL_SPINE_ASN_OFFSET = 1099  # dedicated E/W (GPU) spines, one below the per-plane leaf
GSL_LEAF_ASN_OFFSET = 1100   # GPU leaves, unique per leaf on spined planes


def converged_core_asn(base):
    """Converged core/csl (ns_tiers==1): the whole tier shares the base (iBGP)."""
    return int(base)


def csl_leaf_asn(base, core_num):
    """Dedicated N/S leaf (cl, ns_tiers>1): unique per-leaf ASN."""
    return int(base) + CSL_LEAF_ASN_OFFSET + int(core_num)


def csl_spine_asn(base, spine_idx):
    """Dedicated N/S spine (cs): unique per-spine ASN."""
    return int(base) + CSL_SPINE_ASN_OFFSET + int(spine_idx)


def gsl_leaf_asn(base, plane_num, plane_idx, n_leaves_in_plane):
    """GPU leaf ASN.

    A COLLAPSED (<=2-leaf) plane peers plane-mate<->plane-mate via iBGP
    (`remote-as internal`), so BOTH mates MUST share ONE ASN — the per-leaf
    offset is applied to SPINED (>2-leaf) planes only.
    """
    plane_asn = int(base) + GSL_LEAF_ASN_OFFSET + (int(plane_num) - 1) * GSL_PLANE_ASN_STRIDE
    return plane_asn + ((int(plane_idx) - 1) if int(n_leaves_in_plane) > 2 else 0)


def gsl_spine_asn(base, plane_num):
    """GPU spine ASN — both spines in a plane share one ASN (no spine_idx term)."""
    return int(base) + GSL_SPINE_ASN_OFFSET + (int(plane_num) - 1) * GSL_PLANE_ASN_STRIDE


def oob_asn(base, oob_idx):
    """L3 OOB switch ASN — unique per switch."""
    return int(base) + OOB_ASN_OFFSET + int(oob_idx)


import re as _re
from collections import defaultdict as _defaultdict

# Hostname patterns for the switch tiers, used to reconstruct ASN groups from
# the Nodes/Loopbacks switch names (validate_excel imports this — one source).
_GL_RE = _re.compile(r'^(?:gsl|gl)-plane([12])-', _re.IGNORECASE)
_GS_RE = _re.compile(r'^gs-plane([12])-', _re.IGNORECASE)


def partition_asn_groups(switch_names, ns_tiers=1):
    """Partition switch hostnames into ASN-groups.

    Members of a returned multi-element group MUST share one ASN (iBGP /
    shared-plane invariants); every other switch is its own singleton. Groups:

      - converged core/csl (ns_tiers==1): all ``core-*`` / ``csl-*`` share the base
      - collapsed GPU plane (<=2 leaves): the ``(g)?sl-planeN-*`` leaf-mate pair
      - gs spine pair: ``gs-planeN-*``

    Dedicated ``cl-*`` / ``cs-*`` leaves+spines (ns_tiers>1), spined-plane GPU
    leaves (>2 in a plane), and L3 ``oob-switch-*`` are singletons.

    Returns a list of lists of hostnames (input order preserved within a group).
    """
    ns_tiers = int(ns_tiers or 1)
    names = [str(n).strip() for n in switch_names if n and str(n).strip()]
    plane_leaf_counts = _defaultdict(int)
    for n in names:
        m = _GL_RE.match(n)
        if m:
            plane_leaf_counts[int(m.group(1))] += 1

    groups = {}  # key -> [names]  (dict preserves first-seen order)
    for n in names:
        low = n.lower()
        m_gl = _GL_RE.match(n)
        m_gs = _GS_RE.match(n)
        if low.startswith('core-'):
            key = 'converged-core'
        elif low.startswith('csl-') or low.startswith('cl-'):
            # Converged (share the base, iBGP) at ns_tiers==1; unique dedicated
            # N/S leaves at ns_tiers>1.
            key = 'converged-core' if ns_tiers == 1 else f'single::{n}'
        elif low.startswith('cs-'):
            key = f'single::{n}'
        elif m_gl:
            plane = int(m_gl.group(1))
            key = f'gpu-plane{plane}' if plane_leaf_counts[plane] <= 2 else f'single::{n}'
        elif m_gs:
            key = f'gs-plane{int(m_gs.group(1))}'
        else:  # oob-switch-*, or anything unrecognized -> its own ASN
            key = f'single::{n}'
        groups.setdefault(key, []).append(n)
    return list(groups.values())
