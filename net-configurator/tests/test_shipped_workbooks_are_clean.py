# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""The workbooks we ship must validate cleanly, because partners start from them.

Every OEM's first submission is our default with their addressing dropped in. Whatever
our file gets wrong, theirs gets wrong — and it comes back to us as *their* defect in a
design review.

That is not hypothetical. The `public-v6.0.4` default for `2-8-9-800` declared its OOB
VLAN as `172.16.177.0/24` while addressing nodes in `192.168.200.x`, and still carried
the removed `mgmt_subnets` key. Against the current validator it scores **18 errors**.
The 2026-08 submission inherited them, and the audit report was going to present them as
the partner's design defects. Nothing in this suite noticed, because nothing asserted the
shipped inputs were clean — only that individual checks behaved on synthetic fixtures.

Covers both shipped sites — `default` and `largescale`. `largescale` was outside this gate
until 2026-08-13: the flat `input/largescale-<arch>.xlsx` are byte copies of the per-arch
largescale workbooks, so with only `default` checked they were unguarded on both sides.
The flat `input/sample-<arch>.xlsx` / `input/largescale-<arch>.xlsx` copies are checked too:
they are what a partner downloads first, and the sample differs from the default by a
Settings cell, which is enough to carry a finding of its own.

Two levels, deliberately:

* **Errors: zero, no exceptions.** An error is a workbook that cannot deploy. There is no
  such thing as an acceptable one in a file we hand to a partner.
* **Warnings: pinned to a known set.** Some are legitimately open (a no-op Settings row we
  have not removed yet). Pinning rather than ignoring means the next one has to be looked
  at and added on purpose, which is the same discipline as `KNOWN_UNACCOUNTED` in
  `test_isl_parent_accounting.py` and `KNOWN_BAD_SPEED_CELLS` under ADR-0040.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
VALIDATOR = REPO / "scripts" / "validate_excel.py"

# Both shipped sites, named explicitly rather than globbed as `input/*/*/*.xlsx`, because
# a developer's throwaway site under `input/<arch>/<name>/` must not be able to fail this
# suite — and must not be able to *satisfy* it either.
SHIPPED_SITES = ("default", "largescale")
NESTED = sorted(p for site in SHIPPED_SITES for p in REPO.glob(f"input/*/{site}/*.xlsx")
                if not str(p).endswith(".intake.xlsx"))
FLAT = sorted(p for p in REPO.glob("input/*.xlsx") if re.match(r"(sample|largescale)-", p.name))
SHIPPED = NESTED + FLAT


def _label(p: Path) -> str:
    if p.parent == REPO / "input":
        return p.name
    return f"{p.parent.parent.name}/{p.parent.name}"


# Warning SHAPES our shipped defaults are currently allowed to emit. Substring match,
# so counts and switch names inside a message do not need pinning. Each entry needs a
# reason and an owner, not just a line. Today no shipped workbook warns at all.
#
# Shrinking this set is always safe. GROWING it means a shipped workbook got worse, so
# the addition has to be deliberate.
ALLOWED_WARNING_SHAPES: set[str] = set()


def _run(xlsx: Path) -> str:
    proc = subprocess.run([sys.executable, str(VALIDATOR), str(xlsx)],
                          capture_output=True, text=True, cwd=str(REPO))
    return proc.stdout + proc.stderr


# Report lines carry their severity glyph: "  ❌  [Settings] ..." / "  ⚠️  [Wire Map] ...".
# Matching on the glyph rather than "everything after the banner" is what keeps the
# closing summary line ("✅  No errors found (1 warnings).") out of the result — it sits
# inside the section and read as a warning shape on all seven archs on the first run.
_GLYPH = {"ERRORS": "❌", "WARNINGS": "⚠️"}


def _section(output: str, header: str) -> list[str]:
    """Findings under an `ERRORS (n)` / `WARNINGS (n)` banner in the validator report."""
    glyph, out, grabbing = _GLYPH[header], [], False
    for line in output.splitlines():
        stripped = line.strip()
        if re.match(rf"^{header} \(\d+\)", stripped):
            grabbing = True
            continue
        if not grabbing:
            continue
        if re.match(r"^(ERRORS|WARNINGS) \(\d+\)", stripped):
            break
        if stripped.startswith(glyph):
            out.append(stripped[len(glyph):].strip())
    return out


