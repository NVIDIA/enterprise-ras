#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Generate OCP-flavored Ansible inventory from ERA net-configurator output.

Reads the ERA inventory produced by `make generate` and writes an OCP-grouped
Ansible inventory + Agent-Based Installer manifests under output/<arch>/<site>/ocp/.

Node role resolution (priority order):
  1. ocp-settings.yml node_roles  (explicit, required for production)
  2. Auto-inferred from hostname prefix (fallback — see warning below):
       k8s-*       -> control_plane
       su-*-node-* -> worker_gpu
       storage-*   -> worker_storage
       support-*   -> infra  (WARNING: support nodes may serve as control_plane;
                               use ocp-settings.yml to assign the split explicitly)

GPU node networking — Stage 1 / Stage 2 split:
  Stage 1 (ABI): agent-config.yaml networkConfig contains bond0 (CPU/N-S) only.
                 GPU rail interfaces are excluded — RHCOS during bootstrap may lack
                 drivers for the B3140 400G NICs, and E/W misconfiguration can
                 disrupt cluster formation.
  Stage 2 (Day-2): Apply ocp/day2/nncp-*-gpu-rails.yaml after the NVIDIA Network
                   Operator is installed and healthy.  These NodeNetworkConfigurationPolicy
                   CRs configure per-rail interfaces with correct PBR routing rules
                   (one routing table per rail, ip-from rule per NIC).

Writes:
  output/<arch>/<site>/ocp/
  ├── inventory/
  │   ├── hosts.yml                     OCP-grouped YAML inventory (ansible_host per node)
  │   ├── host_vars/<node>.yml          NMState networkConfig (Stage 1 / bond0 only for GPU nodes)
  │   └── group_vars/all/ocp.yml        OCP cluster vars for Ansible roles
  ├── agent-config.yaml                 ABI per-node config (if ocp-settings.yml present)
  ├── install-config.yaml               ABI cluster manifest (if pull_secret readable)
  └── day2/
      └── nncp-<node>-gpu-rails.yaml    Stage-2 NodeNetworkConfigurationPolicy CRs
                                        (GPU rail interfaces + PBR; apply after NMState Operator)

Usage:
    python3 scripts/generate-ocp-inventory.py --arch 2-8-5-200 [--site default]
    python3 scripts/generate-ocp-inventory.py --arch 2-8-5-200 --site kicktires \\
        --ocp-settings input/2-8-5-200/kicktires/ocp-settings.yml
