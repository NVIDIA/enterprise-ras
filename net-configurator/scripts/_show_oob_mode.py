#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Print the `_oob_uplink_mode` of a generated topology JSON.

Returns 'l2' (default) when the file doesn't exist, isn't parseable,
or doesn't carry the new metadata field. Used by Makefile macros
that need to pick mode-appropriate hosts/files before calling Ansible.

Usage:
    python3 scripts/_show_oob_mode.py <topology.json>
"""
import sys
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from utils import DEFAULT_OOB_UPLINK_MODE, read_topology_oob_uplink_mode  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(DEFAULT_OOB_UPLINK_MODE)
        return 0
    print(read_topology_oob_uplink_mode(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
