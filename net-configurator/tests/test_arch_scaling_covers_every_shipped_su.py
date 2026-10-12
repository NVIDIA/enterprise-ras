# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""GitLab #67 / ERA-99: no valid arch may silently skip the OOB-count check.

`2-4-5-800` has no `ARCH_SCALING` entry (it is dedicated leaf-spine from
SU=1, so a single-tier table would be fiction) and the shipped largescale
workbooks of the B300 arches sit above their single-tier max, so in the
public distribution `get_tier()` returned None and `validate_single_tier_su`
skipped the OOB check without a word. Now every `VALID_ARCHS` member at every
shipped SU either yields an expected OOB count or is explicitly declared
multi-tier-only, and the validator says so when it has no data.
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
DATA_MODELS = REPO.parent / "data-models"
if str(DATA_MODELS) not in sys.path:
    sys.path.insert(0, str(DATA_MODELS))

from _era_context import VALID_ARCHS  # noqa: E402
from arch_scaling import (  # noqa: E402
    ARCH_MULTI_TIER_ONLY, ARCH_SCALING, MAX_SUPPORTED_SU, OOB_SWITCHES_BY_SU,
    expected_oob_switches, get_tier)
from excel_parser import canonical_category  # noqa: E402
import intake_to_legacy  # noqa: E402
from validate_excel import (  # noqa: E402
    ValidationResult, validate_nodes, validate_single_tier_su)

try:
    from models import available_sus, get_arch_row
except ImportError:  # public distribution
    available_sus = get_arch_row = None

SHIPPED = sorted(REPO.glob("input/*/*/*.xlsx"))


def _shipped_su_and_oob(xlsx: Path):
    """Nodes exactly as validate_excel() hands them to validate_single_tier_su."""
    wb = intake_to_legacy.load_workbook(str(xlsx), data_only=True)
    nodes = validate_nodes(wb["Nodes"], ValidationResult())
    sus = {int(n["name"].split("-")[1]) for n in nodes
           if n["name"].startswith("su-") and n.get("enabled", True)}
    oob = sum(1 for n in nodes if n.get("enabled", True)
              and canonical_category(str(n.get("function", "")), n["name"]) == "oob-switch")
    return max(sus), oob, nodes


# ---------------------------------------------------------------------------
# Table shape
# ---------------------------------------------------------------------------

def test_every_valid_arch_has_public_oob_data():
    assert set(OOB_SWITCHES_BY_SU) == set(VALID_ARCHS) == set(MAX_SUPPORTED_SU)


def test_every_arch_without_tiers_is_declared_multi_tier_only():
    tierless = set(VALID_ARCHS) - set(ARCH_SCALING)
    assert tierless == set(ARCH_MULTI_TIER_ONLY), (
        f"arches with no ARCH_SCALING entry must be listed in ARCH_MULTI_TIER_ONLY "
        f"with a reason: {tierless ^ set(ARCH_MULTI_TIER_ONLY)}")
    for arch in ARCH_MULTI_TIER_ONLY:
        assert get_tier(arch, 1) is None, arch
        assert ARCH_MULTI_TIER_ONLY[arch].strip()


@pytest.mark.parametrize("arch", sorted(VALID_ARCHS))
def test_snapshot_reaches_max_supported_su_and_agrees_with_tiers(arch):
    by_su = OOB_SWITCHES_BY_SU[arch]
    assert max(by_su) == MAX_SUPPORTED_SU[arch], arch
    for su, count in by_su.items():
        tier = get_tier(arch, su)
        if tier is not None:
            assert tier.oob_switches == count, (arch, su)


@pytest.mark.parametrize("arch", sorted(VALID_ARCHS))
def test_expected_oob_defined_for_every_supported_su(arch):
    for su in OOB_SWITCHES_BY_SU[arch]:
        got = expected_oob_switches(arch, su)
        assert got is not None, (arch, su)
        count, note = got
        assert count == OOB_SWITCHES_BY_SU[arch][su] and note, (arch, su)
    assert expected_oob_switches(arch, MAX_SUPPORTED_SU[arch] + 1) is None
    assert expected_oob_switches("9-9-9-999", 1) is None


