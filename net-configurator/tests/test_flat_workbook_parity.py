# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Unit tests for the flat-workbook comparison rule.

These use synthetic workbooks in tmp_path, NOT the shipped ones. The shipped
files are gated separately by test_flat_workbooks_match_sites.py; this file
gates the comparison logic itself, so it must not depend on the shipped state
being clean.
"""
import shutil
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import flat_workbook_parity as fwp  # noqa: E402


def _make_workbook(path: Path, site_name: str, extra_row=("core", "5.18.0")):
    """Minimal stand-in with the two sheets the rule cares about."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    settings = wb.active
    settings.title = "Settings"
    settings.append(["Setting", "Value"])
    settings.append(["arch", "2-4-3-200"])
    settings.append(["site_name", site_name])
    settings.append(list(extra_row))
    nodes = wb.create_sheet("Nodes")
    nodes.append(["Role", "Name"])
    nodes.append(["core", "core-01"])
    wb.save(path)


@pytest.fixture
def input_dir(tmp_path):
    """A miniature input/ tree with one arch, both scales, both flat files."""
    root = tmp_path / "input"
    _make_workbook(root / "2-4-3-200" / "default" / "2-4-3-200.xlsx", "default")
    _make_workbook(root / "2-4-3-200" / "largescale" / "2-4-3-200.xlsx", "largescale")
    _make_workbook(root / "sample-2-4-3-200.xlsx", "sample")
    _make_workbook(root / "largescale-2-4-3-200.xlsx", "largescale")
    return root


def test_discover_archs_finds_arch_dirs(input_dir):
    assert fwp.discover_archs(input_dir) == ("2-4-3-200",)


def test_discover_archs_ignores_flat_files(input_dir):
    # The flat files sit in the same directory; they are not archs.
    assert "sample-2-4-3-200" not in fwp.discover_archs(input_dir)


def test_discover_archs_finds_arch_with_only_largescale(input_dir):
    """largescale-* derives from largescale/, so default/ must not gate it."""
    (input_dir / "2-4-3-200" / "default" / "2-4-3-200.xlsx").unlink()
    assert fwp.discover_archs(input_dir) == ("2-4-3-200",)


def test_discover_archs_finds_arch_with_only_default(input_dir):
    (input_dir / "2-4-3-200" / "largescale" / "2-4-3-200.xlsx").unlink()
    assert fwp.discover_archs(input_dir) == ("2-4-3-200",)


def test_check_flags_missing_default_source(input_dir):
    """A missing default/ source must be REPORTED, never silently unchecked.

    Regression: discovery globbed only */default/, so deleting this file made
    the arch invisible and --check exited 0 having examined one arch fewer.
    """
    (input_dir / "2-4-3-200" / "default" / "2-4-3-200.xlsx").unlink()
    problems = fwp.check(input_dir)
    assert len(problems) == 1
    assert "source workbook missing" in problems[0]
    assert "default" in problems[0]


def test_check_flags_missing_largescale_source(input_dir):
    (input_dir / "2-4-3-200" / "largescale" / "2-4-3-200.xlsx").unlink()
    problems = fwp.check(input_dir)
    assert len(problems) == 1
    assert "source workbook missing" in problems[0]
    assert "largescale" in problems[0]


def test_check_flags_orphan_flat_files_when_arch_dir_removed(input_dir):
    """Removing the whole arch dir must not turn both flats into silent orphans."""
    shutil.rmtree(input_dir / "2-4-3-200")
    problems = fwp.check(input_dir)
    assert any("sample-2-4-3-200.xlsx" in p for p in problems), problems
    assert any("largescale-2-4-3-200.xlsx" in p for p in problems), problems


