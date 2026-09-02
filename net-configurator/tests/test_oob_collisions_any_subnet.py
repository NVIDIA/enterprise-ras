# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
ERA-93 part 1 — the duplicate-mgmt-IP gate must inspect the OOB subnet the
workbook DECLARES, not the literal 192.168.200.0/24 it was written against.

Before this, `oob_octet()` returned None for every address outside
192.168.200.0/24, so `find_oob_collisions()` saw zero claims on any brownfield
workbook and passed silently. The registry exists specifically to prevent
duplicate-address wars, and it was structurally unable to see ERA-92
(10.78.220.34 claimed twice, support data plane dead).

A gate that cannot fail on a valid input is worse than no gate, because its
silence is read as a pass.

Two rules this pins down:

* **Reserved offsets follow air-deploy.** `air-deploy.py:183` assigns infra as
  `network_address + octet`, so on `10.78.220.128/25` the utility jump (octet
  78) is `.206`, not `.78`. The gate must reserve the same address air-deploy
  hands out, or it protects an address nobody uses.
* **Duplicate detection is subnet-independent.** Two Nodes-tab hosts sharing an
  address is always wrong; making that finding conditional on a subnet literal
  is what let ERA-92 through.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from oob_reserved import (  # noqa: E402
    OOB_SUBNET,
    UTILITY_OCTET,
    find_oob_collisions,
    oob_octet,
    oob_reserved_for_mode,
)

BROWNFIELD = "10.78.220.128/25"   # the real ERA-92 OOB VLAN


class TestOobOffsetHonoursDeclaredSubnet:
    def test_default_subnet_still_works(self):
        assert oob_octet("192.168.200.78") == UTILITY_OCTET

    def test_offset_is_measured_from_the_declared_network_address(self):
        # 10.78.220.128/25 + 78 == 10.78.220.206 — the address air-deploy
        # actually assigns to the utility jump on that plane.
        assert oob_octet("10.78.220.206", subnets=[BROWNFIELD]) == UTILITY_OCTET

    def test_address_outside_every_declared_subnet_is_ignored(self):
        assert oob_octet("10.99.99.5", subnets=[BROWNFIELD]) is None

    def test_default_subnet_is_not_implied_when_subnets_given(self):
        # A workbook that declares its own OOB VLAN has no 192.168.200.0/24.
        assert oob_octet("192.168.200.78", subnets=[BROWNFIELD]) is None

    def test_multiple_declared_subnets_are_all_checked(self):
        subnets = [BROWNFIELD, "10.78.221.0/24"]
        assert oob_octet("10.78.221.9", subnets=subnets) == 9
        assert oob_octet("10.78.220.141", subnets=subnets) == 13  # .141 - .128


class TestDuplicatesAreCaughtOnAnyDeclaredSubnet:
    def test_two_hosts_sharing_an_address_collide(self):
        claims = [("gpu-01 (row 5)", "10.78.220.141"),
                  ("gpu-02 (row 6)", "10.78.220.141")]
        found = find_oob_collisions(claims, {}, subnets=[BROWNFIELD])
        assert len(found) == 1
        address, owners = found[0]
        assert address == "10.78.220.141"
        assert "gpu-01 (row 5)" in owners and "gpu-02 (row 6)" in owners

    def test_distinct_addresses_do_not_collide(self):
        claims = [("gpu-01 (row 5)", "10.78.220.141"),
                  ("gpu-02 (row 6)", "10.78.220.142")]
        assert find_oob_collisions(claims, {}, subnets=[BROWNFIELD]) == []

    def test_same_offset_in_different_subnets_is_not_a_collision(self):
        # Keying on the offset alone would report a phantom duplicate here.
        subnets = [BROWNFIELD, "10.78.221.0/24"]
        claims = [("a (row 5)", "10.78.220.141"), ("b (row 6)", "10.78.221.13")]
        assert find_oob_collisions(claims, {}, subnets=subnets) == []

    def test_duplicates_are_found_even_outside_every_declared_subnet(self):
        # Never fail open: a duplicate is a duplicate wherever it lands. This
        # is the property whose absence let ERA-92 through.
        claims = [("a (row 5)", "10.99.99.5"), ("b (row 6)", "10.99.99.5")]
        found = find_oob_collisions(claims, {}, subnets=[BROWNFIELD])
        assert [addr for addr, _ in found] == ["10.99.99.5"]

    def test_reserved_infra_address_is_reserved_on_the_declared_subnet(self):
        # A host on network+78 of the declared OOB VLAN squats the utility jump.
        claims = [("bmc-07 (row 22)", "10.78.220.206")]
        found = find_oob_collisions(claims, oob_reserved_for_mode("l3"),
                                    subnets=[BROWNFIELD])
        assert len(found) == 1
        address, owners = found[0]
        assert address == "10.78.220.206"
        assert any("utility" in o for o in owners)

    def test_reserved_offset_outside_the_declared_network_is_not_seeded(self):
        # dhcp-oob is octet 252; 10.78.220.128/25 tops out at .255 == offset
        # 127, so that reservation simply does not exist on this plane.
        claims = [("bmc-07 (row 22)", "10.78.220.252")]  # offset 124
        assert find_oob_collisions(claims, oob_reserved_for_mode("l3"),
                                   subnets=[BROWNFIELD]) == []

    def test_the_original_192_168_200_behaviour_is_unchanged(self):
        claims = [("su-09-node-03 (row 40)", "192.168.200.78")]
        found = find_oob_collisions(claims, oob_reserved_for_mode("l3"))
        assert [a for a, _ in found] == ["192.168.200.78"]


class TestRegistryDefaults:
    def test_default_subnet_constant_unchanged(self):
        assert OOB_SUBNET == "192.168.200.0/24"
