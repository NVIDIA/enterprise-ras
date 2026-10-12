#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Prune per-node artefacts left behind by a previous `make generate`.

Re-generating into the same site after a node was renamed or disabled in the
workbook rewrites every *current* node's files but never removed the old
ones: `configs/<old>-config.sh`, `inventory/host_vars/<old>.yml` and
`topology/node-instructions/<old>.sh` stayed on disk, ready to be applied by
hand to a switch that no longer exists in the design.

Ownership rule — only files this pipeline generated are ever removed:

* A per-node artefact is one file in a generator-owned class:
  ``inventory/host_vars/<node>.yml``, ``configs/<node>-config.sh``,
  ``topology/node-instructions/<node>.sh``.
* After each run the set of per-node artefacts this run *wrote* is recorded
  in ``output/<arch>/<site>/generated-manifest.json``. `make generate` drops
  a start marker (``.generate-started``) before the first generator runs;
  only files modified after that marker, or already listed in the previous
  manifest, are adopted. A file that merely matches a current node's name
  but was not rewritten by this run (an operator's ``configs/<host>-config.sh``
  for a server, say) is never adopted and so can never be pruned later.
* On the next run a file is pruned only if its ``<node>`` is no longer
  current **and** the file is listed in the previous manifest. Files in those
  classes that the manifest does not know about (dropped in by an operator,
  or generated before the manifest existed) are reported and left alone.
* "Current" means a host in ``inventory/hosts``; for
  ``topology/node-instructions`` it additionally means a node of the Air
  topology JSON and — only while that topology is in L2 OOB-uplink mode —
  the legacy-L2 ``air-oob-switch`` / ``dhcp-oob`` / ``oob-server-01``
  scripts. Switching a site to L3 therefore prunes them like any other
  recorded artefact of a departed node.
* Everything outside the three classes — ``group_vars/all/secrets.yml``,
  ``hosts``, ``group_vars/all/main.yml``, the topology JSON, reports — is
  never touched. Air connection details (``ansible_host`` / ``ansible_port``
  / ``ansible_user``) live in the host_vars of *current* hosts, which are
  never pruned.

Usage (run by `make generate` as its last step):
    python3 scripts/prune_stale_artifacts.py --arch 2-8-9-800 --site default
    python3 scripts/prune_stale_artifacts.py --arch 2-8-9-800 --site default --dry-run
    python3 scripts/prune_stale_artifacts.py --arch 2-8-9-800 --site default --mark-start
    python3 scripts/prune_stale_artifacts.py --arch 2-8-9-800 --site default --adopt-all
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import topology_oob_uplink_mode  # noqa: E402

MANIFEST_NAME = "generated-manifest.json"
START_MARKER = ".generate-started"
MANIFEST_SCHEMA = 1

# Legacy-L2 Air infrastructure scripts written by generate-node-instructions.py
# only while the topology is in L2 mode; never hosts in inventory/hosts.
L2_INFRA_NODES = frozenset({"air-oob-switch", "dhcp-oob", "oob-server-01"})

# (directory relative to the site dir, glob, suffix to strip to get the node name)
ARTEFACT_CLASSES = (
    ("inventory/host_vars", "*.yml", ".yml"),
    ("configs", "*-config.sh", "-config.sh"),
    ("topology/node-instructions", "*.sh", ".sh"),
)


def parse_hosts(hosts_path: Path) -> set:
    """Return the host names declared in an INI inventory.

    Only plain host lines count: `[group:children]` and `[group:vars]`
    sections are skipped, comments and blank lines ignored, and inline
    `key=value` host variables dropped.
    """
    hosts = set()
    in_host_section = True
    for raw in hosts_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            in_host_section = ":" not in line
            continue
        if in_host_section:
            hosts.add(line.split()[0])
    return hosts


def parse_topology_nodes(site_dir: Path, arch: str) -> set:
    """Return the node names the node-instruction generator writes scripts
    for from the Air topology JSON: its ``content.nodes`` plus, only when the
    topology's OOB uplink mode is L2, the legacy-L2 infrastructure scripts.
    Empty set when there is no (readable) topology.
    """
    path = site_dir / "topology" / f"{arch}-topology.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    nodes = data.get("content", {}).get("nodes", {})
    current = set(nodes) if isinstance(nodes, dict) else set()
    if topology_oob_uplink_mode(data) == "l2":
        current |= L2_INFRA_NODES
    return current


def mark_start(site_dir: Path) -> Path:
    """Drop the run-start marker; files older than it are not adopted."""
    site_dir.mkdir(parents=True, exist_ok=True)
    marker = site_dir / START_MARKER
    marker.write_text("")
    return marker


