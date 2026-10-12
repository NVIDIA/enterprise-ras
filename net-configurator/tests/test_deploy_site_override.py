# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
`make deploy EXCEL=… SITE=<x>` and `make deploy-exclude-servers EXCEL=… SITE=<x>`
must run *every* step against <x>, not just the import (GitLab #86).

The import step honoured `SITE=` and wrote `.era-context`, but the pipeline
then re-derived the site from the workbook's `Settings.site_name` via
`_excel_context.py`, so generate/topology/node-instructions/Air landed on the
workbook-cell site — overwriting another site's `output/` without a prompt and
leaving `.era-context` pointing somewhere else. `deploy-switches-only` already
did this right; the other two pipelines now apply the same rule.

These recipes contain `$(MAKE)` sub-invocations, which GNU make executes even
under `-n`, so a dry run is not safe here. The tests therefore read the recipe
text (as tests/test_deploy_switches_only_site.py does) and replay the
site-selection shell fragment in isolation.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MAKEFILE = REPO / "Makefile"

pytestmark = pytest.mark.skipif(not MAKEFILE.exists(), reason="Makefile absent")

PIPELINES = ["deploy", "deploy-exclude-servers"]
OVERRIDE_LINE = '[ -z "$(IMPORT_SITE)" ] || _SITE="$(IMPORT_SITE)"; \\'


def _recipe(target):
    text = MAKEFILE.read_text().splitlines()
    out, in_target = [], False
    for line in text:
        if re.match(rf"^{re.escape(target)}:", line):
            in_target = True
            continue
        if in_target:
            if re.match(r"^[A-Za-z_.%$()-][^\s:=]*:", line):
                break
            out.append(line)
    return "\n".join(out)


@pytest.mark.parametrize("target", PIPELINES)
def test_import_site_is_pinned_before_anything_consumes_the_site(target):
    recipe = _recipe(target)
    assert OVERRIDE_LINE in recipe, f"{target}: no IMPORT_SITE override after _excel_context"
    ctx = recipe.index("_excel_context.py '$(EXCEL)')")
    pin = recipe.index(OVERRIDE_LINE)
    first_use = recipe.index('_check_ldap_enabled.py "$$_ARCH" "$$_SITE"')
    assert ctx < pin < first_use
    # Every downstream step is driven by the pinned shell variable, never by
    # the make-level $(SITE) (which absorbs .era-context).
    tail = recipe[pin:]
    assert re.search(r"\$\(MAKE\) generate ARCH=\$\$_ARCH SITE=\$\$_SITE", tail)
    assert "SITE=$(SITE)" not in tail


@pytest.mark.parametrize("target", PIPELINES)
def test_pipeline_does_not_fall_back_to_era_context_or_make_level_arch(target):
    """`deploy-exclude-servers` used to take `$(ARCH)`/`$(SITE)` (i.e. a stale
    `.era-context`) over the workbook being deployed whenever both were set."""
    recipe = _recipe(target)
    body = recipe.split("Importing Excel", 1)[1]
    assert "_era_context.py" not in body
    assert '_ARCH="$(ARCH)"' not in body
    assert '_SITE="$(SITE)"' not in body


def test_deploy_switches_only_reference_pattern_is_unchanged():
    recipe = _recipe("deploy-switches-only")
    assert '_DEPLOY_SITE="$(IMPORT_SITE)"' in recipe


@pytest.mark.parametrize("spelling", ["SITE=zzz-probe", "site=zzz-probe", "Site=zzz-probe"])
def test_every_command_line_spelling_of_site_reaches_the_import(spelling):
    """`site=` is materialised into SITE with origin `file`; IMPORT_SITE must
    not key off `$(origin SITE)` alone (README: `site=` reaches `SITE`)."""
    p = subprocess.run(["make", "-n", "import", "EXCEL=/nonexistent/x.xlsx", spelling],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert 'import-excel.py "/nonexistent/x.xlsx" --site "zzz-probe"' in p.stdout


def test_no_command_line_site_means_workbook_cell_at_import():
    p = subprocess.run(["make", "-n", "import", "EXCEL=/nonexistent/x.xlsx"],
                       cwd=REPO, capture_output=True, text=True, timeout=120,
                       env={k: v for k, v in os.environ.items() if k != "SITE"})
    assert '--site ""' in p.stdout  # the `else` branch (no --site) is what runs


@pytest.mark.parametrize("target", PIPELINES)
def test_ignored_command_line_arch_is_warned_about(target):
    recipe = _recipe(target)
    assert 'if [ -n "$(_ARCH_ON_CLI)" ] && [ "$(ARCH)" != "$$_ARCH" ]' in recipe


SHELL_FRAGMENT = (
    'eval "$CTX"; '
    '[ -z "$IMPORT_SITE" ] || _SITE="$IMPORT_SITE"; '
    'echo "$_ARCH $_SITE"'
)


def _select(import_site):
    env = {"CTX": "_ARCH='2-4-3-200'\n_SITE='sample'", "IMPORT_SITE": import_site}
    return subprocess.run(["bash", "-c", SHELL_FRAGMENT], env=env,
                          capture_output=True, text=True).stdout.strip()


def test_selection_fragment_prefers_the_command_line_site():
    # SITE=audit-lab2 on the command line, workbook cell says "sample".
    assert _select("audit-lab2") == "2-4-3-200 audit-lab2"


def test_selection_fragment_keeps_the_workbook_cell_without_site():
    assert _select("") == "2-4-3-200 sample"


# --- Greptile P1 on !304: a command-line SITE must name the directory the
# importer writes. `lab--2` passed the Makefile guard but import-excel.py
# stored `lab-2`; generate/deploy then looked for `lab--2`.

@pytest.mark.parametrize("raw, canon", [
    ("lab--2", "lab-2"), ("lab-", "lab"), ("-lab", "lab"), ("lab.2", "lab-2"),
])
def test_command_line_site_is_canonicalised_like_the_importer(raw, canon):
    p = subprocess.run(["make", "-n", "import", "EXCEL=/nonexistent/x.xlsx", f"SITE={raw}"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert f'--site "{canon}"' in p.stdout
    assert f"SITE '{raw}' is stored on disk as '{canon}'" in p.stderr


def test_generate_and_import_agree_on_the_site_directory():
    p = subprocess.run(["make", "-n", "generate", "ARCH=2-4-3-200", "SITE=lab--2"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert "input/2-4-3-200/lab-2/" in p.stdout
    assert "lab--2" not in p.stdout


def test_canonical_site_needs_no_warning_and_no_rewrite():
    p = subprocess.run(["make", "-n", "import", "EXCEL=/nonexistent/x.xlsx", "SITE=Lab-2"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert '--site "Lab-2"' in p.stdout
    assert "stored on disk as" not in p.stderr


def test_makefile_and_importer_share_one_site_rule():
    sys_path = str(REPO / "scripts")
    p = subprocess.run(["python3", "-c",
                        f"import sys; sys.path.insert(0, {sys_path!r}); "
                        "import _site_name; print(_site_name.safe_site_name('a..b--c-'))"],
                       capture_output=True, text=True)
    assert p.stdout.strip() == "a-b-c"
    src = (REPO / "scripts" / "import-excel.py").read_text()
    assert "from _site_name import safe_site_name" in src
    assert "_INVALID_SITE_CHARS = re.compile" not in src
