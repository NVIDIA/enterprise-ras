# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Unit tests for the Air-infrastructure address allocator (ERA-134).

Before this module existed, `generate_group_vars` emitted the L2 `dhcp-oob`
OOB address as `network_address + 78`. On `100.82.254.128/26` that is
`100.82.254.206` — outside the subnet — and every server on the Jupiter site
was unreachable. The properties these tests defend:

  * an infra address is ALWAYS a usable host of the declared subnet;
  * the historical octet is honoured when it is free (so shipped /24
    inventories do not churn);
  * taken addresses (nodes, gateway, SVIs, reservations, earlier infra) are
    never handed out twice;
  * exhaustion is a hard `InfraCapacityError`, never a skip or a spill.

Run against `archive/<date>/excel_parser.py.*.bak` (pre-change generator), the
generator-level tests here fail; see the evidence doc for the count.
"""
import ipaddress
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import infra_ip_allocation as a  # noqa: E402
import oob_reserved  # noqa: E402
import excel_parser  # noqa: E402


def plan_infra_addresses(*args, **kwargs):
    # Looked up at call time so the pre-change excel_parser (no planner)
    # fails the two planner tests individually instead of at import.
    return excel_parser.plan_infra_addresses(*args, **kwargs)


JUPITER = "100.82.254.128/26"
DEFAULT = "192.168.200.0/24"


def _hosts(subnet):
    return set(ipaddress.IPv4Network(subnet).hosts())


# ── allocate_infra_ip: preferred / scan / bounds ────────────────────────

def test_slash24_preferred_78_is_honoured():
    assert a.allocate_infra_ip(DEFAULT, [], 78) == "192.168.200.78"


def test_slash25_preferred_78_still_inside():
    assert a.allocate_infra_ip("10.0.0.128/25", [], 78) == "10.0.0.206"


def test_slash26_preferred_78_is_out_of_subnet_falls_to_scan():
    """The Jupiter bug: +78 on a /26 is .206, not a host of the /26."""
    ip = a.allocate_infra_ip(JUPITER, [], 78)
    assert ip != "100.82.254.206"
    assert ipaddress.IPv4Address(ip) in _hosts(JUPITER)
    assert ip == "100.82.254.129"


def test_slash26_with_jupiter_claims_lands_in_subnet():
    taken = a.taken_addresses(
        JUPITER,
        [f"100.82.254.{o}" for o in range(134, 161)],   # 27 servers
        ["100.82.254.129"],                              # declared gateway
        ["100.82.254.130", "100.82.254.131"],            # OOB SVIs
    )
    ip = a.allocate_infra_ip(JUPITER, taken, 78, claimant="dhcp-oob")
    assert ipaddress.IPv4Address(ip) in _hosts(JUPITER)
    assert ipaddress.IPv4Address(ip) not in taken


def test_small_subnet_with_capacity_slash29():
    ip = a.allocate_infra_ip("10.9.9.8/29", ["10.9.9.9", "10.9.9.10"], 78)
    assert ip == "10.9.9.11"


def test_slash30_single_free_host():
    assert a.allocate_infra_ip("10.9.9.0/30", ["10.9.9.1"], 78) == "10.9.9.2"


def test_non_zero_base_preferred_is_relative_to_network_address():
    assert a.allocate_infra_ip("10.20.30.128/25", [], 78) == "10.20.30.206"


def test_never_returns_network_or_broadcast():
    for subnet in (JUPITER, DEFAULT, "10.0.0.0/30", "172.16.5.64/27"):
        net = ipaddress.IPv4Network(subnet)
        ip = ipaddress.IPv4Address(a.allocate_infra_ip(subnet, [], 0))
        assert ip not in (net.network_address, net.broadcast_address)
        ip = ipaddress.IPv4Address(a.allocate_infra_ip(subnet, [], 255))
        assert ip not in (net.network_address, net.broadcast_address)


def test_occupied_preferred_falls_through_to_first_free():
    ip = a.allocate_infra_ip(DEFAULT, ["192.168.200.78", "192.168.200.1"], 78)
    assert ip == "192.168.200.2"


def test_preferred_may_be_a_literal_address():
    assert a.allocate_infra_ip(DEFAULT, [], "192.168.200.77") == "192.168.200.77"


def test_out_of_subnet_taken_entries_are_ignored():
    taken = a.taken_addresses(JUPITER, ["192.168.200.5", "garbage", None, 252])
    assert taken == set()


# ── multiple claimants ──────────────────────────────────────────────────

def test_multiple_infra_nodes_on_one_subnet_are_unique():
    out = a.allocate_infra_ips(DEFAULT, ["192.168.200.1"],
                               [("utility", 78), ("external-dhcp", 77),
                                ("third", 78)])
    assert out["utility"] == "192.168.200.78"
    assert out["external-dhcp"] == "192.168.200.77"
    assert out["third"] == "192.168.200.2"
    assert len(set(out.values())) == 3


def test_multiple_claimants_on_slash26_all_inside():
    taken = [f"100.82.254.{o}" for o in range(129, 161)]
    out = a.allocate_infra_ips(JUPITER, taken, [("a", 78), ("b", 78), ("c", 77)])
    ips = [ipaddress.IPv4Address(v) for v in out.values()]
    assert len(set(ips)) == 3
    assert all(ip in _hosts(JUPITER) for ip in ips)
    assert all(str(ip) not in taken for ip in ips)


# ── explicit-assignment preservation ────────────────────────────────────

def test_explicit_node_assignment_is_never_reused():
    """A server explicitly given .78 keeps it; the infra node moves."""
    taken = a.taken_addresses(DEFAULT, ["192.168.200.78"])
    ip = a.allocate_infra_ip(DEFAULT, taken, 78)
    assert ip != "192.168.200.78"
    assert "192.168.200.78" not in {ip}
    assert ipaddress.IPv4Address("192.168.200.78") in taken


def test_infra_gateway_prefers_declared_else_network_plus_one():
    assert a.infra_gateway(JUPITER, "100.82.254.129") == "100.82.254.129"
    assert a.infra_gateway(JUPITER, None) == "100.82.254.129"
    assert a.infra_gateway(JUPITER, "192.168.200.1") == "100.82.254.129"
    assert a.infra_gateway(DEFAULT, "192.168.200.254") == "192.168.200.254"


# ── exhaustion ──────────────────────────────────────────────────────────

def test_exhausted_subnet_raises_infra_capacity_error():
    taken = [str(h) for h in ipaddress.IPv4Network("10.0.0.0/29").hosts()]
    with pytest.raises(a.InfraCapacityError) as exc:
        a.allocate_infra_ip("10.0.0.0/29", taken, 78, claimant="dhcp-oob")
    err = exc.value
    assert isinstance(err, ValueError)
    assert err.subnet == "10.0.0.0/29"
    assert err.claimant == "dhcp-oob"
    assert err.free_count == 0
    assert "10.0.0.0/29" in str(err) and "dhcp-oob" in str(err)


def test_allocate_infra_ips_is_atomic_on_exhaustion():
    with pytest.raises(a.InfraCapacityError):
        a.allocate_infra_ips("10.0.0.0/30", ["10.0.0.1"],
                             [("a", 78), ("b", 78)])


def test_assert_inside_rejects_the_jupiter_address():
    with pytest.raises(ValueError):
        a.assert_inside(JUPITER, "100.82.254.206", claimant="dhcp-oob")
    assert a.assert_inside(JUPITER, "100.82.254.163") == "100.82.254.163"


# ── registry agreement ──────────────────────────────────────────────────

def test_reserved_registry_does_not_pin_dhcp_oob():
    # The L2 registry must not claim the allocator's preferred slot as a fixed
    # address: a Nodes-tab host on .78 is preserved and dhcp-oob falls through.
    assert a.DHCP_OOB_PREFERRED_OFFSET == 78
    assert 78 not in oob_reserved.OOB_RESERVED_OCTETS_L2
    assert oob_reserved.LEGACY_DHCP_OOB_OCTET == 252
    assert 'dhcp-oob' not in {
        v for k, v in oob_reserved.OOB_RESERVED_OCTETS_L2.items() if k != 252}


def test_node_on_78_in_l2_pushes_dhcp_oob_not_an_error():
    plan = plan_infra_addresses(
        {'oob_mode': 'L2', 'air_mgmt_subnet': '172.20.0.0/24'},
        [{'name': 'oob', 'id': 200, 'vrf': 'OOB', 'subnet': '192.168.200.0/24',
          'gateway': '192.168.200.1'}],
        [{'role': 'OOB Switch', 'name': 'oob-switch-01', 'category': 'oob-switch',
          'index': 0, 'status': 'Active', 'mgmt_ip': '', 'prefix': 24,
          'gateway': '192.168.200.1', 'oob_vlan': '200'},
         {'role': 'GPU Compute', 'name': 'gpu-01', 'category': 'gpu', 'index': 0,
          'status': 'Active', 'mgmt_ip': '192.168.200.78', 'prefix': 24,
          'gateway': '192.168.200.1', 'oob_vlan': '200'}])
    dhcp = plan['oob'][0]['infra']['dhcp-oob']
    assert dhcp != '192.168.200.78'
    infra = [(k, v) for k, v in plan['oob'][0]['infra'].items()]
    assert oob_reserved.find_oob_collisions(
        [('gpu-01', '192.168.200.78')], oob_reserved.oob_reserved_for_mode('l2'),
        subnets=['192.168.200.0/24'], infra_claims=infra) == []


def test_find_oob_collisions_rejects_out_of_subnet_infra_claim():
    with pytest.raises(ValueError, match="not a usable host"):
        oob_reserved.find_oob_collisions(
            [], oob_reserved.oob_reserved_for_mode("l2"),
            subnets=[JUPITER], infra_claims=[("dhcp-oob", "100.82.254.206")])


def test_find_oob_collisions_flags_node_on_infra_address():
    hits = oob_reserved.find_oob_collisions(
        [("gpu-01", "100.82.254.163")], oob_reserved.oob_reserved_for_mode("l2"),
        subnets=[JUPITER], infra_claims=[("dhcp-oob", "100.82.254.163")])
    assert any("100.82.254.163" in str(h) for h in hits)


# ── generator-level planner (fails on the pre-change excel_parser) ──────

def _jupiter_inputs():
    settings = {'oob_mode': 'L2', 'air_mgmt_subnet': '172.20.0.0/24'}
    vlans = [{'name': 'mgmt-subnet-1', 'id': 200, 'vrf': 'OOB', 'subnet': JUPITER,
              'gateway': '100.82.254.129'}]
    nodes = [{'role': 'OOB Switch', 'name': 'oob-switch-01', 'category': 'oob-switch',
              'index': 0, 'status': 'Active', 'mgmt_ip': '', 'prefix': 26,
              'gateway': '100.82.254.129', 'oob_vlan': '200'}]
    for i in range(27):
        nodes.append({'role': 'GPU Compute', 'name': f'gpu-{i + 1:02d}',
                      'category': 'gpu', 'index': i, 'status': 'Active',
                      'mgmt_ip': f'100.82.254.{134 + i}', 'prefix': 26,
                      'gateway': '100.82.254.129', 'oob_vlan': 'mgmt-subnet-1'})
    return settings, vlans, nodes


def test_planner_places_dhcp_oob_inside_slash26():
    settings, vlans, nodes = _jupiter_inputs()
    plan = plan_infra_addresses(settings, vlans, nodes,
                                {'air_mgmt_subnet': '172.20.0.0/24'})
    oob = [p for p in plan['oob'] if p['subnet'] == JUPITER]
    assert oob, plan
    ip = ipaddress.IPv4Address(oob[0]['infra']['dhcp-oob'])
    assert ip in _hosts(JUPITER)
    assert str(ip) not in {n['mgmt_ip'] for n in nodes}
    assert oob[0]['gateway'] == '100.82.254.129'


def test_planner_default_slash24_keeps_78():
    settings = {'oob_mode': 'L2', 'air_mgmt_subnet': '172.20.0.0/24'}
    vlans = [{'name': 'oob', 'id': 200, 'vrf': 'OOB', 'subnet': DEFAULT,
              'gateway': '192.168.200.1'}]
    nodes = [{'role': 'OOB Switch', 'name': 'oob-switch-01', 'category': 'oob-switch',
              'index': 0, 'status': 'Active', 'mgmt_ip': '', 'prefix': 24,
              'gateway': '192.168.200.1', 'oob_vlan': '200'}]
    plan = plan_infra_addresses(settings, vlans, nodes,
                                {'air_mgmt_subnet': '172.20.0.0/24'})
    assert plan['oob'][0]['infra']['dhcp-oob'] == '192.168.200.78'
    assert plan['air_mgmt']['infra']['dhcp-oob'] == '172.20.0.77'
    assert plan['air_mgmt']['gateway'] == '172.20.0.1'


# ── air-mgmt plane: switch eth0 walk + ext-storage on a small subnet ─────

AIR26 = "172.20.0.128/26"


def _air26_inputs(n_switches=6, n_ext=2):
    settings = {'oob_mode': 'L2', 'air_mgmt_subnet': AIR26}
    vlans = [{'name': 'oob', 'id': 200, 'vrf': 'OOB', 'subnet': DEFAULT,
              'gateway': '192.168.200.1'}]
    nodes = [{'role': 'oob-switch', 'name': 'oob-switch-01', 'category': 'oob-switch',
              'index': 0, 'status': 'Active', 'mgmt_ip': '', 'prefix': 24,
              'gateway': '192.168.200.1', 'oob_vlan': '200'}]
    for i in range(n_switches):
        nodes.append({'role': 'core', 'name': f'core-{i + 1:02d}',
                      'category': 'core', 'index': i, 'status': 'Active',
                      'mgmt_ip': f'192.168.200.{10 + i}', 'prefix': 24,
                      'gateway': '192.168.200.1', 'oob_vlan': '200'})
    for i in range(n_ext):
        nodes.append({'role': 'External Storage', 'name': f'ext-storage-{i + 1:02d}',
                      'category': 'ext-storage', 'index': i, 'status': 'Air',
                      'mgmt_ip': f'192.168.200.{40 + i}', 'prefix': 24,
                      'gateway': '192.168.200.1', 'oob_vlan': '200'})
    return settings, vlans, nodes


def test_switch_eth0_walk_stays_inside_slash26_air_mgmt():
    settings, vlans, nodes = _air26_inputs()
    eth0 = excel_parser.air_mgmt_switch_eth0_plan(nodes, AIR26, settings)
    assert len(eth0) == 7  # 6 core + oob-switch
    assert all(ipaddress.IPv4Address(ip) in _hosts(AIR26) for ip in eth0.values())
    assert len(set(eth0.values())) == len(eth0)


def test_switch_eth0_walk_default_slash24_keeps_201_base():
    settings, vlans, nodes = _air26_inputs()
    eth0 = excel_parser.air_mgmt_switch_eth0_plan(nodes, '172.20.0.0/24', settings)
    assert sorted(eth0.values())[0] == '172.20.0.201'


def test_switch_eth0_walk_raises_when_air_mgmt_too_small():
    settings, vlans, nodes = _air26_inputs(n_switches=70)
    with pytest.raises(ValueError, match="too small"):
        excel_parser.air_mgmt_switch_eth0_plan(nodes, AIR26, settings)


def test_planner_places_ext_storage_inside_slash26_air_mgmt():
    settings, vlans, nodes = _air26_inputs()
    plan = plan_infra_addresses(settings, vlans, nodes, {'air_mgmt_subnet': AIR26})
    infra = plan['air_mgmt']['infra']
    assert {'ext-storage-01', 'ext-storage-02'} <= set(infra)
    everything = list(infra.values()) + [plan['air_mgmt']['gateway']]
    assert all(ipaddress.IPv4Address(ip) in _hosts(AIR26) for ip in everything)
    assert len(set(everything)) == len(everything)
    eth0 = set(excel_parser.air_mgmt_switch_eth0_plan(nodes, AIR26, settings).values())
    assert not eth0 & set(everything)


def test_planner_default_slash24_keeps_ext_storage_at_79():
    settings, vlans, nodes = _air26_inputs()
    plan = plan_infra_addresses(settings, vlans, nodes,
                                {'air_mgmt_subnet': '172.20.0.0/24'})
    assert plan['air_mgmt']['infra']['ext-storage-01'] == '172.20.0.79'
    assert plan['air_mgmt']['infra']['ext-storage-02'] == '172.20.0.80'


def _ext_topology(n=2):
    return {"content": {"nodes": {f"ext-storage-{i + 1:02d}": {} for i in range(n)},
                        "links": []}}


def test_discover_ext_storage_uses_planned_eth0():
    from airlib.ext_storage_config import discover_ext_storage_targets
    t = discover_ext_storage_targets(
        _ext_topology(), air_mgmt_subnet=AIR26,
        eth0_ips={'ext-storage-01': '172.20.0.140', 'ext-storage-02': '172.20.0.141'})
    assert [x['eth0_ip'] for x in t] == ['172.20.0.140', '172.20.0.141']


def test_discover_ext_storage_rejects_out_of_subnet_fallback():
    from airlib.ext_storage_config import discover_ext_storage_targets
    with pytest.raises(ValueError, match="not a usable host"):
        discover_ext_storage_targets(_ext_topology(), air_mgmt_subnet=AIR26)
    # default /24 fallback unchanged
    t = discover_ext_storage_targets(_ext_topology(), air_mgmt_subnet='172.20.0.0/24')
    assert [x['eth0_ip'] for x in t] == ['172.20.0.79', '172.20.0.80']


def test_taken_addresses_accepts_any_iterable_including_dict_values():
    eth0 = {'core-01': '172.20.0.130', 'core-02': '172.20.0.131'}
    got = a.taken_addresses(AIR26, eth0.values(), (x for x in [1]))
    assert got == {ipaddress.IPv4Address('172.20.0.129'),
                   ipaddress.IPv4Address('172.20.0.130'),
                   ipaddress.IPv4Address('172.20.0.131')}


# ── validator collision gate seeds the PLANNED gateway, not +1 ──────────

def _gateway_gate_errors(node_ip):
    from validate_excel import ValidationResult, validate_oob_mgmt_ip_collisions
    vlans = [{'id': '200', 'vrf': 'OOB', 'subnet': '10.5.5.0/24',
              'gateway': '10.5.5.100'}]
    nodes = [{'name': 'oob-switch-01', 'function': 'OOB Switch', 'ip': '',
              'prefix': 24, 'gateway': '10.5.5.100', 'oob_vlan': '200', 'row': 2},
             {'name': 'gpu-01', 'function': 'GPU Compute', 'ip': node_ip,
              'prefix': 24, 'gateway': '10.5.5.100', 'oob_vlan': '200', 'row': 3}]
    r = ValidationResult()
    validate_oob_mgmt_ip_collisions(
        nodes, r, settings={'oob_uplink_mode': 'l2'},
        oob_subnets=['10.5.5.0/24'], parsed_vlans=vlans)
    return [e for e in r.errors if 'multiple owners' in e]


def test_gate_flags_node_on_declared_gateway_not_on_plus_one():
    """A declared gateway elsewhere in the subnet is the protected address;
    network+1 is then an ordinary host and must not be false-flagged."""
    assert _gateway_gate_errors('10.5.5.100'), "node on the declared gateway passed"
    assert not _gateway_gate_errors('10.5.5.1'), "network+1 false-flagged"


# ── DHCP pool: subnet-aware dnsmasq range (review round 4) ───────────────

def test_dhcp_pool_slash24_keeps_100_200():
    assert a.dhcp_pool(DEFAULT, ["192.168.200.101"]) == (
        "192.168.200.100", "192.168.200.200")


def test_dhcp_pool_slash26_stays_inside_and_avoids_claims():
    taken = [f"100.82.254.{o}" for o in range(129, 161)] + ["100.82.254.163"]
    lo, hi = a.dhcp_pool(JUPITER, taken)
    lo_a, hi_a = ipaddress.IPv4Address(lo), ipaddress.IPv4Address(hi)
    assert lo_a in _hosts(JUPITER) and hi_a in _hosts(JUPITER)
    assert lo_a <= hi_a
    held = a.taken_addresses(JUPITER, taken)
    assert not any(lo_a <= h <= hi_a for h in held)
    assert (lo, hi) == ("100.82.254.164", "100.82.254.190")


def test_dhcp_pool_full_subnet_is_capacity_error():
    with pytest.raises(a.InfraCapacityError):
        a.dhcp_pool("10.0.0.0/30", ["10.0.0.1", "10.0.0.2"])


def _air_plane(settings, vlans, nodes):
    return plan_infra_addresses(settings, vlans, nodes,
                                {'air_mgmt_subnet': settings['air_mgmt_subnet']})['air_mgmt']


def test_planner_air_mgmt_pool_excludes_gateway_and_infra_on_slash26():
    settings, vlans, nodes = _air26_inputs(n_switches=50)
    for mode in ('L2', 'L3'):
        settings['oob_uplink_mode'] = mode
        plane = _air_plane(settings, vlans, nodes)
        lo, hi = (ipaddress.IPv4Address(x) for x in plane['dhcp_pool'])
        assert lo in _hosts(AIR26) and hi in _hosts(AIR26) and lo <= hi
        for claimed in [plane['gateway'], *plane['infra'].values()]:
            assert not lo <= ipaddress.IPv4Address(claimed) <= hi, (mode, claimed)


def test_planner_air_mgmt_pool_raises_when_only_gateway_would_be_free():
    # 55 core + oob-switch = .130-.185, .129 keep-out, gateway .186, L3 trio +
    # two ext-storage take .187-.190: every usable host is claimed.
    settings, vlans, nodes = _air26_inputs(n_switches=55)
    settings['oob_uplink_mode'] = 'L3'
    with pytest.raises(a.InfraCapacityError, match="DHCP pool"):
        _air_plane(settings, vlans, nodes)


def test_planner_emits_dhcp_pool_inside_slash26():
    settings, vlans, nodes = _jupiter_inputs()
    plan = plan_infra_addresses(settings, vlans, nodes,
                                {'air_mgmt_subnet': '172.20.0.0/24'})
    lo, hi = plan['oob'][0]['dhcp_pool']
    hosts = _hosts(JUPITER)
    assert ipaddress.IPv4Address(lo) in hosts and ipaddress.IPv4Address(hi) in hosts
    node_ips = {n['mgmt_ip'] for n in nodes}
    dhcp_oob = plan['oob'][0]['infra']['dhcp-oob']
    for h in ipaddress.summarize_address_range(
            ipaddress.IPv4Address(lo), ipaddress.IPv4Address(hi)):
        for addr in h:
            assert str(addr) not in node_ips and str(addr) != dhcp_oob
    assert plan['air_mgmt']['dhcp_pool'] == ('172.20.0.100', '172.20.0.200')


def _render_dnsmasq(ztp_interfaces):
    import re
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    tdir = Path(__file__).parent.parent / "roles" / "ztp-server" / "templates"
    env = Environment(loader=FileSystemLoader(str(tdir)), undefined=StrictUndefined,
                      extensions=["jinja2.ext.do"])
    env.filters["regex_replace"] = lambda v, p, r: re.sub(p, r, str(v))
    return env.get_template("dnsmasq.conf.j2").render(
        ztp_interfaces=ztp_interfaces, cumulus_target_release="5.15.0")


def test_dnsmasq_template_renders_in_subnet_range_for_jupiter():
    """The REAL template, fed the generator's ztp_interfaces for the /26."""
    settings, vlans, nodes = _jupiter_inputs()
    plan = plan_infra_addresses(settings, vlans, nodes,
                                {'air_mgmt_subnet': '172.20.0.0/24'})
    plane = plan['oob'][0]
    iface = {'name': 'eth2', 'ip': plane['infra']['dhcp-oob'], 'network': JUPITER,
             'gateway': plane['gateway'], 'purpose': 'mgmt-subnet-1',
             'dnsmasq_listen': True,
             'dhcp_range_start': plane['dhcp_pool'][0],
             'dhcp_range_end': plane['dhcp_pool'][1]}
    out = _render_dnsmasq([iface])
    line = next(ln for ln in out.splitlines() if ln.startswith("dhcp-range=interface:eth2"))
    _, lo, hi, _lease = line.split(",")
    hosts = _hosts(JUPITER)
    assert ipaddress.IPv4Address(lo) in hosts, line
    assert ipaddress.IPv4Address(hi) in hosts, line
    assert "100.82.254.100" not in out and "100.82.254.200" not in out


