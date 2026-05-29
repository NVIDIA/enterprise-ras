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
import json
import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("l2")
        return 0
    path = sys.argv[1]
    if not os.path.exists(path):
        print("l2")
        return 0
    try:
        with open(path) as f:
            mode = str(json.load(f).get("_oob_uplink_mode", "l2")).strip().lower()
        print(mode or "l2")
    except (OSError, json.JSONDecodeError, ValueError):
        print("l2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
