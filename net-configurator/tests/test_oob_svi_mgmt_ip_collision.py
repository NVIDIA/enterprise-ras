# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Switch SVIs and Nodes-tab management IPs must not collide on the OOB VLAN.

Two independent walks share the OOB subnet and used to advance head-on:

* OOB switch SVIs walked UP from the 1st host (``.2`` on a ``.0``-aligned /24);
* Nodes-tab management IPs walk UP from the 9th (``.10``).

So the 9th switch onward landed on a real host's eth0. Four largescale sites
each shipped 8 duplicates — ``cl-01``'s eth0 and ``oob-switch-09``'s SVI were
both ``192.168.200.10``. A duplicate on the OOB VLAN is an ARP/DAD war and
~60% packet loss to the colliding host.

The duplicate-mgmt-IP gate could not see it: it claims only Nodes-tab rows, and
switch SVIs are GENERATED. A gate blind to half the addresses on the plane
reads as a pass, which is why this shipped since at least v6.
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from excel_parser import _oob_switch_svi_ip, _OOB_SVI_LOW_SLOTS  # noqa: E402
from validate_excel import (ValidationResult,  # noqa: E402
                            validate_oob_mgmt_ip_collisions)
from oob_reserved import (find_oob_collisions,  # noqa: E402
                          oob_reserved_for_mode, OOB_RESERVED_OCTETS)

SUBNET = "192.168.200.0/24"
# The fabric switches whose eth0 the old walk ran into, at .10 onward.
NODE_ROWS = [(f"cl-{i + 1:02d} (row {i})", f"192.168.200.{10 + i}") for i in range(8)]


def _svi_claims(count):
    return [(f"oob-switch-{i + 1:02d} SVI (generated)",
             _oob_switch_svi_ip("192.168.200", 0, i, 24)) for i in range(count)]


def test_first_eight_svis_keep_their_historical_addresses():
    """Every site at or under 8 OOB switches must regenerate byte-identically."""
    assert [ip for _, ip in _svi_claims(8)] == [
        f"192.168.200.{2 + i}" for i in range(8)]


def test_ninth_switch_does_not_land_on_a_node_address():
    """The 9th SVI used to be .10 — cl-01's eth0."""
    assert _oob_switch_svi_ip("192.168.200", 0, _OOB_SVI_LOW_SLOTS, 24) != "192.168.200.10"


def test_sixteen_svis_do_not_collide_with_node_mgmt_ips():
    collisions = list(find_oob_collisions(
        _svi_claims(16) + NODE_ROWS, oob_reserved_for_mode("l3"), subnets=[SUBNET]))
    assert not collisions, f"SVI/node collisions: {collisions}"


def test_svis_never_land_on_a_reserved_service_octet():
    """dhcp-oob (.252), the air-mgmt SVI (.254) and the L3 trio are spoken for."""
    reserved = {f"192.168.200.{o}" for o in OOB_RESERVED_OCTETS}
    assert not (set(ip for _, ip in _svi_claims(20)) & reserved)


def test_svis_are_unique():
    ips = [ip for _, ip in _svi_claims(20)]
    assert len(set(ips)) == len(ips)


def test_the_old_linear_walk_would_still_be_caught():
    """Guard the guard.

    If someone reverts to the linear walk, the gate must fail loudly rather
    than pass in silence the way it did before switch SVIs were claimed.
    """
    old = [(f"oob-switch-{i + 1:02d} SVI (generated)", f"192.168.200.{2 + i}")
           for i in range(16)]
    collisions = list(find_oob_collisions(
        old + NODE_ROWS, oob_reserved_for_mode("l3"), subnets=[SUBNET]))
    assert len(collisions) == 8, (
        "the linear walk must be detected as 8 collisions; the gate is blind again")


# --- the gate itself, end to end -------------------------------------------
# The tests above drive find_oob_collisions() with hand-built claims, so they
# pin the ALLOCATOR but say nothing about whether validate_excel actually
# claims the generated SVIs. Deleting that claim loop left every test above
# green — the same blind spot that let this ship. These exercise the real
# validator entry point instead.

def _nodes(*ips):
    return [{'name': f'sw-{i}', 'function': 'OOB Switch', 'ip': ip, 'row': i + 2}
            for i, ip in enumerate(ips)]


