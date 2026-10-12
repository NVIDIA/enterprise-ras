# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
ERA-104 / GitLab #78 — the committed `2-8-5-400` workbooks and their
generated output carry the ERA-00014-001 topology (ADR-0082).

`default` is SU 3 (last converged-core scale: 2 `core`, 2 OOB, no N/S ISL);
`largescale` is SU 8 (2 `csl`, 4 `gl-plane1`, 2 `gs-plane1`, 4 OOB, Table 11's
256 E/W and 18 N/S switch-to-switch cables, every node's eight CX8 ports
spread across all four E/W leaves). The public-tree registrations
(registry, scaling, validator) are pinned here too; CI-matrix and e2e-fixture
coverage live in release/boundary/, which derives them from the models.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
import pytest

NC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NC / "scripts"))
sys.path.insert(0, str(NC / "tests"))

import workbook_access  # noqa: E402
from _valid_archs import VALID_ARCHS  # noqa: E402
from arch_scaling import (ARCH_MULTI_TIER_ONLY, ARCH_SCALING, MAX_SUPPORTED_SU,  # noqa: E402
                          OOB_SWITCHES_BY_SU)
from validate_excel import ARCH_RESTRICTED_FUNCTIONS, ROLE_ENFORCEMENT  # noqa: E402

ARCH = "2-8-5-400"
INPUT = NC / "input" / ARCH
OUTPUT = NC / "output" / ARCH


def _wiremap(site):
    wb = openpyxl.load_workbook(INPUT / site / f"{ARCH}.xlsx", data_only=True)
    return [(str(r["a_name"]), str(r["a_port"]), str(r["z_name"]), str(r["z_port"]))
            for r in workbook_access.wiremap_rows(wb)]


FABRIC_ROLES = {"core", "csl", "gl-plane1", "gs-plane1", "gsl-plane1", "cs", "oob-switch"}


def _switches(rows):
    return {n for a, _, z, _ in rows for n in (a, z) if _role(n) in FABRIC_ROLES}


def _role(name):
    return re.sub(r"-\d+$", "", name)


def _su_count(rows):
    return max(int(m.group(1)) for a, _, z, _ in rows for n in (a, z)
               for m in [re.match(r"^su-(\d+)-", n)] if m)


def test_default_is_su3_converged_core():
    rows = _wiremap("default")
    assert _su_count(rows) == 3
    assert Counter(_role(s) for s in _switches(rows)) == {"core": 2, "oob-switch": 2}
    core_isl = sum(1 for a, _, z, _ in rows if _role(a) == _role(z) == "core")
    assert core_isl == 48, "Table 11 SU 3: 48 E/W switch-to-switch cables, N/S converged (0 of its own)"


def test_largescale_is_su8_leaf_spine_with_dedicated_ns_pair():
    rows = _wiremap("largescale")
    assert _su_count(rows) == 8
    assert Counter(_role(s) for s in _switches(rows)) == {
        "csl": 2, "gl-plane1": 4, "gs-plane1": 2, "oob-switch": 4}


def test_largescale_switch_to_switch_cables_match_table11():
    rows = _wiremap("largescale")
    ew_isl = sum(1 for a, _, z, _ in rows if {_role(a), _role(z)} == {"gl-plane1", "gs-plane1"})
    ns_isl = sum(1 for a, _, z, _ in rows if _role(a) == _role(z) == "csl")
    assert (ew_isl, ns_isl) == (256, 18)


def test_largescale_spreads_every_nodes_eight_cx8_ports_over_all_four_leaves():
    rows = _wiremap("largescale")
    per_node = defaultdict(list)
    for a, ap, z, _ in rows:
        if a.startswith("su-") and ap.startswith("CX8 SuperNIC"):
            per_node[a].append(z)
    assert len(per_node) == 32
    for node, leaves in per_node.items():
        assert len(leaves) == 8, node
        assert Counter(leaves) == {f"gl-plane1-0{i}": 2 for i in range(1, 5)}, node


