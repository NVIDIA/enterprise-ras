# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Emitted `description` values must stay inside NVUE's real limits.

Measured on live switches (ERA-71), identical on Cumulus 5.15.1 and 5.16.1:

    max length          80 characters   (80 accepted, 81 rejected — bisected)
    unquoted spaces     rejected        "Error: Invalid parameter: 'words'"
    quoted spaces       accepted
    charset             permissive — hyphen, dot, slash, colon, UPPERCASE and
                        leading/trailing underscore all accepted

Two of those correct long-standing assumptions. The limit was believed to be
255 (ERA-71's description says so), and `[a-z0-9_]` was believed to be a
platform constraint — it is an RCP style convention, not a platform one.

WHY THIS IS ASSERTED ON THE RENDERED CONFIG
-------------------------------------------
Descriptions do not come from the Excel, so a `validate_excel` check would
guard the wrong door — the Route policy sheet has no description column. They
come from `scripts/inventory_defaults.yml` and from route-map construction in
the parser. Checking the artifact catches a too-long value whatever its source.

WHY IT MATTERS
--------------
An over-length description is not a cosmetic defect. `nv config apply` rejects
the WHOLE config, so a switch configured through Air Node Instructions never
receives its management address and is simply unreachable — the exact failure
ERA-64 shipped, which took every switch in the 2-8-9-800 e2e cell down and cost
four Air cells to bisect.

Current headroom: the longest shipped description is 34 characters.
"""
import re
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
_SHIPPED_SITES = ("default", "largescale")

# ERA-71, bisected on csl-01 (5.16.1): 80 OK, 81 -> "is not one of ['none']".
MAX_DESCRIPTION_LEN = 80

# `nv set ... description <value>` — value runs to end of line.
_DESC = re.compile(r"^nv set .*\bdescription\s+(.+?)\s*$")


def _configs():
    out = []
    for site in _SHIPPED_SITES:
        out += sorted(NC.glob(f"output/*/{site}/configs/*-config.sh"))
    return out


CONFIGS = _configs()


def test_configs_exist():
    """An empty glob would make every parametrised test vacuously pass."""
    assert CONFIGS, "no generated configs found — regenerate before testing"


def _descriptions(path):
    """-> [(line_no, raw_value)] for every emitted description."""
    out = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        m = _DESC.match(line.strip())
        if m:
            out.append((n, m.group(1)))
    return out


@pytest.mark.parametrize("cfg", CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
def test_descriptions_within_length_limit(cfg):
    """Over 80 chars and `nv config apply` rejects the entire config."""
    too_long = [
        f"line {n}: {len(v)} chars — {v[:50]}..."
        for n, v in _descriptions(cfg)
        if len(v.strip('"')) > MAX_DESCRIPTION_LEN
    ]
    assert not too_long, (
        f"{cfg.relative_to(NC)}: description(s) exceed NVUE's {MAX_DESCRIPTION_LEN}-char "
        f"limit. `nv config apply` refuses the whole config, so the switch never "
        f"gets its management address:\n  " + "\n  ".join(too_long))


@pytest.mark.parametrize("cfg", CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
def test_descriptions_with_spaces_are_quoted(cfg):
    """An unquoted space is rejected outright: "Invalid parameter: 'words'".

    ADR-0043 chose underscores partly to sidestep quoting. The probe confirms
    that was the right call rather than a guess — so this guards the choice
    without forbidding a quoted multi-word value, which NVUE does accept.
    """
    bad = []
    for n, v in _descriptions(cfg):
        if " " not in v:
            continue
        if v.startswith('"') and v.endswith('"'):
            continue          # quoted multi-word is valid
        bad.append(f"line {n}: {v[:60]}")
    assert not bad, (
        f"{cfg.relative_to(NC)}: description(s) contain unquoted spaces — NVUE "
        f"rejects these at `nv set`:\n  " + "\n  ".join(bad))


@pytest.mark.parametrize("cfg", CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
def test_no_description_on_objects_that_reject_it(cfg):
    """prefix-list and community-list rules have no `description` attribute.

    Confirmed on both supported releases:
        prefix-list rule     'description' is not one of ['match', 'action']
        community-list rule  'description' is not one of ['community', 'action']

    Emitting one takes the switch down. This is the regression ERA-64 shipped;
    the guard exists so it cannot return by a different route.
    """
    offenders = [
        f"line {n}: {line.strip()[:90]}"
        for n, line in enumerate(cfg.read_text().splitlines(), 1)
        if re.search(r"policy (prefix-list|community-list) \S+ rule \S+ description", line)
    ]
    assert not offenders, (
        f"{cfg.relative_to(NC)}: description emitted on an object NVUE does not "
        f"accept it on — `nv config apply` will reject the entire config:\n  "
        + "\n  ".join(offenders))
