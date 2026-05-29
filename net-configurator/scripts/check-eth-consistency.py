#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Post-generate cross-check that asserts netplan-side and topology-side
eth-numbering agree for every non-switch node.

This guards against the class of bug fixed in MR !26: an off-by-one
between `build_interface_map()` and the topology generator caused
`su-01-node-01`'s bond to pair a CPU NIC with a GPU NIC. The
discrepancy was silent — mii-monitor saw both bond members "up" and
the failure surfaced only as ping timeouts during validate-servers.

Run: scripts/check-eth-consistency.py --arch <arch> --site <site>

Exit 0 if every node's iface map matches between the two sources.
Exit 1 with a per-node diff if anything disagrees.

Invoked automatically at the end of `make generate`.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def _topology_iface_map(topology_json_path: Path) -> dict:
    """Return {node_name: {iface: (peer_node, peer_port)}} from topology JSON."""
    with open(topology_json_path) as f:
        t = json.load(f)
    out = defaultdict(dict)
    for link in t.get('content', {}).get('links', []):
        eps = [e for e in link if isinstance(e, dict)]
        if len(eps) != 2:
            continue
        a, b = eps
        a_node, a_if = a.get('node'), a.get('interface')
        b_node, b_if = b.get('node'), b.get('interface')
        if a_node and a_if and b_node and b_if:
            out[a_node][a_if] = (b_node, b_if)
            out[b_node][b_if] = (a_node, a_if)
    return dict(out)


def _devices_iface_map(devices_main_yml: Path) -> dict:
    """Return {node_name: set(iface)} from group_vars/all/main.yml devices block.

    The `devices.<name>.interfaces` block (when present) holds the netplan-
    side view: each profile is mapped to a list of ethN. We only need the
    set of ethNs per node — the cross-check is on which ethNs each node
    owns, not which profile they fall into.
    """
    import yaml
    with open(devices_main_yml) as f:
        data = yaml.safe_load(f) or {}
    devices = data.get('devices') or {}
    out = {}
    for name, dev in devices.items():
        ifaces = set()
        netifaces = (dev or {}).get('interfaces') or {}
        for prof, lst in netifaces.items():
            for v in (lst or []):
                ifaces.add(v)
        if ifaces:
            out[name] = ifaces
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--arch', required=True)
    ap.add_argument('--site', default='default')
    args = ap.parse_args()

    out_dir = Path('output') / args.arch / args.site
    topo = out_dir / 'topology' / f'{args.arch}-topology.json'
    main_yml = out_dir / 'inventory' / 'group_vars' / 'all' / 'main.yml'
    if not topo.exists() or not main_yml.exists():
        print(f"  [eth-consistency] missing artifact ({topo} or {main_yml}); skipping check")
        return 0

    topo_map = _topology_iface_map(topo)
    dev_map = _devices_iface_map(main_yml)

    mismatches = []
    for name, dev_ifaces in dev_map.items():
        topo_ifaces = set(topo_map.get(name, {}).keys())
        # The devices map only emits hardware NICs (eth0+ from Wire Map);
        # the topology may include the same set. Compare what they share.
        only_dev = dev_ifaces - topo_ifaces
        only_topo = topo_ifaces - dev_ifaces
        if only_dev or only_topo:
            mismatches.append((name, sorted(only_dev), sorted(only_topo)))

    if not mismatches:
        print(f"  [eth-consistency] ✓ {len(dev_map)} server nodes — netplan and topology eth-numbering match")
        return 0

    print(f"  [eth-consistency] ✗ {len(mismatches)} node(s) disagree between netplan and topology:")
    for name, only_dev, only_topo in mismatches[:10]:
        print(f"    {name}:")
        if only_dev:
            print(f"      in netplan but not topology: {only_dev}")
        if only_topo:
            print(f"      in topology but not netplan: {only_topo}")
    print()
    print("  This usually means the parser's build_interface_map() and the")
    print("  topology generator's _oob_eth0 logic have diverged. Bonds may")
    print("  silently pair NICs from different L2 domains — see MR !26.")
    return 1


if __name__ == '__main__':
    sys.exit(main())
