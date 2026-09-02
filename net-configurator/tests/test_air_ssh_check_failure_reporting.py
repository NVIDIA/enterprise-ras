# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
ERA-84 — `air-ssh-check` must not blame the password for a failure it has
already disproved.

The reported run (pipeline 61578362) printed, in this order:

    OK   — Password auth works (Ansible will use this)
    Injecting SSH key for key-based access...
    FAIL — Key injection failed (wrong password or SSH error)
    Default password 'nvidia' may have been changed.
    Check server_ansible_password in secrets.yml

Two lines after proving the credential is correct, it sent the operator to
`secrets.yml`. The cause was structural: `inject_key_via_password()` returned a
bare bool, so the returncode and stderr that would have identified the real
failure were discarded at the point of failure and the caller had nothing left
to report but a guess.

These tests pin both halves of the fix:

  * `classify_ssh_failure()` turns a returncode into a named cause, so an
    ssh-level connection drop (255) is never reported as an authentication
    problem. No exit code was captured for the `utility` failure — that is the
    point; there was nowhere for one to be captured.
  * `_injection_failure_lines()` names the password as a suspect only when the
    evidence implicates it, always names the failing host, and prints the
    underlying ssh stderr instead of guessing.
"""
import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_air_ssh_check():
    spec = importlib.util.spec_from_file_location(
        "air_ssh_check", SCRIPTS / "air-ssh-check.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


air_ssh_check = _load_air_ssh_check()

from airlib.ssh import SSHAttempt, classify_ssh_failure  # noqa: E402


# ---------------------------------------------------------------------------
# classify_ssh_failure — a returncode names a cause
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "returncode,expected",
    [
        (0, ""),            # success
        (5, "auth"),        # sshpass: invalid/incorrect password
        (6, "hostkey"),     # sshpass: unknown host key
        (7, "hostkey"),     # sshpass: IP public key changed
        (255, "connect"),   # ssh: generic error, incl. a dropped connection
        (3, "sshpass"),     # sshpass: general runtime error
        (None, "timeout"),  # subprocess timed out, no returncode at all
    ],
)
def test_classify_ssh_failure_names_the_cause(returncode, expected):
    assert classify_ssh_failure(returncode) == expected


def test_every_sshpass_owned_code_is_classified():
    """sshpass(1) RETURN VALUES documents 1-7; 2-7 are unambiguously sshpass's.

    Exit 7 was missed on the first pass and landed in the `remote` bucket, which
    sends the operator to look at remote filesystem permissions for what is
    actually a changed host key.

    Exit 1 is excluded deliberately, not overlooked — see the test below.
    """
    for code in (2, 3, 4, 5, 6, 7):
        assert classify_ssh_failure(code) != "remote", (
            f"sshpass exit {code} is documented but falls through to the "
            "catch-all remote-command bucket"
        )


def test_exit_1_is_treated_as_a_remote_command_failure_on_purpose():
    """The one genuinely ambiguous code, pinned so the reasoning isn't lost.

    sshpass documents 1 as "invalid command line argument", but every argv here
    is built in-module, while the remote commands actually run (`command -v`,
    `grep -q`, the mkdir chain, `sudo`, `apt-get`) all exit 1 routinely.
    """
    assert classify_ssh_failure(1) == "remote"


def test_only_exit_5_is_an_auth_failure():
    """A dropped connection must never be classified as bad credentials.

    This is the whole bug: 255 and 5 were indistinguishable behind a bool.
    """
    assert classify_ssh_failure(255) != "auth"
    assert classify_ssh_failure(1) != "auth"


# ---------------------------------------------------------------------------
# SSHAttempt — carries the evidence, still usable as a truth value
# ---------------------------------------------------------------------------

def test_ssh_attempt_is_falsy_on_failure_and_keeps_stderr():
    attempt = SSHAttempt(ok=False, returncode=255, stderr="Connection timed out",
                         failure="connect")
    assert not attempt
    assert attempt.returncode == 255
    assert "Connection timed out" in attempt.stderr


def test_ssh_attempt_is_truthy_on_success():
    assert SSHAttempt(ok=True, returncode=0, stderr="", failure="")


# ---------------------------------------------------------------------------
# _injection_failure_lines — what the operator is actually told
# ---------------------------------------------------------------------------

# The specific misdirection from pipeline 61578362. Naming the password to
# *clear* it ("password auth to this host succeeded") is fine and wanted; what
# must never appear once password auth has worked is text that sends the
# operator off to re-check the credential.
CREDENTIAL_ACCUSATIONS = (
    "secrets.yml",
    "server_ansible_password",
    "may have been changed",
    "wrong password",
)


def test_working_password_is_never_blamed_for_an_injection_failure():
    """The reported bug, verbatim: password auth OK, injection failed on utility."""
    lines = air_ssh_check._injection_failure_lines(
        name="utility",
        password_worked=True,
        attempt=SSHAttempt(ok=False, returncode=255,
                           stderr="ssh: connect to host ... : Connection timed out",
                           failure="connect"),
    )
    blob = " ".join(lines).lower()

    for phrase in CREDENTIAL_ACCUSATIONS:
        assert phrase not in blob, (
            f"reported {phrase!r} as a suspect after password auth succeeded: {blob}"
        )
    assert "credential is correct" in blob, (
        "must state positively that the credential is not the problem"
    )


def test_injection_failure_names_the_host_and_shows_stderr():
    lines = air_ssh_check._injection_failure_lines(
        name="utility",
        password_worked=True,
        attempt=SSHAttempt(ok=False, returncode=255,
                           stderr="ssh: connect to host x: Connection timed out",
                           failure="connect"),
    )
    blob = " ".join(lines)

    assert "utility" in blob, "the failing host must be named — CI shows only the failure"
    assert "Connection timed out" in blob, "the underlying ssh error must be shown, not guessed"


def test_the_script_actually_uses_the_reporting_helper():
    """A correct helper nobody calls fixes nothing.

    Pins that the old single-guess message is gone from the source and that the
    injection call site routes through `_injection_failure_lines`.
    """
    source = (SCRIPTS / "air-ssh-check.py").read_text()

    # The literal may still appear in a comment explaining the fix; what must
    # be gone is any code path that *prints* it.
    printed = re.findall(r"console\.print\((.*)\)", source)
    for call in printed:
        assert "wrong password or SSH error" not in call, (
            f"the old guess-message is still printed: {call}"
        )

    assert "_injection_failure_lines(" in source
    # ...called, not merely defined
    assert source.count("_injection_failure_lines") >= 2


def test_a_genuine_bad_password_still_points_at_secrets():
    """Password auth failed AND sshpass said exit 5 — the old message is correct here."""
    lines = air_ssh_check._injection_failure_lines(
        name="dhcp-oob",
        password_worked=False,
        attempt=SSHAttempt(ok=False, returncode=5, stderr="", failure="auth"),
    )
    blob = " ".join(lines).lower()

    assert "secrets.yml" in blob
    assert "dhcp-oob" in blob
