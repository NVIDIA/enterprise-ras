# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Unit tests for scripts/airlib/ext_storage_config.py — the shared ext-storage
FRR-config builder extracted from air-deploy.py so `make fix-ext-storage` and
the air-deploy NI path can't drift (design C3, 2026-07-01).

The byte-identical tests pin the exact strings air-deploy currently emits; if
they change, air-deploy's NI output changed too and both paths change together.
"""
import importlib.util
from pathlib import Path

import pytest

_MOD = (
    Path(__file__).resolve().parent.parent / "scripts" / "airlib" / "ext_storage_config.py"
)
spec = importlib.util.spec_from_file_location("ext_storage_config", _MOD)
esc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(esc)


# Synthetic topology: ext-storage-01 faces csl-01/csl-02 swp63 on eth1/eth2;
# eth0 (outbound) must be ignored. ext-storage-02 faces csl-03 on eth1.
TOPO = {
    "content": {
        "nodes": {
            "ext-storage-01": {},
            "ext-storage-02": {},
            "csl-01": {},
            "core-01": {},
        },
        "links": [
            [{"node": "ext-storage-01", "interface": "eth0"}, {"node": "cust-net-edge-01", "interface": "swp53"}],
            [{"node": "ext-storage-01", "interface": "eth2"}, {"node": "csl-02", "interface": "swp63s0"}],
            [{"node": "ext-storage-01", "interface": "eth1"}, {"node": "csl-01", "interface": "swp63s0"}],
            [{"node": "ext-storage-02", "interface": "eth1"}, {"node": "csl-03", "interface": "swp63s1"}],
        ],
    }
}


def test_discover_targets_indices_ips_and_peers():
    targets = esc.discover_ext_storage_targets(TOPO)
    assert [t["node_name"] for t in targets] == ["ext-storage-01", "ext-storage-02"]
    t0 = targets[0]
    assert t0["idx"] == 0
    assert t0["lo_ip"] == "10.187.5.1"
    assert t0["eth0_ip"] == "172.20.0.79"
    # eth0 (outbound) excluded; only CSL-facing eth* kept, sorted
    assert t0["peer_ifaces"] == ["eth1", "eth2"]
    assert targets[1]["lo_ip"] == "10.187.5.2"
    assert targets[1]["eth0_ip"] == "172.20.0.80"
    assert targets[1]["peer_ifaces"] == ["eth1"]


def test_discover_skips_node_with_no_csl_facing_ifaces():
    topo = {"content": {"nodes": {"ext-storage-01": {}}, "links": [
        [{"node": "ext-storage-01", "interface": "eth0"}, {"node": "cust-net-edge-01", "interface": "swp53"}],
    ]}}
    targets = esc.discover_ext_storage_targets(topo)
    assert targets[0]["peer_ifaces"] == []


def test_build_frr_conf_byte_identical():
    """Pins the exact FRR config air-deploy emits (idx 0)."""
    expected = (
        "frr version 8.4\n"
        "frr defaults traditional\n"
        "hostname ext-storage-01\n"
        "no ipv6 forwarding\n"
        "!\n"
        "interface lo\n"
        " ip address 10.187.5.1/32\n"
        "!\n"
        "router bgp 4260000002\n"
        " bgp router-id 10.187.5.1\n"
        " no bgp default ipv4-unicast\n"
        " no bgp ebgp-requires-policy\n"
        " neighbor STORAGE peer-group\n"
        " neighbor STORAGE remote-as external\n"
        " neighbor STORAGE capability extended-nexthop\n"
        " neighbor eth1 interface peer-group STORAGE\n"
        " neighbor eth2 interface peer-group STORAGE\n"
        " !\n"
        " address-family ipv4 unicast\n"
        "  network 10.187.5.1/32\n"
        "  redistribute connected\n"
        "  neighbor STORAGE activate\n"
        " exit-address-family\n"
        "!\n"
        "line vty\n"
        "!\n"
    )
    assert esc.build_frr_conf("ext-storage-01", "10.187.5.1", ["eth1", "eth2"]) == expected


def test_build_daemons_byte_identical():
    expected = (
        "bgpd=yes\n"
        "ospfd=no\nospf6d=no\nripd=no\nripngd=no\nisisd=no\n"
        "pimd=no\nldpd=no\nnhrpd=no\neigrpd=no\nbabeld=no\n"
        "sharpd=no\npbrd=no\nbfdd=no\nfabricd=no\nvrrpd=no\n"
        "vtysh_enable=yes\n"
        'zebra_options="  -A 127.0.0.1 -s 90000000"\n'
        'bgpd_options="   -A 127.0.0.1"\n'
    )
    assert esc.build_daemons() == expected


def test_build_eth0_netplan_byte_identical():
    expected = (
        "network:\n"
        "  version: 2\n"
        "  renderer: networkd\n"
        "  ethernets:\n"
        "    eth0:\n"
        "      addresses: [172.20.0.79/24]\n"
        "      routes:\n"
        "        - to: 0.0.0.0/0\n"
        "          via: 172.20.0.254\n"
        "      nameservers:\n"
        "        addresses: [8.8.8.8, 8.8.4.4]\n"
        "      dhcp4: false\n"
        "      dhcp6: false\n"
    )
    assert esc.build_eth0_netplan("172.20.0.79") == expected
