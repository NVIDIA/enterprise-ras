# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Regression test for the NOZTP switch-vs-server Node-Instruction classification.

The split N/S + GPU switch roles introduced by the 2026-06 rename — cl-* / cs-*
/ gl-* / gs-* — were missing from the classification prefix lists. In NOZTP
mode every multi-tier fabric therefore handed those switches a *server* NI
(`apt-get install lldpd`, hostnamectl) with zero NVUE config, so a Cumulus
switch booted, found no config and no ZTP disable, and sat in "ZTP in progress"
forever → unreachable. Fix consolidated the four drifted prefix tuples into a
single `SWITCH_HOST_PREFIXES` in air-deploy.py (imported by
generate-node-instructions.py). This test guards against the roles being dropped
again.

ADR-0060 later introduced pre_cabled_rack rack-local OOB switches
(rack-oob-su-<SU>-<N>), which repeated the exact same bug: the new prefix was
never added to SWITCH_HOST_PREFIXES, so every rack-oob switch got a server NI
and hung in ZTP — reproduced live on 2-4-5-800/largescale (148/152 nodes
unreachable, stable across repeated Air attempts). Fixed by adding
`"rack-oob-"`; this test now guards that prefix too.
"""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_air_deploy():
    spec = importlib.util.spec_from_file_location("air_deploy", SCRIPTS / "air-deploy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


air_deploy = _load_air_deploy()

# One example hostname per switch role — all must be classified as switches
# (get the NVUE deferred-apply NI) and skipped from the server NI.
SWITCH_HOSTNAMES = [
    "core-01", "csl-01", "cl-05", "cs-02",
    "gsl-plane1-01", "gl-plane1-03", "gs-plane2-01", "oob-switch-07",
    "rack-oob-su-04-01",
]
# Real Ubuntu servers — must NOT be classified as switches.
SERVER_HOSTNAMES = ["su-01-node-01", "storage-02", "support-03"]

# The roles that were the actual bug (missing from the lists).
SPLIT_ROLE_PREFIXES = ("cl-", "cs-", "gl-", "gs-")


def test_all_switch_prefixes_present():
    sw = air_deploy.SWITCH_HOST_PREFIXES
    for p in ("core-", "csl-", "cl-", "cs-", "gsl-", "gl-", "gs-", "oob-switch-", "rack-oob-"):
        assert p in sw, f"{p!r} missing from SWITCH_HOST_PREFIXES"


def test_split_roles_are_switches_and_skip_server_ni():
    sw = air_deploy.SWITCH_HOST_PREFIXES
    skip = air_deploy.SERVER_NI_SKIP_PREFIXES
    for p in SPLIT_ROLE_PREFIXES:
        assert p in sw, f"{p!r} not in SWITCH_HOST_PREFIXES (multi-tier switch would get a server NI)"
        assert p in skip, f"{p!r} not in SERVER_NI_SKIP_PREFIXES (switch would get a server NI)"


def test_every_switch_hostname_recognized():
    sw = air_deploy.SWITCH_HOST_PREFIXES
    skip = air_deploy.SERVER_NI_SKIP_PREFIXES
    for h in SWITCH_HOSTNAMES:
        assert any(h.startswith(p) for p in sw), \
            f"{h} not recognized as a switch — it would get a server NI and hang in ZTP"
        assert any(h.startswith(p) for p in skip), \
            f"{h} not skipped from the server NI"


def test_servers_are_not_switches():
    sw = air_deploy.SWITCH_HOST_PREFIXES
    for h in SERVER_HOSTNAMES:
        assert not any(h.startswith(p) for p in sw), \
            f"{h} wrongly classified as a switch"


def test_generator_imports_the_shared_constant():
    """generate-node-instructions.py must source SWITCH_HOST_PREFIXES from
    air-deploy.py (single source of truth) rather than re-hardcoding it."""
    gen = (SCRIPTS / "generate-node-instructions.py").read_text()
    assert "SWITCH_HOST_PREFIXES = _air_deploy.SWITCH_HOST_PREFIXES" in gen
    assert "startswith(p) for p in SWITCH_HOST_PREFIXES" in gen
