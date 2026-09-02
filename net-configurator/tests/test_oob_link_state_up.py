# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-56: the OOB switch must bring its access ports up.

`interfaces_up` appears twice in the core template and zero times in the
oob-switch template, so the OOB switch never emitted `link state up` for its
access ports — ~48 stanzas per OOB switch, the single largest residual measured
anywhere in the production-capture exercise, on every deployment that has one.

The reference is explicit and role-specific:

    REFERENCES/2-8-9-800/configs/oob-switch-01.sh:10
        nv set interface swp1-48 link state up          <- whole access range
    REFERENCES/2-8-9-800/configs/csl-01.sh:29
        nv set interface bond3s0,swp3s1 link state up   <- site-specific pair

which is why the fix is driven by `access_ports` (Wire-Map derived) rather than
by the core template's `interfaces_up` — that variable pins reference-topology
ports and the parser deliberately never inherits it, being destructive on a
site-specific wire map.
"""
import re
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
ARCHS = ["2-4-3-200", "2-4-5-800", "2-8-5-200",
         "2-8-9-400", "2-8-9-400-SP", "2-8-9-800"]


def _oob_configs(arch):
    d = NC / "output" / arch / "default" / "configs"
    if not d.is_dir():
        return []
    return sorted(d.glob("oob-switch-*-config.sh"))


@pytest.mark.parametrize("arch", ARCHS)
def test_oob_switch_brings_access_ports_up(arch):
    configs = _oob_configs(arch)
    if not configs:
        pytest.skip(f"no generated OOB configs for {arch}")
    for cfg in configs:
        txt = cfg.read_text()
        assert re.search(r"nv set interface \S+ link state up", txt), (
            f"{arch}/{cfg.name}: no `link state up` — OOB access ports would "
            f"stay administratively down")


@pytest.mark.parametrize("arch", ARCHS)
def test_link_state_up_covers_exactly_the_access_ports(arch):
    """The range brought up must be the access range, not a different one.

    Emitting a hardcoded range here instead of `access_ports` would silently
    diverge the moment a switch's Wire Map gives it a different span, which is
    the adjacent defect ERA-58 records.
    """
    configs = _oob_configs(arch)
    if not configs:
        pytest.skip(f"no generated OOB configs for {arch}")
    for cfg in configs:
        txt = cfg.read_text()
        access = re.search(r"nv set interface (\S+) bridge domain br_default access 200", txt)
        up = re.search(r"nv set interface (\S+) link state up", txt)
        assert access and up, f"{arch}/{cfg.name}: missing access or link-state line"
        assert access.group(1) == up.group(1), (
            f"{arch}/{cfg.name}: link state up covers {up.group(1)} but the "
            f"access ports are {access.group(1)}")


def test_core_config_does_not_gain_a_blanket_link_state_up():
    """Core must NOT get a blanket link-state line.

    The core reference brings up one site-specific pair, not a range. Applying
    the OOB fix to core would emit reference-topology pins onto a site-specific
    wire map — the exact reason `interfaces_up` is excluded from the source
    inventory merge.
    """
    arch = "2-8-9-800"
    d = NC / "output" / arch / "default" / "configs"
    if not d.is_dir():
        pytest.skip("no generated configs")
    for cfg in sorted(d.glob("csl-*-config.sh")) + sorted(d.glob("core-*-config.sh")):
        txt = cfg.read_text()
        blanket = re.search(r"nv set interface swp\d+-\d+ link state up", txt)
        assert not blanket, (
            f"{cfg.name}: emits a blanket `link state up` range — core link "
            f"state is site-specific and must not be pinned")
