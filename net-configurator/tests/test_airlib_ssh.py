# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Shell-injection regression tests for scripts/airlib/ssh.py.

Companion to the ztp.sh.j2 regression tests — catches the *same class
of bug* in the SSH library. The original ZTP-template bug interpolated
``switch_password`` into a single-quoted shell string without
escaping; the fix was Ansible's ``| quote`` filter. A final-pass
review turned up an analogous pattern in ``inject_key_via_password()``
where ``public_key`` was interpolated unquoted into ``echo '{key}'
>> ~/.ssh/authorized_keys``.

These tests pin the fix so a future refactor can't silently
reintroduce the vulnerability.
"""
import shlex
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# airlib.ssh.inject_key_via_password — the fixed pattern
# ---------------------------------------------------------------------------

def _rebuild_inject_cmd(public_key: str) -> str:
    """Reproduce the shell command that inject_key_via_password() constructs.

    Keeping this a local re-construction rather than monkey-patching
    subprocess lets the test focus on just the string-shape invariant
    we care about (safe under shlex tokenization).
    """
    safe_key = shlex.quote(public_key)
    return (
        "mkdir -p ~/.ssh && "
        f"echo {safe_key} >> ~/.ssh/authorized_keys && "
        "chmod 600 ~/.ssh/authorized_keys && "
        "chmod 700 ~/.ssh"
    )


def _extract_echo_args(inject_cmd: str) -> list[str]:
    """Tokenize the `echo ... >> ~/.ssh/authorized_keys` fragment the
    way a shell would, so we can assert the key survived as a single
    literal token (not split by injection)."""
    # The inject_cmd is a chain of `&&`-joined commands. Pull the echo.
    segments = [seg.strip() for seg in inject_cmd.split("&&")]
    echo_seg = next(seg for seg in segments if seg.startswith("echo "))
    # Strip the redirection to isolate the argv-tokenisable part.
    echo_without_redirect = echo_seg.split(">>", 1)[0].strip()
    return shlex.split(echo_without_redirect)


HOSTILE_KEY = "ssh-ed25519 AAAA'; touch /tmp/should-not-exist; echo '"
LEGITIMATE_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKey user@host"


class TestInjectKeyShellInjectionRegression:
    def test_hostile_public_key_stays_as_single_shell_token(self):
        cmd = _rebuild_inject_cmd(HOSTILE_KEY)
        tokens = _extract_echo_args(cmd)
        # echo + exactly one key argument
        assert tokens[0] == "echo"
        assert tokens[1:] == [HOSTILE_KEY], (
            f"public_key was split by the shell — expected one literal "
            f"token, got {tokens[1:]!r}"
        )

    def test_injection_command_never_appears_as_a_token(self):
        """Defence-in-depth: `touch` must never appear in a shell
        command position anywhere in the constructed inject_cmd."""
        cmd = _rebuild_inject_cmd(HOSTILE_KEY)
        # Whole `&&` chain, tokenised — `touch` must only ever sit
        # inside a quoted literal, never as its own token.
        for segment in cmd.split("&&"):
            segment = segment.strip()
            # Strip redirects so shlex can parse the remainder.
            left = segment.split(">>", 1)[0].split(">", 1)[0].strip()
            tokens = shlex.split(left)
            assert "touch" not in tokens, (
                f"injection command leaked to a command position: "
                f"segment={segment!r} tokens={tokens!r}"
            )

    def test_legitimate_key_survives_unchanged(self):
        cmd = _rebuild_inject_cmd(LEGITIMATE_KEY)
        tokens = _extract_echo_args(cmd)
        assert tokens[1:] == [LEGITIMATE_KEY]

    def test_airlib_ssh_actually_uses_shlex_quote(self):
        """Read the real source — if somebody deletes the shlex.quote
        call in a refactor, this test fails even if the unit test
        above keeps passing (because the unit test re-constructs the
        cmd locally)."""
        source = (SCRIPTS_DIR / "airlib" / "ssh.py").read_text()
        # Must import shlex and call shlex.quote on public_key near the
        # inject_cmd construction.
        assert "import shlex" in source
        assert "shlex.quote(public_key)" in source, (
            "inject_key_via_password() must shell-quote the public key — "
            "don't regress the fix from the final-pass review"
        )
        # And the fragile unquoted form must NOT return.
        assert "f\"echo '{public_key}'" not in source, (
            "regression: unquoted echo '{public_key}' interpolation "
            "is back — fix shell-escape it the way we did originally"
        )


# ---------------------------------------------------------------------------
# generate-node-instructions.write_file_cmd — same class of bug
# ---------------------------------------------------------------------------

def _write_file_cmd_local(path: str, content: str) -> str:
    """Re-implementation that mirrors generate-node-instructions.py so
    we can test the shell-shape invariant without importing a module
    whose filename contains a hyphen."""
    import base64
    b64 = base64.b64encode(content.encode()).decode()
    return f"echo {shlex.quote(b64)} | base64 -d > {shlex.quote(path)}"


HOSTILE_PATH = "/tmp/x; rm -rf /tmp/should-not-exist; echo "


class TestWriteFileCmdShellInjection:
    def test_hostile_path_neutralised(self):
        cmd = _write_file_cmd_local(HOSTILE_PATH, "hello world\n")
        # Tokenise the post-pipe redirection target.
        right = cmd.split(">", 1)[1].strip()
        tokens = shlex.split(right)
        assert tokens == [HOSTILE_PATH], (
            f"path was split by the shell — got {tokens!r}"
        )

    def test_real_source_uses_shlex_quote_on_path(self):
        source = (SCRIPTS_DIR / "generate-node-instructions.py").read_text()
        assert "import shlex" in source
        # The fragile unquoted form must not return.
        assert "'{b64}' | base64 -d > {path}" not in source, (
            "regression: path is being interpolated unquoted again — "
            "shlex.quote it"
        )
        # The safe form is required.
        assert "shlex.quote(path)" in source
