# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Unit tests for scripts/oob_reserved.py — the canonical reserved-IP registry
for the flat OOB management subnet and the mgmt-IP collision detector.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from oob_reserved import (
    OOB_RESERVED_OCTETS,
    OOB_RESERVED_OCTETS_L2,
    AIR_MGMT_RESERVED_OCTETS,
    DEFAULT_AIR_MGMT_SUBNET,
    UTILITY_OCTET,
    oob_octet,
    find_oob_collisions,
    oob_reserved_for_mode,
    air_mgmt_intruders,
)


class TestReservedSets:
    def test_air_mgmt_is_subset_of_oob(self):
        assert AIR_MGMT_RESERVED_OCTETS <= set(OOB_RESERVED_OCTETS)

    def test_utility_octet_is_78_and_reserved(self):
        # The 2026-06-24 maxscale collision was on .78 (utility jump).
        assert UTILITY_OCTET == 78
        assert 78 in OOB_RESERVED_OCTETS
        assert 78 in AIR_MGMT_RESERVED_OCTETS

    def test_oob_reserved_matches_generator_skip_set(self):
        # Must equal generate_arch_excel.py's historical _RESERVED_OCTETS so
        # default-scale Nodes tabs regenerate byte-identically.
        assert set(OOB_RESERVED_OCTETS) == {0, 1, 77, 78, 79, 100, 252, 254, 255}

    def test_air_mgmt_matches_parser_skip_set(self):
        # Must equal excel_parser.py's historical _AIR_MGMT_RESERVED so switch
        # eth0 IPs on the 172.20.0.x plane stay byte-identical.
        assert AIR_MGMT_RESERVED_OCTETS == {0, 1, 77, 78, 254, 255}


class TestOobOctet:
    def test_in_subnet_plain(self):
        assert oob_octet("192.168.200.78") == 78

    def test_in_subnet_with_cidr(self):
        assert oob_octet("192.168.200.150/24") == 150

    def test_out_of_subnet_returns_none(self):
        assert oob_octet("172.20.0.78") is None
        assert oob_octet("10.0.0.5") is None

    def test_malformed_returns_none(self):
        assert oob_octet("not-an-ip") is None
        assert oob_octet("192.168.200") is None

    def test_empty_returns_none(self):
        assert oob_octet("") is None
        assert oob_octet(None) is None


class TestFindCollisions:
    def test_no_collisions_clean(self):
        claims = [
            ("gpu-01 (row 5)", "192.168.200.10"),
            ("gpu-02 (row 6)", "192.168.200.11"),
        ]
        assert find_oob_collisions(claims) == []

    def test_node_lands_on_reserved_utility_octet(self):
        claims = [("su-09-node-03 (row 42)", "192.168.200.78")]
        collisions = find_oob_collisions(claims)
        assert len(collisions) == 1
        octet, owners = collisions[0]
        assert octet == 78
        assert "su-09-node-03 (row 42)" in owners
        assert any("utility" in o for o in owners)

    def test_two_nodes_same_octet(self):
        claims = [
            ("gpu-01 (row 5)", "192.168.200.50"),
            ("gpu-02 (row 6)", "192.168.200.50"),
        ]
        collisions = find_oob_collisions(claims)
        assert len(collisions) == 1
        octet, owners = collisions[0]
        assert octet == 50
        assert "gpu-01 (row 5)" in owners and "gpu-02 (row 6)" in owners

    def test_out_of_subnet_ignored(self):
        # A node on a different mgmt subnet never collides on the OOB /24.
        claims = [("server (row 9)", "172.20.0.78")]
        assert find_oob_collisions(claims) == []

    def test_reserved_alone_not_flagged(self):
        # No node claims; reserved owners alone must not be reported.
        assert find_oob_collisions([]) == []


class TestModeAwareReserved:
    def test_l3_reserves_exit_vrf_trio(self):
        for octet in (77, 78, 79):
            assert octet in OOB_RESERVED_OCTETS

    def test_l2_does_not_reserve_exit_vrf_trio(self):
        # In L2 mode external-dhcp/utility/external-conn don't exist.
        for octet in (77, 78, 79, 100):
            assert octet not in OOB_RESERVED_OCTETS_L2

    def test_l2_still_reserves_gateway_and_dhcp_oob(self):
        assert 1 in OOB_RESERVED_OCTETS_L2      # gateway / oob-server-01
        assert 252 in OOB_RESERVED_OCTETS_L2    # dhcp-oob

    def test_mode_selector(self):
        assert oob_reserved_for_mode('l3') is OOB_RESERVED_OCTETS
        assert oob_reserved_for_mode('L3') is OOB_RESERVED_OCTETS
        assert oob_reserved_for_mode('l2') is OOB_RESERVED_OCTETS_L2
        # None/blank/unknown default to L2 (the system default).
        assert oob_reserved_for_mode(None) is OOB_RESERVED_OCTETS_L2
        assert oob_reserved_for_mode('') is OOB_RESERVED_OCTETS_L2
        assert oob_reserved_for_mode('bogus') is OOB_RESERVED_OCTETS_L2

    def test_node_on_78_flagged_in_l3_only(self):
        claims = [("server (row 9)", "192.168.200.78")]
        # L3: collides with utility.
        assert find_oob_collisions(claims, oob_reserved_for_mode('l3'))
        # L2: .78 is free — no false positive.
        assert find_oob_collisions(claims, oob_reserved_for_mode('l2')) == []

    def test_node_on_252_flagged_in_both_modes(self):
        claims = [("server (row 9)", "192.168.200.252")]
        assert find_oob_collisions(claims, oob_reserved_for_mode('l3'))
        assert find_oob_collisions(claims, oob_reserved_for_mode('l2'))


