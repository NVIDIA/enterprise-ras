# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Unit tests for ERA parser and utility functions.

Tests the actual functions in scripts/utils.py, scripts/excel_parser.py,
and scripts/compare_excel_inventory_and_configs.py with concrete inputs.
"""
import re
import sys
from pathlib import Path

import pytest

# Add scripts/ to path so we can import the modules
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from utils import generate_mac, classify_node, is_switch, is_valid_hostname
from excel_parser import (
    classify_host_role,
    ports_to_range_string,
    ROLE_HOST_BASE,
    _sanitize_scalar,
    _svi_switch_ip,
    _svi_gateway_ip,
)
# compare_excel_inventory_and_configs.py is an internal-only script (excluded
# from the public distribution via .publicignore). Guard its import so the
# public test tree still collects — the dependent classes skip when it's absent.
try:
    from compare_excel_inventory_and_configs import (
        _expand_iface_token,
        _natural_key,
        normalize_nvue_line,
    )
    HAS_COMPARE = True
except ImportError:
    HAS_COMPARE = False

requires_compare = pytest.mark.skipif(
    not HAS_COMPARE,
    reason="compare_excel_inventory_and_configs.py not present (internal-only script)",
)


# ---------------------------------------------------------------------------
# utils.generate_mac
# ---------------------------------------------------------------------------

class TestGenerateMac:
    """Tests for the deterministic MAC generation function."""

    def test_format(self):
        """MAC should be in 48:b0:2d:xx:xx:xx format."""
        mac = generate_mac("core-01", "swp1")
        assert re.match(r'^48:b0:2d:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}$', mac)

    def test_deterministic(self):
        """Same inputs should always produce the same MAC."""
        mac1 = generate_mac("su-01-node-01", "eth0")
        mac2 = generate_mac("su-01-node-01", "eth0")
        assert mac1 == mac2

    def test_different_interfaces(self):
        """Different interfaces on the same node should produce different MACs."""
        mac0 = generate_mac("su-01-node-01", "eth0")
        mac1 = generate_mac("su-01-node-01", "eth1")
        assert mac0 != mac1

    def test_different_nodes(self):
        """Different nodes with the same interface should produce different MACs."""
        mac_a = generate_mac("core-01", "swp1")
        mac_b = generate_mac("core-02", "swp1")
        assert mac_a != mac_b

    def test_custom_seed(self):
        """Different seeds should produce different MACs."""
        mac1 = generate_mac("core-01", "swp1", seed="era")
        mac2 = generate_mac("core-01", "swp1", seed="other")
        assert mac1 != mac2


# ---------------------------------------------------------------------------
# utils.classify_node
# ---------------------------------------------------------------------------

class TestClassifyNode:
    """Tests for the unified node classifier."""

    def test_core_switches(self):
        assert classify_node("core-01") == "core"
        assert classify_node("core-02") == "core"

    def test_oob_switches(self):
        assert classify_node("oob-switch-01") == "oob"
        assert classify_node("oob-switch-03") == "oob"

    def test_edge_switches(self):
        assert classify_node("edge-01") == "edge"

    def test_infra_nodes(self):
        assert classify_node("dhcp-oob") == "infra"
        assert classify_node("dhcp-edge") == "infra"
        assert classify_node("oob-server-01") == "infra"

    def test_compute_nodes(self):
        assert classify_node("su-01-node-01") == "compute"
        assert classify_node("su-02-node-04") == "compute"

    def test_storage_nodes(self):
        assert classify_node("storage-01") == "storage"
        assert classify_node("storage-02") == "storage"

    def test_support_nodes(self):
        assert classify_node("support-01") == "support"

    def test_compute_gpu_fabric_short_names_are_switches(self):
        """Post-rename short role names (cl/cs/gl/gs) must map to switch roles.

        Regression: the bare N/S-spine function 'cs' (and gpu 'gs', leaf
        'cl'/'gl') fell through to 'unknown' → 1024 MB in the topology
        generator, below Air's 2048 MB switch minimum, so 2-8-9-800 SU32
        imported INVALID. They are SN56xx compute/GPU-fabric switches and
        must classify as csl/gsl (4096 MB), like their hostname-prefixed and
        legacy forms.
        """
        # bare function names (model ns_spine_function: cs, ew_*_template: gl/gs)
        assert classify_node("cs") == "csl"
        assert classify_node("cl") == "csl"
        assert classify_node("gs") == "gsl"
        assert classify_node("gl") == "gsl"
        # hostname-prefixed forms still work
        assert classify_node("cs-01") == "csl"
        assert classify_node("gs-plane1-01") == "gsl"
        assert classify_node("gl-plane2-08") == "gsl"

    def test_k8s_nodes(self):
        assert classify_node("k8s-01") == "k8s"

    def test_bcme_nodes(self):
        assert classify_node("bcme-01") == "bcme"

    def test_unknown(self):
        assert classify_node("mystery-box") == "unknown"


# ---------------------------------------------------------------------------
# utils.is_switch
# ---------------------------------------------------------------------------

class TestIsSwitch:
    """Tests for is_switch helper."""

    def test_switches_are_switches(self):
        assert is_switch("core-01") is True
        assert is_switch("oob-switch-02") is True
        assert is_switch("edge-01") is True

    def test_servers_are_not_switches(self):
        assert is_switch("su-01-node-01") is False
        assert is_switch("dhcp-oob") is False
        assert is_switch("storage-01") is False


# ---------------------------------------------------------------------------
# utils.is_valid_hostname
# ---------------------------------------------------------------------------

class TestIsValidHostname:
    """Tests for hostname validation."""

    def test_valid_names(self):
        assert is_valid_hostname("core-01") is True
        assert is_valid_hostname("su-01-node-03") is True
        assert is_valid_hostname("oob-switch-01") is True
        assert is_valid_hostname("a") is True

    def test_invalid_names(self):
        assert is_valid_hostname("") is False
        assert is_valid_hostname("SPARE ISL") is False
        assert is_valid_hostname("node with spaces") is False


# ---------------------------------------------------------------------------
# excel_parser.classify_host_role (wrapper around classify_node)
# ---------------------------------------------------------------------------

class TestClassifyHostRole:
    """Tests for the excel_parser wrapper that maps switch roles."""

    def test_switches_map_to_switch(self):
        assert classify_host_role("core-01") == "switch"
        assert classify_host_role("oob-switch-01") == "switch"
        assert classify_host_role("edge-01") == "switch"

    def test_infra_stays_infra(self):
        assert classify_host_role("dhcp-oob") == "infra"

    def test_compute_stays_compute(self):
        assert classify_host_role("su-01-node-01") == "compute"


# ---------------------------------------------------------------------------
# excel_parser.ports_to_range_string
# ---------------------------------------------------------------------------

class TestPortsToRangeString:
    """Tests for NVUE swp range notation generation."""

    def test_empty(self):
        assert ports_to_range_string(set()) == ''

    def test_single_port(self):
        assert ports_to_range_string({5}) == 'swp5'

    def test_contiguous_range(self):
        assert ports_to_range_string({1, 2, 3}) == 'swp1-3'

    def test_disjoint_ports(self):
        assert ports_to_range_string({1, 3, 5}) == 'swp1,swp3,swp5'

    def test_mixed(self):
        result = ports_to_range_string({1, 2, 3, 5, 7, 8})
        assert result == 'swp1-3,swp5,swp7-8'

    def test_large_range(self):
        result = ports_to_range_string(set(range(1, 49)))
        assert result == 'swp1-48'


# ---------------------------------------------------------------------------
# excel_parser._sanitize_scalar
# ---------------------------------------------------------------------------

class TestSanitizeScalar:
    """Free-text cells (VLAN name/purpose/vrf) are rendered into generated
    config files; embedded control chars must not survive to inject directives."""

    def test_strips_embedded_newline(self):
        # A VLAN name with a newline could break out of a dnsmasq comment line.
        assert _sanitize_scalar("OOB\ndhcp-option=evil") == "OOB dhcp-option=evil"

    def test_strips_carriage_return_and_tab(self):
        assert _sanitize_scalar("a\r\nb\tc") == "a b c"

    def test_leaves_normal_text_unchanged(self):
        assert _sanitize_scalar("Storage Network") == "Storage Network"

    def test_trims_ends(self):
        assert _sanitize_scalar("  Compute  ") == "Compute"

    def test_passes_through_none_and_non_strings(self):
        assert _sanitize_scalar(None) is None
        assert _sanitize_scalar(200) == 200


# ---------------------------------------------------------------------------
# compare_excel_inventory_and_configs._expand_iface_token
# ---------------------------------------------------------------------------

@requires_compare
class TestExpandIfaceToken:
    """Tests for NVUE interface range expansion."""

    def test_simple_range(self):
        assert _expand_iface_token('swp49-52') == 'swp49,swp50,swp51,swp52'

    def test_bond_subport_range(self):
        result = _expand_iface_token('bond1s0-3')
        assert result == 'bond1s0,bond1s1,bond1s2,bond1s3'

    def test_no_range(self):
        assert _expand_iface_token('swp1') == 'swp1'

    def test_comma_separated(self):
        result = _expand_iface_token('swp49,swp50,swp51,swp52')
        assert result == 'swp49,swp50,swp51,swp52'

    def test_prefix_carryover(self):
        """Digits-only ranges should inherit prefix from previous item."""
        result = _expand_iface_token('swp1-6,10-17')
        # Should expand to swp1,...,swp6,swp10,...,swp17
        parts = result.split(',')
        assert parts[0] == 'swp1'
        assert parts[5] == 'swp6'
        assert parts[6] == 'swp10'
        assert parts[-1] == 'swp17'
        assert len(parts) == 14

    def test_multi_bond_range(self):
        result = _expand_iface_token('bond1s0-3,bond2s0-3')
        parts = result.split(',')
        assert len(parts) == 8
        assert 'bond1s0' in parts
        assert 'bond2s3' in parts

    def test_mixed_token(self):
        result = _expand_iface_token('spine_bond,swp1-3')
        assert 'spine_bond' in result
        assert 'swp1' in result
        assert 'swp3' in result


# ---------------------------------------------------------------------------
# compare_excel_inventory_and_configs.normalize_nvue_line
# ---------------------------------------------------------------------------

@requires_compare
class TestNormalizeNvueLine:
    """Tests for NVUE line normalization."""

    def test_range_expansion(self):
        line = "nv set interface swp49-52 link state up"
        result = normalize_nvue_line(line)
        assert "swp49,swp50,swp51,swp52" in result

    def test_already_expanded(self):
        line = "nv set interface swp49,swp50,swp51,swp52 link state up"
        result = normalize_nvue_line(line)
        assert "swp49,swp50,swp51,swp52" in result

    def test_non_interface_token_unchanged(self):
        line = "nv set system hostname core-01"
        assert normalize_nvue_line(line) == line

    def test_compact_and_expanded_compare_equal(self):
        compact = normalize_nvue_line("nv set interface swp1-3 link state up")
        expanded = normalize_nvue_line("nv set interface swp1,swp2,swp3 link state up")
        assert compact == expanded


# ---------------------------------------------------------------------------
# compare_excel_inventory_and_configs._natural_key
# ---------------------------------------------------------------------------

@requires_compare
class TestNaturalKey:
    """Tests for natural sort key."""

    def test_sorts_swp_ports_naturally(self):
        ports = ['swp10', 'swp2', 'swp1', 'swp20']
        sorted_ports = sorted(ports, key=_natural_key)
        assert sorted_ports == ['swp1', 'swp2', 'swp10', 'swp20']


# ---------------------------------------------------------------------------
# excel_parser._svi_switch_ip / _svi_gateway_ip
#
# Regression for the customer-reported SVI/VRR bug: for any VLAN whose subnet
# does not start at .0 or whose gateway is not .1, the old code emitted SVI +
# VRR addresses OUTSIDE the declared subnet. The fix derives per-switch host
# IPs from ipaddress.ip_network().hosts() and uses the Excel gateway as VRR.
# (docs/internal/BLOCKING-FIXES.md Open #1)
# ---------------------------------------------------------------------------

class TestSviAddressing:
    """Per-switch SVI host IP + VRR gateway derivation."""

    def test_default_aligned_subnet_byte_identical(self):
        """A .0-aligned /24 with a .1 gateway must reproduce the legacy
        `<base>.<1+core_num>` SVI scheme exactly (zero output drift on the
        shipping default Excels)."""
        subnet, gw = "172.16.178.0/24", "172.16.178.1"
        assert _svi_gateway_ip(subnet, gw) == "172.16.178.1"
        assert _svi_switch_ip(subnet, gw, 1) == "172.16.178.2"   # core-01
        assert _svi_switch_ip(subnet, gw, 2) == "172.16.178.3"   # core-02

    def test_blank_gateway_falls_back_to_first_host(self):
        """No Excel gateway -> first usable host, matching the old `.1`."""
        assert _svi_gateway_ip("172.16.178.0/24", None) == "172.16.178.1"
        assert _svi_gateway_ip("172.16.178.0/24", "") == "172.16.178.1"

    def test_offset_subnet_stays_in_network(self):
        """Offset subnet: 100.82.254.128/27 + .129 gateway. SVI + VRR must land
        inside 100.82.254.128/27, NOT 100.82.254.0/27."""
        import ipaddress
        subnet, gw = "100.82.254.128/27", "100.82.254.129"
        net = ipaddress.ip_network(subnet)
        vrr = _svi_gateway_ip(subnet, gw)
        svi1 = _svi_switch_ip(subnet, gw, 1)
        svi2 = _svi_switch_ip(subnet, gw, 2)
        assert vrr == "100.82.254.129"
        assert ipaddress.ip_address(svi1) in net
        assert ipaddress.ip_address(svi2) in net
        # Never collide with the gateway, and be distinct per switch.
        assert svi1 != vrr and svi2 != vrr and svi1 != svi2

    def test_offset_subnet_does_not_use_dot_zero_base(self):
        """The old bug produced 100.82.254.2 / .1 — explicitly assert we no
        longer emit anything in the .0 network."""
        subnet, gw = "100.82.254.128/27", "100.82.254.129"
        assert not _svi_switch_ip(subnet, gw, 1).startswith("100.82.254.2")
        assert _svi_gateway_ip(subnet, gw) != "100.82.254.1"

    def test_unparseable_subnet_falls_back_legacy(self):
        """Malformed subnet must not crash — fall back to legacy scheme."""
        assert _svi_switch_ip("not-a-subnet", None, 1) == "not-a-subnet.2"
