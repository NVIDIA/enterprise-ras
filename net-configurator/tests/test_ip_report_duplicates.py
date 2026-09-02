# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""`make ip-report` must surface duplicate addresses, not just list them.

The report collects every address on every plane, so it held both halves of the
switch-SVI/node-eth0 collision that shipped on four largescale sites — and said
nothing, because it never compared anything and never included the OOB VLAN SVI
at all.

Two independent gaps, either of which alone made it blind:

* ``switch_rows()`` read SVIs from ``vlan_interfaces``, but OOB switches carry
  theirs as a flat ``svi_ip`` key, so the whole report contained zero VLAN-200
  rows;
* nothing compared the collected addresses.

A report that cannot fail is read as a pass.
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from emit_ip_report import IP_COL, COLUMNS, find_duplicate_ips, switch_rows  # noqa: E402


def _row(name, port, ip):
    r = [""] * len(COLUMNS)
    r[0], r[4], r[IP_COL] = name, port, ip
    return tuple(r)


def test_ip_col_matches_the_header():
    assert COLUMNS[IP_COL] == "IP Address"


def test_detects_the_shipped_svi_versus_eth0_collision():
    dupes = find_duplicate_ips([
        _row("oob-switch-09", "vlan200", "192.168.200.10/24"),
        _row("cl-01", "eth0", "192.168.200.10/24"),
        _row("cl-02", "eth0", "192.168.200.11/24"),
    ])
    assert "192.168.200.10" in dupes
    assert len(dupes["192.168.200.10"]) == 2
    assert "192.168.200.11" not in dupes


def test_prefix_length_does_not_hide_a_duplicate():
    """A /32 loopback and a /24 SVI on one address still collide."""
    assert "10.0.0.5" in find_duplicate_ips([
        _row("sw-a", "lo", "10.0.0.5/32"),
        _row("sw-b", "vlan300", "10.0.0.5/24"),
    ])


def test_placeholders_are_not_duplicates():
    """Every unconfigured host reads CHANGE_ME; that is not a collision."""
    assert not find_duplicate_ips([
        _row("a", "eth0", "CHANGE_ME"), _row("b", "eth0", "CHANGE_ME"),
        _row("c", "eth0", ""), _row("d", "eth0", "-"),
    ])


def test_one_owner_listed_once():
    """The same device/port seen twice is not two owners."""
    assert not find_duplicate_ips([
        _row("sw-a", "vlan200", "10.0.0.9/24"),
        _row("sw-a", "vlan200", "10.0.0.9/24"),
    ])


def test_oob_switch_svi_reaches_the_report():
    """The omission that made the duplicate invisible in the first place.

    OOB switches store the SVI as flat ``svi_ip``; if switch_rows() only reads
    ``vlan_interfaces`` the address never enters the report and no amount of
    duplicate checking can see it.
    """
    rows = list(switch_rows({
        "oob-switch-01": {"ansible_host": "172.20.0.2",
                          "svi_ip": "192.168.200.2/24",
                          "oob_access_vlan": 200},
    }))
    # switch_rows yields the raw 7-tuple (name, type, profile, port, ip, ...);
    # IP_COL indexes the assembled report row, which is a different shape.
    _RAW_IP = 4
    assert any("192.168.200.2" in str(r[_RAW_IP]) for r in rows), (
        f"OOB SVI missing from the report again: {rows}")
    assert any(str(r[3]) == "vlan200" for r in rows), (
        f"OOB SVI not labelled with its VLAN: {rows}")