def _oob_switch_nodes(n):
    """n OOB switches on the Nodes tab, with mgmt IPs that cannot themselves clash."""
    return [{'name': f'oob-switch-{i + 1:02d}', 'function': 'OOB Switch',
             'ip': f'192.168.200.{40 + i}', 'row': i + 2} for i in range(n)]


def test_validator_claims_generated_svis():
    """A host parked on the 9th switch's SVI must be reported by the real gate.

    With 9 OOB switches the 9th SVI is allocated from the top of the subnet.
    A Nodes-tab host sitting on that address is a genuine duplicate, and the
    gate only sees it because validate_excel claims the generated SVIs.
    """
    ninth = _oob_switch_svi_ip('192.168.200', 0, _OOB_SVI_LOW_SLOTS, 24)
    nodes = _oob_switch_nodes(9) + [
        {'name': 'intruder', 'function': 'Support', 'ip': ninth, 'row': 99}]
    r = ValidationResult()
    validate_oob_mgmt_ip_collisions(nodes, r, settings={'oob_uplink_mode': 'l3'},
                                    oob_subnets=['192.168.200.0/24'])
    assert any(ninth in e for e in r.errors), (
        f"gate did not flag {ninth}; it is blind to generated SVIs again. "
        f"errors={r.errors}")


def test_validator_is_quiet_when_nothing_collides():
    """The gate must not cry wolf on a clean site."""
    r = ValidationResult()
    validate_oob_mgmt_ip_collisions(_oob_switch_nodes(9), r,
                                    settings={'oob_uplink_mode': 'l3'},
                                    oob_subnets=['192.168.200.0/24'])
    assert not r.errors, r.errors


# --- multi-OOB-subnet attribution -------------------------------------------
# The generator indexes SVIs PER SUBNET (`per_subnet_index`). Claiming a global
# switch count against every subnet invents phantom SVIs in the high block and
# fails a legitimate workbook on a collision that does not exist. Caught in
# review on !264; these pin the attribution.

_TWO_VLANS = [{'id': '200', 'vrf': 'OOB', 'subnet': '192.168.200.0/24'},
              {'id': '201', 'vrf': 'OOB', 'subnet': '192.168.201.0/24'}]


def _split_switches(per_subnet=6):
    """`per_subnet` OOB switches on each of two OOB VLANs."""
    out = []
    for i in range(per_subnet):
        out.append({'name': f'oob-switch-{i + 1:02d}', 'function': 'oob-switch',
                    'ip': f'192.168.200.{60 + i}', 'row': i + 2, 'oob_vlan': '200'})
    for i in range(per_subnet):
        out.append({'name': f'oob-switch-{i + per_subnet + 1:02d}',
                    'function': 'oob-switch',
                    'ip': f'192.168.201.{60 + i}', 'row': i + 20, 'oob_vlan': '201'})
    return out


def _run(nodes):
    r = ValidationResult()
    validate_oob_mgmt_ip_collisions(
        nodes, r, settings={'oob_uplink_mode': 'l3'},
        oob_subnets=['192.168.200.0/24', '192.168.201.0/24'],
        parsed_vlans=_TWO_VLANS)
    return r


def test_multi_subnet_does_not_invent_phantom_svis():
    """12 switches split 6/6 use idx 0-5 per subnet, so the high block is free.

    Claiming all 12 against BOTH subnets put phantom SVIs on .253/.251/... and
    failed the build against hosts legitimately parked there.
    """
    nodes = _split_switches(6) + [
        {'name': 'host-a', 'function': 'Support', 'ip': '192.168.200.253', 'row': 50},
        {'name': 'host-b', 'function': 'Support', 'ip': '192.168.201.253', 'row': 51}]
    assert not _run(nodes).errors, _run(nodes).errors


def test_multi_subnet_still_catches_a_real_collision():
    """Guard against fixing the false positive by disabling the check."""
    nodes = _split_switches(6) + [
        {'name': 'intruder', 'function': 'Support', 'ip': '192.168.200.2', 'row': 60}]
    errs = _run(nodes).errors
    assert any('192.168.200.2' in e for e in errs), errs
