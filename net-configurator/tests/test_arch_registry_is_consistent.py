# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Every reader of the supported-architecture set must see the same set, and that
set must come from the models (ERA-88).

Adding 2-4-5-400 (ERA-49) surfaced **seven** independent hardcoded arch lists
(Makefile, five scripts, one stale test). ERA-88 replaced them with ONE
committed registry, `scripts/valid_archs.yml`, generated from
`data-models/models/*.yaml` by `data-models/generate_valid_archs.py`:

    data-models/models/<arch>.yaml      source of truth (internal)
        -> scripts/valid_archs.yml      generated, committed, ships public
            -> scripts/_valid_archs.py  the one Python reader
            -> Makefile VALID_ARCHS     sed over the same file

This module therefore checks three things, none of them by listing archs here:

1. **Readers agree.** Every runtime consumer (the five scripts, imported for
   real, plus the Makefile, evaluated for real) exposes exactly the registry.
   Readers are discovered by scanning `scripts/` for the import, so a new
   consumer is covered the day it appears.
2. **No literal copy came back.** A scan for literal `VALID_ARCHS = (...)`
   assignments must find nothing — the pre-ERA-88 failure mode is an eighth
   list nobody compares.
3. **The registry is not stale.** In the internal monorepo the committed file
   must equal the model-derived list (the drift guard); the public tree, which
   has no models, skips that one check and trusts the committed file.

