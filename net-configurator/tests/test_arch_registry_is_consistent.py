# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Every source that names the supported architectures must name the same set.

Adding 2-4-5-400 (ERA-49) surfaced **seven** independent hardcoded arch lists:

    net-configurator/Makefile                VALID_ARCHS
    scripts/_check_ldap_enabled.py           VALID_ARCHS
    scripts/_era_context.py                  VALID_ARCHS
    scripts/_excel_context.py                VALID_ARCHS
    scripts/import-excel.py                  VALID_ARCHS
    scripts/validate_excel.py                VALID_ARCHS
    tests/test_config_validation.py          VALID_ARCHS   <- already stale

The last one had drifted long before this ticket: it listed three of the six
supported archs. Nothing compared them, so a new arch can be half-registered and
every other test still passes — the failure mode recorded in
`feedback_rename_check_every_naming_source`.

Sources are **discovered** by scanning for the assignment rather than listed
here, so an eighth copy is caught the day it appears instead of the day someone
remembers to add it to this test.
"""
import re
import sys
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
REPO = NC.parent

# Literal-list assignment, e.g. VALID_ARCHS = ("a", "b") / {"a","b"} / [a b] (make)
_PY = re.compile(r"^\s*VALID_ARCHS\s*=\s*[\(\{\[]([^)}\]]*)[\)\}\]]", re.M)
_MK = re.compile(r"^VALID_ARCHS\s*:?=\s*(.+)$", re.M)
_ARCH = re.compile(r"\d-\d+-\d+-\d+(?:-SP)?")


def _sources() -> dict[str, set[str]]:
    """Map path -> arch set, for every file that declares VALID_ARCHS."""
    found: dict[str, set[str]] = {}
    roots = [NC / "scripts", NC / "tests", NC / "Makefile"]
    if (REPO / "data-models").is_dir():
        roots.append(REPO / "data-models")

    files: list[Path] = []
    for r in roots:
        if r.is_file():
            files.append(r)
        elif r.is_dir():
            files += [p for p in r.rglob("*") if p.suffix in (".py", "") and p.is_file()]

    for f in files:
        try:
            text = f.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if "VALID_ARCHS" not in text:
            continue
        m = _MK.search(text) if f.name == "Makefile" else _PY.search(text)
        if not m:
            continue
        archs = set(_ARCH.findall(m.group(1)))
        if archs:
            found[str(f.relative_to(REPO))] = archs
    return found


def test_ci_generate_matrix_covers_every_arch():
    """`.gitlab-ci.yml` carries its own arch matrices — a fourteenth source.

    The scan below only sees `VALID_ARCHS` assignments, so it cannot see a YAML
    job matrix. Adding 2-4-5-400 (ERA-49) registered it in every Python/Make
    list and still left it with ZERO CI coverage: absent from the `generate:`
    matrix, so not even the cheap non-Air check ran on it.

    The e2e matrices are deliberately NOT asserted here — they cost Air budget
    per pipeline and already omit archs on purpose (2-8-9-400-SP is in
    `generate:` but not in e2e). `generate:` is the one that should be total.
    """
    ci = (REPO / ".gitlab-ci.yml")
    if not ci.exists():
        pytest.skip("no .gitlab-ci.yml (public tree)")
    text = ci.read_text()

    matrices = re.findall(r"- ARCH: \[([^\]]*)\]", text)
    assert matrices, "no ARCH job matrix found — has the CI layout changed?"
    generate_matrix = max(matrices, key=lambda m: len(_ARCH.findall(m)))
    covered = set(_ARCH.findall(generate_matrix))

    registered = set().union(*_sources().values())
    missing = sorted(registered - covered)
    assert not missing, (
        f"registered archs absent from the CI generate matrix: {missing} — "
        "they would ship with no CI coverage at all"
    )


def test_sources_are_discovered():
    """A vacuous scan would make every assertion below pass."""
    src = _sources()
    assert len(src) >= 6, (
        f"expected at least the 6 known VALID_ARCHS declarations, found "
        f"{len(src)}: {sorted(src)} — has the assignment style changed?"
    )


def test_every_source_names_the_same_arch_set():
    src = _sources()
    sets = {frozenset(v) for v in src.values()}
    if len(sets) > 1:
        union = set().union(*src.values())
        detail = "\n".join(
            f"  {p}: missing {sorted(union - a) or '-'}" for p, a in sorted(src.items())
        )
        pytest.fail(f"arch lists disagree; union is {sorted(union)}\n{detail}")


def test_every_supported_arch_has_committed_input():
    """A registered arch with no workbook is registered in name only."""
    src = _sources()
    archs = set().union(*src.values())
    missing = sorted(a for a in archs if not (NC / "input" / a / "default").is_dir())
    assert not missing, f"registered archs with no input/<arch>/default: {missing}"


@pytest.mark.skipif(not (REPO / "data-models" / "models").is_dir(),
                    reason="data-models absent (public tree)")
def test_every_supported_arch_has_a_model():
    src = _sources()
    archs = set().union(*src.values())
    models = {p.stem for p in (REPO / "data-models" / "models").glob("*.yaml")}
    missing = sorted(archs - models)
    assert not missing, f"registered archs with no data-models/models/<arch>.yaml: {missing}"


# ---------------------------------------------------------------------------
# Registered is not the same as usable
# ---------------------------------------------------------------------------

def _registered_archs() -> list[str]:
    src = _sources()
    return sorted(set().union(*src.values())) if src else []


@pytest.mark.parametrize("arch", _registered_archs())
def test_registered_arch_validates_its_own_default_workbook(arch):
    """Every registered arch's shipped default must pass `validate-excel`.

    The list-consistency tests above check that an arch is *named* everywhere.
    They cannot catch a per-arch allowlist keyed on something other than
    VALID_ARCHS — and adding 2-4-5-400 hit exactly that: an eighth naming
    source, `validate_excel.ARCH_RESTRICTED_FUNCTIONS`, which maps switch role
    -> permitted archs. The arch was registered in all seven VALID_ARCHS
    declarations and still failed validation on its own workbook:

        Function 'core' is only valid on arch(s) ['2-4-3-200', '2-4-5-800',
        '2-8-5-200', '2-8-9-400']; current arch is '2-4-5-400'

    Validating the shipped default end-to-end catches that class regardless of
    where the next allowlist hides.
    """
    import subprocess
    wb = NC / "input" / arch / "default" / f"{arch}.xlsx"
    if not wb.exists():
        pytest.skip(f"no committed default workbook for {arch}")

    proc = subprocess.run(
        [sys.executable, str(NC / "scripts" / "validate_excel.py"), str(wb)],
        capture_output=True, text=True, cwd=NC,
    )
    assert proc.returncode == 0, (
        f"{arch}: committed default fails validate-excel\n"
        + "\n".join(l for l in proc.stdout.splitlines() if "❌" in l)
    )
