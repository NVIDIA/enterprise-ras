#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Check Air resource budget and optionally project topology requirements.

Usage:
    python scripts/air-budget-check.py --arch 2-8-5-200

Or via Makefile:
    make air-budget ARCH=2-8-5-200
"""

import argparse
import json
import ssl
import sys
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import httpx
from rich.console import Console

from airlib.api import get_resource_budget
from airlib.auth import authenticate
from airlib.budget import format_budget_row
from airlib.env import load_air_config, require_config
from airlib.errors import AirError

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Air resource budget")
    parser.add_argument("--arch", required=True, help="Architecture (e.g., 2-8-5-200)")
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

        budget = get_resource_budget(client, base_url, token)

        console.print("[bold]Current Resource Budget:[/]")
        console.print(format_budget_row("CPU", budget.cpu_used, budget.cpu, "vCPUs"))
        console.print(format_budget_row("Memory", budget.memory_used, budget.memory, "MB"))
        console.print(format_budget_row("Storage", budget.storage_used, budget.storage, "GB"))
        console.print(format_budget_row("Simulations", budget.simulations_used, budget.simulations, ""))
        console.print(format_budget_row("UserConfigs", budget.userconfigs_used, budget.userconfigs, "bytes"))
        console.print()

        # Project topology requirements
        topology_path = (project_root / "output" / args.arch / args.site
                         / "topology" / f"{args.arch}-topology.json")
        if topology_path.exists():
            topo = json.loads(topology_path.read_text())
            nodes = topo.get("content", {}).get("nodes", {})
            req_cpu = sum(p.get("cpu", 2) for p in nodes.values())
            req_mem = sum(p.get("memory", 2048) for p in nodes.values())
            req_storage = sum(p.get("storage", 10) for p in nodes.values())

            console.print(f"[bold]Topology Projection ({args.arch}):[/]")
            console.print(f"  Nodes: {len(nodes)}")
            console.print(f"  CPU:     {req_cpu} vCPUs  (available: {budget.cpu - budget.cpu_used})")
            console.print(f"  Memory:  {req_mem} MB  (available: {budget.memory - budget.memory_used})")
            console.print(f"  Storage: {req_storage} GB  (available: {budget.storage - budget.storage_used})")

            # Warnings
            proj_cpu = budget.cpu_used + req_cpu
            proj_mem = budget.memory_used + req_mem
            if budget.cpu > 0 and proj_cpu > budget.cpu:
                console.print(f"  [red]OVER BUDGET:[/] CPU {proj_cpu}/{budget.cpu}")
            elif budget.cpu > 0 and proj_cpu / budget.cpu > 0.90:
                console.print(f"  [yellow]Warning:[/] CPU would be at {proj_cpu}/{budget.cpu} (>90%)")

            if budget.memory > 0 and proj_mem > budget.memory:
                console.print(f"  [red]OVER BUDGET:[/] Memory {proj_mem}/{budget.memory}")
            elif budget.memory > 0 and proj_mem / budget.memory > 0.90:
                console.print(f"  [yellow]Warning:[/] Memory would be at {proj_mem}/{budget.memory} (>90%)")
        else:
            console.print(f"  No topology found at {topology_path}")
            console.print(f"  Run 'make generate ARCH={args.arch}' to project requirements")

    return 0


if __name__ == "__main__":
    sys.exit(main())
