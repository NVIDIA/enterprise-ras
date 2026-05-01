#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Destroy an Air simulation and clean up orphaned UserConfigs.

Usage:
    # Auto-detect running simulation
    python scripts/air-destroy.py --arch 2-8-5-200

    # By name or ID
    python scripts/air-destroy.py --arch 2-8-5-200 --sim ERA-2-8-5-200-default
    python scripts/air-destroy.py --arch 2-8-5-200 --sim a1b2c3d4-...

    # Cleanup orphaned cloud-init configs only
    python scripts/air-destroy.py --arch 2-8-5-200 --cleanup-only

Or via Makefile:
    make air-destroy ARCH=2-8-5-200
    make air-destroy ARCH=2-8-5-200 SIM=ERA-2-8-5-200-default
"""

import argparse
import ssl
import sys
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import httpx
from rich.console import Console

from airlib.api import (
    delete_simulation,
    delete_userconfig,
    find_loaded_simulation,
    list_simulations,
    list_userconfigs,
    resolve_simulation,
    stop_simulation,
)
from airlib.auth import authenticate
from airlib.env import load_air_config, require_config
from airlib.errors import AirAPIError, AirError
from airlib.models import SimState

console = Console()


def cleanup_userconfigs(
    client: httpx.Client, base_url: str, token: str,
    *, prefix: str = "",
) -> int:
    """Delete UserConfigs, optionally filtered by name prefix. Returns count deleted."""
    configs = list_userconfigs(client, base_url, token)
    if prefix:
        configs = [c for c in configs if c.name.startswith(prefix)]

    if not configs:
        console.print("  No UserConfigs to clean up")
        return 0

    deleted = 0
    for config in configs:
        try:
            delete_userconfig(client, base_url, token, config.id)
            console.print(f"  Deleted: {config.name}")
            deleted += 1
        except AirAPIError as exc:
            console.print(f"  [yellow]Warning:[/] Failed to delete {config.name}: {exc}")

    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Destroy an Air simulation and clean up UserConfigs.",
    )
    parser.add_argument("--arch", required=True, help="Architecture (e.g., 2-8-5-200)")
    parser.add_argument("--site", default="default", help="Site name")
    parser.add_argument("--sim", help="Simulation name or UUID (auto-detects if omitted)")
    parser.add_argument("--cleanup-only", action="store_true",
                        help="Only clean up orphaned UserConfigs, don't destroy simulation")
    parser.add_argument("--force", action="store_true",
                        help="Skip confirmation prompt")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    try:
        config = load_air_config(args.arch, args.site, project_root)
        require_config(config, "base_url", "api_key")
    except AirError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return exc.exit_code

    base_url = config["base_url"]

    headers = {"Accept-Encoding": "gzip, deflate, br"}
    with httpx.Client(timeout=120, verify=ssl.create_default_context(), headers=headers) as client:
        try:
            token = authenticate(
                client, base_url,
                config.get("username", ""),
                config["api_key"],
            )
        except AirError as exc:
            console.print(f"[red]Error:[/] {exc}")
            return exc.exit_code

        if args.cleanup_only:
            console.print("Cleaning up UserConfigs...")
            prefix = f"ERA-{args.arch}"
            deleted = cleanup_userconfigs(client, base_url, token, prefix=prefix)
            console.print(f"  Deleted {deleted} UserConfig(s)")
            return 0

        # Find the simulation
        try:
            if args.sim:
                sim = resolve_simulation(client, base_url, token, args.sim)
            else:
                # Try to find by expected title
                expected_title = f"ERA-{args.site}-{args.arch}"
                try:
                    sim = resolve_simulation(client, base_url, token, expected_title)
                except AirAPIError:
                    # Fall back to auto-detecting the single loaded simulation
                    sim = find_loaded_simulation(client, base_url, token)
        except AirError as exc:
            console.print(f"[red]Error:[/] {exc}")
            return exc.exit_code

        console.print(f"  Found: {sim.title} ({sim.id}) [{sim.state}]")

        # Confirm
        if not args.force:
            console.print(f"\n  [bold]This will destroy simulation '{sim.title}'.[/]")
            response = input("  Continue? [y/N]: ").strip().lower()
            if response != "y":
                console.print("  Cancelled.")
                return 0

        # Delete (NGC v3 can delete in any state — no stop needed)
        console.print("Deleting simulation...")
        try:
            delete_simulation(client, base_url, token, sim.id)
            console.print(f"  Deleted: {sim.title}")
        except AirError as exc:
            console.print(f"[red]Error:[/] {exc}")
            return exc.exit_code

        # Cleanup UserConfigs
        console.print("Cleaning up UserConfigs...")
        prefix = sim.title[:40] if sim.title else f"ERA-{args.arch}"
        deleted = cleanup_userconfigs(client, base_url, token, prefix=prefix)
        console.print(f"  Deleted {deleted} UserConfig(s)")

        console.print()
        console.print("[bold]Simulation destroyed.[/]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
