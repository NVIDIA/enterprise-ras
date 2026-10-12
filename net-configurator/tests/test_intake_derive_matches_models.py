# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Derived values must equal the arch model's values for every arch.

This is the guard that makes derivation trustworthy. It runs against the
committed workbooks, so it also detects a workbook drifting from its model.
"""
import importlib.util
import re
import sys
from pathlib import Path

import openpyxl
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

import workbook_access  # noqa: E402
from intake_derive import derive_convergence, derive_gpu_planes  # noqa: E402
from _valid_archs import VALID_ARCHS as ARCHS  # noqa: E402

# Both scales, deliberately. `convergence` is the same for either scale on four
# of the eight archs but FLIPS on the other four (2-4-5-400, 2-8-5-200, 2-8-5-400
# and 2-8-9-400 are collapsed at their default SU and dedicated-GPU at largescale),
# so a default-only run leaves the half of the derivation that distinguishes
# them unexercised on exactly the archs where it matters.
SITES = ["default", "largescale"]

_DM = REPO.parent / "data-models"


def _models():
    """The arch models -- internal, so the caller is internal_only.

    The ORACLE is the point of this file. An earlier revision compared
    derivation against the workbook's own `Settings` sheet, which the intake
    form no longer carries; comparing against the `Derived` sheet instead
    would be circular, since derivation is what writes it. The models are
    outside the workbook entirely.
    """
    if str(_DM) not in sys.path:
        sys.path.insert(0, str(_DM))
    from models import get_arch_row
    spec = importlib.util.spec_from_file_location(
        "_gen_for_derive", _DM / "generate_arch_excel.py")
    gen = importlib.util.module_from_spec(spec)
    sys.modules["_gen_for_derive"] = gen
    spec.loader.exec_module(gen)
    return get_arch_row, gen


def _links(path):
    """The wiremap endpoints, in the shape intake_derive consumes."""
    wb = openpyxl.load_workbook(path, data_only=True)
    return [{"system_name_a": r["a_name"], "system_name_z": r["z_name"]}
            for r in workbook_access.wiremap_rows(wb)]


def _su_count(links):
    """The highest SU the wiremap names -- the model row to compare against."""
    sus = {int(m.group(1))
           for link in links
           for name in link.values()
           for m in [re.match(r"^su-(\d+)-", str(name or ""))] if m}
    return max(sus) if sus else 1


@pytest.mark.internal_only("data-models/generate_arch_excel.py", "data-models/models")
@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("arch", ARCHS)
def test_derived_values_match_the_arch_model(arch, site):
    get_arch_row, gen = _models()
    workbook = REPO / "input" / arch / site / f"{arch}.xlsx"
    if not workbook.exists():
        pytest.skip(f"no {site} workbook for {arch}")
    links = _links(workbook)
    model, row = get_arch_row(arch, _su_count(links))
    assert derive_gpu_planes(links) == gen.plane_count(model)
    assert derive_convergence(links) == gen.row_convergence(row, model)


def test_no_arch_is_silently_skipped():
    """The guard is worthless if it skips. Pin the count."""
    assert len(ARCHS) == 8


def test_near_miss_names_are_excluded_alongside_a_genuine_match():
    """Pins that near-misses are excluded even when a real plane is present.

    Mixing one genuine `gsl-plane1-*` pair with two lookalikes
    (`csl-plane1-01` starts with `c`, not `g`; `oob-l-plane2-x` isn't a
    plane-switch name at all) means the count only proves exclusion if it
    stays at 1 — a regex that widened to match either lookalike would push
    it to 2 or 3. An all-lookalike input can't show this: it would pass at
    `gpu_planes == 1` whether or not the lookalikes were excluded, since 1
    is also the converged-fabric default. This is the case that actually
    catches a future regex edit that loosens the leading-character class
    or the anchor.
    """
    links = [
        {"system_name_a": "gsl-plane1-01", "system_name_z": "csl-plane1-01"},
        {"system_name_a": "oob-l-plane2-x", "system_name_z": "core-01"},
    ]
    assert derive_gpu_planes(links) == 1
    assert derive_convergence(links) == "dedicated_gpu"


def test_all_near_miss_names_derive_to_the_converged_default():
    """No genuine plane names at all -> converged default, not a false match.

    A companion to the mixed-match test above: this pins the "zero real
    matches" path (both near-misses excluded, nothing left to detect),
    which is a different case from "one real match survives among
    near-misses."
    """
    links = [
        {"system_name_a": "csl-plane1-01", "system_name_z": "oob-l-plane2-x"},
    ]
    assert derive_gpu_planes(links) == 1
    assert derive_convergence(links) == "full"
