# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-135: collapsed-core and OOB-switch SVIs must be disjoint on the OOB VLAN.

In ``oob_uplink_mode=l2`` a collapsed-core fabric (``core-0N``) holds an SVI
on the OOB VLAN itself (``_svi_switch_ip`` walk: .2, .3) while the OOB
switches walk the same subnet from .2 as well (``_oob_switch_svi_ip``), so
``core-01`` and ``oob-switch-01`` both rendered ``192.168.200.2/24`` in one
broadcast domain. L3 mode (core OOB SVI has no address) and CSL fabrics
(CSL never carries the OOB VLAN) are unaffected and must stay byte-identical.

``make ip-report`` could not show the collision because ``load_switches``
ignored the flat ``svi_ip`` host_vars shape the L2 OOB switches use.
"""
import sys
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import excel_parser  # noqa: E402
from excel_parser import _svi_switch_ip, get_oob_nodes_for_inventory  # noqa: E402
from emit_ip_report import load_switches  # noqa: E402
from validate_excel import (ValidationResult,  # noqa: E402
                            validate_oob_mgmt_ip_collisions)

VLANS = [{"id": 200, "name": "oob", "subnet": "192.168.200.0/24",
          "gateway": "192.168.200.1", "vrf": "OOB"}]


def _sw(name, category):
    return {"name": name, "role": category, "category": category,
            "status": "Active", "oob_vlan": "200", "mgmt_ip": ""}


def _fabric(core_role, oob_count=2):
    return ([_sw("core-01", core_role), _sw("core-02", core_role)]
            + [_sw(f"oob-switch-{i + 1:02d}", "oob-switch") for i in range(oob_count)])


def _svis(nodes, settings):
    return {n["name"]: n["svi_ip"] for n in get_oob_nodes_for_inventory(nodes, settings, VLANS)}


def test_l2_collapsed_core_oob_switch_svis_skip_the_core_addresses():
    svis = _svis(_fabric("core"), {"oob_uplink_mode": "l2"})
    core = {_svi_switch_ip(VLANS[0]["subnet"], VLANS[0]["gateway"], n) for n in (1, 2)}
    assert core == {"192.168.200.2", "192.168.200.3"}
    assert svis == {"oob-switch-01": "192.168.200.4", "oob-switch-02": "192.168.200.5"}
    assert not core & set(svis.values())


def test_l3_mode_keeps_the_historical_walk():
    assert _svis(_fabric("core"), {"oob_uplink_mode": "l3"}) == {
        "oob-switch-01": "192.168.200.2", "oob-switch-02": "192.168.200.3"}


def test_csl_fabric_l2_keeps_the_historical_walk():
    assert _svis(_fabric("csl"), {"oob_uplink_mode": "l2"}) == {
        "oob-switch-01": "192.168.200.2", "oob-switch-02": "192.168.200.3"}


def test_collapsed_core_svi_ips_only_in_l2_with_core_rows():
    collapsed_core_svi_ips = excel_parser.collapsed_core_svi_ips
    nodes = _fabric("core")
    assert collapsed_core_svi_ips({"oob_uplink_mode": "l2"}, nodes, "192.168.200.0/24") == [
        "192.168.200.2", "192.168.200.3"]
    assert collapsed_core_svi_ips({"oob_uplink_mode": "l3"}, nodes, "192.168.200.0/24") == []
    assert collapsed_core_svi_ips({"oob_uplink_mode": "l2"}, _fabric("csl"), "192.168.200.0/24") == []
    disabled = [dict(n, status="Disabled") if n["category"] == "core" else n for n in nodes]
    assert collapsed_core_svi_ips({"oob_uplink_mode": "l2"}, disabled, "192.168.200.0/24") == []


def test_oob_switch_svi_ips_without_skip_is_the_historical_walk():
    oob_switch_svi_ips = excel_parser.oob_switch_svi_ips
    assert oob_switch_svi_ips("192.168.200", 0, 3, 24) == [
        "192.168.200.2", "192.168.200.3", "192.168.200.4"]
    assert oob_switch_svi_ips("192.168.200", 0, 2, 24, skip=["192.168.200.2/24", "192.168.200.3"]) == [
        "192.168.200.4", "192.168.200.5"]


def _validator_rows(core_role, extra=()):
    rows = [{"name": "core-01", "function": core_role, "row": 2, "enabled": True, "oob_vlan": "200"},
            {"name": "core-02", "function": core_role, "row": 3, "enabled": True, "oob_vlan": "200"},
            {"name": "oob-switch-01", "function": "oob-switch", "row": 4, "enabled": True, "oob_vlan": "200"},
            {"name": "oob-switch-02", "function": "oob-switch", "row": 5, "enabled": True, "oob_vlan": "200"}]
    return rows + list(extra)


def _run_validator(rows, mode):
    result = ValidationResult()
    validate_oob_mgmt_ip_collisions(
        rows, result, settings={"oob_uplink_mode": mode},
        oob_subnets=[VLANS[0]["subnet"]], parsed_vlans=VLANS)
    return [e for e in result.errors if "claimed by multiple owners" in str(e)]


def test_validator_claims_core_svis_in_l2_mode():
    host_on_core_svi = {"name": "support-01", "function": "support", "row": 6,
                        "enabled": True, "ip": "192.168.200.2"}
    errs = _run_validator(_validator_rows("core", [host_on_core_svi]), "l2")
    assert errs and "core-01 OOB SVI (generated)" in str(errs[0])
    # In l3 the core OOB SVI carries no address, so .2 is oob-switch-01's.
    errs = _run_validator(_validator_rows("core", [host_on_core_svi]), "l3")
    assert errs and "oob-switch-01 SVI (generated)" in str(errs[0])
    assert "core-01" not in str(errs[0])


def test_validator_generated_claims_are_self_consistent():
    """Core + oob-switch SVIs alone (no operator rows) never collide."""
    for role, mode in (("core", "l2"), ("core", "l3"), ("csl", "l2")):
        assert _run_validator(_validator_rows(role), mode) == []


def test_ip_report_admits_flat_svi_ip_host_vars(tmp_path):
    (tmp_path / "oob-switch-01.yml").write_text(yaml.safe_dump(
        {"svi_ip": "192.168.200.2/24", "oob_access_vlan": 200}))
    (tmp_path / "core-01.yml").write_text(yaml.safe_dump(
        {"vlan_interfaces": [{"id": "vlan200", "ip": "192.168.200.2/24", "vlan": "200"}]}))
    (tmp_path / "su-01-node-01.yml").write_text(yaml.safe_dump({"eth0_ip": "192.168.200.10"}))
    assert set(load_switches(tmp_path)) == {"oob-switch-01", "core-01"}
