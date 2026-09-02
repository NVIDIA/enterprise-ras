# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Storage-attach profile aliasing in the uplink-capacity floors (ADR-0059).

`public-v6.0.4`'s `2-8-5-200` default defines BOTH `Storage` and `Storage Uplink`
in `VLANs & Profiles` as L2 Trunks on VLAN 500, then cables 20 links under
`Storage Uplink` and zero under `Storage`. The sheet therefore advertises two
valid names for one attachment, and an OEM who picks the other name wires the
same topology to the same ports.

Scoring the unpicked name as zero reported "0.00 Gb/GPU (0x200G)" — which reads
as "no storage network at all" — when the real finding was a capacity shortfall
on links that were plainly there.

This mirrors `oem-audit/era_submission/tests/test_profile_alias.py`. That suite
is internal and does not ship; `resolve_wired_profile` does. A public function
needs a test inside the public tree, or the shipped distribution carries it
untested.
"""
import sys
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NC / "scripts"))

import validate_excel as ve  # noqa: E402


class TestResolveWiredProfile:
    def test_exact_match_wins(self):
        wired = {"Storage Uplink": 20, "Storage": 8}
        assert ve.resolve_wired_profile(wired, "Storage Uplink") == (20, "Storage Uplink")

    def test_falls_back_to_alias(self):
        assert ve.resolve_wired_profile({"Storage": 8}, "Storage Uplink") == (8, "Storage")

    def test_zero_when_neither_wired(self):
        assert ve.resolve_wired_profile({"ISL": 64}, "Storage Uplink") == (0, "Storage Uplink")

    def test_alias_never_inflates_a_wired_canonical(self):
        """A workbook wiring both is scored on the canonical name only."""
        assert ve.resolve_wired_profile({"Storage Uplink": 4, "Storage": 99},
                                        "Storage Uplink")[0] == 4

    def test_a_zero_valued_canonical_still_consults_the_alias(self):
        """`wired` carries explicit zeros, so falsiness — not membership — must gate."""
        assert ve.resolve_wired_profile({"Storage Uplink": 0, "Storage": 8},
                                        "Storage Uplink") == (8, "Storage")

    @pytest.mark.parametrize("label", ["Edge Uplink", "ISL", "N/S Leaf Peer", "Support"])
    def test_unaliased_profiles_never_fall_back(self, label):
        assert ve.resolve_wired_profile({"Storage": 8}, label) == (0, label)

    def test_alias_direction_is_one_way(self):
        """`Storage` is a fallback FOR `Storage Uplink`, never the reverse."""
        assert ve.resolve_wired_profile({"Storage Uplink": 20}, "Storage") == (0, "Storage")


def test_alias_table_is_not_silently_empty():
    """Guards the table itself — an empty map would make every test above vacuous."""
    assert ve._PROFILE_ALIASES.get("Storage Uplink") == ("Storage",)
