# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""SSH command construction and key utilities.

Provides SSH argument building, key-based access checking,
and public key / fingerprint derivation.
"""

import os
import shlex
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

from airlib.errors import AirError, AirSSHError

# SSH option constants
SSH_STRICT_OFF = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
]

# Timeout constants (seconds)
CONNECT_TIMEOUT = 10
SUBPROCESS_TIMEOUT = 20
# apt-get update + install over a sim's NAT path is slow; it is not the same
# budget as a one-shot `true` login check.
REMOTE_INSTALL_TIMEOUT = 300

# sshpass(1) RETURN VALUES documents 1-7; anything else is ssh's own exit code
# passed through. That is why 255 and 5 mean entirely different things and must
# never be collapsed into one "it failed". Per the man page, ssh reports "an
# unimaginative (and non-informative) 255 for all error cases".
SSHPASS_INVALID_ARGS = 1
SSHPASS_CONFLICTING_ARGS = 2
SSHPASS_RUNTIME_ERROR = 3
SSHPASS_PARSE_ERROR = 4
SSHPASS_WRONG_PASSWORD = 5
SSHPASS_UNKNOWN_HOST_KEY = 6
SSHPASS_HOST_KEY_CHANGED = 7
SSH_CONNECT_ERROR = 255


@dataclass(frozen=True)
class SSHAttempt:
    """The outcome of one sshpass/ssh invocation, with the evidence kept.

    Truthy on success, so callers that only care whether it worked read the
    same as they did against the old bare-bool return. Callers that have to
    *explain* a failure now have the returncode and stderr to explain it with,
    rather than guessing (ERA-84).
    """

    ok: bool
    returncode: int | None = None
    stderr: str = ""
    failure: str = ""

    def __bool__(self) -> bool:
        return self.ok


def classify_ssh_failure(returncode: int | None, stderr: str = "") -> str:
    """Name the cause of a failed sshpass/ssh run from its exit code.

    Returns one of "", "auth", "hostkey", "connect", "sshpass", "timeout",
    "remote". `stderr` is accepted for future refinement and deliberately not
    pattern-matched today — the exit code is the reliable signal.

    Note on exit 1: sshpass documents it as "invalid command line argument",
    but every argv here is built by this module, so a remote command exiting 1
    is overwhelmingly the likelier reading. It is classified as "remote".
    """
    if returncode == 0:
        return ""
    if returncode is None:
        return "timeout"
    if returncode == SSHPASS_WRONG_PASSWORD:
        return "auth"
    if returncode in (SSHPASS_UNKNOWN_HOST_KEY, SSHPASS_HOST_KEY_CHANGED):
        return "hostkey"
    if returncode == SSH_CONNECT_ERROR:
        return "connect"
    if returncode in (SSHPASS_CONFLICTING_ARGS, SSHPASS_RUNTIME_ERROR,
                      SSHPASS_PARSE_ERROR):
        return "sshpass"
    return "remote"


def build_ssh_args(
    host: str,
    port: str | int,
    user: str,
    ssh_key_path: str = "",
    *,
    forward_agent: bool = True,
) -> list[str]:
    """Build SSH command arguments.

    Args:
        host: Remote hostname or IP.
        port: SSH port.
        user: SSH username.
        ssh_key_path: Path to private key (supports ~ expansion).
        forward_agent: Enable SSH agent forwarding (-A).
    """
    args = ["ssh", *SSH_STRICT_OFF]
    if forward_agent:
        args.append("-A")
    args.extend(["-p", str(port)])
    if ssh_key_path:
        expanded = Path(ssh_key_path).expanduser()
        if expanded.exists():
            args.extend(["-i", str(expanded)])
    args.append(f"{user}@{host}")
    return args


def check_port_open(host: str, port: str | int, timeout: float = 5.0) -> bool:
    """Check if a TCP port is open (no authentication needed)."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


