# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Forcing-function guard for shipped Excel workbooks.

Relationship ids in a package part must be unique. The original ACLs-sheet
migration derived the new worksheet's id from workbook.xml (sheet r:ids only),
undercounting the styles/theme relationships in workbook.xml.rels and colliding
on rId11 -> Excel's "Removed Records: Worksheet properties" repair on open.
openpyxl and the tool's parser tolerate the collision, so nothing else catches
it. This test asserts, for every shipped workbook:

  1. workbook.xml.rels has no duplicate Relationship ids, and
  2. every <sheet r:id> in workbook.xml resolves to exactly one worksheet
     relationship.
"""
import re
import zipfile
from pathlib import Path

import pytest

INPUT_DIR = Path(__file__).parent.parent / "input"


def discover_workbooks(root):
    """Shipped workbooks under `root`, excluding Excel's owner-lock files.

    Excel writes a 165-byte `~$<name>.xlsx` beside any workbook it has open. It is
    not a workbook — unzipping it raises — so a plain `rglob("*.xlsx")` turns
    "someone has the file open" into a red suite whose message points at workbook
    corruption. Anyone editing a shipped workbook hits this.
    """
    return sorted(p for p in root.rglob("*.xlsx") if not p.name.startswith("~$"))


WORKBOOKS = discover_workbooks(INPUT_DIR)


def test_excel_lock_files_are_not_mistaken_for_workbooks(tmp_path):
    (tmp_path / "real.xlsx").write_bytes(b"")
    (tmp_path / "~$real.xlsx").write_bytes(b"")
    found = [p.name for p in discover_workbooks(tmp_path)]
    assert found == ["real.xlsx"], (
        f"discovery returned {found}; an open-in-Excel lock file must not be "
        f"parsed as a shipped workbook"
    )


def _ids(rels_xml):
    return re.findall(r'<Relationship\b[^>]*\bId="([^"]+)"', rels_xml)


def _sheet_rids(wb_xml):
    return re.findall(r'<sheet [^>]*r:id="([^"]+)"', wb_xml)


@pytest.mark.skipif(not WORKBOOKS, reason="no shipped workbooks found")
@pytest.mark.parametrize("xlsx", WORKBOOKS, ids=lambda p: str(p.relative_to(INPUT_DIR)))
def test_workbook_relationship_ids_are_unique(xlsx):
    with zipfile.ZipFile(xlsx) as zf:
        rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        wbx = zf.read("xl/workbook.xml").decode("utf-8")

    ids = _ids(rels)
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"{xlsx.name}: duplicate Relationship ids in workbook.xml.rels: {dupes}"

    # Every <sheet> must reference a defined, worksheet-typed relationship.
    # id->type map (attribute order varies between writers, so parse per element).
    id_types = {}
    for el in re.findall(r"<Relationship\b[^>]*/>", rels):
        rid = re.search(r'Id="([^"]+)"', el)
        typ = re.search(r'Type="([^"]+)"', el)
        if rid and typ:
            id_types[rid.group(1)] = typ.group(1)

    for rid in _sheet_rids(wbx):
        assert rid in id_types, f"{xlsx.name}: <sheet r:id={rid}> has no relationship"
        assert id_types[rid].endswith("/worksheet"), (
            f"{xlsx.name}: <sheet r:id={rid}> resolves to {id_types[rid]}, not a worksheet"
        )