def test_every_node_has_one_dual_port_b3220_on_the_ns_pair():
    for site, ns_role in (("default", "core"), ("largescale", "csl")):
        rows = _wiremap(site)
        per_node = defaultdict(set)
        for a, ap, z, _ in rows:
            if a.startswith("su-") and ap.startswith("B3220"):
                per_node[a].add(z)
        assert per_node and all(v == {f"{ns_role}-01", f"{ns_role}-02"} for v in per_node.values()), site


@pytest.mark.parametrize("site,expected", [
    ("default", {"core": 2, "oob-switch": 2}),
    ("largescale", {"csl": 2, "gl-plane1": 4, "gs-plane1": 2, "oob-switch": 4}),
])
def test_generated_output_has_one_config_per_switch(site, expected):
    configs = sorted(p.name for p in (OUTPUT / site / "configs").glob("*-config.sh"))
    got = Counter(_role(n[: -len("-config.sh")]) for n in configs)
    assert got == expected, configs


def test_largescale_gpu_leaf_configs_peer_with_both_spines():
    """Each leaf carries 64 unnumbered ISL subport peers (256 cables / 4
    leaves, one subport each) plus loopback overlay sessions to both spines; a
    collapsed render would leave the leaves without any peer."""
    spines = {re.search(r"^lo_ip: ([\d.]+)/32", (OUTPUT / "largescale" / "inventory" / "host_vars"
                                                        / f"gs-plane1-0{i}.yml").read_text(), re.M).group(1)
              for i in (1, 2)}
    assert len(spines) == 2
    for leaf in ("gl-plane1-01", "gl-plane1-04"):
        text = (OUTPUT / "largescale" / "configs" / f"{leaf}-config.sh").read_text()
        assert len(re.findall(r"neighbor swp\d+s\d peer-group internal_isl$", text, re.M)) == 64, leaf
        for ip in spines:
            assert f"neighbor {ip} peer-group overlay" in text, (leaf, ip)
    for spine in ("gs-plane1-01", "gs-plane1-02"):
        text = (OUTPUT / "largescale" / "configs" / f"{spine}-config.sh").read_text()
        assert len(re.findall(r"peer-group underlay$", text, re.M)) == 128, spine


def test_arch_is_registered_everywhere_the_seven_others_are():
    assert ARCH in VALID_ARCHS
    assert MAX_SUPPORTED_SU[ARCH] == 8
    assert OOB_SWITCHES_BY_SU[ARCH] == {1: 2, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4}
    assert ARCH not in ARCH_MULTI_TIER_ONLY, "SU 1-4 are single-tier"
    tiers = ARCH_SCALING[ARCH]
    assert tiers[0].min_su == 1 and tiers[0].gsl_leaves_per_plane is None
    assert tiers[-1].max_su == 4 and tiers[-1].gsl_leaves_per_plane == 2
    assert ROLE_ENFORCEMENT[ARCH] == "strict"
    for fn in ("core", "csl", "cs", "gsl-plane1", "gs-plane1"):
        assert ARCH in ARCH_RESTRICTED_FUNCTIONS[fn], fn
    for fn in ("gsl-plane2", "gs-plane2", "ext-storage"):
        assert ARCH not in ARCH_RESTRICTED_FUNCTIONS[fn], fn


def test_ns_spine_role_is_registered_because_the_model_offers_ns_tier_2():
    """The source topology has no N/S spine, but the model advertises
    `supported_deviations.ns_tier: [source, 1, 2]`, and `--ns-tier 2` emits
    `cs-01`/`cs-02` above `cl-*` leaves (`cl` is unrestricted). The validator's
    role allow-list must cover every Function the generator can emit for the
    arch, or the workbook fails at `make validate-excel` after the generator
    exited 0 (MR !303 review P2)."""
    assert ARCH in ARCH_RESTRICTED_FUNCTIONS["cs"]
    assert "cl" not in ARCH_RESTRICTED_FUNCTIONS
