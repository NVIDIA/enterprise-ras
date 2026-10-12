# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""`ARCH` must be shell-safe before it reaches a shell (GitLab #103, F6).

The Makefile normalises ARCH with a parse-time
`$(shell printf ... | awk -v a='$(ARCH)' ...)` that make evaluates on EVERY
invocation, before any target or `check_arch` runs. A single quote in a
command-line `ARCH=` ended the quoting there. `SITE` already had a make-only
charset guard (test_site_shell_safety.py); this is the same guard for ARCH.

The payloads are inert on purpose: they echo a marker, never destroy.
"""
import subprocess
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent


def _make(arch):
    p = subprocess.run(
        ["make", "-n", "generate", f"ARCH={arch}", "SITE=default"],
        cwd=str(NC), capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


UNSAFE = [
    "a'; echo INJECTED; '",  # ends the single-quoting at the parse-time awk -v
    "a';echo INJECTED;'",
    "a`echo INJECTED`",
    "a$$(echo INJECTED)",
    "a;echo INJECTED",
    "a|echo INJECTED",
    "a&echo INJECTED",
    'a"b',
    "a>out",
    "a b",
    "a\nb",
    "a(b",
    "a*",
]


@pytest.mark.parametrize("arch", UNSAFE, ids=lambda s: repr(s))
def test_unsafe_arch_is_refused(arch):
    rc, out = _make(arch)
    assert rc != 0, f"make accepted ARCH={arch!r}"
    assert "Invalid ARCH" in out, (
        f"ARCH={arch!r} was refused, but not by our guard:\n{out[:400]}"
    )
    assert not any(line.strip() == "INJECTED" for line in out.splitlines()), (
        f"ARCH={arch!r} reached a shell:\n{out[:400]}"
    )


SAFE = ["2-4-3-200", "2-8-5-400", "2-8-9-400-SP", "2-8-9-400-sp"]


@pytest.mark.parametrize("arch", SAFE)
def test_supported_arch_is_accepted(arch):
    rc, out = _make(arch)
    assert "Invalid ARCH" not in out, f"ARCH={arch!r} was rejected:\n{out[:400]}"
    assert rc == 0, out[:400]


def test_unknown_but_safe_arch_still_reaches_check_arch():
    """The guard only refuses unsafe characters; check_arch still names unknown archs."""
    rc, out = _make("9-9-9-999")
    assert "Invalid ARCH" not in out
    assert "Unknown architecture '9-9-9-999'" in out
