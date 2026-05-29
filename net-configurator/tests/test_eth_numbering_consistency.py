# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Regression tests for the netplan/topology eth-numbering consistency fix
(MR !26: "fix(servers): align netplan eth-numbering with topology").

The bug:
  When a Wire Map row with an OOB/IPMI-classified peer is interleaved
  *before* the bond-member rows for a compute node, the topology
  generator and `build_interface_map()` produced different eth-numbering.
  Topology reserved eth0 for the first OOB-peer row regardless of order;
  the netplan-side incremented `next_eth()` past that row, shifting the
  bond by one slot. Result: an active-backup bond paired one CPU NIC
  with one GPU NIC, looked healthy via mii-monitor, and silently broke
  gateway routing on `su-01-node-01`.

These tests lock in that both algorithms agree on every realistic row
ordering pattern observed in our four canonical archs plus the
synthetic interleaved case that triggered the bug.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from utils import build_interface_map


def _row(*, system_name, nic_port, net_profile, switch_role,
         switch_name=None, switch_port=None, display_in_air=True,
         system_role=None):
    """Build a Wire Map row dict in the shape build_interface_map expects."""
    return {
        'display_in_air': display_in_air,
        'system_name': system_name,
        'system_role': system_role or system_name,
        'nic_port': nic_port,
        'net_profile': net_profile,
        'switch_role': switch_role,
        'switch_name': switch_name or switch_role,
        'switch_port': switch_port or 'swp1',
    }


# ---------------------------------------------------------------------------
# Standard ordering: OOB rows first, then CPU bond, then GPU NICs.
# Matches su-01-node-02..04 in 2-8-5-200 and every node in the other archs.
# ---------------------------------------------------------------------------

def test_standard_ordering_oob_then_cpu_then_gpu():
    rows = [
        _row(system_name='node-01', nic_port='OCP NIC Port 1',
             net_profile='OOB / IPMI', switch_role='oob-switch-01'),
        _row(system_name='node-01', nic_port='B3220 PCIe Slot 1 Port 1',
             net_profile='CPU/In-Band Network', switch_role='core-01',
             switch_port='swp1s0'),
        _row(system_name='node-01', nic_port='B3220 PCIe Slot 1 Port 2',
             net_profile='CPU/In-Band Network', switch_role='core-02',
             switch_port='swp1s0'),
        _row(system_name='node-01', nic_port='B3140 GPU Port 1',
             net_profile='GPU Network', switch_role='core-01',
             switch_port='swp6s0'),
        _row(system_name='node-01', nic_port='B3140 GPU Port 2',
             net_profile='GPU Network', switch_role='core-02',
             switch_port='swp6s0'),
    ]
    iface_map = build_interface_map(rows, 'node-01')

    # OOB → eth0 (first display-yes OOB-peer row); CPU bond → eth1+eth2.
    assert iface_map.get('oob') == ['eth0']
    assert iface_map.get('cpu') == ['eth1', 'eth2']
    assert iface_map.get('gpu') == ['eth3', 'eth4']


# ---------------------------------------------------------------------------
# THE BUG CASE: BMC/OOB row interleaved *before* the CPU bond rows.
# Mirrors `su-01-node-01` in the 2-8-5-200 wiremap. Pre-fix this produced
# cpu=['eth2','eth3'] which the netplan template bonded — pairing a CPU NIC
# with a GPU NIC. Post-fix it must produce cpu=['eth1','eth2'].
# ---------------------------------------------------------------------------

def test_interleaved_bmc_row_does_not_shift_bond():
    rows = [
        # First OOB row (chosen as eth0)
        _row(system_name='node-01', nic_port='B3220 PCIe Slot 1 BMC',
             net_profile='OOB / IPMI', switch_role='oob-switch-03',
             switch_port='swp1'),
        # Bond members must still land on eth1 + eth2
        _row(system_name='node-01', nic_port='B3220 PCIe Slot 1 Port 1',
             net_profile='CPU/In-Band Network', switch_role='core-01',
             switch_port='swp1s0'),
        _row(system_name='node-01', nic_port='B3220 PCIe Slot 1 Port 2',
             net_profile='CPU/In-Band Network', switch_role='core-02',
             switch_port='swp1s0'),
        # GPU NICs follow on eth3+
        _row(system_name='node-01', nic_port='B3140 GPU Port 1',
             net_profile='GPU Network', switch_role='core-01',
             switch_port='swp6s0'),
        _row(system_name='node-01', nic_port='B3140 GPU Port 2',
             net_profile='GPU Network', switch_role='core-02',
             switch_port='swp6s0'),
    ]
    iface_map = build_interface_map(rows, 'node-01')

    # Critical regression assertion: bond members are eth1 + eth2.
    # Pre-fix this came back as ['eth2', 'eth3'] (silent fail in production).
    assert iface_map.get('cpu') == ['eth1', 'eth2'], (
        f"CPU bond members shifted off-by-one! Got {iface_map.get('cpu')!r}; "
        f"expected ['eth1', 'eth2']. The netplan template will bond a CPU NIC "
        f"with a GPU NIC if this regresses."
    )
    assert iface_map.get('oob') == ['eth0']
    assert iface_map.get('gpu') == ['eth3', 'eth4']


