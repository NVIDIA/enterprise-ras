# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""The public-artifact gate's two switches, exercised in a throwaway layout.

`internal_only` deselects tests of internal monorepo material where it is
absent, and refuses a marker that could hide a public test. `ERA_NO_SKIP=1`
turns every remaining skip into a failure. Both live in tests/conftest.py; a
copy of it runs here against a scratch tool root so the real suite is untouched.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CONFTEST = Path(__file__).resolve().parent / "conftest.py"

INI = """[pytest]
addopts = --strict-markers -p no:cacheprovider
markers =
    internal_only(*paths): internal monorepo paths
"""

TESTS = '''
import pytest

@pytest.mark.internal_only("data-models/models")
def test_needs_models():
    pass

def test_public():
    pass
'''

SKIPPING = '''
import pytest

def test_skips():
    pytest.skip("fixture absent")
'''


def _layout(tmp_path, body, monorepo=False, models=False, name="net-configurator"):
    tool = tmp_path / name
    (tool / "tests").mkdir(parents=True)
    shutil.copy(CONFTEST, tool / "tests" / "conftest.py")
    (tool / "pytest.ini").write_text(INI)
    (tool / "tests" / "test_sample.py").write_text(body)
    if monorepo:
        (tmp_path / "release").mkdir()
        (tmp_path / "release" / "build-public-tree.sh").write_text("")
    if models:
        (tmp_path / "data-models" / "models").mkdir(parents=True)
    return tool


def _pytest(tool, **env):
    full = {k: v for k, v in os.environ.items() if k != "ERA_NO_SKIP"}
    full.update(env)
    return subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-rs"],
                          cwd=tool, capture_output=True, text=True, env=full)


def test_public_tree_deselects_internal_tests(tmp_path):
    r = _pytest(_layout(tmp_path, TESTS))
    assert r.returncode == 0, r.stdout
    assert "1 passed, 1 deselected" in r.stdout
    assert "internal_only: 1 test(s) deselected" in r.stdout


def test_monorepo_runs_internal_tests(tmp_path):
    r = _pytest(_layout(tmp_path, TESTS, monorepo=True, models=True))
    assert r.returncode == 0, r.stdout
    assert "2 passed" in r.stdout and "deselected" not in r.stdout


def test_artifact_built_inside_a_checkout_does_not_borrow_it(tmp_path):
    tool = _layout(tmp_path, TESTS, monorepo=True, models=True, name=".public-artifact")
    r = _pytest(tool)
    assert r.returncode == 0, r.stdout
    assert "1 passed, 1 deselected" in r.stdout


def test_monorepo_refuses_a_marker_naming_a_missing_path(tmp_path):
    r = _pytest(_layout(tmp_path, TESTS, monorepo=True))
    assert r.returncode == pytest.ExitCode.USAGE_ERROR, r.stdout + r.stderr
    assert "do not exist in the monorepo" in r.stderr


def test_marker_may_not_name_a_public_path(tmp_path):
    body = TESTS.replace('"data-models/models"', '"net-configurator/scripts"')
    r = _pytest(_layout(tmp_path, body))
    assert r.returncode == pytest.ExitCode.USAGE_ERROR, r.stdout + r.stderr
    assert "inside the public tool root" in r.stderr


def test_marker_needs_a_path(tmp_path):
    body = TESTS.replace('("data-models/models")', '()')
    r = _pytest(_layout(tmp_path, body))
    assert r.returncode == pytest.ExitCode.USAGE_ERROR, r.stdout + r.stderr
    assert "needs at least one path" in r.stderr


def test_skip_is_allowed_by_default(tmp_path):
    r = _pytest(_layout(tmp_path, SKIPPING))
    assert r.returncode == 0, r.stdout
    assert "1 skipped" in r.stdout


def test_no_skip_mode_fails_every_skip(tmp_path):
    r = _pytest(_layout(tmp_path, SKIPPING), ERA_NO_SKIP="1")
    assert r.returncode == pytest.ExitCode.TESTS_FAILED, r.stdout
    assert "1 failed" in r.stdout
    assert "ERA_NO_SKIP=1" in r.stdout and "fixture absent" in r.stdout


def test_no_skip_mode_fails_an_empty_parametrize(tmp_path):
    body = '''
import pytest

@pytest.mark.parametrize("x", [])
def test_vacuous(x):
    pass
'''
    r = _pytest(_layout(tmp_path, body), ERA_NO_SKIP="1")
    assert r.returncode == pytest.ExitCode.TESTS_FAILED, r.stdout


def test_no_skip_mode_fails_a_module_level_skip(tmp_path):
    body = '''
import pytest

pytest.skip("whole module", allow_module_level=True)

def test_never():
    pass
'''
    r = _pytest(_layout(tmp_path, body), ERA_NO_SKIP="1")
    assert r.returncode == pytest.ExitCode.TESTS_FAILED, r.stdout
