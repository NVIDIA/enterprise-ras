#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Diagnose and fix SSH key access to Air simulation jump hosts.

When Air simulations are created with NGC Service API keys, cloud-init
does not inject your SSH key.  This script checks SSH key auth against
oob-server-01 and dhcp-oob, and can automatically inject your public
key using password-based SSH (sshpass).

Usage:
    python scripts/air-ssh-check.py --arch 2-8-5-200
    python scripts/air-ssh-check.py --arch 2-8-5-200 --fix

Or via Makefile:
    make air-ssh-check ARCH=2-8-5-200
    make air-ssh-check ARCH=2-8-5-200 FIX=1
"""

import argparse
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import yaml
from rich.console import Console

from airlib.env import load_air_config, _read_vault_file
from airlib.errors import AirError, AirSSHError
from airlib.ssh import (
    check_key_access,
    check_password_access,
    check_port_open,
    get_key_fingerprint,
    get_public_key,
    inject_key_via_password,
    key_needs_passphrase,
    verify_key_in_authorized_keys,
)

console = Console()

# Jump hosts that switch-ztp-deploy needs to SSH into, per OOB-uplink mode.
# L2 mode: the classic ERA jump trio (oob-server-01 = jump, dhcp-oob = ZTP+DHCP).
# L3 mode: the three Ubuntu nodes from the L3 OOB design doc — utility (in-OOB-
# VRF jump + DHCP relay endpoint), external-conn (simulated ISP egress),
# external-dhcp (DHCP server for the OOB VRF). See
# docs/plans/2026-05-20-l3-oob-air-topology.md.
JUMP_HOSTS_L2 = ["oob-server-01", "dhcp-oob"]
JUMP_HOSTS_L3 = ["utility", "external-conn", "external-dhcp"]


def _detect_oob_mode(project_root: Path, arch: str, site: str) -> str:
    """Return 'l2' or 'l3' for this site by reading the generated topology."""
    topo = (project_root / "output" / arch / site / "topology"
            / f"{arch}-topology.json")
    if not topo.exists():
        return "l2"
    try:
        import json
        with open(topo) as f:
            mode = str(json.load(f).get("_oob_uplink_mode", "l2")).strip().lower()
        return mode or "l2"
    except (OSError, ValueError):
        return "l2"


# Fallback password (matches inventories/<arch>/group_vars/all/secrets.yml default)
DEFAULT_SERVER_PASSWORD = "nvidia"


def _load_server_password(project_root: Path, arch: str, site: str) -> str:
    """Load server_ansible_password from secrets.yml (generated or source)."""
    for secrets_path in [
        project_root / "output" / arch / site / "inventory" / "group_vars" / "all" / "secrets.yml",
        project_root / "inventories" / arch / "group_vars" / "all" / "secrets.yml",
    ]:
        try:
            secrets = _read_vault_file(secrets_path)
            pw = str(secrets.get("server_ansible_password", ""))
            if pw and pw != "CHANGE_ME":
                return pw
        except AirError:
            continue
    return DEFAULT_SERVER_PASSWORD


def _load_jump_host_targets(host_vars_dir: Path,
                            mode: str = "l2") -> list[dict]:
    """Read host_vars for jump hosts, return list of connection targets.

    `mode` is the OOB uplink mode resolved from the topology JSON.
    """
    targets = []
    candidates = list(JUMP_HOSTS_L3 if mode == "l3" else JUMP_HOSTS_L2)
    # dhcp-edge is an L2-mode optional jump (e.g. 2-8-9-400). It doesn't
    # exist in L3 mode topologies.
    if mode != "l3" and (host_vars_dir / "dhcp-edge.yml").exists():
        candidates.append("dhcp-edge")

    for node_name in candidates:
        hv_file = host_vars_dir / f"{node_name}.yml"
        if not hv_file.exists():
            console.print(f"  [yellow]Warning:[/] No host_vars for {node_name} — skipping")
            continue
        with open(hv_file) as f:
            hv = yaml.safe_load(f) or {}
        host = hv.get("ansible_host", "")
        port = hv.get("ansible_port", "")
        user = hv.get("ansible_user", "ubuntu")
        if not host or not port or "CHANGE_ME" in str(host):
            console.print(f"  [yellow]Warning:[/] {node_name} not configured "
                          f"(ansible_host={host}, ansible_port={port}) — skipping")
            continue
        targets.append({"name": node_name, "host": host, "port": port, "user": user})

    return targets


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check and fix SSH key access to Air jump hosts",
    )
    parser.add_argument("--arch", required=True, help="Architecture (e.g., 2-8-5-200)")
    parser.add_argument("--site", default="default", help="Site name")
    parser.add_argument("--fix", action="store_true",
                        help="Auto-inject SSH key if auth fails (requires sshpass)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    console.print("[bold]Air SSH Key Access Check[/]")
    console.print()

    # ------------------------------------------------------------------
    # Step 1: Check SSH key path is configured
    # ------------------------------------------------------------------
    try:
        config = load_air_config(args.arch, args.site, project_root)
    except AirError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return exc.exit_code

    ssh_key_path = config.get("ssh_key_path", "")

    if not ssh_key_path:
        console.print("[red]FAIL:[/] No SSH key path configured.")
        console.print()
        console.print("  Run the onboarding wizard to set your SSH key path:")
        console.print("    make air-setup")
        console.print()
        console.print("  Or override for this run:")
        console.print("    export AIR_SSH_KEY_PATH=~/.ssh/id_ed25519")
        return 1

    console.print(f"  SSH key path: {ssh_key_path}")

    # ------------------------------------------------------------------
    # Step 2: Verify key file exists locally
    # ------------------------------------------------------------------
    expanded_key = Path(ssh_key_path).expanduser()
    if not expanded_key.exists():
        console.print(f"[red]FAIL:[/] SSH key not found: {expanded_key}")
        console.print()
        console.print("  Generate a key pair:")
        console.print(f"    ssh-keygen -t ed25519 -f {ssh_key_path}")
        console.print()
        console.print("  Or update the path to point to your existing key.")
        return 1

    try:
        fingerprint = get_key_fingerprint(ssh_key_path)
        console.print(f"  Key fingerprint: {fingerprint}")
    except AirError as exc:
        console.print(f"  [yellow]Warning:[/] {exc}")

    # Prefer .pub companion file (works even if private key is passphrase-protected)
    pub_path = Path(f"{expanded_key}.pub")
    public_key = ""
    if pub_path.exists():
        public_key = pub_path.read_text().strip()
    if not public_key:
        try:
            public_key = get_public_key(ssh_key_path)
        except AirError as exc:
            console.print(f"[red]FAIL:[/] Cannot read public key: {exc}")
            console.print(f"  If your key is passphrase-protected, ensure {pub_path} exists.")
            return 1

    # ------------------------------------------------------------------
    # Step 2b: Check if passphrase-protected key is loaded in ssh-agent
    # ------------------------------------------------------------------
    agent_running = False
    agent_has_key = False
    try:
        agent_result = subprocess.run(
            ["ssh-add", "-l"], capture_output=True, text=True, timeout=5,
        )
        # returncode 2 = no agent, 1 = agent running but no keys, 0 = keys listed
        agent_running = agent_result.returncode != 2
        if agent_result.returncode == 0 and fingerprint:
            agent_has_key = fingerprint in agent_result.stdout
    except (subprocess.TimeoutExpired, OSError):
        pass

    # If the key has a passphrase AND it's not loaded in ssh-agent, every
    # local BatchMode key-auth attempt will fail. That includes this script's
    # `check_key_access` calls — but NOT Ansible plays, because Ansible has
    # `ansible_password` configured for the jump group (see
    # group_vars/servers.yml) and falls back to sshpass automatically.
    #
    # So this isn't a hard failure — it just means the script can't verify
    # local key auth. Inject anyway (server-side authorized_keys is still
    # the right end state for `ssh utility` from the operator's shell), and
    # use server-side verify_key_in_authorized_keys to prove the injection
    # landed. Print a clear note so the operator knows they need ssh-add to
    # actually USE keys locally — but the deploy pipeline continues.
    locked_key = key_needs_passphrase(ssh_key_path) and not agent_has_key

    if locked_key:
        console.print()
        console.print("[bold yellow]NOTE:[/] SSH key requires a passphrase and is not loaded in ssh-agent.")
        console.print("Local key-auth verification will be skipped (server-side checks used instead).")
        console.print("Ansible plays will work via password auth — deploy continues.")
        console.print()
        console.print("To enable `ssh utility` from your shell, load the key once per session:")
        console.print(f"    eval $(ssh-agent) && ssh-add {ssh_key_path}")
        console.print()
    elif not agent_running:
        console.print()
        console.print("[yellow]NOTE:[/] No ssh-agent running, but key is not passphrase-protected — continuing.")
    elif not agent_has_key:
        console.print()
        console.print("[yellow]NOTE:[/] Key not loaded in ssh-agent, but key is not passphrase-protected — continuing.")
    else:
        console.print("  [green]OK[/] — Key loaded in ssh-agent")

    console.print()

    # ------------------------------------------------------------------
    # Step 3: Read host_vars for jump hosts
    # ------------------------------------------------------------------
    host_vars_dir = (
        project_root / "output" / args.arch / args.site / "inventory" / "host_vars"
    )

    if not host_vars_dir.exists():
        console.print(f"[red]FAIL:[/] Host vars not found: {host_vars_dir}")
        console.print()
        console.print(f"  Run 'make air-deploy ARCH={args.arch}' first to create the")
        console.print("  simulation and populate inventory with SSH connection details.")
        return 1

    mode = _detect_oob_mode(project_root, args.arch, args.site)
    targets = _load_jump_host_targets(host_vars_dir, mode=mode)

    if not targets:
        console.print("[red]FAIL:[/] No configured jump hosts found.")
        console.print()
        console.print(f"  Run 'make air-deploy ARCH={args.arch}' or "
                      f"'make air-connect ARCH={args.arch}'")
        return 1

    # ------------------------------------------------------------------
    # Step 4: Load password for auto-fix
    # ------------------------------------------------------------------
    password = _load_server_password(project_root, args.arch, args.site)

    # ------------------------------------------------------------------
    # Step 5: Check each target
    # ------------------------------------------------------------------
    # Statuses: "key_ok", "pass_ok", "fixed", "fail"
    results: dict[str, str] = {}

    for target in targets:
        name = target["name"]
        host = target["host"]
        port = target["port"]
        user = target["user"]

        console.print(f"Checking {name} ({host}:{port})...")

        # 5a: TCP port check
        if not check_port_open(host, port):
            console.print(f"  [red]FAIL[/] — TCP port {port} not reachable")
            console.print(f"  Is the simulation running? Check: make air-list ARCH={args.arch}")
            results[name] = "fail"
            continue

        console.print("  [green]OK[/] — TCP port open")

        # 5b: SSH key auth check (skipped when local key is locked-no-agent —
        # the BatchMode call is guaranteed to fail in that state regardless
        # of remote authorized_keys, and the misleading "WARN — not accepted"
        # message reads as a remote issue when it's actually local).
        if locked_key:
            console.print("  [yellow]SKIP[/] — local key locked, deferring to server-side verification")
            key_ok = False
        else:
            key_ok = check_key_access(host, port, user, ssh_key_path)
            if key_ok:
                console.print("  [green]OK[/] — SSH key auth works")
                results[name] = "key_ok"
                continue
            console.print("  [yellow]WARN[/] — SSH key auth not accepted")

        # 5c: Password auth check (what Ansible actually uses)
        try:
            pass_ok = check_password_access(host, port, user, password)
        except AirSSHError as exc:
            console.print(f"  [yellow]Warning:[/] {exc}")
            pass_ok = False

        if pass_ok:
            console.print("  [green]OK[/] — Password auth works (Ansible will use this)")
            if not args.fix:
                console.print("  Tip: run with FIX=1 to also inject your SSH key")
                results[name] = "pass_ok"
                continue
            # --fix set: inject key even though password works
            console.print("  Injecting SSH key for key-based access...")
        else:
            console.print("  [red]FAIL[/] — Password auth also failed")
            if not args.fix:
                console.print("  Re-run with FIX=1 to attempt key injection")
                results[name] = "fail"
                continue
            console.print("  Attempting key injection with configured password...")

        # 5d: Inject SSH key via password auth
        try:
            injected = inject_key_via_password(host, port, user, password, public_key)
        except AirSSHError as exc:
            console.print(f"  [red]FAIL[/] — {exc}")
            results[name] = "fail"
            continue

        if not injected:
            console.print("  [red]FAIL[/] — Key injection failed (wrong password or SSH error)")
            console.print("  Default password 'nvidia' may have been changed.")
            console.print("  Check server_ansible_password in secrets.yml")
            results[name] = "fail"
            continue

        console.print("  Key injected — verifying...")

        # 5e: Re-verify after injection. If local key auth fails, prove
        # remotely (via password) whether the key is actually in
        # authorized_keys — that distinguishes a true injection failure
        # from a local-side problem (locked private key, missing agent,
        # bad ~/.ssh perms on the controller, etc.).
        if check_key_access(host, port, user, ssh_key_path):
            console.print("  [green]OK[/] — SSH key auth now works")
            results[name] = "fixed"
        elif verify_key_in_authorized_keys(host, port, user, password, public_key):
            console.print("  [yellow]INJECTED[/] — key is in remote authorized_keys, "
                          "but local SSH client can't complete key auth.")
            console.print("  Most likely cause: locked private key or agent issue. "
                          "Ansible will still use password auth.")
            results[name] = "injected_local_blocked"
        else:
            console.print("  [red]FAIL[/] — Key did not land in remote authorized_keys")
            console.print("  Possible causes: home dir perms wrong on remote, "
                          "or sshpass failed silently.")
            results[name] = "fail"

    # ------------------------------------------------------------------
    # Step 6: Summary
    # ------------------------------------------------------------------
    console.print()
    console.print("[bold]Summary:[/]")

    any_fail = False
    any_fixed = False
    any_pass_only = False
    any_local_blocked = False
    for name, status in results.items():
        if status == "key_ok":
            console.print(f"  {name}: [green]OK[/] (key auth)")
        elif status == "pass_ok":
            console.print(f"  {name}: [green]OK[/] (password auth — Ansible will work)")
            any_pass_only = True
        elif status == "fixed":
            console.print(f"  {name}: [green]FIXED[/] (key injected)")
            any_fixed = True
        elif status == "injected_local_blocked":
            console.print(f"  {name}: [yellow]INJECTED[/] (remote OK, local SSH blocked)")
            any_local_blocked = True
        else:
            console.print(f"  {name}: [red]FAIL[/]")
            any_fail = True

    console.print()

    if not any_fail:
        if any_local_blocked:
            console.print("[bold yellow]Keys are in authorized_keys on all hosts, "
                          "but local SSH key auth couldn't be verified.[/]")
            console.print("Ansible plays will use password auth and will succeed.")
            console.print("To also enable key auth locally, ensure your ssh-agent "
                          "has the key loaded and your ~/.ssh perms are correct.")
        elif any_fixed:
            console.print("[bold green]All jump hosts accessible. SSH keys were injected.[/]")
        elif any_pass_only:
            console.print("[bold green]All jump hosts accessible via password auth.[/]")
            console.print("Ansible plays will work. To also enable key auth, run:")
            console.print(f"  make air-ssh-check ARCH={args.arch} FIX=1")
        else:
            console.print("[bold green]All jump hosts accessible. SSH key auth is working.[/]")
        console.print(f"You can now run: make switch-ztp-deploy ARCH={args.arch}")
        return 0

    # Some failures remain
    failed = [n for n, s in results.items() if s == "fail"]
    console.print(f"[bold red]{len(failed)} host(s) not accessible.[/]")

    if not args.fix:
        console.print()
        console.print("To auto-fix, run:")
        console.print(f"  make air-ssh-check ARCH={args.arch} FIX=1")
        console.print()
        console.print("This will SSH in with the default password and inject your public key.")

    return 2


if __name__ == "__main__":
    sys.exit(main())
