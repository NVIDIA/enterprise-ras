# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Unit tests for configuration validation.

Tests cover:
- NVUE command format validation
- IP, MAC, VLAN, BGP ASN, port range, and hostname validation (positive + negative)
- Configuration consistency (VLAN-VNI mapping, interface naming, VRF naming)
- Configuration completeness against real reference configs in REFERENCES/&lt;arch&gt;/configs/
"""
import sys
import pytest
import re
from pathlib import Path

# Make scripts importable so we can use utils.is_valid_hostname
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from utils import is_valid_hostname


# ---------------------------------------------------------------------------
# Architectures and their expected switch inventories
# ---------------------------------------------------------------------------
# Collapsed-core archs only: these are the archs whose N/S fabric is a
# core-01/core-02 pair. The dedicated-GPU archs (2-4-5-800, 2-8-9-800,
# 2-8-9-400-SP) use csl/gsl naming and are covered elsewhere. NOT a registry
# of supported architectures — see tests/test_arch_registry_is_consistent.py.
COLLAPSED_CORE_ARCHS = ["2-4-3-200", "2-8-5-200", "2-8-9-400"]

ARCH_CORE_SWITCHES = {
    "2-4-3-200": ["core-01", "core-02"],
    "2-8-5-200": ["core-01", "core-02"],
    "2-8-9-400": ["core-01", "core-02"],
}

ARCH_OOB_SWITCHES = {
    "2-4-3-200": ["oob-switch-01", "oob-switch-02"],
    "2-8-5-200": ["oob-switch-01", "oob-switch-02", "oob-switch-03"],
    "2-8-9-400": ["oob-switch-01", "oob-switch-02", "oob-switch-03"],
}

# Patterns for extracting NVUE top-level sections from config lines
SECTION_RE = re.compile(r"^nv set (\S+)")

# Regex helpers
IP_PATTERN = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(/\d{1,2})?$")
MAC_PATTERN = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", re.IGNORECASE)
PORT_RANGE_PATTERN = re.compile(r"^(swp)?(\d+(-\d+)?,?)+$")


def _validate_ip_strict(ip_str: str) -> bool:
    """Validate an IP address string (with optional /prefix).

    Checks that each octet is 0-255 and prefix (if present) is 0-32.
    """
    if not ip_str or not isinstance(ip_str, str):
        return False
    parts = ip_str.split("/")
    ip_part = parts[0]
    octets = ip_part.split(".")
    if len(octets) != 4:
        return False
    for o in octets:
        if not o.isdigit():
            return False
        val = int(o)
        if val < 0 or val > 255:
            return False
    if len(parts) == 2:
        prefix = parts[1]
        if not prefix.isdigit():
            return False
        if not (0 <= int(prefix) <= 32):
            return False
    elif len(parts) > 2:
        return False
    return True


def _validate_mac(mac_str: str) -> bool:
    """Validate a MAC address (colon-separated hex pairs)."""
    if not mac_str or not isinstance(mac_str, str):
        return False
    return bool(MAC_PATTERN.match(mac_str))


def _validate_vlan_id(vlan) -> bool:
    """Validate a VLAN ID (integer 1-4094)."""
    try:
        v = int(vlan)
    except (ValueError, TypeError):
        return False
    return 1 <= v <= 4094


def _validate_bgp_asn(asn) -> bool:
    """Validate a BGP ASN (2-byte or 4-byte range)."""
    try:
        a = int(asn)
    except (ValueError, TypeError):
        return False
    return (1 <= a <= 65535) or (4200000000 <= a <= 4294967294)


def _validate_port_range(port_range: str) -> bool:
    """Validate a port range string like 'swp1-6' or 'swp1-6,10-17'.

    Also checks that in each N-M range, N <= M.
    """
    if not port_range or not isinstance(port_range, str):
        return False
    if not PORT_RANGE_PATTERN.match(port_range):
        return False
    # Strip leading 'swp' for numeric validation
    numeric_part = re.sub(r"^swp", "", port_range)
    segments = numeric_part.split(",")
    for seg in segments:
        if not seg:
            return False
        if "-" in seg:
            bounds = seg.split("-")
            if len(bounds) != 2 or not bounds[0].isdigit() or not bounds[1].isdigit():
                return False
            if int(bounds[0]) > int(bounds[1]):
                return False
    return True


def _read_config(project_root: Path, arch: str, switch_name: str) -> str:
    """Read a reference config file from REFERENCES/&lt;arch&gt;/configs/."""
    config_path = (
        project_root
        / "REFERENCES"
        / arch
        / "configs"
        / f"{switch_name}.sh"
    )
    if not config_path.exists():
        pytest.skip(f"Config file not found: {config_path}")
    return config_path.read_text()


def _extract_sections(config_text: str) -> set:
    """Extract the set of top-level NVUE sections from a config file.

    For example, from 'nv set bridge domain ...' extracts 'bridge'.
    """
    sections = set()
    for line in config_text.splitlines():
        line = line.strip()
        if not line.startswith("nv set "):
            continue
        m = SECTION_RE.match(line)
        if m:
            sections.add(m.group(1))
    return sections


# ===========================================================================
# TestConfigurationValidation -- format & positive validation
# ===========================================================================
class TestConfigurationValidation:
    """Test suite for validating generated configurations."""

    def test_cli_config_has_nv_commands(self, sample_nvue_cli_config):
        """Test that generated CLI config has nv set commands."""
        assert "nv set" in sample_nvue_cli_config
        assert "nv config apply" in sample_nvue_cli_config

        lines = sample_nvue_cli_config.strip().split("\n")
        nv_commands = [l for l in lines if l.strip().startswith("nv set")]
        assert len(nv_commands) > 0

    def test_nvue_command_format(self):
        """Test that NVUE commands follow correct format."""
        commands = [
            "nv set system hostname test-switch",
            "nv set interface swp1 link state up",
            "nv set vrf default router bgp enable on",
        ]
        for cmd in commands:
            assert cmd.startswith("nv set")
            parts = cmd.split()
            assert len(parts) >= 4

    def test_ip_address_validation(self):
        """Test validation of valid IP addresses."""
        valid_ips = [
            "10.10.10.1/32",
            "192.168.1.1/24",
            "172.16.0.0/16",
            "10.0.0.1",
            "0.0.0.0/0",
            "255.255.255.255/32",
        ]
        for ip in valid_ips:
            assert _validate_ip_strict(ip), f"Expected valid IP: {ip}"

    def test_mac_address_validation(self):
        """Test validation of valid MAC addresses."""
        valid_macs = [
            "44:38:39:ff:00:ff",
            "00:11:22:33:44:55",
            "aa:bb:cc:dd:ee:ff",
            "48:b0:2d:a1:b2:c3",
        ]
        for mac in valid_macs:
            assert _validate_mac(mac), f"Expected valid MAC: {mac}"

    def test_vlan_id_validation(self):
        """Test validation of valid VLAN IDs."""
        valid_vlans = [1, 100, 200, 300, 4000, 4094]
        for vlan in valid_vlans:
            assert _validate_vlan_id(vlan), f"Expected valid VLAN: {vlan}"

    def test_bgp_asn_validation(self):
        """Test validation of valid BGP ASN values."""
        valid_asns = [1, 65001, 65100, 65535, 4200000000, 4294967294]
        for asn in valid_asns:
            assert _validate_bgp_asn(asn), f"Expected valid ASN: {asn}"

    def test_port_range_validation(self):
        """Test validation of valid port ranges."""
        valid_ranges = [
            "swp1-6",
            "swp10-17",
            "swp1-6,10-17,28-40",
            "swp49-52",
            "swp1",
        ]
        for port_range in valid_ranges:
            assert _validate_port_range(port_range), f"Expected valid range: {port_range}"


# ===========================================================================
# TestInvalidInputs -- negative test cases (fix #18)
# ===========================================================================
class TestInvalidInputs:
    """Negative tests for input validation -- invalid values must be rejected."""

    # -- Invalid VLAN IDs --
    @pytest.mark.parametrize(
        "vlan",
        [0, 4095, -1, "abc", "", None, 99999],
        ids=["zero", "4095", "negative", "non-numeric", "empty-str", "none", "huge"],
    )
    def test_invalid_vlan_ids(self, vlan):
        """VLAN IDs outside 1-4094 or non-numeric must be rejected."""
        assert not _validate_vlan_id(vlan), f"Should reject VLAN: {vlan!r}"

    # -- Invalid BGP ASNs --
    @pytest.mark.parametrize(
        "asn",
        [0, -1, -65535, 65536, 4199999999, 4294967295, "abc", "", None],
        ids=[
            "zero",
            "negative",
            "neg-large",
            "gap-start",
            "gap-end",
            "above-max",
            "non-numeric",
            "empty-str",
            "none",
        ],
    )
    def test_invalid_bgp_asns(self, asn):
        """BGP ASNs outside valid 2-byte or 4-byte ranges must be rejected."""
        assert not _validate_bgp_asn(asn), f"Should reject ASN: {asn!r}"

    # -- Invalid MAC addresses --
    @pytest.mark.parametrize(
        "mac",
        [
            "GG:HH:II:JJ:KK:LL",
            "00:11:22:33:44",
            "00:11:22:33:44:55:66",
            "001122334455",
            "00-11-22-33-44-55",
            "",
            None,
            "zz:zz:zz:zz:zz:zz",
        ],
        ids=[
            "invalid-hex",
            "too-short",
            "too-long",
            "no-colons",
            "dash-separated",
            "empty-str",
            "none",
            "invalid-chars",
        ],
    )
    def test_invalid_mac_addresses(self, mac):
        """Malformed or wrong-length MACs must be rejected."""
        assert not _validate_mac(mac), f"Should reject MAC: {mac!r}"

    # -- Invalid port ranges --
    @pytest.mark.parametrize(
        "port_range",
        [
            "swp10-1",
            "",
            None,
            "swp",
            "swp-1",
            "abc",
            "swp1--2",
            "1-2-3",
        ],
        ids=[
            "backward-range",
            "empty-str",
            "none",
            "swp-only",
            "swp-dash-num",
            "no-swp-prefix-alpha",
            "double-dash",
            "triple-segment",
        ],
    )
    def test_invalid_port_ranges(self, port_range):
        """Backward ranges, empty strings, and malformed formats must be rejected."""
        assert not _validate_port_range(port_range), f"Should reject range: {port_range!r}"

    # -- Invalid IP addresses --
    @pytest.mark.parametrize(
        "ip",
        [
            "999.999.999.999",
            "not-an-ip",
            "",
            None,
            "256.1.1.1",
            "1.2.3",
            "1.2.3.4.5",
            "1.2.3.4/33",
            "1.2.3.4/abc",
            "192.168.1.1//24",
        ],
        ids=[
            "all-999",
            "alpha",
            "empty-str",
            "none",
            "octet-256",
            "three-octets",
            "five-octets",
            "prefix-33",
            "prefix-alpha",
            "double-slash",
        ],
    )
    def test_invalid_ip_addresses(self, ip):
        """IPs with out-of-range octets, wrong format, or bad prefixes must be rejected."""
        assert not _validate_ip_strict(ip), f"Should reject IP: {ip!r}"

    # -- Invalid hostnames (uses is_valid_hostname from scripts/utils.py) --
    @pytest.mark.parametrize(
        "hostname",
        [
            "host name",
            "host@name",
            "",
            "host name!",
            " leading-space",
            "trailing-space ",
            "-leading-dash",
            "trailing-dash-",
        ],
        ids=[
            "space-in-middle",
            "at-sign",
            "empty-str",
            "exclamation",
            "leading-space",
            "trailing-space",
            "leading-dash",
            "trailing-dash",
        ],
    )
    def test_invalid_hostnames(self, hostname):
        """Hostnames with spaces, special chars, or empty must be rejected."""
        assert not is_valid_hostname(hostname), f"Should reject hostname: {hostname!r}"


# ===========================================================================
# TestConfigurationConsistency
# ===========================================================================
class TestConfigurationConsistency:
    """Test consistency across configurations."""

    def test_vlan_vni_mapping_consistency(self):
        """Test that VLAN to VNI mappings follow ERA convention: VNI = VLAN + 4000."""
        vlan_config = [
            {"id": "100", "vni": "4100"},
            {"id": "200", "vni": "4200"},
            {"id": "300", "vni": "4300"},
        ]
        for config in vlan_config:
            vlan_id = int(config["id"])
            vni = int(config["vni"])
            expected_vni = vlan_id + 4000
            assert vni == expected_vni, f"Inconsistent VNI mapping for VLAN {vlan_id}"

    def test_interface_naming_consistency(self):
        """Test that interface names follow consistent patterns."""
        interfaces = ["swp1", "swp2", "swp49", "bond1", "vlan100", "lo"]
        valid_patterns = [
            r"^swp\d+$",
            r"^bond\d+$",
            r"^vlan\d+$",
            r"^lo$",
            r"^eth\d+$",
        ]
        for iface in interfaces:
            assert any(
                re.match(pattern, iface) for pattern in valid_patterns
            ), f"Invalid interface name: {iface}"

    def test_vrf_naming_consistency(self):
        """Test that VRF names are consistent."""
        valid_vrfs = ["default", "mgmt", "EXIT", "INBAND", "OOB"]
        for vrf in valid_vrfs:
            assert vrf.replace("_", "").isalnum() or vrf in [
                "default",
                "mgmt",
            ], f"Invalid VRF name: {vrf}"


# ===========================================================================
# TestConfigurationCompleteness -- tests against real reference configs
# ===========================================================================

# Required NVUE sections per switch role
CORE_REQUIRED_SECTIONS = {"system", "interface", "bridge", "nve", "evpn", "router", "vrf"}
OOB_REQUIRED_SECTIONS = {"system", "interface", "bridge", "vrf"}


def _build_core_params():
    """Build pytest parametrize args for core switches across all architectures."""
    params = []
    for arch in COLLAPSED_CORE_ARCHS:
        for switch in ARCH_CORE_SWITCHES[arch]:
            params.append(pytest.param(arch, switch, id=f"{arch}/{switch}"))
    return params


def _build_oob_params():
    """Build pytest parametrize args for OOB switches across all architectures."""
    params = []
    for arch in COLLAPSED_CORE_ARCHS:
        for switch in ARCH_OOB_SWITCHES[arch]:
            params.append(pytest.param(arch, switch, id=f"{arch}/{switch}"))
    return params


class TestConfigurationCompleteness:
    """Test that reference configurations have all required sections.

    Reads actual config files from REFERENCES/&lt;arch&gt;/configs/ and
    verifies that the expected NVUE top-level sections are present.
    """

    @pytest.mark.parametrize("arch, switch", _build_core_params())
    def test_required_core_switch_sections(self, project_root, arch, switch):
        """Core switch config must contain system, interface, bridge, nve, evpn, router, vrf."""
        config_text = _read_config(project_root, arch, switch)
        sections = _extract_sections(config_text)

        missing = CORE_REQUIRED_SECTIONS - sections
        assert not missing, (
            f"{arch}/{switch}: missing required sections: {sorted(missing)}"
        )

    @pytest.mark.parametrize("arch, switch", _build_oob_params())
    def test_required_oob_switch_sections(self, project_root, arch, switch):
        """OOB switch config must contain system, interface, bridge, vrf."""
        config_text = _read_config(project_root, arch, switch)
        sections = _extract_sections(config_text)

        missing = OOB_REQUIRED_SECTIONS - sections
        assert not missing, (
            f"{arch}/{switch}: missing required sections: {sorted(missing)}"
        )

    @pytest.mark.parametrize("arch, switch", _build_core_params())
    def test_core_has_hostname(self, project_root, arch, switch):
        """Core switch config must set the system hostname."""
        config_text = _read_config(project_root, arch, switch)
        assert re.search(
            r"^nv set system hostname \S+", config_text, re.MULTILINE
        ), f"{arch}/{switch}: missing 'nv set system hostname'"

    @pytest.mark.parametrize("arch, switch", _build_oob_params())
    def test_oob_has_hostname(self, project_root, arch, switch):
        """OOB switch config must set the system hostname."""
        config_text = _read_config(project_root, arch, switch)
        assert re.search(
            r"^nv set system hostname \S+", config_text, re.MULTILINE
        ), f"{arch}/{switch}: missing 'nv set system hostname'"

    @pytest.mark.parametrize("arch, switch", _build_core_params())
    def test_core_has_timezone(self, project_root, arch, switch):
        """Core switch config must set the system timezone."""
        config_text = _read_config(project_root, arch, switch)
        assert re.search(
            r"^nv set system timezone \S+", config_text, re.MULTILINE
        ), f"{arch}/{switch}: missing 'nv set system timezone'"

    @pytest.mark.parametrize("arch, switch", _build_oob_params())
    def test_oob_has_timezone(self, project_root, arch, switch):
        """OOB switch config must set the system timezone."""
        config_text = _read_config(project_root, arch, switch)
        assert re.search(
            r"^nv set system timezone \S+", config_text, re.MULTILINE
        ), f"{arch}/{switch}: missing 'nv set system timezone'"

    @pytest.mark.parametrize("arch, switch", _build_core_params())
    def test_core_has_bgp(self, project_root, arch, switch):
        """Core switch config must have BGP autonomous-system and router-id."""
        config_text = _read_config(project_root, arch, switch)
        assert re.search(
            r"^nv set router bgp autonomous-system \d+", config_text, re.MULTILINE
        ), f"{arch}/{switch}: missing BGP autonomous-system"
        assert re.search(
            r"^nv set router bgp router-id \S+", config_text, re.MULTILINE
        ), f"{arch}/{switch}: missing BGP router-id"

    @pytest.mark.parametrize("arch, switch", _build_core_params())
    def test_core_has_evpn(self, project_root, arch, switch):
        """Core switch config must enable EVPN and multihoming."""
        config_text = _read_config(project_root, arch, switch)
        assert "nv set evpn enable on" in config_text, (
            f"{arch}/{switch}: missing 'nv set evpn enable on'"
        )
        assert "nv set evpn multihoming enable on" in config_text, (
            f"{arch}/{switch}: missing 'nv set evpn multihoming enable on'"
        )

    @pytest.mark.parametrize("arch, switch", _build_core_params())
    def test_core_has_nve_vxlan(self, project_root, arch, switch):
        """Core switch config must enable NVE VxLAN."""
        config_text = _read_config(project_root, arch, switch)
        assert re.search(
            r"^nv set nve vxlan enable on", config_text, re.MULTILINE
        ), f"{arch}/{switch}: missing NVE VxLAN enable"
        assert re.search(
            r"^nv set nve vxlan source address \S+", config_text, re.MULTILINE
        ), f"{arch}/{switch}: missing NVE VxLAN source address"

    @pytest.mark.parametrize("arch, switch", _build_oob_params())
    def test_oob_has_vlan_svi(self, project_root, arch, switch):
        """OOB switch config must have a VLAN SVI (vlan200) with an IP address."""
        config_text = _read_config(project_root, arch, switch)
        assert re.search(
            r"^nv set interface vlan200 ip address \S+", config_text, re.MULTILINE
        ), f"{arch}/{switch}: missing vlan200 SVI IP address"

    @pytest.mark.parametrize("arch, switch", _build_oob_params())
    def test_oob_has_bridge_vlan(self, project_root, arch, switch):
        """OOB switch config must configure bridge VLAN 200."""
        config_text = _read_config(project_root, arch, switch)
        assert re.search(
            r"^nv set bridge domain br_default vlan 200", config_text, re.MULTILINE
        ), f"{arch}/{switch}: missing bridge VLAN 200"
