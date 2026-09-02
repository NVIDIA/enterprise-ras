# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-42: server data-plane host IPs must be allocated INSIDE the declared VLAN
subnet (real prefix + network offset), not a hardcoded `{base}.{offset}/24`.
Observed in the field: Support VLAN 100.82.255.128/27 -> hosts were assigned .101/24,
outside the subnet -> unreachable.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from excel_parser import _dataplane_host_ips  # noqa: E402


class TestSlash24ByteIdentical:
    """/24 subnets keep the legacy octet offsets (existing output unchanged)."""

    def test_compute_bond_slash24(self):
        # legacy: {base}.201/24 for node 0, .202 for node 1
        assert _dataplane_host_ips('172.16.178.0/24', 0, 1, 201, 1) == ['172.16.178.201/24']
        assert _dataplane_host_ips('172.16.178.0/24', 1, 1, 201, 1) == ['172.16.178.202/24']

    def test_storage_pair_slash24(self):
        # legacy: .101/.102 for node 0, .103/.104 for node 1
        assert _dataplane_host_ips('172.16.180.0/24', 0, 2, 101, 2) == \
            ['172.16.180.101/24', '172.16.180.102/24']
        assert _dataplane_host_ips('172.16.180.0/24', 1, 2, 101, 2) == \
            ['172.16.180.103/24', '172.16.180.104/24']

    def test_gpu_multi_slash24(self):
        assert _dataplane_host_ips('192.168.110.0/24', 0, 3, 201, 3) == \
            ['192.168.110.201/24', '192.168.110.202/24', '192.168.110.203/24']


class TestNonSlash24PacksInsideSubnet:
    def test_field_support_slash27(self):
        # 100.82.255.128/27: gateway .129 (net+1); hosts pack from net+2
        assert _dataplane_host_ips('100.82.255.128/27', 0, 2, 101, 2) == \
            ['100.82.255.130/27', '100.82.255.131/27']
        assert _dataplane_host_ips('100.82.255.128/27', 1, 2, 101, 2) == \
            ['100.82.255.132/27', '100.82.255.133/27']

    def test_slash25_offset_network(self):
        # 10.20.30.128/25 (non-.0 network): stays inside .128-.255
        ips = _dataplane_host_ips('10.20.30.128/25', 0, 1, 201, 1)
        assert ips == ['10.20.30.130/25']

    def test_returns_none_when_it_does_not_fit(self):
        # a /30 (2 usable) can't hold a 2-address bond pair
        assert _dataplane_host_ips('10.0.0.0/30', 0, 2, 101, 2) is None

    def test_empty_or_bad_subnet_is_none(self):
        assert _dataplane_host_ips('', 0, 1, 201, 1) is None
        assert _dataplane_host_ips('not-a-subnet', 0, 1, 201, 1) is None


# --- ERA-42 "validate node count fits" (non-/24 data-plane subnets) ---
from validate_excel import (ValidationResult,  # noqa: E402
                            validate_dataplane_subnet_capacity)


def _servers(function, n):
    return [{'function': function, 'name': f'{function}-{i}',
             'enabled': True, 'is_air_documentary': False} for i in range(n)]


