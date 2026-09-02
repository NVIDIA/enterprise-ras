# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""One (node, interface) may be wired by exactly one link, and eth0 is mgmt.

Air validates this server-side and rejects the ENTIRE topology:

    Topology failed to pass validation: {"content": {"links":
      {"271": {"0": {"interface": "Interface eth0 is already defined for node
       ext-storage-01: index 0 of link index 247"}}}}}

The failure mode is why this is a hard gate rather than a warning. The import
returns 200 with a simulation id, then flips to INVALID roughly half a second
later with no nodes, no links and no error field. An INVALID simulation never
appears in the Air UI, so the operator sees `make air-deploy` print
"Node X not found in simulation" for all 48 nodes and no reason for any of it.

It shipped in ALL SIX architectures simultaneously and took two failed deploys
plus a manual API import to diagnose, because nothing between `make generate`
and Air had an opinion about it.

Root cause: ext-storage reaches the management network via cust-net-edge rather
than an oob-switch, so it never matched the pre-scan that reserves eth0 for
every other server. `_next_eth()` therefore started at 0 and gave eth0 to the
first storage uplink; the synthesised mgmt link then claimed eth0 as well.

The invariant that actually matters is the second test here: **eth0 is the
management interface on every node, always.** Compute nodes have always
honoured it — su-01-node-01 carries 18 data links and none of them touch eth0.
"""
import json
from pathlib import Path

import openpyxl
import pytest

NC = Path(__file__).resolve().parent.parent
_SHIPPED_SITES = ("default", "largescale")


def _topologies():
    for p in sorted(NC.glob("output/*/*/topology/*-topology.json")):
        arch, site = p.parts[-4], p.parts[-3]
        if site not in _SHIPPED_SITES:
            continue
        yield pytest.param(p, arch, site, id=f"{arch}/{site}")


CASES = list(_topologies())


def test_topologies_exist():
    """An empty glob would make every parametrised test vacuously pass."""
    assert CASES, "no shipped topologies found — regenerate before testing"


@pytest.mark.parametrize("path,arch,site", CASES)
def test_generated_configs_and_host_vars_belong_to_inventory(path, arch, site):
    site_root = path.parent.parent
    inventory_hosts = {
        line.split()[0]
        for line in (site_root / "inventory" / "hosts").read_text().splitlines()
        if line and not line.startswith("[") and not line.startswith("#")
    }
    config_hosts = {
        item.name.removesuffix("-config.sh")
        for item in (site_root / "configs").glob("*-config.sh")
    }
    host_var_hosts = {
        item.stem
        for item in (site_root / "inventory" / "host_vars").glob("*.yml")
    }
    stale_oob_configs = {
        name for name in config_hosts - inventory_hosts
        if name.startswith(("oob-switch-", "rack-oob-"))
    }
    stale_oob_host_vars = {
        name for name in host_var_hosts - inventory_hosts
        if name.startswith(("oob-switch-", "rack-oob-"))
    }
    assert not stale_oob_configs, (arch, site, sorted(stale_oob_configs))
    assert not stale_oob_host_vars, (arch, site, sorted(stale_oob_host_vars))
    for item in (site_root / "configs").glob("*oob*-config.sh"):
        content = item.read_bytes()
        assert content.endswith(b"\n") and not content.endswith(b"\n\n"), (arch, site, item.name)


def _endpoints(path):
    """-> [(link_index, node, interface)] for every dict endpoint."""
    content = json.loads(path.read_text()).get("content", {})
    out = []
    for idx, link in enumerate(content.get("links", [])):
        if not isinstance(link, list):
            continue
        for ep in link:
            if isinstance(ep, dict) and ep.get("node") and ep.get("interface"):
                out.append((idx, ep["node"], ep["interface"]))
    return out


@pytest.mark.parametrize("path,arch,site", CASES)
def test_no_duplicate_node_interface(path, arch, site):
    """The exact condition Air rejects."""
    eps = _endpoints(path)
    assert eps, f"{arch}/{site}: no link endpoints parsed"

    seen, clashes = {}, []
    for idx, node, iface in eps:
        key = (node, iface)
        if key in seen:
            clashes.append(f"{node} {iface}: links {seen[key]} and {idx}")
        else:
            seen[key] = idx
    assert not clashes, (
        f"{arch}/{site}: duplicate (node, interface) endpoints — Air will "
        f"reject the whole import and leave an INVALID simulation:\n  "
        + "\n  ".join(clashes))


def _management_peer_names(arch, site):
    workbook = NC / "input" / arch / site / f"{arch}.xlsx"
    wb = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    try:
        rows = wb["Nodes"].iter_rows(min_row=2, values_only=True)
        return {
            name
            for function, name, _oob_vlan, _node_type, *_rest in rows
            if str(function or "").strip().lower() in {"oob-switch", "edge", "air-oob"}
        }
    finally:
        wb.close()


@pytest.mark.parametrize("path,arch,site", CASES)
def test_eth0_is_always_management(path, arch, site):
    """eth0 must only ever face a management peer.

    A data link on eth0 is wrong even when it does not collide: it puts fabric
    traffic on the management interface. On ext-storage it also meant FRR was
    peering BGP unnumbered on the same interface holding the static 172.20.0.x
    mgmt address, because `discover_ext_storage_targets` selects peers by
    csl-*/swp*, not by interface name.
    """
    management_peers = _management_peer_names(arch, site)
    offenders = []
    content = json.loads(path.read_text()).get("content", {})
    for idx, link in enumerate(content.get("links", [])):
        if not isinstance(link, list) or len(link) != 2:
            continue
        for i, ep in enumerate(link):
            if not isinstance(ep, dict) or ep.get("interface") != "eth0":
                continue
            peer = link[1 - i]
            # A string endpoint is Air's stub form. `"outbound"` is the L3
            # trio's internet leg (NAT/DNS at first boot) and is management
            # use, not a data link — external-conn / external-dhcp / utility
            # all carry it. Other stub strings are not data links either.
            if not isinstance(peer, dict):
                continue
            peer_node = peer.get("node", "")
            if peer_node not in management_peers and not peer_node.startswith("cust-net-edge-"):
                offenders.append(
                    f"link {idx}: {ep.get('node')} eth0 -> {peer_node}:"
                    f"{peer.get('interface')}")
    assert not offenders, (
        f"{arch}/{site}: eth0 wired to a non-management peer — eth0 is the "
        f"management interface on every node:\n  " + "\n  ".join(offenders))


@pytest.mark.parametrize("path,arch,site", CASES)
def test_ext_storage_data_links_start_at_eth1(path, arch, site):
    """The specific regression, stated positively.

    The Wire Map declares `swp1`/`swp2` for ext-storage. On a server-like node
    the first data port is eth1, not eth0, precisely because eth0 is spoken
    for — this is what the generator's own comment ("wired to CSL swp63 ports
    via Wire Map (eth1, eth2)") had always intended.
    """
    by_node = {}
    for idx, node, iface in _endpoints(path):
        if node.startswith("ext-storage-"):
            by_node.setdefault(node, set()).add(iface)
    if not by_node:
        pytest.skip(f"{arch}/{site}: no ext-storage nodes")

    content = json.loads(path.read_text()).get("content", {})
    for node, ifaces in sorted(by_node.items()):
        assert "eth0" in ifaces, f"{node}: no eth0 at all — mgmt link missing"
        # every eth0 link on this node must face the mgmt bridge
        for idx, link in enumerate(content.get("links", [])):
            if not isinstance(link, list) or len(link) != 2:
                continue
            for i, ep in enumerate(link):
                if (isinstance(ep, dict) and ep.get("node") == node
                        and ep.get("interface") == "eth0"):
                    peer_ep = link[1 - i]
                    if not isinstance(peer_ep, dict):
                        continue
                    peer = peer_ep.get("node", "")
                    assert peer.startswith(("cust-net-edge", "oob-switch")), (
                        f"{node} eth0 faces {peer} — that is a data link on "
                        f"the management interface")
