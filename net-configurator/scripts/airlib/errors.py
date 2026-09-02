# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Typed exceptions for the Air API helpers.

Helpers in this package signal failure by raising one of these rather than
calling sys.exit() or writing to stderr themselves. That keeps the decision
about how to present a failure — and what to exit with — in each script's
main(), which is the only place that knows whether it is running
interactively, under make, or in CI.

Each subclass carries the process exit status that its failure should produce,
so a caller can do `sys.exit(err.exit_code)` without re-deriving it:

    AirConfigError  1   credentials or settings missing / unusable
    AirSSHError     2   could not connect or authenticate over SSH
    AirAPIError     3   Air answered, but with an error or something unexpected
"""

# Exit codes
EXIT_CONFIG = 1
EXIT_SSH = 2
EXIT_API = 3


class AirError(Exception):
    """Base class for all Air script errors."""
    exit_code: int = 1


class AirConfigError(AirError):
    """Missing or invalid configuration (.env, env vars, vault)."""
    exit_code = EXIT_CONFIG


class AirAPIError(AirError):
    """Air API returned an error or unexpected response."""
    exit_code = EXIT_API


class AirSSHError(AirError):
    """SSH connection or authentication failure."""
    exit_code = EXIT_SSH
