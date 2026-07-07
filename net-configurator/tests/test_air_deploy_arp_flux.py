# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Regression test: the Air Node-Instructions ARP-flux mitigation must cover
*storage* hosts, not just GPU hosts.

Storage nodes have two bonds (bond0/bond1) with IPs in the SAME subnet/VLAN
(e.g. 172.16.180.105 + .106 on VLAN 500). With default Linux ARP settings this
causes ARP flux -> EVPN MAC-mobility flap on the anycast VRR -> intermittent
gateway blackhole (root-caused live on a 2-8-9-800 largescale sim: only the
storage nodes were missing the sysctls the GPU hosts got).

The fix must NOT set arp_filter=1 for storage: arp_filter is only safe with the
per-NIC PBR tables the parser emits for gpu_interfaces, which storage lacks.
arp_ignore=1 + arp_announce=2 is the canonical (and sufficient) flux fix.
"""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_air_deploy():
    spec = importlib.util.spec_from_file_location("air_deploy", SCRIPTS / "air-deploy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


air_deploy = _load_air_deploy()


def _joined(dev):
    return "\n".join(air_deploy.build_server_ni_commands("node-x", dev, {}))


STORAGE_DEV = {
    "eth0_ip": "192.168.200.222",
    "bond_ip1": "172.16.180.105/24",
    "bond_ip2": "172.16.180.106/24",
}
GPU_DEV = {"eth0_ip": "192.168.200.60", "gpu_ips": ["192.168.0.5/24", "192.168.16.5/24"]}
PLAIN_DEV = {"eth0_ip": "192.168.200.70"}
SINGLE_BOND_DEV = {"eth0_ip": "192.168.200.80", "bond_ip1": "172.16.180.150/24"}


def test_storage_dual_bond_gets_arp_flux_fix():
    out = _joined(STORAGE_DEV)
    assert "net.ipv4.conf.all.arp_ignore=1" in out
    assert "net.ipv4.conf.all.arp_announce=2" in out


def test_storage_omits_arp_filter_without_pbr():
    # arp_filter needs per-NIC PBR (gpu-only); storage must not enable it.
    assert "net.ipv4.conf.all.arp_filter=1" not in _joined(STORAGE_DEV)


def test_gpu_host_still_gets_full_arp_flux_fix():
    out = _joined(GPU_DEV)
    assert "net.ipv4.conf.all.arp_ignore=1" in out
    assert "net.ipv4.conf.all.arp_announce=2" in out
    assert "net.ipv4.conf.all.arp_filter=1" in out


def test_single_bond_and_plain_nodes_get_no_arp_flux_fix():
    # One same-subnet interface can't flux; don't touch ARP behavior.
    assert "arp_ignore" not in _joined(PLAIN_DEV)
    assert "arp_ignore" not in _joined(SINGLE_BOND_DEV)
