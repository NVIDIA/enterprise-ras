# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-67 / ADR-0046: N/S host-facing bonds are STP edge ports with BPDU guard.

Positive: every `network_roles` bond group that is host-facing (cpu, support,
custom server profiles) and a `br_default` member gets

    nv set interface <bonds> bridge domain br_default stp admin-edge enabled
    nv set interface <bonds> bridge domain br_default stp bpdu-guard enabled

Negative: ISL, the L2 OOB uplink bond, storage bonds, GPU/edge direct
interfaces and any interface that is not a bond never carry either key.
Rendered against the core template directly and against every committed
`*-config.sh`.
"""

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CORE_TEMPLATE = PROJECT_ROOT / "roles" / "core" / "templates" / "core_nvue_cli.j2"
STP_RE = re.compile(r"^nv set interface (\S+) bridge domain br_default stp (admin-edge|bpdu-guard) enabled$", re.M)

# Both committed sites; host leaves render from the core role as core/csl (default) or cl (largescale).
CONFIGS = sorted(PROJECT_ROOT.glob("output/*/*/configs/*-config.sh"))
CONFIGS = [p for p in CONFIGS if p.parts[-3] in ("default", "largescale")]
CORE_CONFIGS = [p for p in CONFIGS if p.name.startswith(("core", "csl", "cl-"))]
NON_CORE_CONFIGS = [p for p in CONFIGS if p not in CORE_CONFIGS]


def _render(vars_):
    env = Environment(loader=FileSystemLoader(str(CORE_TEMPLATE.parent)),
                      undefined=StrictUndefined, extensions=["jinja2.ext.do"])
    env.filters["regex_replace"] = lambda v, p, r: re.sub(p, r, str(v))
    env.filters["quote"] = lambda s: str(s)
    return env.get_template(CORE_TEMPLATE.name).render(**vars_)


def _stp_targets(text):
    """{interface-list: {keys}} for every stp admin-edge/bpdu-guard line."""
    out = {}
    for ifaces, key in STP_RE.findall(text):
        out.setdefault(ifaces, set()).add(key)
    return out


def _bond_group(ports, vlan=100, **extra):
    d = {"ports": ports, "breakout": 4, "lanes": 2, "vlan": vlan, "lacp_bypass": True,
         "port_overrides": {}, "bond_overrides": {}}
    d.update(extra)
    return d


@pytest.fixture
def core_vars():
    """Minimal core context: cpu bond group on ports 1-2 (VLAN 100), GPU direct
    on 3-4, ISL direct on 49-50 — mirrors test_templates.py's core_vars."""
    return {
        "hostname": "core-01",
        "ansible_date_time": {"iso8601": "2026-01-01T00:00:00Z"},
        "lo_ip": "172.16.176.1/32",
        "mh_mac": "44:38:39:BE:EF:01",
        "vlans": [100, 200, 300],
        "vnis": {100: 4100, 200: 4200, 300: 4300},
        "vlan_interfaces": [{"id": "vlan100", "vlan": 100, "ip": "172.16.178.2/24",
                             "vrr": "172.16.178.1/24", "vrf": "default"}],
        "network_roles": {"cpu": _bond_group([1, 2], vlan=100)},
        "gpu_interfaces": {"ports": [3, 4], "breakout": 2, "lanes": 4, "vlan": 200,
                           "state": "up", "port_overrides": {}},
        "isl_interfaces": {"ports": [49, 50], "breakout": 2, "lanes": 4, "port_overrides": {}},
        "interfaces_disabled": [60, 62, 64],
        "interfaces_up": "swp1s0-3,swp2s0-3,swp3s0-1,swp4s0-1,swp49s0-1,swp50s0-1",
        "interfaces_down": "swp60,swp62,swp64",
        "nve_vxlan": {"decap_dscp": "copy", "encap_dscp": "copy", "source": "172.16.176.1"},
        "anycast_mac": "44:38:39:BE:EF:AA",
        "bgp_asn": 65100,
        "router_id": "172.16.176.1",
        "vrf_config": [{"id": "default", "lo": "172.16.176.1/32"}],
        "num_physical_ports": 64,
        "ntp_servers": ["0.pool.ntp.org"],
        "ssh_authorized_keys": [],
        "ldap": {"enabled": False},
        "community_list": {},
        "route_map": {},
        "timezone": "Etc/UTC",
    }


