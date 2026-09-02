# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Fabric links must be cabled in whole optics.

Vocabulary, fixed by the Hardware RA (2026-08-21):

    port / hole  a cage on the switch faceplate -- the parent `swpN`
    cable        one sub-link out of that hole  -- `swpNsX`

An SN5610 OSFP cage fitted with a twin transceiver carries `breakout` cables.
So for any switch↔switch population: `cables == holes x breakout`. A hole
carrying fewer is half a transceiver, which cannot be bought or installed.

This is deliberately MODEL-FREE. It compares the workbook against itself, so it
runs in the public distribution where `data-models/` is absent -- which is where
OEM submissions are validated, and where the model-backed
`validate_isl_geometry_and_count` returns early and checks nothing.

It is also why it catches the real defect without waiting on a spec question:
`2-4-3-200` wires its N/S peer as 7 cables across 4 holes. 7 is odd, so one hole
holds half an optic -- wrong under every candidate RA target.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_excel import find_partial_optics, find_shared_fabric_optics  # noqa: E402


class TestWholeOptics:
    def test_full_population_is_clean(self):
        # 2 holes x breakout 2 = 4 cables
        cables = [("core-01", "swp1s0"), ("core-01", "swp1s1"),
                  ("core-01", "swp2s0"), ("core-01", "swp2s1")]
        assert find_partial_optics(cables, breakout=2) == []

    def test_half_populated_hole_is_reported(self):
        cables = [("core-01", "swp1s0"), ("core-01", "swp1s1"),
                  ("core-01", "swp2s0")]                       # swp2s1 dark
        out = find_partial_optics(cables, breakout=2)
        assert out == [("core-01", "swp2", 1, 2)]

    def test_the_2_4_3_200_peer_shape(self):
        # 7 cables across 4 holes: three full, one half.
        cables = [("core-01", f"swp{p}s{s}") for p in (27, 28, 29) for s in (0, 1)]
        cables.append(("core-01", "swp30s0"))
        out = find_partial_optics(cables, breakout=2)
        assert out == [("core-01", "swp30", 1, 2)]

    def test_breakout_four_needs_four_cables(self):
        cables = [("core-01", f"swp9s{s}") for s in range(3)]
        assert find_partial_optics(cables, breakout=4) == [("core-01", "swp9", 3, 4)]

    def test_unbroken_port_is_not_partial(self):
        # No sub-port suffix: the cage is not broken out, one cable is correct.
        assert find_partial_optics([("oob-switch-01", "swp1")], breakout=1) == []

    def test_each_switch_is_judged_separately(self):
        cables = [("core-01", "swp1s0"), ("core-01", "swp1s1"),
                  ("core-02", "swp1s0")]
        assert find_partial_optics(cables, breakout=2) == [("core-02", "swp1", 1, 2)]


class TestSharedOptics:
    def test_hole_used_by_one_population_is_clean(self):
        per_profile = {"ISL": [("core-01", "swp30s0"), ("core-01", "swp30s1")]}
        assert find_shared_fabric_optics(per_profile) == []

    def test_hole_split_between_two_fabric_populations_is_reported(self):
        # The real 2-4-3-200 case: one transceiver, one cable counted against
        # `switch_switch_cables` and the other against `allocated_ports.isl`.
        per_profile = {"ISL": [("core-01", "swp30s1")],
                       "N/S Leaf Peer": [("core-01", "swp30s0")]}
        out = find_shared_fabric_optics(per_profile)
        assert out == [("core-01", "swp30", ["ISL", "N/S Leaf Peer"])]

    def test_distinct_holes_per_population_are_clean(self):
        per_profile = {"ISL": [("core-01", "swp30s0"), ("core-01", "swp30s1")],
                       "N/S Leaf Peer": [("core-01", "swp31s0"), ("core-01", "swp31s1")]}
        assert find_shared_fabric_optics(per_profile) == []
