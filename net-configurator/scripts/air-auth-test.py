#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Test Air API credentials, connectivity, and show account info.

Usage:
    python scripts/air-auth-test.py --arch 2-8-5-200
    python scripts/air-auth-test.py --arch 2-8-5-200 --site customer-a

Or via Makefile:
    make air-auth-test ARCH=2-8-5-200
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

from airlib.api import get_resource_budget, list_simulations
from airlib.auth import authenticate
from airlib.budget import format_budget_row
from airlib.env import load_air_config, require_config
from airlib.errors import AirError
from airlib.ssh import get_key_fingerprint

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Air API credentials")
    parser.add_argument("--arch", required=True, help="Architecture (e.g., 2-8-5-200)")
    parser.add_argument("--site", default="default", help="Site name")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    console.print("[bold]Air API Credential Test[/]")
    console.print()

    # Load config
    try:
        config = load_air_config(args.arch, args.site, project_root)
    except AirError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return exc.exit_code

    base_url = config.get("base_url", "NOT SET")
    username = config.get("username", "")
    api_key = config.get("api_key", "")
    ssh_key_path = config.get("ssh_key_path", "")

    console.print(f"  Base URL:     {base_url}")
    console.print(f"  Username:     {username or '(NGC direct bearer mode)'}")
    console.print(f"  API Key:      {'*' * 8}...{api_key[-4:]}" if len(api_key) > 4 else f"  API Key:      {'NOT SET'}")
    console.print(f"  SSH Key:      {ssh_key_path}")
    console.print()

    try:
        require_config(config, "base_url", "api_key")
    except AirError as exc:
        console.print(f"[red]FAIL:[/] {exc}")
        return exc.exit_code

    failures: list[str] = []
    subscription_missing = False

    def _is_subscription_error(exc: AirError) -> bool:
        msg = str(exc)
        return "402" in msg and ("PAYMENT_REQUIRED" in msg or "subscription" in msg.lower())

    headers = {"Accept-Encoding": "gzip, deflate, br"}
    with httpx.Client(timeout=30, verify=ssl.create_default_context(), headers=headers) as client:
        # Test authentication
        console.print("Testing authentication...")
        try:
            token = authenticate(client, base_url, username, api_key)
            console.print("  [green]OK[/] - Authenticated successfully")
        except AirError as exc:
            console.print(f"  [red]FAIL[/] - {exc}")
            return exc.exit_code

        # List simulations
        console.print("Listing simulations...")
        try:
            sims = list_simulations(client, base_url, token)
            console.print(f"  [green]OK[/] - {len(sims)} simulation(s)")
            for sim in sims:
                console.print(f"    [{sim.state}] {sim.title}  {sim.id}")
        except AirError as exc:
            console.print(f"  [red]FAIL[/] - {exc}")
            failures.append("list simulations")
            if _is_subscription_error(exc):
                subscription_missing = True

        # Resource budget
        console.print("Checking resource budget...")
        try:
            budget = get_resource_budget(client, base_url, token)
            console.print(f"  [green]OK[/]")
            console.print(format_budget_row("CPU", budget.cpu_used, budget.cpu, "vCPUs"))
            console.print(format_budget_row("Memory", budget.memory_used, budget.memory, "MB"))
            console.print(format_budget_row("Storage", budget.storage_used, budget.storage, "GB"))
            console.print(format_budget_row("Simulations", budget.simulations_used, budget.simulations, ""))
            console.print(format_budget_row("UserConfigs", budget.userconfigs_used, budget.userconfigs, "bytes"))
        except AirError as exc:
            console.print(f"  [red]FAIL[/] - {exc}")
            failures.append("resource budget")
            if _is_subscription_error(exc):
                subscription_missing = True

        # SSH key check (local only — NGC manages keys via web UI, not API)
        if ssh_key_path:
            console.print("Checking SSH key...")
            try:
                fingerprint = get_key_fingerprint(ssh_key_path)
                console.print(f"  [green]OK[/] - Local key: {fingerprint}")
                console.print(f"  Ensure this key is registered in Air: Settings -> SSH Keys")
            except AirError as exc:
                console.print(f"  [yellow]Warning:[/] {exc}")

    console.print()

    if subscription_missing:
        console.print("[bold red]FAIL:[/] Your NGC org does not have an active NVIDIA Air-Inside subscription.")
        console.print("Authentication works, but deployments will fail until a subscription is attached to this account.")
        console.print("Action: request Air-Inside access for your NGC org, or switch to an org that already has it.")
        return 3

    if failures:
        console.print(f"[bold red]FAIL:[/] {len(failures)} check(s) did not pass: {', '.join(failures)}")
        return 3

    console.print("[bold green]All checks passed.[/]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
