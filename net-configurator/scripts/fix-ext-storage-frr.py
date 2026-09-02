#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Auto-remediate ext-storage nodes whose first-boot `apt-get install frr` lost
the DNS/NAT race (the documented `air-deploy.py::_inject_ext_storage_instructions`
failure — silent, surfaces only as a STORAGE-VRF eBGP session Idle on the CSLs).

Usage:  make fix-ext-storage ARCH=<arch> [SITE=<site>]
        python3 scripts/fix-ext-storage-frr.py --arch <arch> [--site <site>]

- Discovers ext-storage targets from the generated topology (shared
  `airlib.ext_storage_config`, so the FRR config matches air-deploy exactly).
- Reaches each node **via the Air jump** (utility), same SSH path the
  validation playbooks use, at the node's air-mgmt eth0 IP.
- Idempotent: a node with FRR already active + configured is a no-op skip.
- Non-zero exit only if a node it *tried* to fix is still down afterward, so a
  healthy fabric is a clean run.
"""
import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import yaml  # noqa: E402

from airlib.ext_storage_config import (  # noqa: E402
    DEFAULT_AIR_MGMT_SUBNET,
    build_daemons,
    build_frr_conf,
    discover_ext_storage_targets,
)


def build_node_remediation(target: dict) -> str:
    """Return the root shell that repairs FRR on one ext-storage node.

    Idempotent (healthy → skip); on the repair path it gates on outbound DNS,
    apt-installs FRR, writes the shared builder's `daemons` + `frr.conf`,
    enables+restarts frr, and verifies. Emits a single `FIX|<node>|...` line
    and exits non-zero only if FRR is still inactive after the attempt.
    """
    node = target["node_name"]
    frr_b64 = base64.b64encode(
        build_frr_conf(node, target["lo_ip"], target["peer_ifaces"]).encode()
    ).decode()
    daemons_b64 = base64.b64encode(build_daemons().encode()).decode()
    return f"""set -u
NODE={node}
# Idempotent: a healthy node (frr active + config present) is a no-op.
if systemctl is-active --quiet frr && [ -f /etc/frr/frr.conf ]; then
  echo "FIX|$NODE|OK|frr already active + configured"; exit 0
fi
echo "FIX|$NODE|REPAIR|frr missing/inactive — installing"
# Gate on outbound DNS (the exact first-boot race we're remediating).
for i in $(seq 1 60); do
  getent hosts archive.ubuntu.com >/dev/null 2>&1 && break
  sleep 5
done
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || true
apt-get install -y -qq frr frr-pythontools
echo '{daemons_b64}' | base64 -d > /etc/frr/daemons
echo '{frr_b64}' | base64 -d > /etc/frr/frr.conf
chown frr:frr /etc/frr/daemons /etc/frr/frr.conf
chmod 640 /etc/frr/daemons /etc/frr/frr.conf
systemctl enable frr
systemctl restart frr
sleep 3
if systemctl is-active --quiet frr; then
  echo "FIX|$NODE|FIXED|frr installed + active"
else
  echo "FIX|$NODE|FAIL|frr still inactive after install"; exit 1
fi
"""


# --------------------------------------------------------------------------
# Orchestration (jump SSH glue — verified live, not unit-tested)
# --------------------------------------------------------------------------

_SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "ConnectTimeout=15",
    "-o", "LogLevel=ERROR",
]


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _run_via_jump(inv_hosts: Path, node_pw: str, eth0_ip: str,
                  script: str) -> tuple[int, str]:
    """Run a root shell on an ext-storage node through the Air jump.

    Uses `ansible jump -m shell` for the hop to the jump — the same proven
    connection the validation playbooks use (Air resolves the jump's SSH
    service/key from the inventory) — then sshpass from the jump to the node's
    air-mgmt eth0. The remediation is base64-embedded so it survives both hops.
    """
    script_b64 = base64.b64encode(script.encode()).decode()
    inner = (
        f"echo {script_b64} | base64 -d | "
        f"sshpass -p '{node_pw}' ssh {' '.join(_SSH_OPTS)} "
        f"ubuntu@{eth0_ip} 'sudo bash -s'"
    )
    cmd = ["ansible", "jump", "-i", str(inv_hosts), "-m", "shell", "-a", inner]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return p.returncode, (p.stdout + p.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Remediate ext-storage FRR via the jump")
    ap.add_argument("--arch", required=True)
    ap.add_argument("--site", default="default")
    args = ap.parse_args()

    base = Path("output") / args.arch / args.site
    topo_path = base / "topology" / f"{args.arch}-topology.json"
    inv_hosts = base / "inventory" / "hosts"
    if not topo_path.exists():
        print(f"❌ topology not found: {topo_path} (run `make generate` first)")
        return 2
    if not inv_hosts.exists():
        print(f"❌ inventory not found: {inv_hosts} (run air-deploy first).")
        return 2
    topology = json.loads(topo_path.read_text())

    # ERA-93: read the air-mgmt plane from the same generated inventory
    # air-deploy pinned it from, so a re-install lands on the addresses the sim
    # actually has instead of the 172.20.0.x literal the builder defaults to.
    _main_yml = base / "inventory" / "group_vars" / "all" / "main.yml"
    air_mgmt_subnet = (_load_yaml(_main_yml) or {}).get("air_mgmt_subnet")

    targets = [t for t in discover_ext_storage_targets(
        topology, air_mgmt_subnet=air_mgmt_subnet or DEFAULT_AIR_MGMT_SUBNET)
        if t["peer_ifaces"]]
    if not targets:
        print("✓ No ext-storage nodes with CSL uplinks in this topology — nothing to fix.")
        return 0

    secrets = _load_yaml(base / "inventory" / "group_vars" / "all" / "secrets.yml")
    node_pw = secrets.get("server_ansible_password", "")

    print(f"Remediating {len(targets)} ext-storage node(s) via the Air jump...", flush=True)
    tried_and_failed = []
    for t in targets:
        script = build_node_remediation(t)
        rc, out = _run_via_jump(inv_hosts, node_pw, t["eth0_ip"], script)
        # The remediation may emit an intermediate "FIX|…|REPAIR|…" before its
        # final verdict — take the LAST FIX line as the outcome.
        fix_lines = [l for l in out.splitlines() if l.startswith("FIX|")]
        line = fix_lines[-1] if fix_lines else \
            f"FIX|{t['node_name']}|FAIL|no FIX line from jump (rc={rc})"
        print(f"  {line}", flush=True)
        # A node counts as failed only if it was NOT already OK/FIXED.
        if "|OK|" not in line and "|FIXED|" not in line:
            tried_and_failed.append(t["node_name"])

    if tried_and_failed:
        print(f"❌ Still down after remediation: {', '.join(tried_and_failed)}")
        return 1
    print("✓ ext-storage FRR remediation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