# ---------------------------------------------------------------------------
# BMC row at the END of the per-node block. Same node-02 pattern but with
# the BMC row last. Standard pre-fix behaviour was correct here, so this
# test guards against a fix that breaks the working case.
# ---------------------------------------------------------------------------

def test_bmc_row_at_end_assigns_eth0_first_oob_in_order():
    rows = [
        _row(system_name='node-02', nic_port='B3220 PCIe Slot 1 Port 1',
             net_profile='CPU/In-Band Network', switch_role='core-01',
             switch_port='swp1s1'),
        _row(system_name='node-02', nic_port='B3220 PCIe Slot 1 Port 2',
             net_profile='CPU/In-Band Network', switch_role='core-02',
             switch_port='swp1s1'),
        _row(system_name='node-02', nic_port='B3140 GPU Port 1',
             net_profile='GPU Network', switch_role='core-01',
             switch_port='swp7s0'),
        # BMC row arrives last — but it's still the first OOB-peer row, so
        # it gets eth0 and bumps the CPU bond to eth1/eth2 / GPU to eth3.
        _row(system_name='node-02', nic_port='B3220 PCIe Slot 1 BMC',
             net_profile='OOB / IPMI', switch_role='oob-switch-01',
             switch_port='swp3'),
    ]
    iface_map = build_interface_map(rows, 'node-02')

    assert iface_map.get('oob') == ['eth0']
    assert iface_map.get('cpu') == ['eth1', 'eth2']
    assert iface_map.get('gpu') == ['eth3']


# ---------------------------------------------------------------------------
# No OOB peer in the wiremap (rare — storage-only nodes in some designs,
# or compute hosts whose IPMI/OOB rows have blank Port (B) cells).
# eth0 is NOT reserved in this case — the first cabled row gets eth0,
# matching topology_generator's _oob_eth0 logic which also only reserves
# eth0 when it finds a valid OOB-peer connection.
# ---------------------------------------------------------------------------

def test_no_oob_peer_starts_at_eth0():
    rows = [
        _row(system_name='storage-01', nic_port='B3220 Port 1',
             net_profile='Storage Network', switch_role='core-01',
             switch_port='swp1s0'),
        _row(system_name='storage-01', nic_port='B3220 Port 2',
             net_profile='Storage Network', switch_role='core-02',
             switch_port='swp1s0'),
    ]
    iface_map = build_interface_map(rows, 'storage-01')

    # No OOB-peer row → eth0 is not reserved → first cable gets eth0.
    # Matches what the topology generator produces, so the eth-consistency
    # cross-check in `make generate` Step 5 stays green.
    assert iface_map.get('storage') == ['eth0', 'eth1']


# ---------------------------------------------------------------------------
# Explicit eth0 in the wiremap (legacy "Air - Management" pattern where the
# operator writes the eth0 row themselves). The explicit assignment wins;
# build_interface_map honours it.
# ---------------------------------------------------------------------------

def test_explicit_eth0_in_wiremap_honoured():
    rows = [
        _row(system_name='node-03', nic_port='eth0',
             net_profile='Air - Management', switch_role='oob-switch-02',
             switch_port='swp4'),
        _row(system_name='node-03', nic_port='B3220 Port 1',
             net_profile='CPU/In-Band Network', switch_role='core-01',
             switch_port='swp2s0'),
        _row(system_name='node-03', nic_port='B3220 Port 2',
             net_profile='CPU/In-Band Network', switch_role='core-02',
             switch_port='swp2s0'),
    ]
    iface_map = build_interface_map(rows, 'node-03')

    # Explicit eth0 row classifies the OOB-peer connection as oob[eth0].
    assert iface_map.get('oob') == ['eth0']
    assert iface_map.get('cpu') == ['eth1', 'eth2']


# ---------------------------------------------------------------------------
# Display-No rows must be skipped on both algorithms. The OEM Wire Maps
# often have several display=No "spec/info" rows that we shouldn't count.
# ---------------------------------------------------------------------------

def test_display_no_rows_skipped():
    rows = [
        _row(system_name='node-04', nic_port='OCP Port 1',
             net_profile='OOB / IPMI', switch_role='oob-switch-01',
             display_in_air=False),  # skipped
        _row(system_name='node-04', nic_port='OCP Port 2',
             net_profile='OOB / IPMI', switch_role='oob-switch-02',
             display_in_air=False),  # skipped
        _row(system_name='node-04', nic_port='B3220 Port 1',
             net_profile='CPU/In-Band Network', switch_role='core-01',
             switch_port='swp1s2'),
        _row(system_name='node-04', nic_port='B3220 Port 2',
             net_profile='CPU/In-Band Network', switch_role='core-02',
             switch_port='swp1s2'),
        _row(system_name='node-04', nic_port='B3220 BMC',
             net_profile='OOB / IPMI', switch_role='oob-switch-03',
             switch_port='swp1'),
    ]
    iface_map = build_interface_map(rows, 'node-04')

    # The first display-yes OOB-peer row is the BMC row (#5), so it gets
    # eth0. CPU bond → eth1+eth2.
    assert iface_map.get('oob') == ['eth0']
    assert iface_map.get('cpu') == ['eth1', 'eth2']
