#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Switch-port grammar: the validator and the topology generator must agree.

Regression guard for ERA-96 / GitLab #66. There used to be two parsers — a
case-INSENSITIVE regex in validate_excel.py and a case-SENSITIVE one in
topology_generator.py. `SWP49` therefore passed `make validate-excel` and was
then silently dropped from the generated topology: a cabled link disappeared
from the fabric with no error at any stage.

The rule these tests encode: **the validator must never be more permissive
than the consumer.** Anything the validator accepts, the topology generator
must be able to parse. The reverse (consumer accepts more) is safe, because
the validator then reports it to the operator instead of dropping it.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from utils import SWP_PORT_RE, parse_swp_port  # noqa: E402
import topology_generator  # noqa: E402
import validate_excel  # noqa: E402


CASE_VARIANTS = ["swp49", "SWP49", "Swp49", "sWp49", "swp49s3", "SWP49S3", "Swp49s3", "swp49S3"]


@pytest.mark.parametrize("token", CASE_VARIANTS)
def test_validator_and_topology_agree_on_case(token):
    """Every case variant the validator accepts must also parse for topology."""
    assert SWP_PORT_RE.match(token), f"validator rejected {token!r}"
    assert parse_swp_port(token) is not None, (
        f"validator accepts {token!r} but the topology generator drops it — "
        "this is the ERA-96 silent-link-loss bug")


@pytest.mark.parametrize("token,expected", [
    ("swp49", (49, None)),
    ("SWP49", (49, None)),
    ("Swp49", (49, None)),
    ("swp49s3", (49, 3)),
    ("SWP49S3", (49, 3)),
    ("swp1", (1, None)),
    ("swp64s7", (64, 7)),
    ("50", (50, None)),      # bare number — accepted by the consumer
])
def test_parse_swp_port_accepts(token, expected):
    assert parse_swp_port(token) == expected


@pytest.mark.parametrize("token", ["", "   ", "NA", "swp", "swps3", "eth0", "swp49s", "x50", None])
def test_parse_swp_port_rejects(token):
    assert parse_swp_port(token) is None


def test_no_validator_accepted_token_is_dropped_by_topology():
    """Exhaustive sweep: nothing the validator accepts may fail to parse."""
    dropped = []
    for base in (1, 7, 49, 64):
        for sub in (None, 0, 3):
            stem = f"swp{base}" if sub is None else f"swp{base}s{sub}"
            for variant in (stem, stem.upper(), stem.capitalize()):
                if SWP_PORT_RE.match(variant) and parse_swp_port(variant) is None:
                    dropped.append(variant)
    assert not dropped, f"validator accepts but topology drops: {dropped}"


def test_bare_number_asymmetry_is_deliberate_and_fails_closed():
    """The consumer accepts bare numbers; the validator does not.

    That direction is safe — the operator is told at validate time rather than
    having the port silently dropped. Pinned so it stays a decision, not drift.
    """
    assert parse_swp_port("50") == (50, None)
    assert SWP_PORT_RE.match("50") is None


def test_both_modules_use_the_one_canonical_implementation():
    """Guards against a local copy being reintroduced in either module."""
    assert topology_generator.parse_swp_port is parse_swp_port
    assert validate_excel.SWP_PORT_RE is SWP_PORT_RE