def load_manifest(site_dir: Path) -> set:
    path = site_dir / MANIFEST_NAME
    if not path.exists():
        return set()
    data = json.loads(path.read_text())
    return set(data.get("files", []))


def write_manifest(site_dir: Path, arch: str, site: str, files: list) -> Path:
    path = site_dir / MANIFEST_NAME
    payload = {
        "schema": MANIFEST_SCHEMA,
        "arch": arch,
        "site": site,
        "note": "Per-node artefacts written by `make generate`; "
                "prune_stale_artifacts.py removes a listed file only when its "
                "node has left inventory/hosts. Do not hand-edit.",
        "files": sorted(files),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def prune(site_dir: Path, arch: str, site: str, dry_run: bool = False,
          since: float = None) -> dict:
    """Prune stale per-node artefacts and rewrite the manifest.

    ``since`` is the run-start time (epoch seconds): a current node's file is
    adopted into the manifest only if it was modified at or after it, or was
    already listed. ``None`` adopts every current node's file (first-time
    adoption of a site generated before the manifest existed).

    Returns {"current": [...], "pruned": [...], "unmanaged": [...],
    "skipped": [...]} with site-relative paths; ``skipped`` are files of
    current nodes that this run did not write and that are not owned.
    """
    hosts_path = site_dir / "inventory" / "hosts"
    if not hosts_path.exists():
        raise FileNotFoundError(f"inventory not found: {hosts_path}")
    hosts = parse_hosts(hosts_path)
    topo_nodes = parse_topology_nodes(site_dir, arch)
    owned = load_manifest(site_dir)

    current, pruned, unmanaged, skipped = [], [], [], []
    for rel_dir, pattern, suffix in ARTEFACT_CLASSES:
        directory = site_dir / rel_dir
        if not directory.is_dir():
            continue
        live = hosts | topo_nodes if rel_dir == "topology/node-instructions" else hosts
        for path in sorted(directory.glob(pattern)):
            if not path.is_file():
                continue
            node = path.name[: -len(suffix)]
            rel = str(path.relative_to(site_dir))
            if node in live:
                if rel in owned or since is None or path.stat().st_mtime >= since:
                    current.append(rel)
                else:
                    skipped.append(rel)
            elif rel in owned:
                pruned.append(rel)
                if not dry_run:
                    path.unlink()
            else:
                unmanaged.append(rel)

    if not dry_run:
        write_manifest(site_dir, arch, site, current)
    return {"current": current, "pruned": pruned, "unmanaged": unmanaged,
            "skipped": skipped}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--arch", required=True)
    parser.add_argument("--site", default="default")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be pruned; touch nothing")
    parser.add_argument("--base-dir", type=Path, default=None,
                        help="tool root (default: parent of scripts/)")
    parser.add_argument("--mark-start", action="store_true",
                        help=f"write {START_MARKER} and exit (run before the generators)")
    parser.add_argument("--adopt-all", action="store_true",
                        help="adopt every current node's file regardless of the "
                             "start marker (one-off adoption of a pre-manifest site)")
    args = parser.parse_args(argv)

    base = args.base_dir or Path(__file__).resolve().parent.parent
    site_dir = base / "output" / args.arch / args.site
    marker = site_dir / START_MARKER
    if args.mark_start:
        mark_start(site_dir)
        return 0

    since = None
    if not args.adopt_all:
        if not marker.exists():
            print(f"❌ {marker.relative_to(base)} not found: run with --mark-start "
                  "before generating, or --adopt-all to adopt a pre-manifest site")
            return 1
        since = marker.stat().st_mtime
    try:
        result = prune(site_dir, args.arch, args.site, dry_run=args.dry_run, since=since)
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        return 1
    if not args.dry_run and marker.exists():
        marker.unlink()

    verb = "would prune" if args.dry_run else "pruned"
    print(f"  Generated artefacts tracked: {len(result['current'])} "
          f"({site_dir.relative_to(base) / MANIFEST_NAME})")
    for rel in result["pruned"]:
        print(f"  ✓ {verb} stale {rel}")
    if result["pruned"]:
        print(f"  {verb.capitalize()} {len(result['pruned'])} stale per-node "
              "artefact(s) for nodes no longer in inventory/hosts")
    for rel in result["unmanaged"]:
        print(f"  ⚠️  {rel}: node not in inventory/hosts but not recorded in "
              f"{MANIFEST_NAME} — left in place (remove by hand if stale)")
    for rel in result["skipped"]:
        print(f"  ℹ️  {rel}: not written by this run — not adopted into {MANIFEST_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