class TestRenderedTemplate:
    def test_cpu_bond_group_gets_both_keys_once(self, core_vars):
        out = _render(core_vars)
        targets = _stp_targets(out)
        bonds = "bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3"
        assert targets == {bonds: {"admin-edge", "bpdu-guard"}}
        assert out.count("stp admin-edge enabled") == 1 and out.count("stp bpdu-guard enabled") == 1

    def test_stp_keys_follow_bridge_membership_of_same_bonds(self, core_vars):
        out = _render(core_vars)
        bonds = "bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3"
        access = out.index(f"nv set interface {bonds} bridge domain br_default access 100")
        edge = out.index(f"nv set interface {bonds} bridge domain br_default stp admin-edge enabled")
        guard = out.index(f"nv set interface {bonds} bridge domain br_default stp bpdu-guard enabled")
        assert access < edge < guard

    def test_support_and_custom_server_roles_are_guarded(self, core_vars):
        core_vars["network_roles"]["support"] = _bond_group([5], vlan=200)
        core_vars["network_roles"]["bcm"] = _bond_group([6], vlan="300,400", vlan_untagged=300)
        targets = _stp_targets(_render(core_vars))
        assert targets["bond5s0,bond5s1,bond5s2,bond5s3"] == {"admin-edge", "bpdu-guard"}
        assert targets["bond6s0,bond6s1,bond6s2,bond6s3"] == {"admin-edge", "bpdu-guard"}

    def test_oob_l2_uplink_bond_is_not_guarded(self, core_vars):
        core_vars["network_roles"]["oob"] = _bond_group([59], vlan=200, breakout=8, lanes=1,
                                                        lacp_bypass=False)
        out = _render(core_vars)
        assert "bond59s0,bond59s1,bond59s2,bond59s3,bond59s4,bond59s5,bond59s6,bond59s7 bridge domain br_default access 200" in out
        assert not any("bond59" in ifaces for ifaces in _stp_targets(out))

    def test_storage_bond_is_not_guarded(self, core_vars):
        core_vars["network_roles"]["storage"] = _bond_group([7], vlan=300)
        out = _render(core_vars)
        assert "bond7s0,bond7s1,bond7s2,bond7s3 bridge domain br_default access 300" in out
        assert not any("bond7" in ifaces for ifaces in _stp_targets(out))

    def test_isl_role_in_network_roles_is_not_guarded(self, core_vars):
        core_vars["network_roles"]["isl"] = _bond_group([49], vlan=100)
        out = _render(core_vars)
        assert not any("bond49" in ifaces for ifaces in _stp_targets(out))

    def test_host_role_without_bridge_vlan_is_not_guarded(self, core_vars):
        core_vars["network_roles"]["cpu"]["vlan"] = None
        out = _render(core_vars)
        assert _stp_targets(out) == {}

    def test_gpu_and_isl_direct_interfaces_never_guarded(self, core_vars):
        out = _render(core_vars)
        for ifaces in _stp_targets(out):
            for iface in ifaces.split(","):
                assert iface.startswith("bond"), f"stp key on non-bond {iface}"
                assert not re.match(r"bond(3|4|49|50)s", iface), f"GPU/ISL port guarded: {iface}"


@pytest.mark.parametrize("cfg", CORE_CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
class TestCommittedCoreConfigs:
    def test_every_host_bond_group_has_both_keys(self, cfg):
        """Every bridged bond group in the committed core configs is a host group.
        The shipped workbooks are all L3-OOB with no L2 storage bonds, so a bridged
        `oob`/`storage` group never appears here; the template's exclusion of those
        roles is covered by TestRenderedTemplate, not by this committed-output check.
        If such output is ever committed, this test needs the group filtered out."""
        text = cfg.read_text()
        host_groups = re.findall(
            r"^nv set interface (bond\S+) bridge domain br_default (?:vlan|access) \S+$", text, re.M)
        assert host_groups, f"{cfg.name}: fixture assumption — core has bridged host bonds"
        targets = _stp_targets(text)
        for group in host_groups:
            assert targets.get(group) == {"admin-edge", "bpdu-guard"}, f"{cfg.name}: {group}"
        assert set(targets) == set(host_groups), f"{cfg.name}: stp keys on non-host groups"

    def test_stp_keys_only_on_bonds(self, cfg):
        for ifaces, _ in STP_RE.findall(cfg.read_text()):
            assert all(i.startswith("bond") for i in ifaces.split(",")), f"{cfg.name}: {ifaces}"

    def test_isl_and_uplink_interfaces_not_guarded(self, cfg):
        text = cfg.read_text()
        guarded = {i for ifaces, _ in STP_RE.findall(text) for i in ifaces.split(",")}
        # ISL/edge/OOB-uplink/GPU are direct swp interfaces; none may be guarded.
        assert not any(i.startswith("swp") for i in guarded), f"{cfg.name}: {guarded}"
        # Any bond carrying a BGP neighbor or an IP address is a fabric link, not a host bond.
        for bond in re.findall(r"^nv set interface (bond\S+?) ipv?4? address", text, re.M):
            assert bond not in guarded, f"{cfg.name}: routed bond {bond} guarded"


@pytest.mark.parametrize("cfg", NON_CORE_CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
def test_non_core_roles_are_untouched(cfg):
    """Spine, GL, OOB and edge configs have no host bonds and gain no stp keys."""
    assert STP_RE.search(cfg.read_text()) is None, cfg.name


@pytest.mark.parametrize("site", ["default", "largescale"])
def test_every_committed_arch_has_core_configs(site):
    committed = {p.parent.name for p in PROJECT_ROOT.glob(f"output/*/{site}")}
    covered = {p.parts[-4] for p in CORE_CONFIGS if p.parts[-3] == site}
    assert committed and covered == committed
