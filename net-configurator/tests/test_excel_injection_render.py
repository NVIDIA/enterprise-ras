# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Excel-injection render-layer defenses (findings #16, #5, #7):

  * #16 — login-banner: the single-quote escape `replace("'", "'\\''")` must be the
          LAST filter, applied AFTER {site}/{arch}/{hostname} substitution, so a
          quote injected via Excel `site_name` can't break out of the
          `nv set system message ... '...'` shell argument.
  * #5  — ntp server / date-time timezone must be `| quote`'d in every role
          template (core already was; oob/gl/spine were not).
  * #7  — Excel-sourced prefix-list fields (pl.id/rule.id/rule.match) must be
          `| quote`'d.

Two layers: structural (the real template files use the safe pattern — catches
drift) + behavioral (the pattern actually neutralizes a benign touch-payload when
run through bash).
"""
import re
import shlex
import subprocess
from pathlib import Path

import pytest
from jinja2 import Environment

ROLES = Path(__file__).resolve().parent.parent / "roles"
BANNER_TEMPLATES = [
    ROLES / "core/templates/core_nvue_cli.j2",
    ROLES / "oob-switch/templates/oob_nvue_cli.j2",
    ROLES / "gl/templates/gl_nvue_cli.j2",
    ROLES / "spine/templates/spine_nvue_cli.j2",
]


# ── structural: real template files use the safe pattern ──────────────────

@pytest.mark.parametrize("tmpl", BANNER_TEMPLATES, ids=lambda p: p.parent.parent.name)
def test_banner_escape_is_last_filter(tmpl):
    """The quote-escape must come AFTER the placeholder substitutions."""
    for line in tmpl.read_text().splitlines():
        if "message pre-login" in line or "message post-login" in line:
            assert "replace('{site}'" in line and "replace(\"'\"" in line
            # escape must appear AFTER the {arch} substitution (i.e. last)
            assert line.index("replace('{arch}'") < line.index("replace(\"'\""), (
                f"{tmpl}: quote-escape runs before placeholder substitution "
                f"(#16 injection): {line.strip()}")


@pytest.mark.parametrize("tmpl", BANNER_TEMPLATES, ids=lambda p: p.parent.parent.name)
def test_ntp_and_timezone_quoted(tmpl):
    for line in tmpl.read_text().splitlines():
        s = line.strip()
        if s.startswith("nv set system ntp server "):
            assert "| quote" in s, f"{tmpl}: unquoted ntp server (#5): {s}"
        if s.startswith("nv set system date-time timezone "):
            assert "| quote" in s, f"{tmpl}: unquoted timezone (#5): {s}"


def test_prefix_list_fields_quoted():
    core = (ROLES / "core/templates/core_nvue_cli.j2").read_text()
    for line in core.splitlines():
        if "prefix-list {{ pl.id" in line:
            assert "pl.id | quote" in line and "rule.id | quote" in line, line
            if " match " in line:
                assert "rule.match | quote" in line, line


# ── behavioral: the pattern neutralizes a real injection through bash ──────

def _env():
    e = Environment()
    e.filters["quote"] = lambda s: shlex.quote(str(s))
    return e


def test_banner_pattern_blocks_injection(tmp_path):
    """Reproduce the #16 fix expression and prove a quote-injection in `site`
    cannot execute a command when the line is run by bash."""
    marker = tmp_path / "PWNED_BANNER"
    payload = f"x'; touch {marker}; echo 'y"  # tries to break out of '...'
    expr = ("nv set system message pre-login '{{ msg "
            "| replace('{site}', site) | replace(\"'\", \"'\\\\''\") }}'")
    rendered = _env().from_string(expr).render(msg="Welcome {site}", site=payload)
    # Run it: `nv` doesn't exist (exit 127), but if the quote broke out the
    # `touch` would run as a separate command. shlex must also see one arg.
    subprocess.run(["bash", "-c", rendered], capture_output=True)
    assert not marker.exists(), f"banner injection executed: {rendered}"


def test_quote_filter_blocks_injection(tmp_path):
    """`| quote` on ntp/timezone/prefix values neutralizes a metacharacter payload."""
    marker = tmp_path / "PWNED_QUOTE"
    payload = f"pool.ntp.org; touch {marker}"
    expr = "nv set system ntp server {{ val | quote }}"
    rendered = _env().from_string(expr).render(val=payload)
    subprocess.run(["bash", "-c", rendered], capture_output=True)
    assert not marker.exists(), f"quote injection executed: {rendered}"


def test_quote_filter_noop_on_safe_values():
    """Sanity: quote does NOT alter shell-safe values (so valid configs are
    byte-identical)."""
    env = _env()
    for safe in ["pool.ntp.org", "0.0.0.0/0", "PL1", "10", "Etc/UTC"]:
        out = env.from_string("{{ v | quote }}").render(v=safe)
        assert out == safe, f"quote altered safe value {safe!r} -> {out!r}"
