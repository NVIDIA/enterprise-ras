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
directories that actually exist. The site block needed `override` to reach a
command-line value (GitLab #63) -- before that it only ever fired for an
environment or `.era-context` SITE.

Driven through `make -n` so this tests the real Makefile, including precedence
against `.era-context`.
"""
import os
import re
import shutil
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


@pytest.mark.parametrize("arch_arg,site_arg", [
    ("ARCH=2-8-9-400-SP", f"SITE={PROBE_SITE}"),
    ("arch=2-8-9-400-SP", f"site={PROBE_SITE}"),
    ("arch=2-8-9-400-sp", f"site={PROBE_SITE.upper()}"),
    ("ARCH=2-8-9-400-sp", f"site={PROBE_SITE}"),
])
def test_readme_four_spellings_resolve_to_the_same_arch(arch_arg, site_arg):
    """README's "Case-insensitive variables" table, spelling for spelling.

    `ARCH=2-8-9-400-sp` (canonical name, lower-case value) is the one that
    needs `override`: a plain `ARCH :=` cannot replace a command-line variable,
    so the value reached check_arch un-normalised (GitLab #87).
    """
    resolved = _resolve(arch_arg, site_arg)
    assert resolved is not None
    assert resolved[0] == "2-8-9-400-SP"


def test_uppercase_name_lowercase_value_reaches_generate():
    p = subprocess.run(["make", "-n", "generate", "ARCH=2-8-9-400-sp",
                        f"SITE={PROBE_SITE}"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert "excel_parser.py --arch 2-8-9-400-SP" in p.stdout
    assert "--arch 2-8-9-400-sp" not in p.stdout


def test_secrets_target_still_sees_a_normalised_command_line_arch():
    """`override` changes $(origin ARCH); `make secrets ARCH=…` must still be
    per-deployment mode, and an *environment* ARCH must still not be."""
    p = subprocess.run(["make", "-n", "secrets", "ARCH=2-8-9-400-sp",
                        f"SITE={PROBE_SITE}"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert f"secrets-setup.py --arch 2-8-9-400-SP --site {PROBE_SITE}" in p.stdout
    env = {**os.environ, "ARCH": "2-8-9-400-sp"}
    p = subprocess.run(["make", "-n", "secrets"], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=120)
    assert "secrets-setup.py" in p.stdout
    assert "--arch" not in p.stdout


# GitLab #63: the directory-matching block. `default` exists for every arch
# (committed reference output), and no arch has a `DEFAULT` sibling, so the
# probe is unambiguous. `default` is fine as the *expected* value here: the
# argument is `DEFAULT`, so a make that ignores the block still prints `DEFAULT`.
def _generate_site(*make_args, env=None):
    p = subprocess.run(["make", "-n", "generate", *make_args], cwd=REPO,
                       env=env, capture_output=True, text=True, timeout=120)
    m = re.search(r"excel_parser\.py --arch \S+ --site (\S+)", p.stdout)
    return (m.group(1) if m else None), p.stderr


@pytest.mark.parametrize("arch", ["2-8-9-400-SP", "2-8-9-400-sp", "2-4-3-200"])
def test_command_line_site_matches_existing_directory_case_insensitively(arch):
    """`SITE=DEFAULT` on the command line must land on the existing `default/`
    (GitLab #63: a plain `SITE :=` could not reassign a command-line variable,
    so the operator was sent to output/<arch>/DEFAULT/ instead)."""
    site, err = _generate_site(f"ARCH={arch}", "SITE=DEFAULT")
    assert site == "default", err
    assert "SITE 'DEFAULT' matches existing site directory 'default'" in err


def test_lowercase_site_alias_matches_existing_directory():
    """README: `site=CUSTOMER-A` finds an existing `customer-a`."""
    site, _ = _generate_site("arch=2-8-9-400-sp", "site=DEFAULT")
    assert site == "default"


def test_environment_site_matches_existing_directory():
    """Regression guard, not a #63 discriminator: an environment SITE was the one
    case the plain `SITE :=` could already reassign."""
    env = {k: v for k, v in os.environ.items() if k != "SITE"}
    site, _ = _generate_site("ARCH=2-8-9-400-SP", env={**env, "SITE": "Default"})
    assert site == "default"


def test_exact_site_is_left_alone_without_warning():
    site, err = _generate_site("ARCH=2-8-9-400-SP", "SITE=default")
    assert site == "default"
    assert "matches existing site directory" not in err


def test_unmatched_site_is_passed_through_as_typed():
    """No directory matches: the error downstream must name what was typed."""
    site, err = _generate_site("ARCH=2-8-9-400-SP", f"SITE={PROBE_SITE.upper()}")
    assert site == PROBE_SITE.upper()
    assert "matches existing site directory" not in err


def test_directory_match_reaches_import_and_secrets_targets():
    """`override` changes $(origin SITE); IMPORT_SITE and _SECRETS_SITE key on
    _SITE_ON_CLI so the matched value still counts as an explicit site."""
    p = subprocess.run(["make", "-n", "secrets", "ARCH=2-8-9-400-SP", "SITE=DEFAULT"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert "secrets-setup.py --arch 2-8-9-400-SP --site default" in p.stdout
    p = subprocess.run(["make", "-pn", "generate", "ARCH=2-8-9-400-SP", "SITE=DEFAULT"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert re.search(r"^IMPORT_SITE := default$", p.stdout, re.M)
    assert re.search(r"^SITE := default$", p.stdout, re.M)


def _scratch_tree(tmp_path, ctx_arch, ctx_site="default"):
    """Copy of the Makefile + parse-time scripts with a stale `.era-context`
    pointing at `ctx_arch`, so an EXCEL-driven target's real arch (read from
    the workbook by the importer) differs from make's $(ARCH)."""
    tree = tmp_path / "tree"
    (tree / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "Makefile", tree / "Makefile")
    for name in ("valid_archs.yml", "_valid_archs.py", "_era_context.py", "_site_name.py"):
        shutil.copy(REPO / "scripts" / name, tree / "scripts" / name)
    (tree / ".era-context").write_text(f"arch: {ctx_arch}\nsite: {ctx_site}\n")
    return tree


def _import_site(tree, *make_args):
    p = subprocess.run(["make", "-n", "import", *make_args], cwd=tree,
                       capture_output=True, text=True, timeout=120)
    m = re.search(r'import-excel\.py "\S+" --site "([^"]+)"', p.stdout)
    return (m.group(1) if m else None), p.stderr


def test_excel_driven_import_keeps_explicit_site_when_context_arch_is_stale(tmp_path):
    """2026-09-23 review P2: `.era-context` says 2-4-3-200, which has a
    `review-case/` output; the workbook is 2-8-9-800, which already has the
    exact `Review-Case/`. The directory match must not use the stale arch to
    retarget an explicit `SITE=` for an EXCEL-driven target."""
    tree = _scratch_tree(tmp_path, "2-4-3-200")
    (tree / "output/2-4-3-200/review-case").mkdir(parents=True)
    wb = tree / "input/2-8-9-800/Review-Case/2-8-9-800.xlsx"
    wb.parent.mkdir(parents=True)
    wb.write_bytes(b"")
    site, err = _import_site(
        tree, f"EXCEL={wb.relative_to(tree)}", "SITE=Review-Case")
    assert site == "Review-Case", err
    assert "matches existing site directory" not in err


def test_excel_driven_import_does_not_match_directories_even_under_context_arch(tmp_path):
    """With EXCEL= the arch is the workbook's, never $(ARCH); no directory
    match is attempted at all, only the importer's own canonicalisation."""
    tree = _scratch_tree(tmp_path, "2-8-9-800")
    (tree / "output/2-8-9-800/review-case").mkdir(parents=True)
    site, err = _import_site(tree, "EXCEL=some.xlsx", "SITE=Review-Case")
    assert site == "Review-Case", err
    assert "matches existing site directory" not in err
    site, _ = _import_site(tree, "excel=some.xlsx", "SITE=Review-Case")
    assert site == "Review-Case"


def test_non_excel_target_still_matches_directories_under_context_arch(tmp_path):
    """Control for the EXCEL guard: `make generate SITE=…` with the arch from
    `.era-context` still gets the #63 directory match."""
    tree = _scratch_tree(tmp_path, "2-4-3-200")
    (tree / "output/2-4-3-200/review-case").mkdir(parents=True)
    p = subprocess.run(["make", "-n", "generate", "SITE=Review-Case"], cwd=tree,
                       capture_output=True, text=True, timeout=120)
    assert "--arch 2-4-3-200 --site review-case" in p.stdout, p.stdout + p.stderr
    assert "SITE 'Review-Case' matches existing site directory 'review-case'" in p.stderr


@pytest.mark.parametrize("raw, canon", [
    ("lab--2", "lab-2"), ("lab.2", "lab-2"), ("lab-", "lab"), ("Lab-2", "Lab-2"),
])
def test_secrets_target_uses_the_canonicalised_command_line_site(raw, canon):
    """Canonicalising SITE uses `override`, which changes $(origin SITE); the
    secrets wizard must still treat it as an explicit site, not fall back to
    `default` (2026-09-22 review P2)."""
    for arch in ("2-8-9-400-SP", "2-8-9-400-sp"):
        p = subprocess.run(["make", "-n", "secrets", f"ARCH={arch}", f"SITE={raw}"],
                           cwd=REPO, capture_output=True, text=True, timeout=120)
        assert f"secrets-setup.py --arch 2-8-9-400-SP --site {canon}" in p.stdout, arch


def test_secrets_target_ignores_environment_and_missing_site():
    env = {k: v for k, v in os.environ.items() if k != "SITE"}
    p = subprocess.run(["make", "-n", "secrets", "ARCH=2-8-9-400-SP"], cwd=REPO,
                       env=env, capture_output=True, text=True, timeout=120)
    assert "--site default" in p.stdout
    p = subprocess.run(["make", "-n", "secrets", "ARCH=2-8-9-400-SP"], cwd=REPO,
                       env={**env, "SITE": "lab--2"}, capture_output=True, text=True, timeout=120)
    assert "--site default" in p.stdout


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
