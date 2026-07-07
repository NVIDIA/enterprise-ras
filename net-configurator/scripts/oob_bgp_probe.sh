#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# OOB↔CSL BGP probe (design C1) — READ ONLY.
#
# Runs ON an OOB Cumulus switch, streamed over SSH from the jump:
#     sshpass -e ssh ... cumulus@<oob-switch> "bash -s -- '<sudo_pw>'" < oob_bgp_probe.sh
#
# It only DUMPS `show bgp vrf all summary json` (root via `sudo -S`). The
# PASS/FAIL classification runs on the jump via scripts/oob_bgp_classify.py, so
# the classifier stays unit-testable and this probe shares ZERO code with
# scripts/switch_health_probe.sh (the required isolation — no carrier-down
# suppression leaking in from switch-health).
PW="${1:-}"
echo "$PW" | sudo -S -p '' vtysh -c 'show bgp vrf all summary json' 2>/dev/null
