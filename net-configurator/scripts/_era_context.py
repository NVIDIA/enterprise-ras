#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Validate `.era-context` and print shell-safe ARCH / SITE assignments.

Usage (from a Makefile recipe or shell):

    eval "$(python3 scripts/_era_context.py)"
    # sets: _ARCH and _SITE in the calling shell

Prints two lines of the form:

    _ARCH='2-8-5-200'
    _SITE='default'

Both values are passed through ``shlex.quote`` so they are safe to
``eval``. Exits non-zero with a diagnostic on stderr if ``.era-context``
is missing, malformed, or contains values that don't pass input
validation (e.g. an arch name not in the known set, or a site name
with characters that could traverse paths / inject shell metacharacters).

This script exists specifically to replace a 200-plus-char inline
Python one-liner in the Makefile that interpolated ``.era-context``
values directly into a Python string literal — a path-traversal /
command-injection hazard if the context file ever contained a
malicious ARCH or SITE. Centralising read + validation here means
every Makefile target that consumes the context gets the same
protection.
"""

import re
import shlex
import sys
from pathlib import Path

VALID_ARCHS = {"2-4-3-200", "2-8-5-200", "2-8-9-400", "2-8-9-800"}
# Site names end up in filesystem paths (input/<arch>/<site>/...), so
# require a conservative allowlist — no slashes, no dots-only, no spaces.
SITE_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")

CONTEXT_PATH = Path(".era-context")


def die(message: str) -> None:
    sys.stderr.write(f"era-context error: {message}\n")
    sys.exit(1)


def main() -> int:
    if not CONTEXT_PATH.exists():
        die(
            "no .era-context in the current directory — "
            "run `make use ARCH=<type> [SITE=<name>]` to create one"
        )

    arch = None
    site = None
    for raw_line in CONTEXT_PATH.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^arch:\s*(\S+)\s*$", line)
        if m:
            arch = m.group(1)
            continue
        m = re.match(r"^site:\s*(\S+)\s*$", line)
        if m:
            site = m.group(1)
            continue

    if arch is None:
        die(".era-context is missing an 'arch:' line")
    if arch not in VALID_ARCHS:
        die(
            f"invalid arch {arch!r} in .era-context — must be one of: "
            + ", ".join(sorted(VALID_ARCHS))
        )
    if site is None:
        site = "default"
    if not SITE_RE.match(site):
        die(
            f"invalid site {site!r} in .era-context — must match "
            "[A-Za-z0-9_-][A-Za-z0-9._-]* (no slashes, no leading dot)"
        )
    # Extra belt-and-braces against path traversal via sneaky site names.
    if ".." in site or site in ("", ".", ".."):
        die(f"invalid site {site!r} in .era-context — disallowed value")

    # shlex.quote preserves single quotes if the value ever contains any,
    # though the regex above already forbids them.
    print(f"_ARCH={shlex.quote(arch)}")
    print(f"_SITE={shlex.quote(site)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
