#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Write `<arch>-complete.xlsx`: the authored workbook with every IP filled in.

ERA-109. An intake form may be authored sparse -- the operator supplies the
cabling and lets the tool allocate addresses. That is convenient to author
and impossible to review: nothing shows what the tool actually chose until
you read generated Ansible inventory.

This writes a second workbook BESIDE the source in `input/`, identical in
shape, with the resolved values filled in:

    input/<arch>/<site>/<arch>.xlsx            authored, may be sparse
    input/<arch>/<site>/<arch>-complete.xlsx   every IP present

It goes in `input/`, not `output/`, because it is an INPUT: feed it straight
back in and you get the same configs, with nothing left to allocate. That
round trip is the idempotence test.

Values come from the generated inventory rather than from a second copy of
the allocator, so the workbook cannot disagree with what actually gets
deployed -- if they ever differ, the workbook is wrong by construction.

Completed workbooks are regenerated on every import and are gitignored.
"""
import argparse
import shutil
import sys
from pathlib import Path

import openpyxl
import yaml

sys.path.insert(0, str(Path(__file__).parent))
import intake_style  # noqa: E402
from intake_reader import column_map, header_row  # noqa: E402

COMPLETE_SUFFIX = "-complete.xlsx"

# Switch Data column (normalised) -> where the resolved value lives.
#   host_vars key, or ("vrf", <VRF name>) for a per-VRF loopback.
#
# `Mgmt IP` is deliberately NOT `ansible_host`. `ansible_host` is whatever
# address the controller reaches the switch on -- in Air that is the
# air-mgmt plane (172.20.0.x), not the OOB address the workbook means
# (192.168.200.x). Writing it here produced a completed workbook that
# generated DIFFERENT configs when fed back in, which is how the round-trip
# check caught it. The OOB address is `devices[<name>].eth0_ip`, handled
# separately below.
_SWITCH_FIELDS = {
    "loopback ip": "lo_ip",
    "router-id": "router_id",
    "oob lo": ("vrf", "OOB"),
    "inband (n-s) lo": ("vrf", "INBAND"),
    "exit lo": ("vrf", "EXIT"),
    "gpu lo": ("vrf", "GPU"),
    "storage lo": ("vrf", "STORAGE"),
}

# Host Data, one row per resolved interface.
HOST_COMPLETE_HEADERS = [
    "System Name", "Physical Interface", "Logical Interface", "IP",
    "NICOSName", "Mac Address", "Profile", "Function", "Type", "Prefix",
    "Gateway", "ZTP", "Enabled", "OOB VLAN", "Notes",
]


def _load_inventory(inv_dir):
    """Return (host_vars, devices, host_asn) from a generated inventory."""
    host_vars = {}
    hv_dir = inv_dir / "host_vars"
    if hv_dir.is_dir():
        for f in sorted(hv_dir.glob("*.yml")):
            host_vars[f.stem] = yaml.safe_load(f.read_text()) or {}

    devices = {}
    main = inv_dir / "group_vars" / "all" / "main.yml"
    if main.is_file():
        devices = (yaml.safe_load(main.read_text()) or {}).get("devices", {}) or {}

    return host_vars, devices, _host_asn(inv_dir, host_vars)


def _host_asn(inv_dir, host_vars):
    """Map switch name -> ASN.

    Per-host when the host carries its own, else the ASN of the group it
    belongs to. Group membership comes from the generated `hosts` file rather
    than from a naming convention -- this repo has shipped name-matching bugs
    before (see ADR history), and the inventory already states the answer.
    """
    asn = {name: hv["asn"] for name, hv in host_vars.items() if hv.get("asn")}

    group_asn = {}
    gv_dir = inv_dir / "group_vars"
    if gv_dir.is_dir():
        for f in sorted(gv_dir.glob("*.yml")):
            data = yaml.safe_load(f.read_text()) or {}
            value = data.get("asn") or data.get("bgp_asn")
            if value:
                group_asn[f.stem] = value

    hosts_file = inv_dir / "hosts"
    if hosts_file.is_file():
        group = None
        for line in hosts_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                group = line[1:-1].split(":")[0]
                continue
            if not line or line.startswith("#") or group is None:
                continue
            host = line.split()[0]
            if host not in asn and group in group_asn:
                asn[host] = group_asn[group]
    return asn


def _eth_to_physical(inv_dir, source_xlsx):
    """(host, ethN) -> (physical NIC label, network profile).

    Two hops, both from artifacts rather than a re-derivation:
      topology links   (host, ethN)      <-> (switch, swpPort)
      Wire Map         (switch, swpPort) ->  the server-side NIC label
    Reproducing the eth numbering here instead would be a second copy of
    the topology generator's allocator, free to drift from the one that
    actually deploys.

    Returns {} when the topology has not been generated; callers fall back
    to leaving `Physical Interface` blank rather than guessing.
    """
    import json

    topo_dir = inv_dir.parent / "topology"
    topo = next(iter(sorted(topo_dir.glob("*-topology.json"))), None)
    if topo is None:
        return {}

    try:
        content = (json.loads(topo.read_text()) or {}).get("content") or {}
    except (ValueError, OSError):
        return {}

    sys.path.insert(0, str(Path(__file__).parent))
    from emit_ip_report import load_wiremap
    wm = load_wiremap(Path(source_xlsx))

    out = {}
    for link in content.get("links") or []:
        if not isinstance(link, list) or len(link) != 2:
            continue
        if not all(isinstance(end, dict) for end in link):
            continue                    # some entries are plain strings
        for near, far in (link, link[::-1]):
            iface = str(near.get("interface") or "")
            far_port = str(far.get("interface") or "")
            if not iface.startswith("eth") or not far_port.startswith("swp"):
                continue
            label, profile = wm.get((str(far.get("node")), far_port), (None, ""))
            if label:
                out[(str(near.get("node")), iface)] = (label, profile)
    return out


def _fill_switch_data(ws, host_vars, host_asn, devices):
    cols = column_map(ws)
    name_col = cols.get("name")
    if not name_col:
        return 0
    filled = 0
    for r in range(header_row(ws) + 1, ws.max_row + 1):
        name = ws.cell(r, name_col).value
        if not name:
            continue
        key = str(name).strip()
        hv = host_vars.get(key)
        if not hv:
            continue

        # OOB management address — see the note on _SWITCH_FIELDS.
        mgmt_col = cols.get("mgmt ip")
        eth0 = (devices.get(key) or {}).get("eth0_ip")
        if mgmt_col and eth0:
            ws.cell(r, mgmt_col, eth0)
            filled += 1
        for col_name, source in _SWITCH_FIELDS.items():
            col = cols.get(col_name)
            if not col:
                continue
            if isinstance(source, tuple):
                value = (hv.get("vrf_loopbacks") or {}).get(source[1])
            else:
                value = hv.get(source)
            if value not in (None, ""):
                ws.cell(r, col, value)
                filled += 1
        asn_col = cols.get("asn")
        if asn_col and host_asn.get(str(name).strip()):
            ws.cell(r, asn_col, host_asn[str(name).strip()])
            filled += 1
    return filled


def _host_interface_rows(ws, devices, eth_map):
    """One row per PHYSICAL port, using the template's own column meanings.

    Physical Interface  the Wire Map's NIC label -- the join back to cabling
    NICOSName           the OS name (ethN)
    Logical Interface   what the OS presents: bond0/bond1, else the ethN

    Bond membership is therefore visible as rows sharing a Logical Interface,
    each naming its own physical port. An earlier version put ethN in
    Physical Interface and left NICOSName empty, which made a Host Data row
    impossible to trace to a cable.
    """
    cols = column_map(ws)
    key_col = cols.get("system name")
    if not key_col:
        return []

    authored, order = {}, []
    for r in range(header_row(ws) + 1, ws.max_row + 1):
        name = ws.cell(r, key_col).value
        if not name:
            continue
        name = str(name).strip()
        if name not in authored:
            order.append(name)
            authored[name] = {h: ws.cell(r, c).value for h, c in cols.items()}

    rows = []
    for name in order:
        base = authored[name]

        def row(eth, logical, ip):
            label, profile = eth_map.get((name, eth), (None, None))
            return [
                name,
                label,                          # Physical Interface (Wire Map)
                logical,                        # Logical Interface
                ip,
                eth,                            # NICOSName (OS name)
                base.get("mac address"),
                profile or base.get("profile"),
                base.get("function"), base.get("type"), base.get("prefix"),
                base.get("gateway"), base.get("ztp"), base.get("enabled"),
                base.get("oob vlan"), base.get("notes"),
            ]

        dev = devices.get(name)
        if not dev:
            rows.append(row(None, None, base.get("ip")))
            continue

        ifaces = dev.get("interfaces") or {}
        if dev.get("eth0_ip"):
            rows.append(row("eth0", "eth0", dev["eth0_ip"]))

        # Bonds: one row per MEMBER port, all sharing the bond's logical name
        # and its address, so the bond's composition is readable off the sheet.
        data = [e for plane in ("support", "storage", "cpu")
                for e in (ifaces.get(plane) or []) if e != "eth0"]
        if dev.get("bond_ip"):
            for eth in data:
                rows.append(row(eth, "bond0", dev["bond_ip"]))
        else:
            if dev.get("bond_ip1"):
                for eth in data[0:2]:
                    rows.append(row(eth, "bond0", dev["bond_ip1"]))
            if dev.get("bond_ip2"):
                for eth in data[2:4]:
                    rows.append(row(eth, "bond1", dev["bond_ip2"]))

        for gnic in dev.get("gpu_interfaces") or []:
            eth = gnic.get("iface")
            rows.append(row(eth, eth, gnic.get("ip")))
        if not dev.get("gpu_interfaces"):
            gpu = [e for e in (ifaces.get("gpu") or []) if e != "eth0"]
            for i, ip in enumerate(dev.get("gpu_ips") or []):
                eth = gpu[i] if i < len(gpu) else f"gpu{i + 1}"
                rows.append(row(eth, eth, ip))

        if not rows or rows[-1][0] != name:
            rows.append(row(None, None, base.get("ip")))
    return rows


def _rewrite_host_data(wb, devices, eth_map):
    old = wb["Host Data"]
    position = wb.sheetnames.index("Host Data")     # keep it where it was
    rows = _host_interface_rows(old, devices, eth_map)
    wb.remove(old)
    # create_sheet appends, which shoved Host Data to the end of the tab bar
    # and broke the sheet order the template defines. Put it back.
    ws = wb.create_sheet("Host Data", position)
    for c, name in enumerate(HOST_COMPLETE_HEADERS, start=1):
        ws.cell(1, c, name)
    for r, values in enumerate(rows, start=2):
        for c, value in enumerate(values, start=1):
            if value is not None:
                ws.cell(r, c, value)
    return len(rows)


def complete_path(source):
    source = Path(source)
    return source.with_name(source.stem + COMPLETE_SUFFIX)


def emit(source_xlsx, inventory_dir, out_path=None):
    """Write the completed workbook. Returns its path."""
    source_xlsx = Path(source_xlsx)
    inventory_dir = Path(inventory_dir)
    out_path = Path(out_path) if out_path else complete_path(source_xlsx)

    host_vars, devices, host_asn = _load_inventory(inventory_dir)
    if not host_vars and not devices:
        raise SystemExit(
            f"❌ {inventory_dir}: no generated inventory to read resolved "
            "addresses from. Run `make generate` first.")

    shutil.copy(source_xlsx, out_path)
    wb = openpyxl.load_workbook(out_path)

    if "Switch Data" in wb.sheetnames:
        _fill_switch_data(wb["Switch Data"], host_vars, host_asn,
                          devices)
    if "Host Data" in wb.sheetnames:
        eth_map = _eth_to_physical(inventory_dir, source_xlsx)
        _rewrite_host_data(wb, devices, eth_map)

    note = ("# Generated by `make import`. Every address below is the value "
            "the tool resolved. Edits here are ignored -- change the source "
            "workbook instead.")
    if "Derived" in wb.sheetnames:
        d = wb["Derived"]
        d.cell(d.max_row + 2, 1, note)

    # The completed workbook is a COPY of the source, so it inherits whatever
    # that file carried -- including a freeze on `Deployment` from a workbook
    # converted before freezing was dropped there. Clear it rather than
    # propagate it into every completed copy from here on.
    for name in ("Deployment", "Derived"):
        if name in wb.sheetnames:
            wb[name].freeze_panes = None

    for ws in wb.worksheets:
        if ws.title in ("Switch Data", "Host Data"):
            spec = intake_style.SHEET_SPECS.get(ws.title)
            hrow = spec["header"][0] if spec else 1
            headers = [ws.cell(hrow, c).value
                       for c in range(1, ws.max_column + 1)]
            intake_style.style_sheet(ws, headers)

    wb.save(out_path)
    return out_path


def resolve_and_emit(source_xlsx, arch, site, out_path=None):
    """Resolve into a throwaway inventory, then emit the completed workbook.

    `make import` runs before anything has been generated, so there is no
    inventory to read yet. Resolving into a temp directory keeps the
    completed workbook a product of the REAL pipeline -- the alternative,
    a second copy of the allocator living here, is exactly how a workbook
    ends up disagreeing with the configs it claims to describe.
    """
    import subprocess
    import tempfile

    source_xlsx = Path(source_xlsx)
    with tempfile.TemporaryDirectory() as tmp:
        inv = Path(tmp) / "inventory"
        inv.mkdir()
        r = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "excel_parser.py"),
             "--arch", arch, "--site", site, "--skip-validate"],
            cwd=Path(__file__).parent.parent,
            capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(
                "❌ could not resolve addresses for the completed workbook:\n"
                f"{r.stdout}\n{r.stderr}")
        # Topology too: it carries the authoritative eth -> switch-port
        # assignment, which is half of the join that fills `Physical
        # Interface`. Without it every Host Data row loses its link back to
        # the cabling -- the whole point of that column. Non-fatal, because
        # a completed workbook without the join still beats none.
        subprocess.run(
            [sys.executable,
             str(Path(__file__).parent / "topology_generator.py"),
             "generate", "--arch", arch, "--site", site],
            cwd=Path(__file__).parent.parent,
            capture_output=True, text=True)

        generated = (Path(__file__).parent.parent / "output" / arch / site
                     / "inventory")
        return emit(source_xlsx, generated, out_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, help="authored workbook")
    ap.add_argument("--inventory", help="generated inventory directory")
    ap.add_argument("--arch", help="resolve first, then emit (with --site)")
    ap.add_argument("--site", help="site to resolve (with --arch)")
    ap.add_argument("--out", help="destination (default: <name>-complete.xlsx)")
    args = ap.parse_args()

    if args.arch and args.site:
        path = resolve_and_emit(args.source, args.arch, args.site, args.out)
    elif args.inventory:
        path = emit(args.source, args.inventory, args.out)
    else:
        ap.error("give either --inventory, or --arch and --site")
    print(f"✓ Completed workbook (every resolved address): {path}")


if __name__ == "__main__":
    main()