def check_key_access(
    host: str,
    port: str | int,
    user: str,
    ssh_key_path: str = "",
) -> bool:
    """Check if SSH key authentication works (BatchMode, no password)."""
    args = build_ssh_args(host, port, user, ssh_key_path, forward_agent=False)
    args.extend([
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
        "true",
    ])
    try:
        result = subprocess.run(args, capture_output=True, timeout=SUBPROCESS_TIMEOUT)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def get_public_key(private_key_path: str) -> str:
    """Derive public key from private key file using ssh-keygen.

    Args:
        private_key_path: Path to the private SSH key file (supports ~ expansion).

    Returns:
        The public key string (e.g., "ssh-ed25519 AAAA... comment").

    Raises:
        AirError: If the private key file doesn't exist or ssh-keygen fails.
    """
    expanded_path = Path(private_key_path).expanduser()
    if not expanded_path.exists():
        raise AirError(f"SSH private key not found: {expanded_path}")

    try:
        result = subprocess.run(
            ["ssh-keygen", "-y", "-f", str(expanded_path)],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise AirError(
            f"Failed to derive public key from {expanded_path}: {exc.stderr.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AirError(
            f"Timed out deriving public key from {expanded_path}"
        ) from exc
    except FileNotFoundError as exc:
        raise AirError("ssh-keygen not found in PATH") from exc


def get_key_fingerprint(key_path: str) -> str:
    """Compute SHA256 fingerprint of an SSH key.

    Works with both public and private key files.

    Returns:
        The SHA256 fingerprint (e.g., "SHA256:abc123...").

    Raises:
        AirError: If the key file doesn't exist or ssh-keygen fails.
    """
    expanded_path = Path(key_path).expanduser()
    if not expanded_path.exists():
        raise AirError(f"SSH key not found: {expanded_path}")

    try:
        result = subprocess.run(
            ["ssh-keygen", "-l", "-f", str(expanded_path)],
            capture_output=True, text=True, check=True, timeout=10,
        )
        # Output format: "256 SHA256:abc123... comment (ED25519)"
        parts = result.stdout.strip().split()
        if len(parts) >= 2:
            return parts[1]
        raise AirError(f"Unexpected ssh-keygen output: {result.stdout}")
    except subprocess.CalledProcessError as exc:
        raise AirError(
            f"Failed to compute fingerprint for {expanded_path}: {exc.stderr.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AirError(
            f"Timed out computing fingerprint for {expanded_path}"
        ) from exc
    except FileNotFoundError as exc:
        raise AirError("ssh-keygen not found in PATH") from exc


def check_password_access(
    host: str,
    port: str | int,
    user: str,
    password: str,
) -> bool:
    """Check if SSH password authentication works (sshpass).

    Returns:
        True if password auth succeeds.

    Raises:
        AirSSHError: If sshpass is not installed.
    """
    if not shutil.which("sshpass"):
        raise AirSSHError(
            "sshpass is not installed. Install it with: sudo apt install sshpass"
        )

    cmd = [
        "sshpass", "-e",
        "ssh",
        *SSH_STRICT_OFF,
        "-p", str(port),
        "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
        "-o", "PubkeyAuthentication=no",
        f"{user}@{host}",
        "true",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
            env={**os.environ, "SSHPASS": password},
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def key_needs_passphrase(private_key_path: str) -> bool:
    """Return True if the SSH private key file is passphrase-protected.

    A passphrase-locked key without a loaded ssh-agent breaks every
    BatchMode SSH attempt (including Ansible's), so callers use this to
    distinguish "remote auth broken" from "local key not usable".
    """
    expanded = Path(private_key_path).expanduser()
    if not expanded.exists():
        return False
    try:
        result = subprocess.run(
            ["ssh-keygen", "-y", "-P", "", "-f", str(expanded)],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode != 0
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return False


def verify_key_in_authorized_keys(
    host: str,
    port: str | int,
    user: str,
    password: str,
    public_key: str,
) -> bool:
    """Confirm a public key is in the remote ~/.ssh/authorized_keys (via sshpass).

    Used after `inject_key_via_password` to prove the key landed server-side,
    independent of whether the local SSH client can complete key auth (a
    passphrase-locked key + no ssh-agent would fail BatchMode key auth even
    when the key is correctly present remotely).

    Compares the base64 body of the key — comment fields are stripped before
    matching so injected-with-comment vs stored-without-comment both match.
    """
    if not shutil.which("sshpass"):
        return False

    key_parts = public_key.strip().split()
    if len(key_parts) < 2:
        return False
    key_body = key_parts[1]

    cmd = [
        "sshpass", "-e",
        "ssh",
        *SSH_STRICT_OFF,
        "-p", str(port),
        "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
        "-o", "PubkeyAuthentication=no",
        f"{user}@{host}",
        f"grep -qF {shlex.quote(key_body)} ~/.ssh/authorized_keys",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
            env={**os.environ, "SSHPASS": password},
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def build_remote_package_install_cmd(package: str) -> str:
    """Build the remote shell command that installs one apt package.

    Non-interactive throughout: this runs over SSH from CI and from Air Node
    Instructions, neither of which has a TTY, so a debconf prompt would hang
    rather than fail. The index is refreshed first because a fresh Air node has
    no package lists at all.
    """
    safe = shlex.quote(package)
    return (
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq && "
        f"DEBIAN_FRONTEND=noninteractive apt-get install -y -qq {safe}"
    )


def run_remote_command(
    host: str,
    port: str | int,
    user: str,
    remote_cmd: str,
    *,
    password: str = "",
    ssh_key_path: str = "",
    timeout: int = SUBPROCESS_TIMEOUT,
) -> SSHAttempt:
    """Run one command on a remote host, keeping the evidence.

    Authenticates with `password` (via sshpass) or `ssh_key_path` (BatchMode) —
    the caller passes whichever it has actually verified. Probing over an
    unverified credential produces auth failures that look like whatever the
    probe was asking about.
    """
    if password:
        if not shutil.which("sshpass"):
            raise AirSSHError(
                "sshpass is not installed. Install it with: sudo apt install sshpass"
            )
        cmd = ["sshpass", "-e", "ssh", *SSH_STRICT_OFF,
               "-p", str(port),
               "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
               "-o", "PubkeyAuthentication=no",
               f"{user}@{host}", remote_cmd]
        env = {**os.environ, "SSHPASS": password}
    elif ssh_key_path:
        expanded = Path(ssh_key_path).expanduser()
        cmd = ["ssh", *SSH_STRICT_OFF,
               "-p", str(port),
               "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
               "-o", "BatchMode=yes",
               "-i", str(expanded),
               f"{user}@{host}", remote_cmd]
        env = dict(os.environ)
    else:
        raise AirSSHError("run_remote_command needs either a password or a key path")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return SSHAttempt(ok=False, returncode=None, failure="timeout",
                          stderr=f"timed out after {timeout}s")
    except OSError as exc:
        return SSHAttempt(ok=False, returncode=None, failure="sshpass",
                          stderr=str(exc))

    return SSHAttempt(
        ok=result.returncode == 0,
        returncode=result.returncode,
        stderr=(result.stderr or "").strip(),
        failure=classify_ssh_failure(result.returncode, result.stderr or ""),
    )


def remote_has_command(
    host: str,
    port: str | int,
    user: str,
    command: str,
    *,
    password: str = "",
    ssh_key_path: str = "",
) -> bool:
    """Return True if `command` is on the remote host's PATH.

    Note this asks about the REMOTE host. Every other sshpass call in this
    module uses sshpass on the controller to reach a jump host; this one checks
    whether the jump host itself can go on to reach the switches (ERA-85).
    """
    return bool(run_remote_command(
        host, port, user,
        f"command -v {shlex.quote(command)} >/dev/null 2>&1",
        password=password, ssh_key_path=ssh_key_path,
    ))


def install_remote_package(
    host: str,
    port: str | int,
    user: str,
    package: str,
    *,
    password: str = "",
    ssh_key_path: str = "",
) -> SSHAttempt:
    """Install one apt package on a remote host.

    Runs after the sim is up, which is when the node's outbound NAT path is
    actually working — an install attempted at first-boot Node-Instruction time
    races the NAT host that provides its route to the archive.

    Uses `sudo -n`: passwordless sudo for the login user is assumed and NOT
    verified here. Where it does not hold this fails cleanly with sudo's own
    stderr rather than hanging on a prompt.
    """
    return run_remote_command(
        host, port, user,
        f"sudo -n sh -c {shlex.quote(build_remote_package_install_cmd(package))}",
        password=password, ssh_key_path=ssh_key_path,
        timeout=REMOTE_INSTALL_TIMEOUT,
    )


def inject_key_via_password(
    host: str,
    port: str | int,
    user: str,
    password: str,
    public_key: str,
) -> SSHAttempt:
    """Inject an SSH public key into a remote host using password auth (sshpass).

    Appends the public key to ~/.ssh/authorized_keys on the remote host,
    creating the .ssh directory if needed.

    Args:
        host: Remote hostname.
        port: SSH port.
        user: SSH username.
        password: Password for sshpass authentication.
        public_key: Full public key line (e.g. "ssh-ed25519 AAAA...").

    Returns:
        An `SSHAttempt` — truthy on success, and on failure carrying the
        returncode, stderr and classified cause so the caller can report what
        actually went wrong instead of guessing at the password (ERA-84).

    Raises:
        AirSSHError: If sshpass is not installed.
    """
    if not shutil.which("sshpass"):
        raise AirSSHError(
            "sshpass is not installed. Install it with: sudo apt install sshpass"
        )

    # Shell-escape the public key before interpolating into the remote command.
    # SSH public keys are almost never going to contain a single quote in
    # practice, but the class-of-bug pattern matches the shell injection we
    # just fixed in ztp.sh.j2 — belt-and-braces here keeps it safe against
    # a tampered SSH key supplied from an untrusted source.
    safe_key = shlex.quote(public_key)
    inject_cmd = (
        "mkdir -p ~/.ssh && "
        f"echo {safe_key} >> ~/.ssh/authorized_keys && "
        "chmod 600 ~/.ssh/authorized_keys && "
        "chmod 700 ~/.ssh"
    )

    cmd = [
        "sshpass", "-e",
        "ssh",
        *SSH_STRICT_OFF,
        "-p", str(port),
        "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
        "-o", "PubkeyAuthentication=no",
        f"{user}@{host}",
        inject_cmd,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
            env={**os.environ, "SSHPASS": password},
        )
    except subprocess.TimeoutExpired:
        return SSHAttempt(
            ok=False, returncode=None, failure="timeout",
            stderr=f"timed out after {SUBPROCESS_TIMEOUT}s",
        )
    except OSError as exc:
        return SSHAttempt(ok=False, returncode=None, failure="sshpass",
                          stderr=str(exc))

    return SSHAttempt(
        ok=result.returncode == 0,
        returncode=result.returncode,
        stderr=(result.stderr or "").strip(),
        failure=classify_ssh_failure(result.returncode, result.stderr or ""),
    )
