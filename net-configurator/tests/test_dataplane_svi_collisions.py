# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
ERA-93 / ADR-0058 — a server data-plane IP must never equal a fabric address.

ADR-0058 fixed the ALLOCATOR (hosts pack above the gateway AND one address per
SVI-bearing switch). Nothing CHECKED it, which is why ERA-92 cost a day: on a
Support VLAN 10.78.220.32/27 the cores' SVIs were .34/.35, k8s-01 was allocated
exactly those, the gateway .33 never ARPed, and the support data plane was dead
while every validator reported green.

These tests pin the detector against the real ERA-92 numbers, in both the
pre-fix (reserved=2) and post-fix (reserved=4) allocations, so the gate is
demonstrably able to FAIL — the property ERA-93 says these instruments lacked.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from excel_parser import _dataplane_host_ips  # noqa: E402
from validate_excel import (  # noqa: E402
    fabric_claimed_ips,
    find_dataplane_svi_collisions,
    validate_dataplane_svi_collisions,
)

ERA92_SUBNET = "10.78.220.32/27"
ERA92_GATEWAY = "10.78.220.33"


class _Result:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, sheet, msg):
        self.errors.append((sheet, msg))

    def warn(self, sheet, msg):
        self.warnings.append((sheet, msg))


class TestFabricClaimedIps:
    def test_gateway_and_two_core_svis_on_the_era92_subnet(self):
        claimed = fabric_claimed_ips(ERA92_SUBNET, ERA92_GATEWAY, 2)
        assert claimed["10.78.220.33"] == "VRR / anycast gateway"
        assert claimed["10.78.220.34"] == "switch SVI (core-01)"
        assert claimed["10.78.220.35"] == "switch SVI (core-02)"

    def test_legacy_slash24_layout(self):
        claimed = fabric_claimed_ips("172.16.178.0/24", "172.16.178.1", 2)
        assert claimed["172.16.178.1"] == "VRR / anycast gateway"
        assert claimed["172.16.178.2"] == "switch SVI (core-01)"
        assert claimed["172.16.178.3"] == "switch SVI (core-02)"


class TestDetectorFiresOnTheRealBug:
    def test_pre_adr_0058_allocation_is_caught(self):
        # reserved=2 is what ERA-42 shipped: gateway only. k8s-01 lands on
        # .34/.35 — the two core SVIs.
        ips = _dataplane_host_ips(ERA92_SUBNET, 0, 2, 101, 2, reserved=2)
        assert ips == ["10.78.220.34/27", "10.78.220.35/27"]
        hits = find_dataplane_svi_collisions(
            [("k8s-01", ip) for ip in ips],
            fabric_claimed_ips(ERA92_SUBNET, ERA92_GATEWAY, 2))
        assert [h[0] for h in hits] == ["10.78.220.34", "10.78.220.35"]
        assert all("SVI" in h[2] for h in hits)

    def test_post_adr_0058_allocation_is_clean(self):
        ips = _dataplane_host_ips(ERA92_SUBNET, 0, 2, 101, 2, reserved=4)
        assert ips == ["10.78.220.36/27", "10.78.220.37/27"]
        assert find_dataplane_svi_collisions(
            [("k8s-01", ip) for ip in ips],
            fabric_claimed_ips(ERA92_SUBNET, ERA92_GATEWAY, 2)) == []

    def test_a_host_on_the_gateway_is_caught(self):
        hits = find_dataplane_svi_collisions(
            [("k8s-01", "10.78.220.33/27")],
            fabric_claimed_ips(ERA92_SUBNET, ERA92_GATEWAY, 2))
        assert hits and hits[0][2] == "VRR / anycast gateway"


class TestWiredIntoTheValidator:
    def _nodes(self):
        return [
            {"function": "core-01", "name": "core-01", "enabled": True},
            {"function": "core-02", "name": "core-02", "enabled": True},
            {"function": "k8s", "name": "k8s-01", "enabled": True},
        ]

    def test_shipped_style_support_vlan_is_clean(self):
        vlans = [{"name": "Support", "subnet": ERA92_SUBNET,
                  "gateway": ERA92_GATEWAY}]
        r = _Result()
        validate_dataplane_svi_collisions(self._nodes(), vlans, r)
        assert r.errors == []

    def test_no_support_vlan_declared_is_a_no_op(self):
        r = _Result()
        validate_dataplane_svi_collisions(self._nodes(), [], r)
        assert r.errors == []

    def test_malformed_subnet_is_left_to_its_own_gate(self):
        vlans = [{"name": "Support", "subnet": "not-a-subnet", "gateway": ""}]
        r = _Result()
        validate_dataplane_svi_collisions(self._nodes(), vlans, r)
        assert r.errors == []
