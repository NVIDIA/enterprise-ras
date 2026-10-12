# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Phase 0's structural equivalence gate (re-scoped 2026-09-08 after two
measured gaps -- see internal-docs/plans/2026-09-08-intake-form-design.md,
"Phase 0 -- prove it."): a converted workbook must parse to the same
`settings`, Cumulus `versions` and `nodes` structures a legacy parse of
the original produces, for every key the intake path actually carries.

This asserts STRUCTURAL equivalence only -- same parsed settings, versions
and nodes. Byte-identical generated output is asserted separately by
tests/test_intake_generation_equivalence.py, which runs the real parser and
compares the artifacts; keep both, because structural equality says nothing
about the thirteen downstream call sites that read legacy sheets directly.

This test exercises the parsing helpers (`_parse_intake_settings` /
`_parse_intake_nodes`) directly rather than going through
`process_excel_template`, so a failure here points at the reader rather than
at the whole pipeline.

What this DOES prove: the converter, the intake reader, the two derivation
functions and the sheet-name mapping agree with the legacy path on every
settings/version/node field they together carry today -- the parsing half
of Phase 0's promise, without claiming the generation half.
"""
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

NC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NC / "scripts"))

from excel_parser import (  # noqa: E402
    _parse_intake_nodes,
    _parse_intake_settings,
    parse_nodes,
    parse_settings,
    parse_versions,
)

# The frozen legacy sample -- see conftest. This compares the two parsing
# paths, so it needs a workbook in each format, and `input/` now holds only
# the intake form.
sys.path.insert(0, str(Path(__file__).parent))
from conftest import LEGACY_SAMPLE  # noqa: E402

LEGACY_XLSX = LEGACY_SAMPLE

# The exact settings/version keys the intake path produces for this
# fixture -- measured by running `_parse_intake_settings` against the real
# converted 2-8-9-800/default workbook, not guessed. Pinned rather than a
# floor: a regression that drops one of these while another key appears
# (keeping the total count unchanged) must fail loudly, not slip through
# a `len(...) >= N` check. If a future task deliberately adds or removes a
# derived setting, update this set as part of that change.
# Grew from 14 to 26 when the converter stopped over-stripping. It had been
# removing all 14 of DERIVED_SETTINGS from `Deployment` on the theory that the
# parser would rebuild them, but only 2 are derivable -- so 12 real values were
# destroyed and four of them silently fell back to WRONG hardcoded defaults
# downstream. The converter now strips only what intake_derive can actually
# rebuild and declares the rest, which is what closes the settings gap.
EXPECTED_INTAKE_SETTINGS_KEYS = frozenset({
    # carried before the fix
    'anycast_mac', 'convergence', 'deploy_in_air', 'gpu_planes',
    'ldap_base_dn', 'ldap_domain', 'ldap_enabled', 'ldap_root_dn',
    'mh_mac', 'ntp_servers', 'post_login_message', 'pre_login_message',
    'status_page_enabled', 'timezone',
    # recovered by the fix -- declared in Deployment, not derived
    'architecture', 'disabled_ports', 'ew_tiers', 'gpu_vlan_mode',
    'ldap_servers', 'loopback_base', 'netq_ip', 'ns_tiers',
    'num_physical_ports', 'oob_uplink_mode', 'site_name', 'ztp_server',
})
EXPECTED_INTAKE_VERSION_ROLES = frozenset({'core', 'oob', 'csl', 'gsl'})

# Node keys the intake path does not yet carry. `parse_nodes()` (legacy)
# and `_read_intake_node_rows()` (intake) both build the identical 11-key
# schema {role, name, category, index, status, mac_address, mgmt_ip,
# prefix, gateway, ztp, oob_vlan} -- measured equal for this fixture -- so
# today there is nothing to exclude. Kept as a named, explicit set (rather
# than a bare comparison) so a future schema drift
# shows up as a decision to make, not a silent narrowing of the gate.
NODE_KEYS_NOT_CARRIED_BY_INTAKE = set()


@pytest.fixture(scope="module")
def converted_workbook(tmp_path_factory):
    dst = tmp_path_factory.mktemp("intake") / "2-8-9-800-intake.xlsx"
    subprocess.run(
        ["python3", "scripts/convert_workbook.py", str(LEGACY_XLSX), str(dst)],
        cwd=NC, check=True)
    return dst


def test_intake_settings_and_versions_match_legacy_for_every_carried_key(converted_workbook):
    legacy_wb = openpyxl.load_workbook(LEGACY_XLSX, data_only=True)
    legacy_settings = parse_settings(legacy_wb['Settings'])
    new_format = 'Air_Only' in legacy_wb.sheetnames
    legacy_versions = parse_versions(legacy_wb['Settings']) if new_format else {}

    intake_wb = openpyxl.load_workbook(converted_workbook, data_only=True)
    intake_settings, intake_versions = _parse_intake_settings(intake_wb)

    # Pin the carried key set exactly -- not just its size -- so a
    # regression that drops one derived setting while another appears
    # (net count unchanged) still fails. We do NOT assert this equals the
    # *legacy* key set: 12 legacy settings (architecture, site_name,
    # ns_tiers, ew_tiers, loopback_base, num_physical_ports,
    # disabled_ports, gpu_vlan_mode, oob_uplink_mode, ztp_server, netq_ip,
    # ldap_servers) have no intake derivation yet; that gap is Phase 1 work
    # (internal-docs/plans/2026-09-08-intake-form-design.md, "Phase 1 --
    # all 14 cells").
    assert set(intake_settings) == EXPECTED_INTAKE_SETTINGS_KEYS, (
        f"intake settings key set changed -- got {sorted(intake_settings)}, "
        f"expected {sorted(EXPECTED_INTAKE_SETTINGS_KEYS)}. If this is a "
        "deliberate addition/removal, update EXPECTED_INTAKE_SETTINGS_KEYS.")
    assert set(intake_versions) == EXPECTED_INTAKE_VERSION_ROLES, (
        f"intake Cumulus version roles changed -- got {sorted(intake_versions)}, "
        f"expected {sorted(EXPECTED_INTAKE_VERSION_ROLES)}. If this is a "
        "deliberate addition/removal, update EXPECTED_INTAKE_VERSION_ROLES.")

    # Now that the key sets are pinned, every one of those keys' values
    # must equal the legacy parse.
    mismatches = {
        key: (value, legacy_settings.get(key))
        for key, value in intake_settings.items()
        if value != legacy_settings.get(key)
    }
    assert not mismatches, (
        "intake settings diverge from legacy for a key the intake path "
        f"carries -- (intake, legacy): {mismatches}")

    version_mismatches = {
        role: (value, legacy_versions.get(role))
        for role, value in intake_versions.items()
        if value != legacy_versions.get(role)
    }
    assert not version_mismatches, (
        "intake Cumulus versions diverge from legacy -- "
        f"(intake, legacy): {version_mismatches}")

    # Guard against vacuity: the exact-set assertions above only mean
    # something if the expected sets themselves are non-trivial. A FLOOR, not
    # an exact count -- the exact membership is already pinned by
    # EXPECTED_INTAKE_SETTINGS_KEYS above, and duplicating the number here
    # just means editing two places for every deliberate change, which is how
    # the pin ends up loosened out of annoyance.
    assert len(EXPECTED_INTAKE_SETTINGS_KEYS) >= 20
    assert len(EXPECTED_INTAKE_VERSION_ROLES) == 4


def test_intake_nodes_match_legacy_for_every_carried_key(converted_workbook):
    legacy_wb = openpyxl.load_workbook(LEGACY_XLSX, data_only=True)
    legacy_nodes = parse_nodes(legacy_wb['Nodes'])

    intake_wb = openpyxl.load_workbook(converted_workbook, data_only=True)
    intake_nodes = _parse_intake_nodes(intake_wb)

    # Guard against vacuity, part 1: fix the expected count for this
    # fixture so a future regression that drops/duplicates nodes on
    # *both* sides at once (which a bare `==` would miss) still shows up.
    assert len(legacy_nodes) == 35
    assert len(intake_nodes) == 35

    legacy_by_name = {n['name']: n for n in legacy_nodes}
    intake_by_name = {n['name']: n for n in intake_nodes}
    assert len(legacy_by_name) == len(legacy_nodes), "legacy node names are not unique"
    assert len(intake_by_name) == len(intake_nodes), "intake node names are not unique"
    assert set(intake_by_name) == set(legacy_by_name), (
        "intake and legacy parses disagree on the set of node names:\n"
        f"  only in intake: {sorted(set(intake_by_name) - set(legacy_by_name))}\n"
        f"  only in legacy: {sorted(set(legacy_by_name) - set(intake_by_name))}")

    legacy_key_union = set().union(*(n.keys() for n in legacy_nodes))
    expected_node_keys = legacy_key_union - NODE_KEYS_NOT_CARRIED_BY_INTAKE
    assert expected_node_keys, "legacy node schema minus exclusions is empty -- nothing to compare"

    # Per-node key-set check FIRST, and separately from the value check.
    # Walking only `intake_node.items()` for values would never notice a
    # SINGLE node missing a key (e.g. one Host Data row with a blank
    # extension column) as long as other nodes still carry it -- only a
    # fleet-wide drop would show up in an aggregate key-union check. This
    # asserts the full 11-key shape on every node, by name.
    key_mismatches = {}
    value_mismatches = {}
    for name, intake_node in intake_by_name.items():
        actual_keys = set(intake_node.keys())
        if actual_keys != expected_node_keys:
            key_mismatches[name] = {
                'missing': sorted(expected_node_keys - actual_keys),
                'unexpected': sorted(actual_keys - expected_node_keys),
            }
            continue  # wrong shape -- comparing values would be meaningless
        legacy_node = legacy_by_name[name]
        for key in expected_node_keys:
            if intake_node[key] == legacy_node.get(key):
                continue
            # `oob_vlan` is DERIVED onto the intake form where the legacy
            # Nodes tab left it blank: the legacy sheet only stamps it on
            # oob-switch rows, so every other node on the OOB network carried
            # an empty cell that says nothing to whoever fills the form. The
            # value is the sole VRF-OOB VLAN -- exactly what
            # `resolve_oob_vlans` would default a blank to -- so it is an
            # enrichment, not a divergence, and generated configs are
            # unchanged (test_intake_generation_equivalence proves that).
            # A legacy value that is PRESENT and different is still a failure.
            if key == 'oob_vlan' and not legacy_node.get(key):
                continue
            value_mismatches.setdefault(name, {})[key] = (intake_node[key], legacy_node.get(key))

    assert not key_mismatches, (
        "one or more nodes are missing/adding keys relative to the "
        f"expected {sorted(expected_node_keys)} schema: {key_mismatches}")
    assert not value_mismatches, f"intake nodes diverge from legacy: {value_mismatches}"

    # Guard against vacuity, part 2: 35 nodes, each checked against an
    # 11-key expected schema -- 385 individual field comparisons above.
    assert len(intake_by_name) == 35
    assert len(expected_node_keys) == 11
