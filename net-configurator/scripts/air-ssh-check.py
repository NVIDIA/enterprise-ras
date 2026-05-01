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
)

console = Console()

# Jump hosts that switch-ztp-deploy needs to SSH into
JUMP_HOSTS = ["oob-server-01", "dhcp-oob"]

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


def _load_jump_host_targets(host_vars_dir: Path) -> list[dict]:
    """Read host_vars for jump hosts, return list of connection targets."""
    targets = []
    # Check standard jump hosts + dhcp-edge if present
    candidates = list(JUMP_HOSTS)
    if (host_vars_dir / "dhcp-edge.yml").exists():
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

    if not agent_running:
        console.print()
        console.print("[yellow]WARN:[/] No ssh-agent running.")
        console.print("  Key-based auth will fail if your key has a passphrase.")
        console.print("  Start the agent and load your key:")
        console.print()
        console.print(f"    eval $(ssh-agent) && ssh-add {ssh_key_path}")
        console.print()
        console.print("  To make this persistent across terminal sessions, add to ~/.bashrc:")
        console.print('    if [ -z "$SSH_AUTH_SOCK" ]; then eval $(ssh-agent -s) > /dev/null; fi')
        console.print()
    elif not agent_has_key:
        console.print()
        console.print("[yellow]WARN:[/] SSH key not loaded in ssh-agent.")
        console.print("  Key-based auth will fail if your key has a passphrase.")
        console.print("  Load it now:")
        console.print()
        console.print(f"    ssh-add {ssh_key_path}")
        console.print()
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

    targets = _load_jump_host_targets(host_vars_dir)

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

        # 5b: SSH key auth check
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

        # 5e: Re-verify after injection
        if check_key_access(host, port, user, ssh_key_path):
            console.print("  [green]OK[/] — SSH key auth now works")
            results[name] = "fixed"
        else:
            console.print("  [red]FAIL[/] — Key auth still fails after injection")
            results[name] = "fail"

    # ------------------------------------------------------------------
    # Step 6: Summary
    # ------------------------------------------------------------------
    console.print()
    console.print("[bold]Summary:[/]")

    any_fail = False
    any_fixed = False
    any_pass_only = False
    for name, status in results.items():
        if status == "key_ok":
            console.print(f"  {name}: [green]OK[/] (key auth)")
        elif status == "pass_ok":
            console.print(f"  {name}: [green]OK[/] (password auth — Ansible will work)")
            any_pass_only = True
        elif status == "fixed":
            console.print(f"  {name}: [green]FIXED[/] (key injected)")
            any_fixed = True
        else:
            console.print(f"  {name}: [red]FAIL[/]")
            any_fail = True

    console.print()

    if not any_fail:
        if any_fixed:
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
