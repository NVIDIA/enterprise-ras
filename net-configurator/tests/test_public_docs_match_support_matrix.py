# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Public docs agree with the support matrix and the code (GitLab #99 / H11).

`docs/ARCH_SUPPORT_MATRIX.md` is the authoritative arch x feature record
(AGENTS.md "Architecture Support"). The README's "Tested" table is a subset
of it, so each README row must equal the matrix row of the same name, and
both tables must name every shipped architecture. The remaining checks pin
claims review #4 found contradicting the code.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from excel_parser import _deploy_in_air  # noqa: E402

README = ROOT / "README.md"
MATRIX = ROOT / "docs" / "ARCH_SUPPORT_MATRIX.md"
EXCEL_GUIDE = ROOT / "docs" / "EXCEL_CONFIGURATION_GUIDE.md"


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table_after(path, heading):
    """(header cells, {feature: cells}) of the first table after `heading`."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index(heading)
    rows = []
    for line in lines[start + 1:]:
        if line.startswith("|"):
            rows.append(line)
        elif rows:
            break
    header, _sep, *body = rows
    return _cells(header), {_cells(r)[0]: _cells(r)[1:] for r in body}


def _archs(header):
    return {a for cell in header[1:] for a in re.findall(r"`([^`]+)`", cell)}


def _shipped_archs():
    return {p.name for p in (ROOT / "input").iterdir()
            if p.is_dir() and (p / "default" / f"{p.name}.xlsx").is_file()}


def test_readme_tested_rows_are_matrix_rows():
    r_head, r_rows = _table_after(README, "### Tested")
    m_head, m_rows = _table_after(MATRIX, "## Tested features")
    assert r_head == m_head, "README and matrix columns differ"
    assert r_rows, "README Tested table is empty"
    for feature, cells in r_rows.items():
        assert feature in m_rows, f"README row {feature!r} is not in the matrix"
        assert cells == m_rows[feature], (feature, cells, m_rows[feature])


def test_both_tables_name_every_shipped_arch():
    shipped = _shipped_archs()
    assert len(shipped) == 8, shipped
    for path, heading in ((README, "### Tested"),
                          (MATRIX, "## Tested features")):
        assert _archs(_table_after(path, heading)[0]) == shipped, path.name


def test_readme_does_not_call_the_default_one_su():
    """Defaults are 1-5 SU depending on the arch (matrix Architectures table)."""
    text = README.read_text(encoding="utf-8")
    assert "default (1 SU)" not in text and "1-SU default" not in text


def test_deploy_in_air_absent_default_is_documented_as_the_code_has_it():
    assert _deploy_in_air({}) is True and _deploy_in_air({"deploy_in_air": ""}) is False
    text = EXCEL_GUIDE.read_text(encoding="utf-8")
    rows = re.findall(r"^\| `deploy_in_air` \| (.+) \|$", text, re.MULTILINE)
    assert rows and all(r.startswith("`Yes`") for r in rows), rows
    assert "`deploy_in_air` defaults to `Yes`" in text
    assert "absent or blank" not in text


def test_nvue_compat_records_completed_air_campaign_and_limits():
    text = (ROOT / "docs" / "NVUE_VERSION_COMPAT.md").read_text(encoding="utf-8")
    assert "all eight architectures" in text
    assert "48 final runs on\n5.18.3" in text
    assert "not every optional feature combination or physical hardware" in text
    assert "not yet deployed" not in text
    assert "2-8-5-400" in text


def test_docs_install_from_pinned_requirements():
    """An ad-hoc `pip install ansible` ignores the ansible-core pin."""
    unpinned = re.compile(r"\b(?:pip3?|apt(?:-get)?) install\b[^\n`]*\b(ansible|openpyxl|jinja2|httpx)\b")
    hits = []
    for path in [README, *sorted((ROOT / "docs").glob("*.md"))]:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if unpinned.search(line.split("#")[0]):
                hits.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not hits, "\n".join(hits)


def test_excel_guide_uses_intake_sheets_and_current_loopback_rule():
    text = EXCEL_GUIDE.read_text(encoding="utf-8")
    assert not re.search(r"^### (Settings|Nodes)\b", text, re.MULTILINE)
    assert "Settings.loopback_base" not in text
    assert "4 + core_num" not in text, "removed GPU-VRF loopback formula"
    assert "VRF_LOOPBACK_BLOCKS" in text
