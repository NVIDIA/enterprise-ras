# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
ERA-85 — `sshpass` must be present on the Air jump host.

`utility` is the documented `ansible_target` / `jump_host` and the only path to
the switches for anything that isn't a full `make` target. It ships without
`sshpass`, so it cannot authenticate to a switch non-interactively. That has now
cost two separate pieces of work months apart: the ping-matrix NODATA result
during ERA-42/44 validation, and a probe run on 2026-08-07.

The tool never noticed, because nothing ever asked. These tests pin that
`air-ssh-check` asks — and that with FIX=1 it installs the package, on the one
code path that runs *after* the sim is up and NAT is working, which is when apt
can actually succeed.

Note the two sshpasses are different machines: every existing use is sshpass on
the *controller*, reaching a jump host. This is sshpass on the *jump host*,
reaching the switches.
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

from airlib.ssh import build_remote_package_install_cmd  # noqa: E402


# ---------------------------------------------------------------------------
# The install command itself
# ---------------------------------------------------------------------------

def test_install_command_is_non_interactive():
    """An NI/CI context has no TTY — a prompt is a hang, not a failure."""
    cmd = build_remote_package_install_cmd("sshpass")

    assert "DEBIAN_FRONTEND=noninteractive" in cmd
    assert re.search(r"install\b.*\s-y\b|\s-y\b.*install", cmd), (
        "apt-get install must pass -y"
    )


def test_install_command_updates_the_index_first():
    """A fresh Air node has no package lists; install alone 404s."""
    cmd = build_remote_package_install_cmd("sshpass")
    assert "apt-get update" in cmd
    assert cmd.index("apt-get update") < cmd.index("install")


def test_install_command_quotes_the_package_name():
    """Same class-of-bug as the ztp.sh.j2 / inject_key_via_password quoting."""
    cmd = build_remote_package_install_cmd("sshpass; rm -rf /")

    assert "; rm -rf /" not in cmd.replace("'sshpass; rm -rf /'", ""), (
        "package name must be shell-quoted, not interpolated raw"
    )
    assert "'sshpass; rm -rf /'" in cmd


# ---------------------------------------------------------------------------
# air-ssh-check has to actually ask
# ---------------------------------------------------------------------------

def test_air_ssh_check_probes_for_sshpass_on_the_jump_host():
    source = (SCRIPTS / "air-ssh-check.py").read_text()

    assert "remote_has_command" in source, (
        "air-ssh-check must probe the jump host for sshpass — the whole bug is "
        "that nothing ever asked"
    )
    assert "sshpass" in source


# ---------------------------------------------------------------------------
# The probe must use an auth path that was actually verified
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status,expected",
    [
        ("key_ok", "key"),                  # key verified; password NEVER tested
        ("pass_ok", "password"),
        ("fixed", "password"),              # reached only via a working password
        ("injected_local_blocked", "password"),
        ("fail", None),
        (None, None),                       # host absent from results entirely
    ],
)
def test_probe_uses_only_an_auth_path_that_was_verified(status, expected):
    """A `key_ok` host short-circuits before password auth is ever checked.

    Probing it over sshpass with an unverified password (the fallback is the
    literal 'nvidia') fails for credential reasons and gets reported as
    "sshpass is not installed" — a false warning about the exact thing this
    feature exists to detect.
    """
    assert air_ssh_check._probe_auth_for(status) == expected


def test_missing_sshpass_is_reported_as_actionable_without_fix():
    """Without FIX=1 the operator still has to be told, and told what to run."""
    lines = air_ssh_check._sshpass_status_lines(
        name="utility", present=False, installed=None,
    )
    blob = " ".join(lines)

    assert "utility" in blob
    assert "sshpass" in blob
    assert "FIX=1" in blob, "must name the flag that fixes it"


def test_a_successful_install_says_it_installed_rather_than_found():
    """Observed live on ERA-era8485-2-4-3-200: FIX=1 installed sshpass and
    reported "sshpass present on utility".

    True, but it hides that FIX=1 changed the host. An operator reading the
    report cannot tell a host that already had it from one this run modified,
    which is the difference between "nothing happened" and "a package was
    installed on your jump host".
    """
    lines = air_ssh_check._sshpass_status_lines(
        name="utility", present=True, installed=True,
    )
    blob = " ".join(lines).lower()

    assert "installed sshpass" in blob, (
        "a host this run modified must not be reported as merely 'present'"
    )


def test_present_sshpass_is_reported_ok():
    lines = air_ssh_check._sshpass_status_lines(
        name="utility", present=True, installed=None,
    )
    blob = " ".join(lines).lower()

    assert "ok" in blob
    assert "fix=1" not in blob, "nothing to fix — don't tell the operator to run it"


def test_failed_install_does_not_claim_success():
    lines = air_ssh_check._sshpass_status_lines(
        name="utility", present=False, installed=False,
    )
    blob = " ".join(lines).lower()

    assert "fail" in blob
    assert "installed sshpass" not in blob


def test_failed_install_shows_the_underlying_error_not_a_guess():
    """ERA-84's lesson applied here: report what happened, don't speculate.

    `sudo -n` on a node without passwordless sudo is a completely different
    problem from a missing route to the archive, and only the stderr says which.
    """
    from airlib.ssh import SSHAttempt

    lines = air_ssh_check._sshpass_status_lines(
        name="utility", present=False, installed=False,
        attempt=SSHAttempt(ok=False, returncode=1,
                           stderr="sudo: a password is required",
                           failure="remote"),
    )
    blob = " ".join(lines)

    assert "sudo: a password is required" in blob
