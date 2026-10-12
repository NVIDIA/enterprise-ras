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

    # Cleanup orphaned cloud-init configs only (this site's, never another's)
    python scripts/air-destroy.py --arch 2-8-5-200 --site lab --cleanup-only

Or via Makefile:
    make air-destroy ARCH=2-8-5-200
    make air-destroy ARCH=2-8-5-200 SIM=ERA-2-8-5-200-default
"""

import argparse
import re
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
    list_userconfigs,
    resolve_simulation,
)
from airlib.auth import authenticate
from airlib.env import load_air_config, require_config
from airlib.errors import AirAPIError, AirConfigError, AirError
from _valid_archs import VALID_ARCHS

console = Console()

SITE_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")
USERCONFIG_NAME_MAX = 64


def era_title(site: str, arch: str) -> str:
    """The simulation title air-deploy gives a site: `ERA-<site>-<arch>`."""
    return f"ERA-{site}-{arch}"


def _contains_arch(tokens: list[str], archs: tuple[str, ...]) -> bool:
    for arch in archs:
        want = arch.split("-")
        for i in range(len(tokens) - len(want) + 1):
            if tokens[i:i + len(want)] == want:
                return True
    return False


def owned_by(
    name: str, site: str, arch: str, archs: tuple[str, ...] = VALID_ARCHS,
) -> bool:
    """True if `name` is this site's title, or the title plus a `-<suffix>`.

    A prefix test alone is not ownership: `ERA-lab-2-8-9-400-` also starts
    `ERA-lab-2-8-9-400-SP` and `ERA-lab-2-8-9-400-x-2-4-3-200` (site
    `lab-2-8-9-400-x`). Every ERA title ends in an arch, so a suffix that
    contains an arch, or continues `arch` into a longer one, is another
    site's. Air keeps only the first 64 characters of a name, and the cut can
    drop a foreign arch or extend another title into ours, so no name at that
    cap is provably ours. Ambiguous names are kept, never deleted.
    """
    if len(name) >= USERCONFIG_NAME_MAX:
        return False
    title = era_title(site, arch)
    if name == title:
        return True
    if not name.startswith(title + "-"):
        return False
    rest = name[len(title) + 1:].split("-")
    if _contains_arch(rest, archs):
        return False
    for other in archs:
        if other.startswith(arch + "-"):
            tail = other[len(arch) + 1:].split("-")
            if rest[:len(tail)] == tail:
                return False
    return True


def check_site_arch(site: str, arch: str) -> None:
    """Refuse an ARCH/SITE that no air-deploy run could have titled.

    SITE uses the Makefile / `.era-context` SITE grammar, which is what
    `air-deploy` titles with; it admits `.`, unlike `safe_site_name()`.
    """
    if arch not in VALID_ARCHS:
        raise AirConfigError(
            f"unknown arch {arch!r} — must be one of: {', '.join(sorted(VALID_ARCHS))}")
    if not SITE_RE.match(site) or ".." in site:
        raise AirConfigError(
            f"invalid site {site!r} — must match [A-Za-z0-9_-][A-Za-z0-9._-]*")


def cleanup_userconfigs(
    client: httpx.Client, base_url: str, token: str, *, prefix: str = "",
) -> int:
    """Delete UserConfigs whose name starts with `prefix`. Returns count deleted."""
    configs = list_userconfigs(client, base_url, token)
    if prefix:
        configs = [c for c in configs if c.name.startswith(prefix)]
    return delete_userconfigs(client, base_url, token, configs)


def maybe_truncated(name: str, site: str, arch: str) -> bool:
    """True if `name` is at Air's cap and could be this site's title, cut."""
    title = era_title(site, arch)
    return len(name) >= USERCONFIG_NAME_MAX and (
        name.startswith(title + "-") or name == title[:USERCONFIG_NAME_MAX])


def owned_userconfigs(
    client: httpx.Client, base_url: str, token: str, site: str, arch: str,
) -> tuple[list, list]:
    """(UserConfigs `owned_by` this site, ones at the cap kept as unprovable)."""
    configs = list_userconfigs(client, base_url, token)
    return ([c for c in configs if owned_by(c.name, site, arch)],
            [c for c in configs if maybe_truncated(c.name, site, arch)])


def delete_userconfigs(
    client: httpx.Client, base_url: str, token: str, configs: list,
) -> int:
    """Delete `configs`, warning on each failure. Returns count deleted."""
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
                        help="Only delete this site's UserConfigs (ERA-<site>-<arch>[-…]); "
                             "never touches a simulation")
    parser.add_argument("--force", action="store_true",
                        help="Skip confirmation prompt")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    if args.cleanup_only:
        try:
            check_site_arch(args.site, args.arch)
        except AirConfigError as exc:
            console.print(f"[red]Error:[/] {exc}")
            return exc.exit_code

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
            title = era_title(args.site, args.arch)
            console.print(f"Cleaning up UserConfigs named {title} or {title}-…")
            try:
                configs, kept = owned_userconfigs(
                    client, base_url, token, args.site, args.arch)
            except AirError as exc:
                console.print(f"[red]Error:[/] {exc}")
                return exc.exit_code
            for config in kept:
                console.print(
                    f"  [yellow]Kept:[/] {config.name} — at Air's "
                    f"{USERCONFIG_NAME_MAX}-char name limit, so it may be another "
                    "site's name cut short; delete it by hand if it is yours")
            for config in configs:
                console.print(f"  Matched: {config.name}")
            if configs and not args.force:
                try:
                    response = input(
                        f"  Delete these {len(configs)} UserConfig(s)? [y/N]: "
                    ).strip().lower()
                except EOFError:
                    console.print("  No TTY to confirm — pass --force to delete without a prompt. Cancelled.")
                    return 0
                if response != "y":
                    console.print("  Cancelled.")
                    return 0
            deleted = delete_userconfigs(client, base_url, token, configs)
            console.print(f"  Deleted {deleted} UserConfig(s)")
            return 0

        # Find the simulation
        try:
            if args.sim:
                sim = resolve_simulation(client, base_url, token, args.sim)
            else:
                # Try to find by expected title
                expected_title = era_title(args.site, args.arch)
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
            try:
                response = input("  Continue? [y/N]: ").strip().lower()
            except EOFError:
                # Non-interactive: cancel cleanly instead of a raw EOFError.
                console.print("  No TTY to confirm — pass --force to destroy without a prompt. Cancelled.")
                return 0
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