class TestAirMgmtIntruders:
    def test_node_on_air_mgmt_is_flagged(self):
        claims = [("gpu-01 (row 5)", "172.20.0.50")]
        out = air_mgmt_intruders(claims, DEFAULT_AIR_MGMT_SUBNET)
        assert out == [("gpu-01 (row 5)", "172.20.0.50")]

    def test_node_collides_with_switch_eth0_range(self):
        # .201 is in the historical switch-eth0 walk range — operator can't see it.
        claims = [("server (row 9)", "172.20.0.201")]
        assert air_mgmt_intruders(claims, DEFAULT_AIR_MGMT_SUBNET)

    def test_oob_plane_node_not_flagged(self):
        claims = [("gpu-01 (row 5)", "192.168.200.10")]
        assert air_mgmt_intruders(claims, DEFAULT_AIR_MGMT_SUBNET) == []

    def test_respects_custom_air_mgmt_subnet(self):
        claims = [("gpu-01 (row 5)", "10.99.0.5")]
        assert air_mgmt_intruders(claims, "10.99.0.0/24")
        assert air_mgmt_intruders(claims, DEFAULT_AIR_MGMT_SUBNET) == []

    def test_blank_or_bad_subnet_is_noop(self):
        claims = [("gpu-01 (row 5)", "172.20.0.50")]
        assert air_mgmt_intruders(claims, "") == []
        assert air_mgmt_intruders(claims, None) == []
        assert air_mgmt_intruders(claims, "not-a-cidr") == []

    def test_cidr_suffix_on_node_ip_handled(self):
        claims = [("gpu-01 (row 5)", "172.20.0.50/24")]
        assert air_mgmt_intruders(claims, DEFAULT_AIR_MGMT_SUBNET)


class TestValidateExcelGateWiring:
    """The pure helper is wired into validate_excel as a hard error gate."""

    def _run(self, parsed_nodes, settings=None):
        from validate_excel import (
            validate_oob_mgmt_ip_collisions,
            ValidationResult,
        )
        result = ValidationResult()
        validate_oob_mgmt_ip_collisions(parsed_nodes, result, settings=settings)
        return result

    def test_clean_nodes_no_error(self):
        nodes = [
            {'function': 'gpu', 'name': 'gpu-01', 'row': 5, 'ip': '192.168.200.10'},
            {'function': 'gpu', 'name': 'gpu-02', 'row': 6, 'ip': '192.168.200.11'},
        ]
        assert self._run(nodes).ok

    def test_l2_node_on_78_is_not_flagged(self):
        # Default mode is L2 → .78 is free, no false positive.
        nodes = [
            {'function': 'support', 'name': 'su-09-node-03', 'row': 42,
             'ip': '192.168.200.78'},
        ]
        assert self._run(nodes, settings={'oob_uplink_mode': 'l2'}).ok
        # No setting at all → also defaults to L2.
        assert self._run(nodes).ok

    def test_l3_node_on_78_is_error(self):
        nodes = [
            {'function': 'support', 'name': 'su-09-node-03', 'row': 42,
             'ip': '192.168.200.78'},
        ]
        result = self._run(nodes, settings={'oob_uplink_mode': 'l3'})
        assert not result.ok
        assert any('192.168.200.78' in e for e in result.errors)

    def test_two_servers_same_ip_is_error(self):
        nodes = [
            {'function': 'gpu', 'name': 'gpu-01', 'row': 5, 'ip': '192.168.200.50'},
            {'function': 'gpu', 'name': 'gpu-02', 'row': 6, 'ip': '192.168.200.50'},
        ]
        assert not self._run(nodes).ok

    def test_nodes_off_both_planes_no_error(self):
        nodes = [
            {'function': 'gpu', 'name': 'gpu-01', 'row': 5, 'ip': '10.1.2.10'},
            {'function': 'gpu', 'name': 'gpu-02', 'row': 6, 'ip': '10.1.2.11'},
        ]
        # Unrelated subnet — neither plane's gate applies.
        assert self._run(nodes).ok

    def test_node_strays_into_air_mgmt_is_error(self):
        nodes = [
            {'function': 'gpu', 'name': 'gpu-01', 'row': 5, 'ip': '172.20.0.50'},
        ]
        result = self._run(nodes)
        assert not result.ok
        assert any('air-mgmt subnet' in e for e in result.errors)

    def test_air_mgmt_check_respects_settings_subnet(self):
        nodes = [
            {'function': 'gpu', 'name': 'gpu-01', 'row': 5, 'ip': '10.50.0.9'},
        ]
        assert not self._run(nodes, settings={'air_mgmt_subnet': '10.50.0.0/24'}).ok
        # Default air-mgmt subnet — 10.50.0.9 is harmless.
        assert self._run(nodes).ok