@pytest.mark.internal_only("data-models/models")
@pytest.mark.parametrize("arch", sorted(VALID_ARCHS))
def test_oob_by_su_matches_generator_models(arch):
    """Drift guard: the public snapshot IS the models' topology_by_su.oob."""
    from_model = {su: int(get_arch_row(arch, su)[1]["oob"]) for su in available_sus(arch)}
    assert OOB_SWITCHES_BY_SU[arch] == from_model, arch


# ---------------------------------------------------------------------------
# Every shipped workbook, public-mode validator
# ---------------------------------------------------------------------------

@pytest.fixture
def public_mode(monkeypatch):
    """Make `from models import ...` fail as it does in the public tree."""
    monkeypatch.setitem(sys.modules, "models", None)


@pytest.mark.parametrize("xlsx", SHIPPED, ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}")
def test_shipped_workbook_su_is_covered_and_oob_matches(xlsx, public_mode):
    arch = xlsx.parent.parent.name
    su, oob, nodes = _shipped_su_and_oob(xlsx)
    expected = expected_oob_switches(arch, su)
    assert expected is not None, f"{arch} SU={su}: no OOB fan-out data"
    assert expected[0] == oob, f"{arch}/{xlsx.parent.name} SU={su}: workbook has {oob} OOB"
    result = ValidationResult()
    validate_single_tier_su({"architecture": arch}, nodes, result)
    assert not [w for w in result.warnings if "OOB" in w], result.warnings


def test_public_validator_warns_on_2_4_5_800_oob_mismatch(public_mode):
    xlsx = REPO / "input" / "2-4-5-800" / "largescale" / "2-4-5-800.xlsx"
    su, oob, nodes = _shipped_su_and_oob(xlsx)
    dropped = next(n for n in nodes if canonical_category(
        str(n.get("function", "")), n["name"]) == "oob-switch")
    dropped["enabled"] = False
    result = ValidationResult()
    validate_single_tier_su({"architecture": "2-4-5-800"}, nodes, result)
    hits = [w for w in result.warnings
            if f"Active OOB switch count ({oob - 1})" in w and f"expected {oob}" in w]
    assert hits, result.warnings
    assert "dedicated leaf-spine" in hits[0]


@pytest.mark.parametrize("mode", ["public", "internal"])
def test_validator_warns_when_every_oob_switch_is_disabled(mode, monkeypatch):
    """0 active OOB switches must be reported, not treated as 'nothing to compare'."""
    if mode == "public":
        monkeypatch.setitem(sys.modules, "models", None)
    xlsx = REPO / "input" / "2-4-5-800" / "largescale" / "2-4-5-800.xlsx"
    su, oob, nodes = _shipped_su_and_oob(xlsx)
    for n in nodes:
        if canonical_category(str(n.get("function", "")), n["name"]) == "oob-switch":
            n["enabled"] = False
    result = ValidationResult()
    validate_single_tier_su({"architecture": "2-4-5-800"}, nodes, result)
    assert [w for w in result.warnings
            if "Active OOB switch count (0)" in w and f"expected {oob}" in w], result.warnings


def test_public_validator_refuses_su_between_supported_counts(public_mode):
    """SU=5 is not a generator-supported SU for 2-8-9-400 (models jump 4→6).

    The public tree has no models, so it must refuse SU=5 from the discrete
    snapshot the same way the internal tree does -- not accept it because
    5 < 16 and then only warn that there is no fan-out data (GitLab #98).
    """
    nodes = [{"name": f"su-{su:02d}-node-01", "function": "gpu", "enabled": True}
             for su in range(1, 6)]
    nodes += [{"name": f"oob-switch-{i:02d}", "function": "oob-switch",
               "category": "oob-switch", "enabled": True} for i in range(1, 4)]
    result = ValidationResult()
    validate_single_tier_su({"architecture": "2-8-9-400"}, nodes, result)
    assert [e for e in result.errors
            if "Active SU count (5) is not generator-supported for 2-8-9-400" in e
            and "Supported generator SUs: 1, 2, 3, 4, 6, 8, 12, 16" in e], result.errors
