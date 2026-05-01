# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Typed exceptions for Air API scripts.

Shared functions raise these instead of calling sys.exit() or
printing directly, letting each script's main() format errors.

Exit code mapping:
  1 = config error (missing .env, missing vars)  -> AirConfigError
  2 = SSH error (connection, auth failure)        -> AirSSHError
  3 = API error (HTTP, unexpected response)       -> AirAPIError
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