@pytest.mark.skipif(not SHIPPED, reason="no shipped workbooks present")
@pytest.mark.parametrize("xlsx", SHIPPED, ids=_label)
def test_shipped_workbook_has_no_errors(xlsx):
    """A partner starts from this file. It must not contain a defect they inherit.

    This is the gate that was missing when public-v6.0.4 shipped with 18 of them.
    """
    errors = _section(_run(xlsx), "ERRORS")
    assert not errors, (
        f"{_label(xlsx)} ships with {len(errors)} validator error(s). "
        f"A partner submitting this unchanged gets them back as their own defects:\n  "
        + "\n  ".join(errors[:10])
    )


@pytest.mark.skipif(not SHIPPED, reason="no shipped workbooks present")
@pytest.mark.parametrize("xlsx", SHIPPED, ids=_label)
def test_shipped_workbook_warnings_stay_pinned(xlsx):
    """No NEW warning shape may appear in a workbook we hand out."""
    unexpected = [w for w in _section(_run(xlsx), "WARNINGS")
                  if not any(shape in w for shape in ALLOWED_WARNING_SHAPES)]
    assert not unexpected, (
        f"{_label(xlsx)} emits a warning shape not in "
        f"ALLOWED_WARNING_SHAPES. Fix the workbook, or add it deliberately with a "
        f"reason and an owner:\n  " + "\n  ".join(unexpected[:10])
    )


def test_selection_covers_every_tracked_workbook():
    """The selection above must not silently narrow — that is how the gap got here.

    `largescale-*.xlsx` sat outside every gate for months precisely because a glob said
    `input/*/default/*` and nobody re-read it.

    The expectation therefore comes from **git**, not from `SHIPPED_SITES`. Building it
    from the same constant the selection uses makes the test circular: dropping
    `"largescale"` shrinks both sides and 16 tests pass looking exactly like 30. Asked
    against the index, that mutation fails, which is the only version of this test worth
    having. Tracked-ness is also the right definition of "shipped" — a developer's
    throwaway site under `input/<arch>/<name>/` is untracked and stays out of both sets.
    """
    ls = subprocess.run(["git", "ls-files", "input/*/*/*.xlsx",
                         "input/sample-*.xlsx", "input/largescale-*.xlsx"],
                        cwd=str(REPO), capture_output=True, text=True)
    if ls.returncode != 0 or not ls.stdout.strip():
        pytest.skip("not a git checkout (source tarball) — nothing to cross-check against")

    expected = {"/".join(line.split("/")[1:3]) for line in ls.stdout.split()}
    actual = {_label(p) for p in SHIPPED}
    assert actual == expected, (
        "the shipped-workbook selection does not match what git tracks under input/.\n"
        f"  tracked but NOT checked: {sorted(expected - actual)}\n"
        f"  checked but not tracked: {sorted(actual - expected)}"
    )


# The tag lives in the monorepo's history (a shallow CI clone may lack it);
# a public checkout need not carry it at all. git runs where the marker looks:
# the monorepo root, not the tool root.
@pytest.mark.internal_only(".git")
def test_the_gate_would_have_caught_the_v6_default():
    """Proof the gate is not vacuous, run against the file that motivated it.

    `public-v6.0.4`'s 2-8-9-800 default is the real regression this suite failed to
    catch. If this ever stops finding errors there, the parser above has drifted and
    both tests are passing for the wrong reason.

    That workbook predates the intake form, and the validator no longer reads a
    legacy workbook at all (ADR-0064 D1), so convert it first — the same one-time
    step a partner on an old file takes. The defects are in the addressing, which
    conversion carries across unchanged.
    """
    blob = subprocess.run(
        ["git", "show", "public-v6.0.4:input/2-8-9-800/default/2-8-9-800.xlsx"],
        cwd=str(REPO.parent), capture_output=True)
    if blob.returncode != 0 or not blob.stdout:
        pytest.skip("public-v6.0.4 tag not present in this checkout")

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        legacy = Path(tmp) / "v6-legacy.xlsx"
        legacy.write_bytes(blob.stdout)
        old = Path(tmp) / "v6.xlsx"
        conv = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "convert_workbook.py"),
             str(legacy), str(old)],
            cwd=str(REPO), capture_output=True, text=True)
        assert conv.returncode == 0, f"conversion failed:\n{conv.stdout}\n{conv.stderr}"
        errors = _section(_run(old), "ERRORS")

    assert errors, "the v6 default reported no errors — the section parser has drifted"
    assert any("mgmt_subnets" in e for e in errors)
    assert any("not within any OOB VLAN subnet" in e for e in errors)