"""

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Architecture-level GPU boot disk defaults.
# OEM-specific control_plane/infra/storage disks come from ocp-settings.yml.
# See: era-ocp-configurator/vars/arch-oem-disk-defaults.yml for the full table.
# ---------------------------------------------------------------------------
GPU_DISK_DEFAULTS = {
    "2-4-3-200":    "/dev/nvme0n1",
    "2-4-5-800":    "/dev/nvme2n1",  # GB200 NVL72: E1.S cache drives enumerate first
    "2-8-5-200":    "/dev/nvme0n1",
    "2-8-9-400":    "/dev/nvme0n1",  # UNVERIFIED — OEM-dependent
    "2-8-9-400-SP": "/dev/nvme0n1",  # UNVERIFIED
    "2-8-9-800":    "/dev/nvme2n1",  # GB200 NVL72: same as 2-4-5-800
}

FALLBACK_DISK = "/dev/sda"

# Routing table IDs assigned per GPU rail for PBR (matches VLAN IDs 901-904).
GPU_RAIL_TABLE_BASE = 900

OCP_ROLES = ("control_plane", "infra", "worker_gpu", "worker_storage")

INSTALLER_ROLE = {
    "control_plane": "master",
    "infra":         "worker",
    "worker_gpu":    "worker",
    "worker_storage": "worker",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def write_yaml(path, data, header=None):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        if header:
            f.write(header + "\n")
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _parse_cidr(cidr):
    """Return (ip_str, prefix_int) from '172.16.178.201/24'."""
    ip, prefix = cidr.split("/")
    return ip, int(prefix)


def infer_ocp_role(hostname):
    """Auto-infer OCP role from ERA hostname prefix."""
    if hostname.startswith("k8s-"):
        return "control_plane"
    if re.match(r"su-\d+-node-", hostname):
        return "worker_gpu"
    if hostname.startswith("storage-"):
        return "worker_storage"
    if hostname.startswith("support-"):
        return "infra"
    return None


def resolve_disk(hostname, ocp_role, arch, overrides):
    """Four-step disk resolution: override → gpu-default → arch-fallback → /dev/sda.

    Returns (device_path, used_fallback).  Callers should aggregate used_fallback
    and emit a single summary warning rather than one warning per node.
    """
    if hostname in overrides:
        return overrides[hostname], False
    if ocp_role == "worker_gpu":
        dev = GPU_DISK_DEFAULTS.get(arch)
        if dev:
            return dev, False
    return FALLBACK_DISK, True


# ---------------------------------------------------------------------------
# NMState network config (mirrors era-ocp-configurator build_nmstate_network_config)
# ---------------------------------------------------------------------------

def build_nmstate_network_config(device_data, site_vars, ocp_role):
    """Return nmstate networkConfig dict for a node."""
    common     = site_vars.get("common", {})
    ifaces_map = device_data.get("interfaces", {})
    interfaces = []
    routes     = []
    rules      = []

    def _bond(members, cidr, gateway):
        if not (cidr and members):
            return
        ip, prefix = _parse_cidr(cidr)
        interfaces.append({
            "name": "bond0",
            "type": "bond",
            "state": "up",
            "ipv4": {
                "enabled": True,
                "dhcp": False,
                "address": [{"ip": ip, "prefix-length": prefix}],
            },
            "link-aggregation": {"mode": "active-backup", "port": list(members)},
        })
        if gateway:
            routes.append({
                "destination": "0.0.0.0/0",
                "next-hop-address": gateway,
                "next-hop-interface": "bond0",
            })

    if ocp_role in ("control_plane", "infra"):
        members = ifaces_map.get("support") or ifaces_map.get("cpu", [])
        cidr    = device_data.get("bond_ip1") or device_data.get("bond_ip")
        gw      = common.get("support_gateway") or common.get("cpu_gateway")
        _bond(members, cidr, gw)

    elif ocp_role == "worker_gpu":
        _bond(ifaces_map.get("cpu", []),
              device_data.get("bond_ip"),
              common.get("cpu_gateway"))
        # GPU rail interfaces (eth3+) are intentionally excluded from the ABI
        # networkConfig.  They are applied post-install via NNCP CRs in ocp/day2/.

    elif ocp_role == "worker_storage":
        members = ifaces_map.get("storage", [])
        cidr    = device_data.get("bond_ip1") or device_data.get("bond_ip")
        gw      = common.get("storage_gateway") or common.get("cpu_gateway")
        _bond(members, cidr, gw)

    config = {}
    if interfaces:
        config["interfaces"] = interfaces
    if routes:
        config["routes"] = {"config": routes}
    if rules:
        config["route-rules"] = {"config": rules}
    return config


# ---------------------------------------------------------------------------
# Stage-2 GPU rail config (NodeNetworkConfigurationPolicy)
# ---------------------------------------------------------------------------

def _build_gpu_rail_desiredstate(device_data, site_vars):
    """Return nmstate desiredState dict for GPU rail interfaces only.

    Handles both the structured gpu_interfaces list (explicit gateway + table per
    NIC) and the flat gpu_ips fallback (assigns routing tables 901-904 sequentially
    to match the per_rail VLAN numbering).  Returns None when no GPU data is present.
    """
    common         = site_vars.get("common", {})
    ifaces_map     = device_data.get("interfaces", {})
    gpu_ifaces_list = device_data.get("gpu_interfaces")
    gpu_ips_list   = device_data.get("gpu_ips")
    gpu_nic_names  = ifaces_map.get("gpu", [])

    interfaces, routes, rules = [], [], []

    if gpu_ifaces_list:
        for gi in gpu_ifaces_list:
            nic_ip, nic_prefix = _parse_cidr(gi["ip"])
            interfaces.append({
                "name": gi["iface"],
                "type": "ethernet",
                "state": "up",
                "ipv4": {
                    "enabled": True,
                    "dhcp": False,
                    "address": [{"ip": nic_ip, "prefix-length": nic_prefix}],
                },
            })
            routes.append({
                "destination": "0.0.0.0/0",
                "next-hop-address": gi["gateway"],
                "next-hop-interface": gi["iface"],
                "table-id": gi["table"],
            })
            rules.append({
                "ip-from": f"{nic_ip}/32",
                "route-table": gi["table"],
                "priority": 100,
            })

    elif gpu_ips_list and gpu_nic_names:
        gw = common.get("gpu_gateway") or common.get("cpu_gateway")
        for i, (nic_name, nic_cidr) in enumerate(zip(gpu_nic_names, gpu_ips_list)):
            table_id = GPU_RAIL_TABLE_BASE + i + 1  # 901, 902, 903, 904
            nic_ip, nic_prefix = _parse_cidr(nic_cidr)
            interfaces.append({
                "name": nic_name,
                "type": "ethernet",
                "state": "up",
                "ipv4": {
                    "enabled": True,
                    "dhcp": False,
                    "address": [{"ip": nic_ip, "prefix-length": nic_prefix}],
                },
            })
            if gw:
                routes.append({
                    "destination": "0.0.0.0/0",
                    "next-hop-address": gw,
                    "next-hop-interface": nic_name,
                    "table-id": table_id,
                })
            rules.append({
                "ip-from": f"{nic_ip}/32",
                "route-table": table_id,
                "priority": 100 + i,
            })

    else:
        return None

    state = {}
    if interfaces:
        state["interfaces"] = interfaces
    if routes:
        state["routes"] = {"config": routes}
    if rules:
        state["route-rules"] = {"config": rules}
    return state or None


def build_gpu_nncp(hostname, device_data, site_vars):
    """Return a NodeNetworkConfigurationPolicy CR dict for GPU rail interfaces.

    Returns None when the node has no GPU rail data (not a GPU node or data absent).
    """
    desired_state = _build_gpu_rail_desiredstate(device_data, site_vars)
    if desired_state is None:
        return None
    return {
        "apiVersion": "nmstate.io/v1",
        "kind":       "NodeNetworkConfigurationPolicy",
        "metadata":   {"name": f"{hostname}-gpu-rails"},
        "spec": {
            "nodeSelector": {"kubernetes.io/hostname": hostname},
            "desiredState": desired_state,
        },
    }


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------

def build_role_map(ocp_settings, devices, arch, site):
    """
    Return {hostname: ocp_role} for all OCP-managed nodes.

    Uses ocp_settings['node_roles'] if present; otherwise auto-infers from
    hostname prefix.  Warns when auto-inference produces no control_plane
    nodes (common for architectures without k8s-* hosts).
    """
    if ocp_settings and "node_roles" in ocp_settings:
        role_map = {}
        for ocp_role, hostnames in ocp_settings["node_roles"].items():
            for h in hostnames:
                role_map[h] = ocp_role
        return role_map

    # Auto-inference fallback
    print("  NOTE: no ocp-settings.yml node_roles found — auto-inferring OCP roles from hostnames.")
    role_map = {}
    for hostname in sorted(devices.keys()):
        role = infer_ocp_role(hostname)
        if role:
            role_map[hostname] = role

    if not any(r == "control_plane" for r in role_map.values()):
        print(
            "\n  WARNING: no control_plane nodes found via auto-inference.\n"
            "  This architecture has no k8s-* hosts.  To designate control plane nodes,\n"
            "  create input/{arch}/{site}/ocp-settings.yml with explicit node_roles.\n"
            "  See: era-ocp-configurator/input/ocp-settings.yml for the schema.\n".format(arch=arch, site=site),
            file=sys.stderr,
        )

    return role_map


def build_hosts_yaml(role_map, era_host_vars):
    """Build OCP-grouped YAML inventory dict with ansible_host per node."""
    groups = {role: {} for role in OCP_ROLES}
    for hostname, ocp_role in sorted(role_map.items()):
        if ocp_role not in groups:
            continue
        ansible_host = era_host_vars.get(hostname, {}).get("ansible_host", "")
        groups[ocp_role][hostname] = {"ansible_host": ansible_host} if ansible_host else {}

    return {
        "all": {
            "children": {
                f"ocp_{role}": {"hosts": hosts}
                for role, hosts in groups.items()
                if hosts
            }
        }
    }


def build_ocp_group_vars(ocp_settings, site_vars, ocp_out_dir):
    """Build group_vars/all/ocp.yml content dict."""
    common = site_vars.get("common", {})

    if ocp_settings and "cluster" in ocp_settings:
        cluster = ocp_settings["cluster"]
        all_nodes = []
        for hostnames in ocp_settings.get("node_roles", {}).values():
            all_nodes.extend(hostnames)
        return {
            "ocp_cluster_name":       cluster.get("name", ""),
            "ocp_cluster_domain":     cluster.get("domain", ""),
            "ocp_api_vip":            cluster.get("api_vip", ""),
            "ocp_ingress_vip":        cluster.get("ingress_vip", ""),
            "ocp_machine_network":    common.get("cpu_network", ""),
            "ocp_pull_secret_path":   ocp_settings.get("pull_secret_path", "~/.era-secrets/pull-secret.json"),
            "ocp_ssh_key_path":       ocp_settings.get("ssh_key_path", "~/.ssh/id_rsa.pub"),
            "ocp_node_hostnames":     all_nodes,
            "ocp_install_output_dir": str(ocp_out_dir),
        }

    # Stub — ocp-settings.yml not present
    return {
        "ocp_cluster_name":       "",
        "ocp_cluster_domain":     "",
        "ocp_api_vip":            "",
        "ocp_ingress_vip":        "",
        "ocp_machine_network":    common.get("cpu_network", ""),
        "ocp_pull_secret_path":   "~/.era-secrets/pull-secret.json",
        "ocp_ssh_key_path":       "~/.ssh/id_rsa.pub",
        "ocp_node_hostnames":     [],
        "ocp_install_output_dir": str(ocp_out_dir),
    }


def build_agent_config(ocp_settings, role_map, era_host_vars, site_vars, arch):
    """Render agent-config.yaml dict."""
    devices  = site_vars.get("devices", {})
    overrides = {}
    cluster_name = "ocp-era"
    oem = "dell"

    if ocp_settings:
        cluster_name = ocp_settings.get("cluster", {}).get("name", cluster_name)
        oem          = ocp_settings.get("oem", oem)
        overrides    = ocp_settings.get("install_disk", {}).get("overrides") or {}

    # rendezvous IP: first control_plane node's bond IP
    rendezvous_ip = None
    for hostname, ocp_role in role_map.items():
        if ocp_role == "control_plane":
            dev = devices.get(hostname, {})
            cidr = dev.get("bond_ip1") or dev.get("bond_ip")
            if cidr:
                rendezvous_ip, _ = _parse_cidr(cidr)
                break

    agent_hosts = []
    for hostname in sorted(role_map):
        ocp_role    = role_map[hostname]
        device_data = devices.get(hostname)
        if device_data is None:
            print(f"  WARNING: {hostname} not in devices block — skipping", file=sys.stderr)
            continue

        disk, _        = resolve_disk(hostname, ocp_role, arch, overrides)
        mac            = device_data.get("mac")
        network_config = build_nmstate_network_config(device_data, site_vars, ocp_role)

        agent_hosts.append({
            "hostname":        hostname,
            "role":            INSTALLER_ROLE[ocp_role],
            "rootDeviceHints": {"deviceName": disk},
            "interfaces":      [{"name": "eth0", "macAddress": mac}] if mac else [],
            "networkConfig":   network_config,
        })

    return {
        "apiVersion": "v1alpha1",
        "kind":       "AgentConfig",
        "metadata":   {"name": cluster_name},
        "rendezvousIP": rendezvous_ip,
        "hosts":      agent_hosts,
    }


def build_install_config(ocp_settings, site_vars, role_map):
    """Render install-config.yaml dict.  Returns None if pull_secret unreadable."""
    cluster = ocp_settings.get("cluster", {})
    common  = site_vars.get("common", {})

    pull_secret_path = os.path.expanduser(ocp_settings.get("pull_secret_path", ""))
    ssh_key_path     = os.path.expanduser(ocp_settings.get("ssh_key_path", ""))

    try:
        pull_secret = open(pull_secret_path).read().strip()
    except (FileNotFoundError, OSError) as exc:
        print(f"  NOTE: pull secret not readable ({exc}) — skipping install-config.yaml generation",
              file=sys.stderr)
        return None

    try:
        ssh_key = open(ssh_key_path).read().strip()
    except (FileNotFoundError, OSError) as exc:
        print(f"  NOTE: SSH key not readable ({exc}) — skipping install-config.yaml generation",
              file=sys.stderr)
        return None

    cp_count = sum(1 for r in role_map.values() if r == "control_plane")
    worker_count = sum(1 for r in role_map.values() if r != "control_plane")
    cpu_network  = common.get("cpu_network", "")

    return {
        "apiVersion": "v1",
        "baseDomain": cluster.get("domain", ""),
        "metadata":   {"name": cluster.get("name", "")},
        "compute": [{"hyperthreading": "Enabled", "name": "worker", "replicas": worker_count}],
        "controlPlane": {"hyperthreading": "Enabled", "name": "master", "replicas": cp_count},
        "networking": {
            "networkType": "OVNKubernetes",
            "clusterNetwork": [{"cidr": "10.128.0.0/14", "hostPrefix": 23}],
            "serviceNetwork": ["172.30.0.0/16"],
            "machineNetwork": [{"cidr": cpu_network}],
        },
        "platform": {
            "baremetal": {
                "apiVIPs":     [cluster.get("api_vip", "")],
                "ingressVIPs": [cluster.get("ingress_vip", "")],
            }
        },
        "pullSecret": pull_secret,
        "sshKey":     ssh_key,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arch",  required=True, help="Architecture (e.g. 2-8-5-200)")
    parser.add_argument("--site",  default="default", help="Site name (default: default)")
    parser.add_argument("--ocp-settings", default=None,
                        help="Path to ocp-settings.yml (default: input/<arch>/<site>/ocp-settings.yml)")
    args = parser.parse_args()

    base_dir   = Path("output") / args.arch / args.site
    inv_dir    = base_dir / "inventory"
    ocp_dir    = base_dir / "ocp"

    if not inv_dir.is_dir():
        sys.exit(
            f"ERROR: ERA inventory not found at {inv_dir}\n"
            f"  Run 'make generate ARCH={args.arch} SITE={args.site}' first."
        )

    # Load ERA inventory
    site_vars = load_yaml(inv_dir / "group_vars" / "all" / "main.yml")
    devices   = site_vars.get("devices", {})

    era_host_vars = {}
    hv_dir = inv_dir / "host_vars"
    if hv_dir.is_dir():
        for f in hv_dir.iterdir():
            if f.suffix in (".yml", ".yaml"):
                era_host_vars[f.stem] = load_yaml(f)

    # Load ocp-settings.yml (optional)
    settings_path = args.ocp_settings or f"input/{args.arch}/{args.site}/ocp-settings.yml"
    ocp_settings  = None
    if os.path.isfile(settings_path):
        ocp_settings = load_yaml(settings_path)
        print(f"  Using ocp-settings.yml: {settings_path}")
    else:
        print(f"  No ocp-settings.yml found at {settings_path} — using auto-inference")

    print(f"Generating OCP inventory for {args.arch} (site: {args.site})")

    role_map = build_role_map(ocp_settings, devices, args.arch, args.site)
    if not role_map:
        sys.exit("ERROR: no OCP nodes found in ERA inventory (devices block is empty or unrecognized)")

    # Summarize role assignment
    for role in OCP_ROLES:
        nodes = [h for h, r in sorted(role_map.items()) if r == role]
        if nodes:
            print(f"  {role:16s}: {', '.join(nodes)}")

    # ── OCP Ansible inventory ─────────────────────────────────────────────
    hosts_yaml = build_hosts_yaml(role_map, era_host_vars)
    hosts_path = ocp_dir / "inventory" / "hosts.yml"
    write_yaml(hosts_path, hosts_yaml,
               header="---\n# Generated by net-configurator generate-ocp-inventory.py — do not edit manually.")
    print(f"\n  ✓ {hosts_path}")

    # ── Per-node host_vars ────────────────────────────────────────────────
    overrides = {}
    oem = "dell"
    if ocp_settings:
        overrides = ocp_settings.get("install_disk", {}).get("overrides") or {}
        oem       = ocp_settings.get("oem", oem)

    fallback_disk_roles = set()
    for hostname, ocp_role in sorted(role_map.items()):
        device_data = devices.get(hostname)
        if device_data is None:
            print(f"  WARNING: {hostname} not in devices block — skipping host_vars", file=sys.stderr)
            continue

        ansible_host = era_host_vars.get(hostname, {}).get("ansible_host", "")
        network_config = build_nmstate_network_config(device_data, site_vars, ocp_role)
        disk, used_fallback = resolve_disk(hostname, ocp_role, args.arch, overrides)
        if used_fallback:
            fallback_disk_roles.add(ocp_role)

        hv_content = {
            "ansible_host": ansible_host,
            "ocp_role":     ocp_role,
            "oob_mac":      device_data.get("mac", ""),
            "install_disk": disk,
            "networkConfig": network_config,
        }
        hv_path = ocp_dir / "inventory" / "host_vars" / f"{hostname}.yml"
        write_yaml(hv_path, hv_content,
                   header=f"---\n# Generated by net-configurator — {hostname} OCP node vars")
        print(f"  ✓ {hv_path}")

    if fallback_disk_roles:
        roles_str = ", ".join(sorted(fallback_disk_roles))
        print(
            f"\n  NOTE: install_disk defaulted to {FALLBACK_DISK} for roles: {roles_str}\n"
            f"  Set ocp-settings.yml install_disk.overrides or add OEM disk defaults.",
            file=sys.stderr,
        )

    # ── group_vars ────────────────────────────────────────────────────────
    gv_content = build_ocp_group_vars(ocp_settings, site_vars, str(ocp_dir))
    gv_path = ocp_dir / "inventory" / "group_vars" / "all" / "ocp.yml"
    write_yaml(gv_path, gv_content,
               header="---\n# Generated by net-configurator generate-ocp-inventory.py — do not edit manually.")
    print(f"  ✓ {gv_path}")

    # ── ABI manifests (require ocp-settings.yml) ──────────────────────────
    if ocp_settings:
        agent_cfg  = build_agent_config(ocp_settings, role_map, era_host_vars, site_vars, args.arch)
        ac_path    = ocp_dir / "agent-config.yaml"
        write_yaml(ac_path, agent_cfg)
        print(f"  ✓ {ac_path}")

        install_cfg = build_install_config(ocp_settings, site_vars, role_map)
        if install_cfg:
            ic_path = ocp_dir / "install-config.yaml"
            write_yaml(ic_path, install_cfg)
            print(f"  ✓ {ic_path}")
    else:
        print(
            "\n  ABI manifests (agent-config.yaml, install-config.yaml) require ocp-settings.yml.\n"
            f"  Create input/{args.arch}/{args.site}/ocp-settings.yml to enable full generation.\n"
            "  See: era-ocp-configurator/input/ocp-settings.yml for the schema."
        )

    # ── Day-2 GPU rail NMState policies ──────────────────────────────────────
    gpu_nodes = sorted(h for h, r in role_map.items() if r == "worker_gpu")
    nncp_count = 0
    for hostname in gpu_nodes:
        device_data = devices.get(hostname)
        if device_data is None:
            continue
        nncp = build_gpu_nncp(hostname, device_data, site_vars)
        if nncp:
            nncp_path = ocp_dir / "day2" / f"nncp-{hostname}-gpu-rails.yaml"
            write_yaml(nncp_path, nncp,
                       header=f"---\n# Stage-2 GPU rail NNCP for {hostname}\n"
                              "# Apply after NVIDIA Network Operator is installed and healthy:\n"
                              "#   oc apply -f ocp/day2/")
            print(f"  ✓ {nncp_path}")
            nncp_count += 1

    if nncp_count:
        print(f"\n  Day-2 GPU rail policies ({nncp_count} nodes): {ocp_dir}/day2/")
        print("  Apply post-install: oc apply -f ocp/day2/")
    elif gpu_nodes:
        print(f"\n  NOTE: {len(gpu_nodes)} worker_gpu node(s) found but no GPU rail data in ERA inventory.",
              file=sys.stderr)

    print(f"\n✅ OCP inventory written to {ocp_dir}/")


if __name__ == "__main__":
    main()
