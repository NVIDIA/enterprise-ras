# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Unit tests for scripts/airlib/ext_storage_config.py — the shared ext-storage
FRR-config builder extracted from air-deploy.py so `make fix-ext-storage` and
the air-deploy NI path can't drift (design C3, 2026-07-01).

The byte-identical tests pin the exact strings air-deploy currently emits; if
they change, air-deploy's NI output changed too and both paths change together.
"""
import json
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


# ── Peer discovery must not depend on the switch's ROLE NAME ──────────────
#
# Found 2026-08-13 on a 2-4-5-400 sample deploy: switch health reported
# STORAGE/ipv4Unicast/swp62s0-s2 = Idle on core-01/core-02, and
# `make fix-ext-storage` answered "nothing to fix" and exited 0. Discovery
# filtered peers with `peer_node.startswith("csl-")`, but the storage-facing
# switch is named per arch and scale:
#
#   core-*  collapsed core at default scale   (2-4-3-200, 2-4-5-400, 2-8-5-200, 2-8-9-400)
#   cl-*    largescale                        (2-4-5-800, 2-8-9-400-SP, 2-8-9-800)
#   csl-*   the remaining six
#
# 8 of the 14 shipped topologies matched nothing, so the remediation could not
# see the very links it exists to fix. It was first read as a stale cl-/csl-
# rename; it is broader than that, which is why these tests assert on the
# STRUCTURE of the cabling rather than on any name.
NAME_FAMILIES_TOPO = {
    "content": {
        "nodes": {"ext-storage-01": {}, "ext-storage-02": {}, "ext-storage-03": {}},
        "links": [
            # eth0 is outbound. Note its peer port is a swp* too, so eth0 has to
            # be excluded BY INTERFACE, not by "peer isn't a switch port".
            [{"node": "ext-storage-01", "interface": "eth0"}, {"node": "cust-net-edge-01", "interface": "swp53"}],
            [{"node": "ext-storage-01", "interface": "eth1"}, {"node": "core-01", "interface": "swp62s0"}],
            [{"node": "ext-storage-01", "interface": "eth2"}, {"node": "core-01", "interface": "swp62s1"}],
            [{"node": "ext-storage-02", "interface": "eth0"}, {"node": "cust-net-edge-01", "interface": "swp54"}],
            [{"node": "ext-storage-02", "interface": "eth1"}, {"node": "cl-01", "interface": "swp59s0"}],
            [{"node": "ext-storage-02", "interface": "eth2"}, {"node": "cl-05", "interface": "swp59s1"}],
            [{"node": "ext-storage-03", "interface": "eth1"}, {"node": "csl-01", "interface": "swp63s0"}],
        ],
    }
}


@pytest.mark.parametrize("node,expected", [
    ("ext-storage-01", ["eth1", "eth2"]),   # core-*  — collapsed core
    ("ext-storage-02", ["eth1", "eth2"]),   # cl-*    — largescale fan-out
    ("ext-storage-03", ["eth1"]),           # csl-*   — the only name that used to work
])
def test_discover_finds_peers_for_every_switch_name_family(node, expected):
    """A storage uplink is a storage uplink whatever the switch is called."""
    targets = {t["node_name"]: t for t in esc.discover_ext_storage_targets(NAME_FAMILIES_TOPO)}
    assert targets[node]["peer_ifaces"] == expected, (
        f"{node} resolved {targets[node]['peer_ifaces']}; peer discovery is still "
        f"keyed on the switch's role name, so `make fix-ext-storage` will report "
        f"'nothing to fix' and exit 0 while the STORAGE eBGP sessions stay Idle."
    )


def test_discover_spans_a_fan_out_to_many_switches():
    """largescale cables one ext-storage node across up to 8 leaves.

    A fix that merely swaps one name prefix for another still works here; a fix
    that assumes a single peer switch does not. Written because that was exactly
    the wrong turn taken while diagnosing this.
    """
    links = [[{"node": "ext-storage-01", "interface": "eth0"},
              {"node": "cust-net-edge-01", "interface": "swp53"}]]
    links += [[{"node": "ext-storage-01", "interface": f"eth{i}"},
               {"node": f"cl-{i:02d}", "interface": "swp59s0"}] for i in range(1, 9)]
    topo = {"content": {"nodes": {"ext-storage-01": {}}, "links": links}}
    got = esc.discover_ext_storage_targets(topo)[0]["peer_ifaces"]
    assert got == [f"eth{i}" for i in range(1, 9)]


SHIPPED_TOPOLOGIES = sorted(
    p for site in ("default", "largescale")
    for p in (Path(__file__).resolve().parent.parent).glob(f"output/*/{site}/topology/*.json")
)


@pytest.mark.skipif(not SHIPPED_TOPOLOGIES, reason="no generated topologies present")
@pytest.mark.parametrize("topo_path", SHIPPED_TOPOLOGIES,
                         ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}")
def test_every_shipped_topology_resolves_its_ext_storage_peers(topo_path):
    """The real cabling, not a fixture that encodes the assumption under test.

    The synthetic fixture above used only `csl-*` peers, which is precisely why
    this bug survived: the test data agreed with the bug.
    """
    topo = json.loads(topo_path.read_text())
    targets = esc.discover_ext_storage_targets(topo)
    if not targets:
        pytest.skip("arch has no ext-storage nodes")
    broken = [t["node_name"] for t in targets if not t["peer_ifaces"]]
    assert not broken, (
        f"{topo_path.parts[-4]}/{topo_path.parts[-3]}: {broken} resolved no peer "
        f"interfaces, so `make fix-ext-storage` silently does nothing for them."
    )


# ---------------------------------------------------------------------------
# ERA-93 — the air-mgmt plane is operator-selectable (ADR-0056). These builders
# hardcoded 172.20.0.79+ and 172.20.0.254, so a deployment that moved
# air_mgmt_subnet got ext-storage nodes addressed on a plane that does not
# exist. Same class as ERA-90, in a path that topology never exercised.
# ---------------------------------------------------------------------------
class TestExtStorageFollowsAirMgmtSubnet:
    def test_default_plane_is_unchanged(self):
        t = esc.discover_ext_storage_targets(TOPO)[0]
        assert t["eth0_ip"] == "172.20.0.79"

    def test_eth0_ip_follows_a_moved_plane(self):
        targets = esc.discover_ext_storage_targets(
            TOPO, air_mgmt_subnet="10.78.255.0/24")
        assert [t["eth0_ip"] for t in targets] == ["10.78.255.79", "10.78.255.80"]

    def test_netplan_default_is_unchanged(self):
        out = esc.build_eth0_netplan("172.20.0.79")
        assert "addresses: [172.20.0.79/24]" in out
        assert "via: 172.20.0.254" in out

    def test_netplan_gateway_and_prefix_follow_the_plane(self):
        # The gateway is derived the same way air-deploy assigns the SVI
        # (network_address + 254), so the two cannot disagree about where
        # cust-net-edge-01 lives. A sub-/24 air-mgmt plane would put that
        # offset outside the network in BOTH places — a separate modelling
        # gap, deliberately not papered over here with divergent arithmetic.
        out = esc.build_eth0_netplan("10.78.255.79",
                                     air_mgmt_subnet="10.78.255.0/24")
        assert "addresses: [10.78.255.79/24]" in out
        assert "via: 10.78.255.254" in out

    def test_malformed_plane_falls_back_to_the_default(self):
        out = esc.build_eth0_netplan("172.20.0.79", air_mgmt_subnet="not-a-cidr")
        assert "addresses: [172.20.0.79/24]" in out
        assert "via: 172.20.0.254" in out
