# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""`make import` must not silently change the case of the site it was given.

`_safe_site_name()` lowercased. Nothing downstream does: the Makefile uses
`$(SITE)` verbatim, and `make generate` looks for
`input/<arch>/$(SITE)/<arch>.xlsx`. So import wrote one directory and generate
read another, and the only sites affected were the ones with an uppercase letter.

Found by the first e2e run of `2-8-9-400-SP` (pipeline 64062522, 2026-08-22) --
the only arch whose NAME carries uppercase, so `SITE=ci-<id>-2-8-9-400-SP-noztp`
became `...-2-8-9-400-sp-noztp` on disk:

    make import  wrote ->  input/2-8-9-400-SP/ci-...-2-8-9-400-sp-noztp/
    make generate looked -> input/2-8-9-400-SP/ci-...-2-8-9-400-SP-noztp/
    [File] Not found

It is not CI-only. Any operator using a mixed-case site name hits it, and the
Makefile's site-normalisation block -- which exists to reconcile exactly this and
whose comment names `Customer-A` -- does not fire (see GitLab #63).

Sanitisation of genuinely unsafe characters is unchanged; only the case-folding
goes.
"""
import re
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from import_excel_shim import _safe_site_name  # noqa: E402


class TestCaseIsPreserved:
    def test_uppercase_survives(self):
        assert _safe_site_name("Customer-A") == "Customer-A"

    def test_the_2_8_9_400_sp_ci_site(self):
        site = "ci-64062522-2-8-9-400-SP-noztp"
        assert _safe_site_name(site) == site

    def test_mixed_case_survives(self):
        assert _safe_site_name("MyLab2") == "MyLab2"


class TestSanitisationStillApplies:
    @pytest.mark.parametrize("raw,want", [
        ("my site", "my-site"),
        ("a/b", "a-b"),
        ("--lead--trail--", "lead-trail"),  # runs of dashes collapse to one
        ("", "default"),
        ("   ", "default"),
        ("!!!", "default"),
    ])
    def test_unsafe_input_is_still_sanitised(self, raw, want):
        assert _safe_site_name(raw) == want

    def test_shell_metacharacters_are_neutralised(self):
        out = _safe_site_name("a;rm -rf /")
        assert ";" not in out and "/" not in out and " " not in out

    def test_result_always_satisfies_the_makefile_site_guard(self):
        """Whatever comes out must match the charset the Makefile SITE guard allows."""
        for raw in ("Customer-A", "my site", "a;rm -rf /", "MiXeD.2", "x" * 40):
            out = _safe_site_name(raw)
            assert re.fullmatch(r"[A-Za-z0-9._-]+", out), f"{raw!r} -> {out!r}"
