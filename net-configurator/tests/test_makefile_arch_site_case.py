# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
`make <target> arch=... site=...` must behave like `ARCH=... SITE=...`.

Make variable names are case-sensitive, so `make validation-bundle site=default`
set an unrelated variable and SITE fell through to `.era-context`. The command
looked like it worked and quietly targeted a different site — reported after it
sent a bundle request at the wrong deployment.

Values are normalized too: `2-8-9-400-sp` resolves to `2-8-9-400-SP` (the only
arch carrying uppercase), and a site name matches case-insensitively against the
directories that actually exist.

Driven through `make -n` so this tests the real Makefile, including precedence
against `.era-context`.
"""
import re
import subprocess

import pytest

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CMD = re.compile(r"make_validation_bundle\.py\s+--arch\s+(\S+)\s+--site\s+(\S+)")


def _resolve(*make_args):
    """Return (arch, site) as the Makefile resolves them, or None if it errored."""
    p = subprocess.run(["make", "-n", "validation-bundle", *make_args],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    m = CMD.search(p.stdout)
    return (m.group(1), m.group(2)) if m else None


pytestmark = pytest.mark.skipif(
    not (REPO / "Makefile").exists(), reason="Makefile absent")


# A site name that cannot arrive from anywhere else. `default` is unusable as a
# probe: it is also the fallback when SITE is unset, so `site=default` "passing"
# proves nothing — an ignored alias produces the identical result. That is not
# hypothetical; the first version of these tests only discriminated because the
# developer's `.era-context` happened to say `evpnval`, and CI (which has no
# context file) both failed one test and silently under-tested the rest.
PROBE_SITE = "zzz-case-probe"


def test_lowercase_site_is_honoured():
    """The reported bug: `site=...` was ignored and SITE fell through."""
    assert _resolve("ARCH=2-8-9-800", f"site={PROBE_SITE}") == (
        "2-8-9-800", PROBE_SITE)


def test_lowercase_arch_is_honoured():
    """Two distinct archs: whatever `.era-context` holds, it cannot satisfy
    both, so a broken alias fails at least one."""
    for arch in ("2-4-3-200", "2-8-9-400"):
        assert _resolve(f"arch={arch}", f"SITE={PROBE_SITE}") == (
            arch, PROBE_SITE), arch


def test_both_lowercase():
    assert _resolve("arch=2-4-3-200", f"site={PROBE_SITE}") == (
        "2-4-3-200", PROBE_SITE)


def test_uppercase_still_works():
    assert _resolve("ARCH=2-4-3-200", f"SITE={PROBE_SITE}") == (
        "2-4-3-200", PROBE_SITE)


def test_uppercase_wins_when_both_given():
    """An explicit ARCH=/SITE= must not be overridden by a stray lowercase."""
    assert _resolve("ARCH=2-8-9-800", "arch=2-4-3-200",
                    f"SITE={PROBE_SITE}", "site=other-probe") == (
        "2-8-9-800", PROBE_SITE)


def test_arch_value_case_is_normalized():
    """`-sp` -> `-SP`; 2-8-9-400-SP is the only arch with uppercase in its name."""
    arch, _ = _resolve("arch=2-8-9-400-sp", f"site={PROBE_SITE}")
    assert arch == "2-8-9-400-SP"


def test_unknown_arch_is_reported_with_the_value_typed():
    """Normalization must not mangle a typo into something unrecognisable —
    the error should echo what the operator actually wrote."""
    p = subprocess.run(["make", "-n", "validation-bundle", "ARCH=bogus-arch"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert "bogus-arch" in p.stdout + p.stderr


def test_any_case_reaches_the_canonical_variable():
    """Not just lowercase — the alias pass upper-cases whatever was typed."""
    for spelling in ("site", "Site", "sItE", "SIte"):
        assert _resolve("ARCH=2-8-9-800", f"{spelling}={PROBE_SITE}") == (
            "2-8-9-800", PROBE_SITE), spelling


def _recipe(*make_args):
    p = subprocess.run(["make", "-n", *make_args], cwd=REPO,
                       capture_output=True, text=True, timeout=120)
    return p.stdout


@pytest.mark.parametrize("target,upper,lower,value", [
    ("import", "EXCEL", "excel", "/tmp/x.xlsx"),
    ("switch-ztp-deploy", "NOZTP", "noztp", "1"),
])
def test_other_user_variables_are_case_insensitive_too(target, upper, lower, value):
    """The alias pass covers every operator-facing variable, not only ARCH/SITE.
    Comparing whole recipes catches a variable that reaches make but is then
    consumed somewhere this test doesn't know to look."""
    base = ["ARCH=2-8-9-800", "SITE=default"]
    assert _recipe(target, *base, f"{upper}={value}") == \
           _recipe(target, *base, f"{lower}={value}")


def test_an_unlisted_variable_name_is_not_aliased():
    """Only known variables are aliased. Aliasing arbitrary names would let a
    typo — `sight=` for `site=` — silently become a real setting, which is the
    same class of bug this whole change exists to remove.

    Uses the probe value precisely because it can arrive no other way: asserting
    `!= "default"` was wrong, since `default` is the legitimate fallback when
    SITE is unset — which is how this passed locally and failed in CI."""
    _, site = _resolve("ARCH=2-8-9-800", f"sight={PROBE_SITE}")
    assert site != PROBE_SITE, "a typo must not be promoted to SITE"


def test_unknown_site_passes_through_unchanged():
    """No matching directory ⇒ leave it alone, so the downstream 'no generated
    output at ...' message names the site the operator asked for."""
    assert _resolve("ARCH=2-8-9-800", "site=doesnotexist") == (
        "2-8-9-800", "doesnotexist")