def test_check_flags_orphan_flat_when_arch_renamed(input_dir):
    """A renamed arch dir leaves the old flat files behind; report them."""
    (input_dir / "2-4-3-200").rename(input_dir / "2-4-5-400")
    for scale in ("default", "largescale"):
        (input_dir / "2-4-5-400" / scale / "2-4-3-200.xlsx").rename(
            input_dir / "2-4-5-400" / scale / "2-4-5-400.xlsx")
    problems = fwp.check(input_dir)
    orphans = [p for p in problems if "orphaned" in p]
    assert len(orphans) == 2, problems
    assert all("2-4-3-200" in p for p in orphans)


def test_orphan_problems_clean_when_every_flat_has_an_arch(input_dir):
    assert fwp.orphan_problems(input_dir, fwp.discover_archs(input_dir)) == []


def test_main_check_returns_one_on_orphan(input_dir, capsys):
    """The release-gate path fails on an orphan, not just on staleness."""
    shutil.rmtree(input_dir / "2-4-3-200")
    assert fwp.main(["--check", str(input_dir)]) == 1
    assert "orphaned" in capsys.readouterr().out


def test_check_passes_when_flat_matches_source(input_dir):
    assert fwp.check(input_dir) == []


def test_check_flags_stale_sample(input_dir):
    _make_workbook(input_dir / "2-4-3-200" / "default" / "2-4-3-200.xlsx",
                   "default", extra_row=("core", "5.16.1"))
    problems = fwp.check(input_dir)
    assert len(problems) == 1
    assert "sample-2-4-3-200.xlsx" in problems[0]


def test_check_flags_stale_largescale(input_dir):
    _make_workbook(input_dir / "2-4-3-200" / "largescale" / "2-4-3-200.xlsx",
                   "largescale", extra_row=("core", "5.16.1"))
    problems = fwp.check(input_dir)
    assert len(problems) == 1
    assert "largescale-2-4-3-200.xlsx" in problems[0]


def test_check_flags_missing_flat_file(input_dir):
    (input_dir / "sample-2-4-3-200.xlsx").unlink()
    problems = fwp.check(input_dir)
    assert len(problems) == 1
    assert "missing" in problems[0].lower()


def test_check_flags_wrong_site_name(input_dir):
    _make_workbook(input_dir / "sample-2-4-3-200.xlsx", "default")
    problems = fwp.check(input_dir)
    assert len(problems) == 1
    assert "site_name" in problems[0]


def test_expected_cells_rewrites_only_site_name(input_dir):
    source = input_dir / "2-4-3-200" / "default" / "2-4-3-200.xlsx"
    actual = fwp.workbook_cells(source)
    expected = fwp.expected_cells(source, "sample")
    assert expected["Nodes"] == actual["Nodes"]
    assert expected["Settings"] != actual["Settings"]
    flat = [c for row in expected["Settings"] for c in row]
    assert "sample" in flat and "default" not in flat


def test_main_check_returns_zero_when_clean(input_dir, capsys):
    assert fwp.main(["--check", str(input_dir)]) == 0


def test_main_check_returns_one_and_prints_when_stale(input_dir, capsys):
    (input_dir / "sample-2-4-3-200.xlsx").unlink()
    assert fwp.main(["--check", str(input_dir)]) == 1
    assert "sample-2-4-3-200.xlsx" in capsys.readouterr().out


def test_check_refuses_to_pass_on_empty_tree(tmp_path):
    """Empty arch tree must not report clean — prevents vacuous-success defects."""
    empty_input_dir = tmp_path / "empty_input"
    empty_input_dir.mkdir()
    problems = fwp.check(empty_input_dir)
    assert len(problems) > 0
    assert str(empty_input_dir) in problems[0]


def test_main_check_returns_one_on_empty_tree(tmp_path, capsys):
    """CLI must fail on empty tree — the release gate path."""
    empty_input_dir = tmp_path / "empty_input"
    empty_input_dir.mkdir()
    assert fwp.main(["--check", str(empty_input_dir)]) == 1
    output = capsys.readouterr().out
    assert "empty" in output.lower() or "no arch" in output.lower()
