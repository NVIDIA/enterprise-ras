#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Ansible wrapper for Windows compatibility.

Ansible doesn't officially support Windows as a controller.
This wrapper patches os.get_blocking() (which fails on Windows)
before importing Ansible, allowing ansible-playbook to run.

Usage:
    python ansible_wrapper.py playbook <playbook.yml> [ansible args...]
    python ansible_wrapper.py galaxy <galaxy args...>
"""

import locale
import os
import sys

# Windows compatibility patches — applied before importing Ansible.
# Ansible doesn't officially support Windows as a controller.
if sys.platform == "win32":
    # Patch 1: os.get_blocking() raises OSError on Windows
    _original_get_blocking = getattr(os, "get_blocking", None)

    def _safe_get_blocking(fd):
        try:
            return _original_get_blocking(fd)
        except OSError:
            return True  # Assume blocking (safe default)

    os.get_blocking = _safe_get_blocking

    # Patch 2: Ansible requires UTF-8 locale, Windows defaults to cp1252.
    # Ansible's initialize_locale() calls locale.getlocale() and
    # sys.getfilesystemencoding() and fails if either isn't UTF-8.
    # Patch both to report UTF-8 on Windows.
    _original_getlocale = locale.getlocale

    def _utf8_getlocale(category=locale.LC_CTYPE):
        try:
            loc, enc = _original_getlocale(category)
        except (locale.Error, ValueError):
            loc, enc = '', 'UTF-8'
        return loc, 'UTF-8'

    locale.getlocale = _utf8_getlocale
    locale.getpreferredencoding = lambda do_setlocale=True: "UTF-8"
    sys.getfilesystemencoding = lambda: "utf-8"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ansible_wrapper.py playbook <playbook.yml> [args...]")
        sys.exit(1)

    subcmd = sys.argv[1]
    # Remove the subcommand from argv so Ansible sees the right args
    sys.argv = [f"ansible-{subcmd}"] + sys.argv[2:]

    if subcmd == "playbook":
        from ansible.cli.playbook import main
    elif subcmd == "galaxy":
        from ansible.cli.galaxy import main
    elif subcmd == "inventory":
        from ansible.cli.inventory import main
    elif subcmd == "vault":
        from ansible.cli.vault import main
    else:
        print(f"Unknown subcommand: {subcmd}")
        print("Supported: playbook, galaxy, inventory, vault")
        sys.exit(1)

    sys.exit(main())
