# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
import sys
from pathlib import Path

import pytest

# Add scripts/ to path so we can import the modules
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from excel_parser import resolve_oob_vlans, get_oob_nodes_for_inventory

VLANS = [
    {"id": 200, "name": "oob-rack-1", "subnet": "192.168.200.0/24", "gateway": "192.168.200.1", "vrf": "OOB"},
    {"id": 201, "name": "oob-rack-2", "subnet": "192.168.201.0/24", "gateway": "192.168.201.1", "vrf": "OOB"},
    {"id": 300, "name": "in-band", "subnet": "172.16.178.0/24", "gateway": "172.16.178.1", "vrf": "INBAND"},
]

def test_distinct_vlan_per_switch():
    oob = [{"name": "oob-switch-01", "oob_vlan": "200"},
           {"name": "oob-switch-02", "oob_vlan": "201"}]
    r = resolve_oob_vlans(VLANS, oob)
    assert r["vlan_by_switch"]["oob-switch-01"]["subnet"] == "192.168.200.0/24"
    assert r["vlan_by_switch"]["oob-switch-02"]["subnet"] == "192.168.201.0/24"
    assert r["subnets"] == ["192.168.200.0/24", "192.168.201.0/24"]
    assert r["default_vlan_id"] is None  # >1 OOB vlan -> no single default

def test_blank_switch_uses_sole_default():
    single = [v for v in VLANS if v["id"] != 201]
    oob = [{"name": "oob-switch-01", "oob_vlan": ""},
           {"name": "oob-switch-02", "oob_vlan": ""}]
    r = resolve_oob_vlans(single, oob)
    assert r["default_vlan_id"] == 200
    assert r["vlan_by_switch"]["oob-switch-01"]["subnet"] == "192.168.200.0/24"
    assert r["subnets"] == ["192.168.200.0/24"]  # deduped: shared subnet

def test_unknown_vlan_id_resolves_none():
    oob = [{"name": "oob-switch-01", "oob_vlan": "999"}]
    r = resolve_oob_vlans(VLANS, oob)
    assert r["vlan_by_switch"]["oob-switch-01"] is None

def test_oob_nodes_svi_from_vlan_shared_subnet():
    nodes = [
        {"name": "oob-switch-01", "role": "OOB Switch", "category": "oob-switch",
         "status": "Active", "oob_vlan": "200", "mgmt_ip": "10.0.0.11"},
        {"name": "oob-switch-02", "role": "OOB Switch", "category": "oob-switch",
         "status": "Active", "oob_vlan": "200", "mgmt_ip": "10.0.0.12"},
    ]
    vlans = [{"id": 200, "name": "oob", "subnet": "192.168.200.0/24",
              "gateway": "192.168.200.1", "vrf": "OOB"}]
    out = get_oob_nodes_for_inventory(nodes, {}, vlans)
    ips = {n["name"]: n["svi_ip"] for n in out}
    assert ips == {"oob-switch-01": "192.168.200.2", "oob-switch-02": "192.168.200.3"}
    assert all(n["gateway"] == "192.168.200.1" and n["prefix"] == 24 for n in out)

def test_oob_nodes_svi_distinct_subnets():
    nodes = [
        {"name": "oob-switch-01", "role": "OOB Switch", "category": "oob-switch",
         "status": "Active", "oob_vlan": "200", "mgmt_ip": "10.0.0.11"},
        {"name": "oob-switch-02", "role": "OOB Switch", "category": "oob-switch",
         "status": "Active", "oob_vlan": "201", "mgmt_ip": "10.0.0.12"},
    ]
    vlans = [
        {"id": 200, "name": "oob-1", "subnet": "192.168.200.0/24", "gateway": "192.168.200.1", "vrf": "OOB"},
        {"id": 201, "name": "oob-2", "subnet": "192.168.201.0/24", "gateway": "192.168.201.1", "vrf": "OOB"},
    ]
    out = get_oob_nodes_for_inventory(nodes, {}, vlans)
    ips = {n["name"]: n["svi_ip"] for n in out}
    assert ips == {"oob-switch-01": "192.168.200.2", "oob-switch-02": "192.168.201.2"}


# ─── management_switches retirement ─────────────────
#
# The OOB switch count is now derived purely from the Active oob-switch rows
# on the Nodes tab — no Settings key drives it, and there is no synthetic
# padding. These tests prove: (1) an absent management_switches resolves the
# correct count from Nodes, (2) a stale/present management_switches value is
# fully ignored (no truncation, no padding), (3) Inactive oob-switch rows are
# excluded, and (4) each real switch gets its own correct SVI.

def _three_switch_fixture():
    nodes = [
        {"name": "oob-switch-01", "role": "OOB Switch", "category": "oob-switch",
         "status": "Active", "oob_vlan": "200", "mgmt_ip": "10.0.0.11"},
        {"name": "oob-switch-02", "role": "OOB Switch", "category": "oob-switch",
         "status": "Active", "oob_vlan": "200", "mgmt_ip": "10.0.0.12"},
        {"name": "oob-switch-03", "role": "OOB Switch", "category": "oob-switch",
         "status": "Active", "oob_vlan": "200", "mgmt_ip": "10.0.0.13"},
    ]
    vlans = [{"id": 200, "name": "oob", "subnet": "192.168.200.0/24",
              "gateway": "192.168.200.1", "vrf": "OOB"}]
    return nodes, vlans


def test_oob_count_derived_from_nodes_when_management_switches_absent():
    nodes, vlans = _three_switch_fixture()
    out = get_oob_nodes_for_inventory(nodes, {}, vlans)
    assert len(out) == 3
    names = {n["name"] for n in out}
    assert names == {"oob-switch-01", "oob-switch-02", "oob-switch-03"}
    ips = {n["name"]: n["svi_ip"] for n in out}
    assert ips == {
        "oob-switch-01": "192.168.200.2",
        "oob-switch-02": "192.168.200.3",
        "oob-switch-03": "192.168.200.4",
    }


def test_stale_management_switches_does_not_truncate_result():
    # A stale value smaller than the real Nodes count must NOT truncate the
    # result — management_switches no longer has any effect on the count.
    nodes, vlans = _three_switch_fixture()
    out = get_oob_nodes_for_inventory(nodes, {"management_switches": 1}, vlans)
    assert len(out) == 3


def test_stale_management_switches_does_not_pad_result():
    # A stale value larger than the real Nodes count must NOT synthesize
    # extra oob-switch-NN nodes — no more synthetic padding.
    nodes, vlans = _three_switch_fixture()
    out = get_oob_nodes_for_inventory(nodes, {"management_switches": 5}, vlans)
    assert len(out) == 3
    assert all(n.get("mgmt_ip") for n in out)  # all real nodes, none synthetic


def test_inactive_oob_switch_excluded_from_count():
    nodes, vlans = _three_switch_fixture()
    nodes[2]["status"] = "Inactive"
    out = get_oob_nodes_for_inventory(nodes, {}, vlans)
    assert len(out) == 2
    assert {n["name"] for n in out} == {"oob-switch-01", "oob-switch-02"}
