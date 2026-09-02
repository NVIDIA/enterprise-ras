# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Every sub-port an ISL parent breaks out into must be accounted for.

An ISL parent broken out 2x has s0 and s1. If the Wire Map wires only s0 and
says nothing at all about s1, half a physical port silently carries no ISL
capacity — and nothing in the workbook records whether that was intended.

The workbook already has a convention for "this sub-port exists and is
deliberately not used": a Wire Map row with the `Unused` network profile.
2-8-9-800 `csl-01 swp59s2..s7` all carry one. The gap this check closes is the
sub-port that is neither wired nor marked `Unused` — it is simply absent.

Two shipped defaults have exactly that, on the same port:

  2-8-9-800     csl-01/csl-02  swp58s1  absent (swp58s0 wired ISL)
  2-8-9-400-SP  csl-01/csl-02  swp58s1  absent (swp58s0 wired ISL)

Those four are NOT a count defect. `fabrics.north_south.allocated_ports.isl`
declares 10 sub-ports at SU=2 and the Wire Map has exactly 10 (5 cables x 2
ends), so the odd 5-link ISL is what the model specifies. The defect is the
missing accounting row, which is why this is a warning and why the four are
pinned as an exact set below rather than fixed here.

Scope note: breakout is Excel-driven only for csl/core. gl/gs hardcode 2x in
their own template (gl_plane1.yml carries no breakout key), so applying the
Excel ISL profile's breakout to a gl parent produces false positives — 288 of
them on 2-4-5-800. The check must resolve breakout the same way the templates
do, per port, from the profiles that actually claim it.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import validate_excel as _ve  # noqa: E402  (needs the sys.path insert above)

REPO = Path(__file__).resolve().parent.parent
VALIDATOR = REPO / "scripts" / "validate_excel.py"
ARCHS = ["2-4-3-200", "2-4-5-800", "2-8-5-200",
         "2-8-9-400", "2-8-9-400-SP", "2-8-9-800"]

MARKER = "unaccounted sub-port"

# Exact set, asserted as a set. Accounting for one of these must fail the
# suite rather than silently shrink it (same discipline as ADR-0040's
# KNOWN_BAD_SPEED_CELLS).
KNOWN_UNACCOUNTED = set()
# Emptied 2026-08-06 (ERA-72). The generator now emits an `Unused` Wire Map row
# for every sub-port an ISL parent creates but the allocator does not wire, so
# spare ISL capacity is RECORDED rather than inferred.
#
# This was blocked on tooling for as long as the workbooks were hand-maintained
# — closing it meant inserting rows into a shipped .xlsx, which the patch script
# cannot do and which must not be done by round-tripping through openpyxl.
# Generating the workbooks from the models removed the obstacle entirely.
#
# Keep this empty. A new entry means the generator stopped accounting for a
# sub-port, not that the debt grew.


def _run(xlsx):
    return subprocess.run([sys.executable, str(VALIDATOR), str(xlsx)],
                          capture_output=True, text=True, cwd=str(REPO))


#   "[Wire Map] csl-01 swp58: unaccounted sub-port(s) s1 on an ISL parent ..."
# Anchored on both sides: the same line also lists the sub-ports that ARE
# wired ("Wired as ISL: s0"), so a bare scan for sN tokens over-matches.
_FINDING_RE = re.compile(
    r"(?P<sw>\S+)\s+(?P<parent>swp\d+):\s+unaccounted sub-port\(s\)\s+"
    r"(?P<subs>s\d+(?:,\s*s\d+)*)\s+on an ISL parent")


def _findings(arch, xlsx):
    """(arch, switch, parent, sub) tuples parsed out of the validator output."""
    p = _run(xlsx)
    found = set()
    for line in (p.stdout + p.stderr).splitlines():
        m = _FINDING_RE.search(line)
        if not m:
            continue
        for sub in re.findall(r"s\d+", m.group("subs")):
            found.add((arch, m.group("sw"), m.group("parent"), sub))
    return found


@pytest.mark.parametrize("arch", ARCHS)
def test_isl_parent_accounting_matches_known_set(arch):
    """Only the four pinned sub-ports may be unaccounted, and they must still be."""
    xlsx = REPO / "input" / arch / "default" / f"{arch}.xlsx"
    if not xlsx.exists():
        pytest.skip(f"{arch} Excel absent")

    expected = {k for k in KNOWN_UNACCOUNTED if k[0] == arch}
    assert _findings(arch, xlsx) == expected


def test_gl_gs_parents_are_now_in_scope_and_clean():
    """gl/gs ISL parents are checked, and 2-4-5-800 has nothing to report.

    This test used to assert the OPPOSITE — that gl/gs were deliberately out of
    scope, because their breakout level was not Excel-driven and applying the
    declared profile produced 288 phantom holes on this arch.

    Two things changed. ADR-0042 corrected 2-4-5-800's ISL profile so it
    declares the breakout the Wire Map actually wires, which removed the phantom
    findings. ERA-73 then made gl/gs/gsl read that same profile, which is what
    makes including them *correct* rather than merely quiet: before it, an
    operator declaring 4x would have been flagged for sub-ports gl never
    rendered.
    """
    xlsx = REPO / "input" / "2-4-5-800" / "default" / "2-4-5-800.xlsx"
    if not xlsx.exists():
        pytest.skip("2-4-5-800 Excel absent")
    assert "gl" in _ve._EXCEL_DRIVEN_BREAKOUT_FUNCTIONS, (
        "gl dropped out of scope — ERA-73 made its breakout Excel-driven")
    assert not _findings("2-4-5-800", xlsx)