def test_dnsmasq_template_legacy_iface_keeps_100_200():
    """Inventories generated before the pool keys existed still render as before."""
    out = _render_dnsmasq([{'name': 'eth2', 'ip': '192.168.200.78', 'network': DEFAULT,
                            'gateway': '192.168.200.1', 'purpose': 'mgmt-subnet-1',
                            'dnsmasq_listen': True}])
    assert "dhcp-range=interface:eth2,192.168.200.100,192.168.200.200,12h" in out


# ── air-deploy boot commands: air-mgmt prefix, not /24 or the OOB prefix ─

def _load_air_deploy():
    import importlib.util
    spec = importlib.util.spec_from_file_location("air_deploy_era134", SCRIPTS_DIR / "air-deploy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _apply_script(commands):
    import base64
    import re
    line = next(c for c in commands if "> /opt/era/apply.sh" in c and "base64 -d" in c)
    return base64.b64decode(re.search(r"echo '([^']+)'", line).group(1)).decode()


def test_switch_ni_commands_use_air_mgmt_prefix():
    ad = _load_air_deploy()
    ad.set_oob_plane(DEFAULT, "192.168.200.1")
    ad.set_air_mgmt_subnet(AIR26)
    script = _apply_script(ad.build_switch_ni_commands("core-01", "nv set x", "172.20.0.140", "pw"))
    assert "nv set interface eth0 ipv4 address 172.20.0.140/26" in script
    assert "ip addr replace 172.20.0.140/26 dev eth0" in script
    assert "172.20.0.140/24" not in script
    ad.set_air_mgmt_subnet("172.20.0.0/24")
    script = _apply_script(ad.build_switch_ni_commands("core-01", "nv set x", "172.20.0.201", "pw"))
    assert "nv set interface eth0 ipv4 address 172.20.0.201/24" in script
    assert "ip addr replace 172.20.0.201/24 dev eth0" in script


def test_air_mgmt_prefixlen_differs_from_oob_prefix():
    ad = _load_air_deploy()
    ad.set_oob_plane(JUPITER, "100.82.254.129")
    ad.set_air_mgmt_subnet(AIR26)
    assert ad.oob_prefixlen() == 26 and ad.air_mgmt_prefixlen() == 26
    ad.set_oob_plane(DEFAULT, "192.168.200.1")
    assert ad.oob_prefixlen() == 24 and ad.air_mgmt_prefixlen() == 26
