# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Regression guard: the *dead* source
`inventories/<arch>/host_vars/` files (per-switch core/leaf/spine/cl/cs/gl/gs
host_vars) are regenerated fresh into ``output/`` on every run and were
deleted from the source seed.

The *live* exception: the Air virtual-node seeds
(``external-conn``/``external-dhcp``/``utility`` for L3-OOB,
``dhcp-oob``/``oob-server-01`` for L2-OOB). These nodes never appear in the
Excel Nodes sheet, so ``generate_host_vars()`` cannot produce them. Instead,
the merge loop in ``scripts/excel_parser.py`` ("Merge host_vars for Air
virtual nodes from source inventory") reads each ``inventories/<arch>/
host_vars/<vnode>.yml`` seed on every generate and writes it into the output
inventory (preserving any real ``ansible_host`` that air-deploy wrote). They
carry static connection scaffolding (``ansible_host: CHANGE_ME``, hostname,
port, user) — not deployment-derived facts — so they stay as seed files.

Every per-switch flow reads ``-i output/<arch>/<site>/inventory/hosts``
(``Makefile`` ``INVENTORY_DIR = output/$(ARCH)/$(SITE)/inventory``); source
host_vars are never read for real switches. The only textual reference to
source host_vars was a vestigial pre-rename glob in the ``generate`` recipe's
``AIR_SWITCHES_ONLY`` block (``host_vars/leaf*smn*ipp6.yml``) that matched
zero files after the cl/cs/gl/gs role rename — confirmed dead and removed.

This test asserts: (a) each source ``host_vars/`` dir contains ONLY the
allowed virtual-node seeds — no per-switch host_vars crept back; (b) the
seeds the merge loop reads still exist; and (c) the Makefile has no
source-host_vars reference.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The only source host_vars the parser's Air-virtual-node merge loop reads.
ALLOWED_VNODE_SEEDS = {
    "external-conn.yml",
    "external-dhcp.yml",
    "utility.yml",
    "dhcp-oob.yml",
    "oob-server-01.yml",
}


def test_source_host_vars_contain_only_virtual_node_seeds():
    """No per-switch (core/leaf/spine/cl/cs/gl/gs) host_vars in the source seed.

    Only the Air virtual-node seeds the merge loop actually reads may remain;
    everything else is regenerated into output/ and must stay deleted.
    """
    inventories_dir = REPO / "inventories"
    assert inventories_dir.is_dir(), f"expected {inventories_dir} to exist"
    stray = []
    for hv_dir in sorted(inventories_dir.glob("*/host_vars")):
        if not hv_dir.is_dir():
            continue
        for f in sorted(hv_dir.glob("*.yml")):
            if f.name not in ALLOWED_VNODE_SEEDS:
                stray.append(str(f.relative_to(REPO)))
    assert stray == [], (
        "source host_vars must contain only Air virtual-node seeds "
        f"({sorted(ALLOWED_VNODE_SEEDS)}); dead per-switch host_vars found"
        f": {stray}"
    )


def test_air_vnode_host_vars_live_in_single_home():
    """The Air virtual-node host_vars moved from the per-arch seed
    `inventories/<arch>/host_vars/` into the single-home
    `scripts/inventory_defaults.yml` ('host_vars' section). No seed host_vars
    dirs remain, and each arch entry there carries the COMPLETE vnode set (an
    operator can switch a site between L2- and L3-OOB, so both modes' seeds must
    be present). Archs that carry none (2-4-5-800 — a known normalization gap)
    are simply absent from the section.
    """
    import yaml
    stray = [str(p.relative_to(REPO)) for p in (REPO / "inventories").glob("*/host_vars")
             if p.is_dir()]
    assert stray == [], f"seed host_vars dirs must be gone: {stray}"

    defaults = yaml.safe_load((REPO / "scripts" / "inventory_defaults.yml").read_text())
    hv = defaults.get("host_vars") or {}
    assert hv, "inventory_defaults.yml must carry the Air virtual-node host_vars"
    incomplete = {}
    for arch, entry in hv.items():
        present = {f"{k}.yml" for k in entry} & ALLOWED_VNODE_SEEDS
        missing = ALLOWED_VNODE_SEEDS - present
        if missing:
            incomplete[arch] = sorted(missing)
    assert not incomplete, (
        "each arch's vnode host_vars in inventory_defaults.yml must be complete "
        f"{sorted(ALLOWED_VNODE_SEEDS)}; missing: {incomplete}"
    )


def test_makefile_has_no_source_host_vars_reference():
    """The Makefile must not reference `inventories/<arch>/host_vars/` (source host_vars)."""
    text = (REPO / "Makefile").read_text()
    # Match the source-tree pattern specifically (inventories/.../host_vars),
    # not the *output* INVENTORY_DIR/host_vars references, which are legitimate.
    hits = re.findall(r"inventories/[^\s\"']*host_vars", text)
    assert hits == [], (
        f"Makefile must not read source host_vars (vestigial glob): {hits}"
    )


def test_inventory_dir_points_at_output_not_inventories():
    """`INVENTORY_DIR` (used by every live generate/deploy/validate target) is output-rooted."""
    text = (REPO / "Makefile").read_text()
    m = re.search(r"^INVENTORY_DIR\s*=\s*(\S+)", text, re.MULTILINE)
    assert m, "INVENTORY_DIR definition not found in Makefile"
    assert m.group(1) == "output/$(ARCH)/$(SITE)/inventory", (
        "INVENTORY_DIR must stay output-rooted — source inventories/<arch>/ "
        "host_vars are never read at deploy time"
    )