class TestDataplaneCapacityValidation:
    def test_small_support_subnet_errors(self):
        # 3 support servers = 6 addrs; a /29 (2 usable after gw) can't hold them
        nodes = _servers('support', 3)
        vlans = [{'name': 'Support', 'subnet': '172.16.179.0/29'}]
        r = ValidationResult()
        validate_dataplane_subnet_capacity(nodes, vlans, r)
        assert any('holds only' in e and 'of 3 server' in e for e in r.errors), r.errors

    def test_shortfall_message_names_the_number_left_unaddressed(self):
        """"Too small" did not say how short. The count is the actionable part."""
        nodes = _servers('support', 3)
        vlans = [{'name': 'Support', 'subnet': '172.16.179.0/29'}]
        r = ValidationResult()
        validate_dataplane_subnet_capacity(nodes, vlans, r)
        msg = next(e for e in r.errors if 'holds only' in e)
        assert 'get NO' in msg, msg

    def test_fitting_non_slash24_no_error(self):
        # 3 support servers fit a /27 (30 usable)
        nodes = _servers('support', 3)
        vlans = [{'name': 'Support', 'subnet': '172.16.179.128/27'}]
        r = ValidationResult()
        validate_dataplane_subnet_capacity(nodes, vlans, r)
        assert not any('holds only' in e for e in r.errors)

    def test_slash24_gets_no_special_case(self):
        """A /24 that genuinely cannot fit errors like any other prefix.

        This used to `continue` on /24, which is what hid the real bug: the
        allocator's legacy `.201` base left 54 usable slots, so four shipped
        largescale workbooks addressed ~half their compute nodes while
        `validate_excel` printed "No errors found". 200 support servers need
        400 addresses and do not fit a /24 even repacked from the bottom, so
        this is a true capacity error now.
        """
        nodes = _servers('support', 200)
        vlans = [{'name': 'Support', 'subnet': '172.16.179.0/24'}]
        r = ValidationResult()
        validate_dataplane_subnet_capacity(nodes, vlans, r)
        assert any('holds only' in e and 'of 200 server' in e
                   for e in r.errors), r.errors

    def test_slash24_repacks_rather_than_dropping_nodes(self):
        """128 compute nodes fit a /24 — the old .201 base is what did not.

        Regression guard for the four largescale references. `.201 + 127`
        overflows, but only .0 and .1 sit below .201, so repacking from the
        bottom seats all 128 with room to spare.
        """
        from excel_parser import _dataplane_host_ips
        ips = [_dataplane_host_ips('172.16.178.0/24', i, 1, 201, 1, total=128)
               for i in range(128)]
        assert all(x is not None for x in ips), "some nodes got no address"
        assert len({x[0] for x in ips}) == 128, "addresses are not unique"

    def test_support_pool_counts_k8s_and_bcme(self):
        """'support', 'k8s' and 'bcme' share ONE address pool.

        The repack guard needs the size of the POOL, not of one role name. A
        pre-count that bucketed only the literal 'support' role handed the
        allocator a total three times too small here: it concluded the legacy
        .101 base fit, and 13 of 90 nodes silently got no address — the same
        failure this module exists to prevent. Caught in review on MR !262.
        """
        from excel_parser import build_devices
        nodes = []
        for role, n in (('support', 30), ('k8s', 30), ('bcme', 30)):
            for i in range(n):
                nodes.append({'name': f'{role}-{i + 1:02d}', 'role': role,
                              'status': 'Active',
                              'mgmt_ip': f'192.168.200.{i + 10}',
                              'mac': f'02:00:00:00:{i:02x}:{n:02x}'})
        vlans = [{'name': 'Support', 'subnet': '172.16.179.0/24',
                  'gateway': '172.16.179.1'},
                 {'name': 'CPU/In-Band', 'subnet': '172.16.178.0/24',
                  'gateway': '172.16.178.1'}]
        devices = build_devices(nodes, vlans)
        pool = [v for v in devices.values()
                if v.get('role') in ('support', 'k8s', 'bcme')]
        assert len(pool) == 90, len(pool)
        addressed = [v for v in pool if v.get('bond_ip1')]
        assert len(addressed) == 90, (
            f"{90 - len(addressed)} pool node(s) got no address — the "
            f"pre-count is undercounting the shared pool again")
        assert len({v['bond_ip1'] for v in addressed}) == 90, "duplicate addresses"

    def test_role_alloc_pool_matches_the_allocation_branches(self):
        """The pool table is the single source of the grouping.

        validate_excel.py's `checks` list encodes the same one. If a new role
        joins an existing pool in the main loop and not here, `total` silently
        undercounts, so assert the mapping rather than trusting the comment.
        """
        from excel_parser import _ROLE_ALLOC_POOL
        assert _ROLE_ALLOC_POOL['support'] == 'support'
        assert _ROLE_ALLOC_POOL['k8s'] == 'support'
        assert _ROLE_ALLOC_POOL['bcme'] == 'support'
        assert _ROLE_ALLOC_POOL['compute'] == 'compute'
        assert _ROLE_ALLOC_POOL['storage'] == 'storage'

    def test_slash24_that_fits_keeps_the_legacy_base(self):
        """Small and default sites must stay byte-identical."""
        from excel_parser import _dataplane_host_ips
        assert _dataplane_host_ips('172.16.178.0/24', 0, 1, 201, 1,
                                   total=8) == ['172.16.178.201/24']

    def test_slash24_that_fits_is_silent(self):
        """The warning must not fire on a /24 that genuinely holds everyone."""
        nodes = _servers('support', 3)
        vlans = [{'name': 'Support', 'subnet': '172.16.179.0/24'}]
        r = ValidationResult()
        validate_dataplane_subnet_capacity(nodes, vlans, r)
        assert not any('holds only' in m
                       for m in list(r.errors) + list(r.warnings))
