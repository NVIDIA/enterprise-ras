# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
The ADR index must agree with the ADRs it indexes.

Found during the 2026-08-11 status sweep: `internal-docs/adr/README.md` listed
ADR-0033 as **Proposed** while the ADR itself had said *"Accepted + fully
implemented"* since 2026-07-21. The index is what anyone scanning release
readiness actually reads, so a stale row misreports whether a decision has
landed — and the drift is invisible because nothing compares the two.

The status *values* are deliberately not constrained here: an ADR may legitimately
read "Accepted (partially superseded by 0004)" or "Proposed — blocked by ERA-53".
What is pinned is the first word — Proposed / Accepted / Superseded — which is
the part the index summarises and the part a reader acts on.

Internal-only: `internal-docs/` never ships public (ADR-0027), so this test is a
no-op in a public tree.
"""
import re
from pathlib import Path

import pytest

ADR_DIR = Path(__file__).resolve().parents[2] / "internal-docs" / "adr"

pytestmark = pytest.mark.skipif(
    not ADR_DIR.is_dir(), reason="internal-docs/adr absent (public tree)"
)


def _first_word(status: str) -> str:
    m = re.match(r"\s*([A-Za-z]+)", status)
    return m.group(1).lower() if m else ""


# Numbered files in adr/ that are NOT decision records and so carry no status.
# Listed explicitly rather than skipped by "has no Status line", which would let
# a real ADR lose its status and go unnoticed — the drift this test exists for.
# Keyed by FILENAME, not number: adr/ contains two 0031-* files — the decision
# record and a supporting audit note that shares its number.
NOT_DECISION_RECORDS = {
    "0031-seed-liveness-audit.md":
        "evidence note filed alongside ADR-0031's decision, not a decision itself",
}


def _file_statuses() -> dict[str, str]:
    out = {}
    for f in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")):
        num = f.name[:4]
        m = re.search(r"\*\*Status:\*\*\s*(.+)", f.read_text())
        if f.name in NOT_DECISION_RECORDS:
            assert m is None, (
                f"{f.name} is listed as a non-decision document but now has a "
                "**Status:** line — remove it from NOT_DECISION_RECORDS"
            )
            continue
        assert m, f"{f.name} has no **Status:** line"
        out[num] = _first_word(m.group(1))
    return out


def _index_statuses() -> dict[str, str]:
    out = {}
    for ln in (ADR_DIR / "README.md").read_text().splitlines():
        m = re.match(r"\|\s*\[(\d{4})\]", ln)
        if not m:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        out[m.group(1)] = _first_word(cells[-1])
    return out


def test_every_adr_appears_in_the_index():
    missing = sorted(set(_file_statuses()) - set(_index_statuses()))
    assert not missing, f"ADRs absent from the index: {missing}"


def test_index_status_matches_the_adr_itself():
    files, index = _file_statuses(), _index_statuses()
    drift = {n: (files[n], index[n])
             for n in sorted(files) if n in index and files[n] != index[n]}
    assert not drift, (
        "index disagrees with the ADR file (adr, file_says, index_says): "
        + "; ".join(f"{n}: {f} vs {i}" for n, (f, i) in drift.items())
    )


def test_the_check_is_not_vacuous():
    """An empty glob or a changed table format would make both tests pass."""
    files = _file_statuses()
    assert len(files) >= 50, f"only {len(files)} ADRs parsed — has the layout changed?"
    assert len(_index_statuses()) >= 50, "index rows did not parse"
