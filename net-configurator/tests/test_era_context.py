# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Tests for scripts/_era_context.py.

This script parses ``.era-context`` and emits shell-safe
``_ARCH=<value>`` / ``_SITE=<value>`` assignments that the Makefile
``eval`` to avoid the old injection hazard of interpolating raw
``grep | cut`` output into an inline Python one-liner. The invariants
locked in here:

- Valid context → predictable, shell-safe output, exit 0.
- Missing context → exit 1 with a helpful diagnostic.
- Invalid arch (not in the known set) → exit 1.
- Path-traversal attempts in site (``../evil``) → exit 1.
- Shell-metacharacter injection in arch/site → regex refuses to match,
  validator treats the line as absent.
- Site defaults to ``default`` when omitted.
"""
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parent.parent / "scripts" / "_era_context.py"


def _run(cwd: Path) -> subprocess.CompletedProcess:
    """Run the validator with ``cwd`` as the process working directory."""
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


@pytest.fixture
def ctx_dir(tmp_path):
    """Isolated working directory for a .era-context file."""
    return tmp_path


def _write_ctx(ctx_dir: Path, body: str) -> None:
    (ctx_dir / ".era-context").write_text(body)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_context_emits_shell_safe_assignments(ctx_dir):
    _write_ctx(ctx_dir, "arch: 2-8-5-200\nsite: customer-a\n")
    result = _run(ctx_dir)
    assert result.returncode == 0, result.stderr
    assert "_ARCH=2-8-5-200" in result.stdout
    assert "_SITE=customer-a" in result.stdout


def test_site_defaults_to_default_when_absent(ctx_dir):
    _write_ctx(ctx_dir, "arch: 2-4-3-200\n")
    result = _run(ctx_dir)
    assert result.returncode == 0
    assert "_SITE=default" in result.stdout


def test_comments_and_blank_lines_ignored(ctx_dir):
    _write_ctx(
        ctx_dir,
        "# ERA Deployment Context\n"
        "\n"
        "arch: 2-8-9-400\n"
        "# trailing comment\n"
        "site: lab\n",
    )
    result = _run(ctx_dir)
    assert result.returncode == 0
    assert "_ARCH=2-8-9-400" in result.stdout
    assert "_SITE=lab" in result.stdout


def test_all_three_valid_arches_accepted(ctx_dir):
    for arch in ("2-4-3-200", "2-8-5-200", "2-8-9-400"):
        _write_ctx(ctx_dir, f"arch: {arch}\nsite: default\n")
        result = _run(ctx_dir)
        assert result.returncode == 0, f"{arch}: {result.stderr}"
        assert f"_ARCH={arch}" in result.stdout


# ---------------------------------------------------------------------------
# Missing / malformed
# ---------------------------------------------------------------------------

def test_missing_context_file_fails_with_hint(ctx_dir):
    # Intentionally no .era-context in ctx_dir.
    result = _run(ctx_dir)
    assert result.returncode == 1
    assert "no .era-context" in result.stderr
    assert "make use" in result.stderr


def test_missing_arch_line_fails(ctx_dir):
    _write_ctx(ctx_dir, "site: default\n")
    result = _run(ctx_dir)
    assert result.returncode == 1
    assert "missing an 'arch:' line" in result.stderr


def test_empty_file_fails(ctx_dir):
    _write_ctx(ctx_dir, "")
    result = _run(ctx_dir)
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# Input validation — security-critical cases
# ---------------------------------------------------------------------------

def test_unknown_arch_rejected(ctx_dir):
    _write_ctx(ctx_dir, "arch: 1-2-3-456\nsite: default\n")
    result = _run(ctx_dir)
    assert result.returncode == 1
    assert "invalid arch" in result.stderr
    # Error should mention the allowlist so the user can self-correct.
    assert "2-8-5-200" in result.stderr


def test_path_traversal_in_arch_rejected(ctx_dir):
    _write_ctx(ctx_dir, "arch: ../../../etc/passwd\nsite: default\n")
    result = _run(ctx_dir)
    assert result.returncode == 1
    # Either the regex doesn't match (missing arch) or the allowlist
    # rejects it — both are acceptable, neither leaks the value into
    # anything executable.
    assert "arch" in result.stderr.lower()


def test_path_traversal_in_site_rejected(ctx_dir):
    _write_ctx(ctx_dir, "arch: 2-8-5-200\nsite: ../evil\n")
    result = _run(ctx_dir)
    assert result.returncode == 1
    assert "invalid site" in result.stderr


def test_slash_in_site_rejected(ctx_dir):
    _write_ctx(ctx_dir, "arch: 2-8-5-200\nsite: a/b\n")
    result = _run(ctx_dir)
    assert result.returncode == 1


def test_dots_only_site_rejected(ctx_dir):
    _write_ctx(ctx_dir, "arch: 2-8-5-200\nsite: ..\n")
    result = _run(ctx_dir)
    assert result.returncode == 1


def test_quote_escape_injection_in_arch_rejected(ctx_dir):
    # Classic shell-quote breakout attempt. The `\S+` capture stops at
    # the first space; the remainder fails `\s*$`, so the arch line
    # never matches, and we fall through to "missing arch:".
    _write_ctx(
        ctx_dir,
        "arch: 2-8-5-200'; touch /tmp/should-not-exist; echo '\nsite: default\n",
    )
    result = _run(ctx_dir)
    assert result.returncode == 1
    # Whatever the reason, it must not exit 0 (success).
    assert "_ARCH=" not in result.stdout


def test_command_substitution_in_site_rejected(ctx_dir):
    # Same shape as above — spaces after `$(` break the strict regex
    # and site silently falls back to 'default'. Either is safe; what
    # matters is that `$(rm ...)` is never emitted unquoted.
    _write_ctx(
        ctx_dir,
        "arch: 2-8-5-200\nsite: $(rm -rf /tmp/should-not-exist)\n",
    )
    result = _run(ctx_dir)
    # The line as written has spaces, so regex fails and site defaults.
    # Defaults are safe — and critically, the raw command-substitution
    # string never appears in stdout.
    assert "$(rm" not in result.stdout
    assert "rm -rf" not in result.stdout


def test_newline_in_site_cannot_inject_extra_assignment(ctx_dir):
    # If regex were lax, a multi-line site value could emit an extra
    # `_SITE=...` line. Strict `\S+` + `\s*$` anchors prevent that.
    _write_ctx(ctx_dir, "arch: 2-8-5-200\nsite: default\n_EXTRA=pwned\n")
    result = _run(ctx_dir)
    assert result.returncode == 0
    assert "_EXTRA" not in result.stdout


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------

def test_output_is_evaluable_by_shell(ctx_dir):
    """End-to-end: the Makefile consumes this via `eval` — simulate."""
    _write_ctx(ctx_dir, "arch: 2-8-5-200\nsite: customer-a\n")
    result = _run(ctx_dir)
    assert result.returncode == 0

    # Parse as sh would.
    shell_check = subprocess.run(
        ["bash", "-c", f'eval "{result.stdout}"; echo "$_ARCH|$_SITE"'],
        capture_output=True,
        text=True,
    )
    assert shell_check.returncode == 0
    assert shell_check.stdout.strip() == "2-8-5-200|customer-a"
