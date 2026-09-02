# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""HARD GATE: the shipped flat workbooks must match the sites they derive from.

`input/sample-<arch>.xlsx` and `input/largescale-<arch>.xlsx` are copies of the
per-arch site workbooks. Nothing about a stale copy looks wrong — it opens,
validates and deploys; it just describes a fabric that has since changed. That
is why this has to be a test rather than a convention: on 2026-08-07 the
per-arch workbooks were regenerated and the flat ones were not, and the lag went
unnoticed for two weeks.

These workbooks are a derived artifact, regenerated from the per-arch sources by
the maintainers. A failure here means the copy has fallen behind its source, not
that the flat file should be hand-edited into agreement.

Comparison is on cell content, not bytes, so a harmless re-zip does not produce
a red test that is not a real defect.
"""
import sys
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent  # net-configurator/
INPUT = NC / "input"

sys.path.insert(0, str(NC / "scripts"))

import flat_workbook_parity as fwp  # noqa: E402

ARCHS = fwp.discover_archs(INPUT)


def test_input_tree_has_archs():
    """Guard the guard — an empty arch list would make every test below vacuous."""
    assert ARCHS, f"no arch site directories found under {INPUT}"


@pytest.mark.parametrize("arch", ARCHS)
@pytest.mark.parametrize("prefix,scale", fwp.FAMILIES)
def test_flat_workbook_exists(arch, prefix, scale):
    """Every arch has both flat counterparts.

    Catches the 2-4-5-400 case: a new arch added without its flat files.
    """
    flat = fwp.flat_for(INPUT, prefix, arch)
    assert flat.exists(), (
        f"{flat.name} is missing for arch {arch}. {fwp.REMEDY}")


@pytest.mark.parametrize("arch", ARCHS)
@pytest.mark.parametrize("prefix,scale", fwp.FAMILIES)
def test_source_workbook_exists(arch, prefix, scale):
    """Both scales of every discovered arch are present.

    Discovery is the union of the two scales, so an arch with only one of them
    reaches here and is reported, rather than vanishing from the guard.
    """
    source = fwp.source_for(INPUT, arch, scale)
    assert source.exists(), f"source workbook missing at {source}"


def test_no_orphan_flat_workbooks():
    """No flat workbook survives its arch directory being renamed or removed."""
    problems = fwp.orphan_problems(INPUT, ARCHS)
    assert problems == [], "\n".join(problems)


@pytest.mark.parametrize("arch", ARCHS)
@pytest.mark.parametrize("prefix,scale", fwp.FAMILIES)
def test_flat_workbook_matches_source(arch, prefix, scale):
    """The flat workbook still equals its per-arch source, cell for cell."""
    source = fwp.source_for(INPUT, arch, scale)
    flat = fwp.flat_for(INPUT, prefix, arch)
    if not source.exists():
        pytest.skip("covered by test_source_workbook_exists")
    if not flat.exists():
        pytest.skip("covered by test_flat_workbook_exists")
    wanted_site = "sample" if prefix == "sample" else scale
    expected = fwp.expected_cells(source, wanted_site)
    actual = fwp.workbook_cells(flat)
    assert expected == actual, (
        f"{flat.name} is stale vs {arch}/{scale}: "
        f"{fwp._first_difference(expected, actual)}. {fwp.REMEDY}")


@pytest.mark.parametrize("arch", ARCHS)
@pytest.mark.parametrize("prefix,scale", fwp.FAMILIES)
def test_flat_workbook_site_name(arch, prefix, scale):
    """The one cell that legitimately differs must hold the expected value."""
    flat = fwp.flat_for(INPUT, prefix, arch)
    if not flat.exists():
        pytest.skip("covered by test_flat_workbook_exists")
    site = fwp._site_name_of(fwp.workbook_cells(flat))
    assert site == ("sample" if prefix == "sample" else scale)


def test_check_reports_clean():
    """The aggregate the promotion gate calls agrees with the tests above."""
    problems = fwp.check(INPUT)
    assert problems == [], "\n".join(problems)
