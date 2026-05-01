#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Validate generated configs against architecture requirements.

Requirements come from docs/requirements/ (common.yml + <arch>.yml) which
contain ONLY values explicitly stated in the architecture PDFs.

Usage:
    python3 scripts/validate_requirements.py --arch 2-8-5-200
    python3 scripts/validate_requirements.py  # validates all architectures
"""
import argparse
import re
import sys
from pathlib import Path

import yaml


class Result:
    def __init__(self):
        self.passes = []
        self.failures = []
        self.warnings = []

    def ok(self, msg):
        self.passes.append(msg)

    def fail(self, msg):
        self.failures.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    @property
    def success(self):
        return len(self.failures) == 0


def _load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def _sorted_ints(lst):
    return sorted(int(x) for x in lst)


# ---------------------------------------------------------------------------
# Checks against common.yml (PDF-sourced)
# ---------------------------------------------------------------------------

def check_vlans(common, core, result):
    """Validate VLAN IDs and VNI mappings."""
    gen_vlans = set(core.get('vlans', []))
    gen_vnis = core.get('vnis', {})

    for vlan_id_str, spec in common.get('vlans', {}).items():
        vlan_id = int(vlan_id_str)
        expected_vni = spec['vni']

        if vlan_id in gen_vlans:
            result.ok(f"VLAN {vlan_id} ({spec['name']}) present")
        else:
            result.fail(f"VLAN {vlan_id} ({spec['name']}) MISSING")

        actual_vni = gen_vnis.get(vlan_id) or gen_vnis.get(str(vlan_id))
        if actual_vni == expected_vni:
            result.ok(f"VLAN {vlan_id} VNI {expected_vni} correct")
        elif actual_vni is not None:
            result.fail(f"VLAN {vlan_id} VNI: expected {expected_vni}, got {actual_vni}")
        else:
            result.fail(f"VLAN {vlan_id} VNI {expected_vni} MISSING")


def check_vrfs(common, core, result):
    """Validate VRF L3 VNI mappings."""
    gen_vrf_vnis = core.get('vrf_vnis', {})

    for vrf_name, spec in common.get('vrfs', {}).items():
        expected_vni = spec['l3_vni']
        actual_vni = gen_vrf_vnis.get(vrf_name)

        if actual_vni == expected_vni:
            result.ok(f"VRF {vrf_name} L3 VNI {expected_vni} correct")
        elif actual_vni is not None:
            result.fail(f"VRF {vrf_name} L3 VNI: expected {expected_vni}, got {actual_vni}")
        else:
            result.fail(f"VRF {vrf_name} L3 VNI {expected_vni} MISSING")


def check_evpn_mac(common, core, result):
    """Validate EVPN multihoming MAC."""
    expected = common.get('evpn', {}).get('multihoming_mac')
    actual = core.get('mh_mac')

    if not expected:
        return

    if actual and actual.upper() == expected.upper():
        result.ok(f"EVPN MH MAC {expected} correct")
    elif actual:
        result.fail(f"EVPN MH MAC: expected {expected}, got {actual}")
    else:
        result.fail(f"EVPN MH MAC {expected} MISSING")


def check_loopback(common, config_lines, result):
    """Validate core-01 loopback IP."""
    expected = common.get('loopbacks', {}).get('core-01')
    if not expected:
        return

    if any(f'{expected}' in l and 'lo' in l for l in config_lines):
        result.ok(f"Loopback core-01 = {expected} correct")
    else:
        result.fail(f"Loopback core-01 = {expected} MISSING from config")


def check_bgp_community(common, config_lines, result):
    """Validate BGP community value."""
    community = common.get('bgp', {}).get('community')
    if not community:
        return

    if any(f'community {community}' in l for l in config_lines):
        result.ok(f"BGP community {community} present")
    else:
        result.fail(f"BGP community {community} MISSING")


def check_route_policy(common, config_lines, result):
    """Validate route maps and prefix lists exist."""
    rp = common.get('route_policy', {})

    for name in rp.get('prefix_lists', {}):
        if any(f'prefix-list {name}' in l for l in config_lines):
            result.ok(f"Prefix-list {name} present")
        else:
            result.fail(f"Prefix-list {name} MISSING")

    for name in rp.get('route_maps', {}):
        if any(f'route-map {name}' in l for l in config_lines):
            result.ok(f"Route-map {name} present")
        else:
            result.fail(f"Route-map {name} MISSING")


def check_qos(common, config_lines, result):
    """Validate QoS buffer split."""
    qos = common.get('qos', {})
    rdma_pct = qos.get('buffer_rdma_percent')
    lossy_pct = qos.get('buffer_lossy_percent')

    if rdma_pct and any(f'roce-lossless memory-percent {rdma_pct}' in l for l in config_lines):
        result.ok(f"QoS roce-lossless {rdma_pct}% correct")
    elif rdma_pct:
        result.fail(f"QoS roce-lossless {rdma_pct}% MISSING")

    if lossy_pct and any(f'default-lossy memory-percent {lossy_pct}' in l for l in config_lines):
        result.ok(f"QoS default-lossy {lossy_pct}% correct")
    elif lossy_pct:
        result.fail(f"QoS default-lossy {lossy_pct}% MISSING")

    # PFC watchdog — PDF says "all host-facing interfaces"
    if any('pfc-watchdog' in l and 'enable' in l for l in config_lines):
        result.ok("PFC watchdog enabled on interfaces")
    else:
        result.fail("PFC watchdog MISSING from config")


def check_evpn_features(common, config_lines, result):
    """Validate EVPN features: state, multihoming, ARP suppression."""
    evpn = common.get('evpn_features', {})

    if evpn.get('state') == 'enabled':
        if any('evpn state enabled' in l or 'evpn enable on' in l for l in config_lines):
            result.ok("EVPN state enabled")
        else:
            result.fail("EVPN state enabled MISSING")

    if evpn.get('multihoming_state') == 'enabled':
        if any('evpn multihoming state enabled' in l or 'evpn multihoming enable on' in l for l in config_lines):
            result.ok("EVPN multihoming state enabled")
        else:
            result.fail("EVPN multihoming state enabled MISSING")

    if evpn.get('arp_suppression'):
        if any('arp-nd-suppress' in l for l in config_lines):
            result.ok("ARP suppression configured")
        else:
            result.warn("ARP suppression NOT in generated config (may be default in 5.16)")

    if evpn.get('head_end_replication'):
        # Verified by NVE source address being set (VTEP)
        if any('nve vxlan source' in l for l in config_lines):
            result.ok("NVE VXLAN source (head-end replication) configured")
        else:
            result.fail("NVE VXLAN source address MISSING (head-end replication)")


def check_bridge(common, config_lines, result):
    """Validate bridge type."""
    bridge = common.get('bridge', {})
    if bridge.get('type') == 'vlan-aware':
        if any('bridge domain br_default type vlan-aware' in l for l in config_lines):
            result.ok("Bridge type vlan-aware correct")
        else:
            result.fail("Bridge type vlan-aware MISSING")


def check_inter_vrf(common, config_lines, result):
    """Validate inter-VRF route leaking and filters."""
    ivr = common.get('inter_vrf_routing', {})
    if not ivr:
        return

    # Check route import statements
    for src_vrf in ivr.get('exit_imports_from', []):
        if any(f'EXIT' in l and 'route-import' in l and src_vrf in l for l in config_lines):
            result.ok(f"EXIT VRF imports from {src_vrf}")
        else:
            # Also check via route-import from-vrf list
            if any(f'EXIT' in l and 'from-vrf' in l and 'list' in l and src_vrf in l for l in config_lines):
                result.ok(f"EXIT VRF imports from {src_vrf}")
            else:
                result.warn(f"EXIT VRF import from {src_vrf} — not directly verifiable in config lines")

    # Check filters
    for filter_name in ivr.get('filters', {}):
        if any(f'route-map {filter_name}' in l for l in config_lines):
            result.ok(f"Route filter {filter_name} present")
        else:
            result.fail(f"Route filter {filter_name} MISSING")


def check_dhcp_relay(common, config_lines, result):
    """Validate DHCP relay configuration."""
    dr = common.get('dhcp_relay', {})
    if not dr:
        return

    if dr.get('exit_vrf_relay'):
        if any('dhcp-relay' in l and 'EXIT' in l for l in config_lines):
            result.ok("DHCP relay in EXIT VRF configured")
        else:
            result.warn("DHCP relay EXIT VRF — not found in config (may depend on exit_dhcp_servers setting)")


def check_telemetry(common, config_lines, result):
    """Validate telemetry/histogram configuration."""
    telem = common.get('telemetry', {})
    if not telem:
        return

    if telem.get('histogram_collection'):
        if any('histogram' in l for l in config_lines):
            result.ok("Telemetry histogram configuration present")
        else:
            result.warn("Telemetry histogram NOT in generated config")

    if any('telemetry state enabled' in l for l in config_lines):
        result.ok("Telemetry state enabled")
    else:
        result.warn("Telemetry state enabled NOT in config")


def check_bond_esi(common, core, config_lines, result):
    """Validate bond naming pattern and ESI formula."""
    bn = common.get('bond_naming', {})
    if not bn:
        return

    # Check that bonds follow bondXsY naming
    bond_lines = [l for l in config_lines if 'bond' in l and 'member' in l]
    if bond_lines:
        # Verify pattern: bond<N>s<M> bond member swp<N>s<M>
        correct = 0
        wrong = 0
        for l in bond_lines:
            m = re.search(r'bond(\d+)s(\d+) bond member swp(\d+)s(\d+)', l)
            if m and m.group(1) == m.group(3) and m.group(2) == m.group(4):
                correct += 1
            elif m:
                wrong += 1
        if correct > 0 and wrong == 0:
            result.ok(f"Bond naming bondXsY=swpXsY pattern correct ({correct} bonds)")
        elif wrong > 0:
            result.fail(f"Bond naming: {wrong} bonds don't match bondXsY=swpXsY pattern")
    else:
        result.warn("No bond member lines found in config")

    # Check ESI formula: local-id should be X*10+Y
    esi_lines = [l for l in config_lines if 'segment local-id' in l]
    if esi_lines:
        correct = 0
        wrong = 0
        for l in esi_lines:
            m = re.search(r'bond(\d+)s(\d+).*local-id (\d+)', l)
            if m:
                expected_esi = int(m.group(1)) * 10 + int(m.group(2))
                actual_esi = int(m.group(3))
                if actual_esi == expected_esi:
                    correct += 1
                else:
                    wrong += 1
        if correct > 0 and wrong == 0:
            result.ok(f"ESI local-id formula (X*10+Y) correct ({correct} bonds)")
        elif wrong > 0:
            result.fail(f"ESI local-id: {wrong} bonds have wrong local-id (expected X*10+Y)")


# ---------------------------------------------------------------------------
# Checks against per-arch YAML (PDF-sourced)
# ---------------------------------------------------------------------------

def check_port_role(role_name, spec, gen_data, result):
    """Validate a single port role."""
    if gen_data is None:
        result.fail(f"{role_name}: role MISSING entirely from generated config")
        return

    # Ports
    expected_ports = _sorted_ints(spec.get('ports', []))
    actual_ports = _sorted_ints(gen_data.get('ports', []))
    if actual_ports == expected_ports:
        result.ok(f"{role_name} ports {expected_ports} correct")
    else:
        missing = sorted(set(expected_ports) - set(actual_ports))
        extra = sorted(set(actual_ports) - set(expected_ports))
        if missing:
            result.fail(f"{role_name} ports MISSING: {missing}")
        if extra:
            result.warn(f"{role_name} ports EXTRA: {extra}")
        if not missing and not extra:
            result.ok(f"{role_name} ports correct")

    # Breakout
    expected_bo = spec.get('breakout')
    actual_bo = gen_data.get('breakout')
    if expected_bo is not None:
        if actual_bo == expected_bo:
            result.ok(f"{role_name} breakout {expected_bo}x correct")
        else:
            result.fail(f"{role_name} breakout: expected {expected_bo}x, got {actual_bo}x")

    # Lanes
    expected_lanes = spec.get('lanes')
    actual_lanes = gen_data.get('lanes')
    if expected_lanes is not None:
        if actual_lanes == expected_lanes:
            result.ok(f"{role_name} lanes {expected_lanes} correct")
        else:
            result.fail(f"{role_name} lanes: expected {expected_lanes}, got {actual_lanes}")


def check_core_ports(arch_spec, core, result):
    """Validate all core switch port role assignments."""
    spec_ports = arch_spec.get('core_ports', {})
    network_roles = core.get('network_roles', {})
    gpu_if = core.get('gpu_interfaces')
    isl_if = core.get('isl_interfaces')
    edge_if = core.get('edge_interfaces')

    role_mapping = {
        'cpu': network_roles.get('cpu'),
        'gpu': gpu_if,
        'support': network_roles.get('support'),
        'isl': isl_if,
        'oob_uplink': network_roles.get('oob'),
        'storage': network_roles.get('storage'),
        'edge': edge_if,
    }

    for role_name, spec in spec_ports.items():
        if role_name in ('disabled', 'spare'):
            continue
        gen_data = role_mapping.get(role_name)
        check_port_role(role_name, spec, gen_data, result)

    # Disabled ports
    disabled_spec = spec_ports.get('disabled', {})
    expected_disabled = _sorted_ints(disabled_spec.get('ports', []))
    actual_disabled = _sorted_ints(core.get('interfaces_disabled', []))

    if expected_disabled:
        missing = sorted(set(expected_disabled) - set(actual_disabled))
        extra = sorted(set(actual_disabled) - set(expected_disabled))
        if not missing and not extra:
            result.ok(f"Disabled ports {expected_disabled} correct")
        else:
            if missing:
                result.fail(f"Disabled ports MISSING: {missing}")
            if extra:
                result.warn(f"Disabled ports EXTRA (not in arch doc): {extra}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def validate_arch(arch, site, project_root):
    req_dir = project_root / 'docs' / 'requirements'
    output_dir = project_root / 'output' / arch / site

    common = _load_yaml(req_dir / 'common.yml')
    arch_spec = _load_yaml(req_dir / f'{arch}.yml')

    core_yml = output_dir / 'inventory' / 'group_vars' / 'core.yml'

    if not core_yml.exists():
        print(f"  SKIP: {core_yml} not found (run 'make generate ARCH={arch}' first)")
        return None

    core = _load_yaml(core_yml)

    # Find the first core switch config file.
    # The filename uses the OEM hostname (e.g., spine01-config.sh),
    # not the Ansible host name (core-01). Look up the hostname from
    # host_vars, then fall back to scanning the configs directory.
    config_sh = None
    host_vars_dir = output_dir / 'inventory' / 'host_vars'
    core01_vars = host_vars_dir / 'core-01.yml'
    if core01_vars.exists():
        hv = _load_yaml(core01_vars)
        oem_name = (hv or {}).get('hostname', 'core-01')
        candidate = output_dir / 'configs' / f'{oem_name}-config.sh'
        if candidate.exists():
            config_sh = candidate
    # Fallback: grab the first *-config.sh in configs/
    if config_sh is None:
        configs_dir = output_dir / 'configs'
        if configs_dir.is_dir():
            for f in sorted(configs_dir.glob('*-config.sh')):
                config_sh = f
                break

    config_lines = []
    if config_sh and config_sh.exists():
        config_lines = [l.strip() for l in config_sh.read_text().splitlines()]
    else:
        print(f"  ⚠️  No core switch config found in {output_dir / 'configs'}/")
        print(f"     Run 'make generate ARCH={arch}' first.")

    result = Result()

    # Common checks (from PDFs)
    check_vlans(common, core, result)
    check_vrfs(common, core, result)
    check_evpn_mac(common, core, result)
    check_loopback(common, config_lines, result)
    check_bgp_community(common, config_lines, result)
    check_route_policy(common, config_lines, result)
    check_qos(common, config_lines, result)

    # EVPN, bridge, inter-VRF, DHCP relay, telemetry, bonds
    check_evpn_features(common, config_lines, result)
    check_bridge(common, config_lines, result)
    check_inter_vrf(common, config_lines, result)
    check_dhcp_relay(common, config_lines, result)
    check_telemetry(common, config_lines, result)
    check_bond_esi(common, core, config_lines, result)

    # Per-arch checks (from PDFs)
    check_core_ports(arch_spec, core, result)

    return result


def main():
    parser = argparse.ArgumentParser(
        description='Validate generated configs against architecture requirements (PDF-sourced)'
    )
    parser.add_argument('--arch', help='Architecture to validate (validates all if omitted)')
    parser.add_argument('--site', default='default', help='Site name (default: default)')
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    req_dir = project_root / 'docs' / 'requirements'

    if args.arch:
        archs = [args.arch]
    else:
        archs = sorted(
            p.stem for p in req_dir.glob('*.yml')
            if p.stem != 'common'
        )

    all_passed = True

    for arch in archs:
        req_file = req_dir / f'{arch}.yml'
        if not req_file.exists():
            print(f"\n  No requirements file for {arch}, skipping")
            continue

        print(f"\n{'=' * 60}")
        print(f"  {arch} (site={args.site})")
        print(f"  Source: {_load_yaml(req_file).get('source_document', 'unknown')}")
        print(f"{'=' * 60}")

        result = validate_arch(arch, args.site, project_root)
        if result is None:
            all_passed = False
            continue

        if result.failures:
            print(f"\n  FAILURES ({len(result.failures)}):")
            for msg in result.failures:
                print(f"    FAIL  {msg}")

        if result.warnings:
            print(f"\n  WARNINGS ({len(result.warnings)}):")
            for msg in result.warnings:
                print(f"    WARN  {msg}")

        total = len(result.passes) + len(result.failures) + len(result.warnings)
        print(f"\n  {len(result.passes)} passed, {len(result.failures)} failed, {len(result.warnings)} warnings ({total} checks)")
        print(f"  {'PASS' if result.success else 'FAIL'}")

        if not result.success:
            all_passed = False

    print(f"\n{'=' * 60}")
    print(f"  {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    print(f"{'=' * 60}")
    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