The arch-keyed residue (`ARCH_RESTRICTED_FUNCTIONS`, `ARCH_SCALING`,
`MAX_SUPPORTED_SU`, `inventory_defaults.yml`) is deliberately NOT collapsed into
the registry — those carry per-arch *values*, not membership — and is covered by
`test_registered_arch_validates_its_own_default_workbook` end-to-end.
"""
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
REPO = NC.parent
SCRIPTS = NC / "scripts"
REGISTRY = SCRIPTS / "valid_archs.yml"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _valid_archs import VALID_ARCHS as REGISTRY_ARCHS, load_valid_archs  # noqa: E402

# Literal-list assignment, e.g. VALID_ARCHS = ("a", "b") / {"a","b"} / [a b] (make)
_PY_LITERAL = re.compile(r"^\s*VALID_ARCHS\s*=\s*[\(\{\[]([^)}\]]*)[\)\}\]]", re.M)
_MK_LITERAL = re.compile(r"^VALID_ARCHS\s*:?=\s*(.+)$", re.M)
_ARCH = re.compile(r"\d-\d+-\d+-\d+(?:-SP)?")
_IMPORT = re.compile(r"^from _valid_archs import .*\bVALID_ARCHS\b", re.M)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _literal_sources() -> dict[str, set[str]]:
    """path -> arch set for every file that still hardcodes a VALID_ARCHS list."""
    found: dict[str, set[str]] = {}
    roots = [SCRIPTS, NC / "tests", NC / "Makefile"]
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
        m = _MK_LITERAL.search(text) if f.name == "Makefile" else _PY_LITERAL.search(text)
        if not m:
            continue
        archs = set(_ARCH.findall(m.group(1)))
        if archs:
            found[str(f.relative_to(REPO))] = archs
    return found


def _python_readers() -> list[Path]:
    """Every script that imports VALID_ARCHS from the shared reader."""
    return sorted(p for p in SCRIPTS.glob("*.py")
                  if p.name != "_valid_archs.py" and _IMPORT.search(p.read_text()))


def _import_script(path: Path):
    """Import a script by path (import-excel.py has a hyphen; validate_excel
    pulls in openpyxl-heavy siblings) without executing its CLI."""
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _makefile_archs() -> set[str]:
    """What `make` itself computes for VALID_ARCHS after evaluating the Makefile."""
    proc = subprocess.run(["make", "-pn", "-f", "Makefile"], capture_output=True,
                          text=True, cwd=NC)
    m = re.search(r"^VALID_ARCHS\s*:?=\s*(.+)$", proc.stdout, re.M)
    assert m, "make did not report a VALID_ARCHS value — has the Makefile changed?"
    return set(m.group(1).split())


# ---------------------------------------------------------------------------
# 1. Readers agree
# ---------------------------------------------------------------------------

def test_registry_file_is_the_committed_public_source():
    assert REGISTRY.is_file(), f"{REGISTRY} missing — run `make valid-archs` (internal)"
    assert load_valid_archs(REGISTRY) == REGISTRY_ARCHS
    assert len(REGISTRY_ARCHS) >= 7, REGISTRY_ARCHS
    assert "GENERATED" in REGISTRY.read_text(), "registry must say it is generated"


def test_python_readers_are_discovered():
    """A vacuous scan would make the agreement test below pass."""
    readers = [p.name for p in _python_readers()]
    expected = {"_check_ldap_enabled.py", "_era_context.py", "_excel_context.py",
                "import-excel.py", "validate_excel.py"}
    assert expected <= set(readers), (
        f"expected the five ERA-88 readers to import from _valid_archs, found {readers}"
    )


@pytest.mark.parametrize("script", _python_readers(), ids=lambda p: p.name)
def test_every_python_reader_sees_the_registry(script):
    mod = _import_script(script)
    assert tuple(mod.VALID_ARCHS) == REGISTRY_ARCHS, script.name


def test_makefile_sees_the_registry():
    assert _makefile_archs() == set(REGISTRY_ARCHS)


def test_makefile_case_normalisation_uses_the_registry():
    """`ARCH=2-8-9-400-sp` is matched case-insensitively against VALID_ARCHS;
    it only resolves because the registry read succeeded."""
    sp = next(a for a in REGISTRY_ARCHS if a.endswith("-SP"))
    proc = subprocess.run(["make", "-pn", "-f", "Makefile", f"ARCH={sp.lower()}"],
                          capture_output=True, text=True, cwd=NC)
    m = re.search(r"^_ARCH_MATCH\s*:?=\s*(\S+)$", proc.stdout, re.M)
    assert m and m.group(1) == sp, proc.stdout[-500:]


@pytest.mark.internal_only("data-models/models")
def test_makefile_repair_target_runs_without_a_registry(tmp_path):
    """The recovery the guard advertises must actually be reachable: with the
    registry missing, arch-dependent goals fail closed but `make valid-archs`
    regenerates the file."""
    scratch = tmp_path / "repo"
    (scratch / "net-configurator" / "scripts").mkdir(parents=True)
    shutil.copytree(REPO / "data-models" / "models", scratch / "data-models" / "models",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (scratch / "data-models" / "generate_valid_archs.py").write_bytes(
        (REPO / "data-models" / "generate_valid_archs.py").read_bytes())
    (scratch / "Makefile.internal").write_bytes((REPO / "Makefile.internal").read_bytes())
    nc = scratch / "net-configurator"
    (nc / "Makefile").write_bytes((NC / "Makefile").read_bytes())

    def run(*goals):
        return subprocess.run(["make", "-f", "Makefile", *goals],
                              capture_output=True, text=True, cwd=nc)

    broken = run("-n", "generate", "ARCH=2-8-9-800")
    assert broken.returncode != 0 and "valid_archs.yml is missing" in broken.stderr

    bare = run()
    assert bare.returncode != 0 and "valid_archs.yml is missing" in bare.stderr

    repaired = run("valid-archs")
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr
    assert load_valid_archs(nc / "scripts" / "valid_archs.yml") == REGISTRY_ARCHS
    assert run("check-valid-archs").returncode == 0


# ---------------------------------------------------------------------------
# 2. No literal copy came back
# ---------------------------------------------------------------------------

def test_no_literal_valid_archs_list_remains():
    stray = _literal_sources()
    assert not stray, (
        "hardcoded VALID_ARCHS lists reintroduced — read scripts/valid_archs.yml "
        "via _valid_archs instead:\n  " + "\n  ".join(sorted(stray))
    )


# ---------------------------------------------------------------------------
# 3. The registry is not stale (internal monorepo only)
# ---------------------------------------------------------------------------

_MODELS = REPO / "data-models" / "models"
_GENERATOR = REPO / "data-models" / "generate_valid_archs.py"
_internal_only = pytest.mark.internal_only("data-models/models", "data-models/generate_valid_archs.py")


@_internal_only
def test_registry_matches_model_files():
    models = tuple(sorted(p.stem for p in _MODELS.glob("*.yaml")))
    assert REGISTRY_ARCHS == models, (
        f"scripts/valid_archs.yml drifted from data-models/models — run `make valid-archs`\n"
        f"  registry: {REGISTRY_ARCHS}\n  models:   {models}"
    )


@_internal_only
def test_generator_check_mode_passes_on_committed_registry():
    proc = subprocess.run([sys.executable, str(_GENERATOR), "--check"],
                          capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@_internal_only
def test_generator_check_mode_fails_on_a_stale_registry(tmp_path):
    """Discrimination: a registry missing one model arch must be reported."""
    stale = tmp_path / "valid_archs.yml"
    stale.write_text(REGISTRY.read_text().replace(f"  - {REGISTRY_ARCHS[-1]}\n", ""))
    proc = subprocess.run([sys.executable, str(_GENERATOR), "--check", "--output", str(stale)],
                          capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "stale" in proc.stdout

    proc = subprocess.run([sys.executable, str(_GENERATOR), "--output", str(stale)],
                          capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0
    assert stale.read_text() == REGISTRY.read_text()


# ---------------------------------------------------------------------------
# The reader fails closed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body,msg", [
    ("archs:\n", "no archs"),
    ("archs:\n  - 2-4-3-200\n  - 2-4-3-200\n", "duplicate"),
    ("archs:\n  - not-an-arch\n", "malformed"),
    ("archs:\n  - 2-4-3-200\nother: 1\n", "unexpected line"),
], ids=["empty", "duplicate", "malformed", "trailing-key"])
def test_reader_rejects_a_bad_registry(tmp_path, body, msg):
    bad = tmp_path / "valid_archs.yml"
    bad.write_text("---\n# header\n" + body)
    with pytest.raises(RuntimeError, match=msg):
        load_valid_archs(bad)


def test_reader_rejects_a_missing_registry(tmp_path):
    with pytest.raises(RuntimeError, match="missing"):
        load_valid_archs(tmp_path / "nope.yml")


def test_reader_round_trips_the_registry_without_yaml(tmp_path):
    """Comments and quoting are tolerated; order is preserved (it's a tuple)."""
    f = tmp_path / "valid_archs.yml"
    f.write_text("---\n# c\narchs:  # c\n  - '2-4-3-200'\n  - \"2-8-9-400-SP\"  # c\n")
    assert load_valid_archs(f) == ("2-4-3-200", "2-8-9-400-SP")


# ---------------------------------------------------------------------------
# Registered is not the same as usable
# ---------------------------------------------------------------------------

@pytest.mark.internal_only(".gitlab-ci.yml")
def test_ci_generate_matrix_covers_every_arch():
    """`.gitlab-ci.yml` carries its own arch matrices — YAML cannot read the
    registry, so this is the one restatement that must stay and be checked.

    Adding 2-4-5-400 (ERA-49) registered it in every Python/Make list and
    still left it with ZERO CI coverage: absent from the `generate:` matrix.

    The e2e matrices are deliberately NOT asserted here — they cost Air budget
    per pipeline and already omit archs on purpose (2-8-9-400-SP is in
    `generate:` but not in e2e). `generate:` is the one that should be total.
    """
    ci = REPO / ".gitlab-ci.yml"
    matrices = re.findall(r"- ARCH: \[([^\]]*)\]", ci.read_text())
    assert matrices, "no ARCH job matrix found — has the CI layout changed?"
    generate_matrix = max(matrices, key=lambda m: len(_ARCH.findall(m)))
    covered = set(_ARCH.findall(generate_matrix))
    missing = sorted(set(REGISTRY_ARCHS) - covered)
    assert not missing, (
        f"registered archs absent from the CI generate matrix: {missing} — "
        "they would ship with no CI coverage at all"
    )


def test_every_supported_arch_has_committed_input():
    """A registered arch with no workbook is registered in name only."""
    missing = sorted(a for a in REGISTRY_ARCHS if not (NC / "input" / a / "default").is_dir())
    assert not missing, f"registered archs with no input/<arch>/default: {missing}"


@pytest.mark.parametrize("arch", REGISTRY_ARCHS)
def test_registered_arch_validates_its_own_default_workbook(arch):
    """Every registered arch's shipped default must pass `validate-excel`.

    The agreement tests above check that an arch is *named* everywhere. They
    cannot catch a per-arch allowlist keyed on something other than the
    registry — and adding 2-4-5-400 hit exactly that: an eighth naming source,
    `validate_excel.ARCH_RESTRICTED_FUNCTIONS`, which maps switch role ->
    permitted archs. The arch was registered everywhere and still failed
    validation on its own workbook:

        Function 'core' is only valid on arch(s) ['2-4-3-200', '2-4-5-800',
        '2-8-5-200', '2-8-9-400']; current arch is '2-4-5-400'

    Validating the shipped default end-to-end catches that class regardless of
    where the next allowlist hides.
    """
    wb = NC / "input" / arch / "default" / f"{arch}.xlsx"
    if not wb.exists():
        pytest.skip(f"no committed default workbook for {arch}")

    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_excel.py"), str(wb)],
        capture_output=True, text=True, cwd=NC,
    )
    assert proc.returncode == 0, (
        f"{arch}: committed default fails validate-excel\n"
        + "\n".join(l for l in proc.stdout.splitlines() if "❌" in l)
    )
