# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""`SITE` must be shell-safe before it reaches a shell.

`scripts/_era_context.py` validates SITE against `^[A-Za-z0-9_-][A-Za-z0-9._-]*$`
-- but only for the value read from `.era-context`. A command-line `SITE=`
bypassed it, and the Makefile splices `$(SITE)` into a `$(shell ... '$(SITE)' ...)`
that make evaluates on EVERY invocation regardless of target, plus 29 recipe
lines unquoted. A single quote ended the quoting before any recipe ran.

The payloads below are inert on purpose -- they would echo or redirect, never
destroy -- because a test that proves injection by causing damage is a bad test.
What is asserted is that make refuses the value, not what the value would have
done.
"""
import subprocess
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent


def _make(site):
    """`make -n generate` with a given SITE. Returns (rc, combined output)."""
    p = subprocess.run(
        ["make", "-n", "generate", "ARCH=2-8-5-200", f"SITE={site}"],
        cwd=str(NC), capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


UNSAFE = [
    "a;echo INJECTED",       # command separator
    "a|echo INJECTED",       # pipe
    "a&echo INJECTED",       # background / chain
    "a`echo INJECTED`",      # backtick substitution
    "a'b",                   # ends the single-quoting at the parse-time $(shell)
    'a"b',                   # double quote
    "a>out",                 # redirect out
    "a<in",                  # redirect in
    "a b",                   # whitespace -> two make words
    "a\nb",                  # embedded newline
    "a(b",                   # subshell open
    "a*",                    # glob
]


@pytest.mark.parametrize("site", UNSAFE, ids=lambda s: repr(s))
def test_unsafe_site_is_refused(site):
    rc, out = _make(site)
    assert rc != 0, f"make accepted SITE={site!r}"
    assert "Invalid SITE" in out, (
        f"SITE={site!r} was refused, but not by our guard — the message was:\n{out[:400]}"
    )
    # The refusal message quotes the offending value back, so the payload TEXT
    # appears in the output either way. Execution is distinguishable because the
    # marker would land on a line of its own.
    assert not any(line.strip() == "INJECTED" for line in out.splitlines()), (
        f"SITE={site!r} reached a shell:\n{out[:400]}"
    )


SAFE = ["default", "largescale", "my-lab", "my_lab", "lab.2", "Customer-A", "ci-12345-x"]


@pytest.mark.parametrize("site", SAFE)
def test_safe_site_is_accepted(site):
    rc, out = _make(site)
    assert "Invalid SITE" not in out, f"legitimate SITE={site!r} was rejected:\n{out[:400]}"


def test_the_guard_is_not_vacuous():
    """A guard that never fires is indistinguishable from no guard."""
    rc, out = _make("a;echo INJECTED")
    assert "Invalid SITE" in out and rc != 0
