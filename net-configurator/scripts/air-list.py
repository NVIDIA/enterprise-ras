#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""List Air simulations with state and SSH service info.

Usage:
    python scripts/air-list.py --arch 2-8-5-200

Or via Makefile:
    make air-list ARCH=2-8-5-200
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

from airlib.api import get_ssh_services, list_simulations
from airlib.auth import authenticate
from airlib.env import load_air_config, require_config
from airlib.errors import AirError

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="List Air simulations")
    parser.add_argument("--arch", required=True, help="Architecture (for credential loading)")
    parser.add_argument("--site", default="default", help="Site name")
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
    with httpx.Client(timeout=30, verify=ssl.create_default_context(), headers=headers) as client:
        try:
            token = authenticate(
                client, base_url,
                config.get("username", ""),
                config["api_key"],
            )
        except AirError as exc:
            console.print(f"[red]Error:[/] {exc}")
            return exc.exit_code

        sims = list_simulations(client, base_url, token)
        if not sims:
            console.print("No simulations found.")
            return 0

        console.print(f"[bold]{len(sims)} simulation(s):[/]")
        console.print()

        for sim in sims:
            state_color = "green" if sim.is_loaded else "yellow" if sim.state == "STORED" else "dim"
            console.print(f"  [{state_color}]{sim.state:8s}[/]  {sim.title}")
            console.print(f"           ID: {sim.id}")
            if sim.owner:
                console.print(f"           Owner: {sim.owner}")

            # Show SSH services for loaded simulations
            if sim.is_loaded:
                try:
                    services = get_ssh_services(client, base_url, token, sim.id)
                    for svc in services:
                        if svc.is_ready:
                            console.print(f"           SSH: ssh -p {svc.src_port} ubuntu@{svc.host}")
                except AirError:
                    pass
            console.print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
