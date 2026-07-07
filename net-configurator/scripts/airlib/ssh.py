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


def inject_key_via_password(
    host: str,
    port: str | int,
    user: str,
    password: str,
    public_key: str,
) -> bool:
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
        True if key injection succeeded.

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
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False
