# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Every published workbook must use its architecture's best GPU VLAN mode.

`single` lumps every GPU NIC of every node into one subnet. It is supported,
but it is not what anyone deploys, and shipping it as the example meant no
published cell ever exercised per-rail addressing at scale — the one
combination that was broken. All 7 `default` cells and all 7 flat `sample-*`
files already comply; all 14 `largescale` files did not.

`generator_parity.py` cannot catch this: it reads `gpu_vlan_mode` out of the
workbook it is reproducing, so it confirms a workbook is self-consistent but
never that the mode is the right one.

The expected mode is derivable from the workbook alone — `gpu_planes` is in
Settings — which is why this test needs no model load and can live inside
net-configurator without reaching across to data-models.
"""
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import workbook_access  # noqa: E402

NC = Path(__file__).resolve().parent.parent


def _published_workbooks():
    for p in sorted(NC.glob("input/*/*/*.xlsx")):
        arch, site = p.parts[-3], p.parts[-2]
        if site in ("default", "largescale") and p.stem == arch:
            yield pytest.param(p, id=f"{arch}/{site}")
    # `make convert-workbook` writes `<name>.intake.xlsx` beside its source,
    # so one can sit next to a published workbook. It is a converted copy,
    # not a published workbook, and it has no `Settings` sheet to read a GPU
    # mode from -- including it fails this check on a file that is doing
    # nothing wrong. Same rule as `tests/conftest.legacy_workbooks`.
    for p in sorted(NC.glob("input/sample-*.xlsx")):
        if True:
            yield pytest.param(p, id=p.stem)
    for p in sorted(NC.glob("input/largescale-*.xlsx")):
        if True:
            yield pytest.param(p, id=p.stem)


def _derived(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        return workbook_access.derived(wb)
    finally:
        wb.close()


def _settings(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        return workbook_access.settings(wb)
    finally:
        wb.close()


@pytest.mark.parametrize("path", list(_published_workbooks()))
def test_published_workbook_uses_best_gpu_mode(path):
    s = _settings(path)
    mode = str(s.get("gpu_vlan_mode") or "").strip()
    planes = int(_derived(path).get("gpu_planes") or s.get("gpu_planes") or 1)
    expected = "per_rail_per_plane" if planes > 1 else "per_rail"
    assert mode == expected, (
        f"{path.name} declares gpu_vlan_mode={mode!r} with gpu_planes={planes}; "
        f"expected {expected!r}. Published workbooks must ship the best "
        f"available GPU rail allocation — regenerate without --gpu-vlan-mode "
        f"so the model default applies.")


@pytest.mark.parametrize("path", list(_published_workbooks()))
def test_no_published_workbook_uses_single(path):
    assert str(_settings(path).get("gpu_vlan_mode") or "").strip() != "single", (
        f"{path.name} ships gpu_vlan_mode=single. `single` remains a supported "
        f"mode, but it must never be the published default.")


def test_the_check_actually_covers_every_published_workbook():
    """A discovery bug that silently matched nothing would make this file
    pass while checking zero workbooks.

    32 = 16 nested (8 default + 8 largescale) + 8 sample- + 8 largescale-.
    The 8 release/e2e/fixtures workbooks are internal, already compliant,
    and outside net-configurator/ — a test that ships must not reach across
    the public boundary to find them.
    """
    assert len(list(_published_workbooks())) == 32
