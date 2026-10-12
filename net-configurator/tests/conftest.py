# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Pytest configuration and fixtures for ERA switch configuration tests.
"""
import os
import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def sample_nvue_cli_config():
    """Return a sample NVUE CLI configuration."""
    return """#!/bin/bash
# Sample NVUE CLI configuration

nv set system hostname test-switch
nv set system timezone Etc/Zulu
nv set interface lo ip address 10.10.10.1/32
nv set interface lo type loopback
nv set interface swp1 link state up
nv set interface swp1 type swp
nv set bridge domain br_default vlan 100
nv set bridge domain br_default vlan 200
nv config apply -y
"""


@pytest.fixture
def core_cli_template(project_root):
    """Return path to core switch CLI template."""
    return project_root / "roles" / "core" / "templates" / "core_nvue_cli.j2"


@pytest.fixture
def oob_cli_template(project_root):
    """Return path to OOB switch CLI template."""
    return project_root / "roles" / "oob-switch" / "templates" / "oob_nvue_cli.j2"


@pytest.fixture
def ztp_sh_template(project_root):
    """Return path to the ZTP bootstrap shell-script template."""
    return project_root / "roles" / "ztp-server" / "templates" / "ztp.sh.j2"


# --- legacy vs intake-form workbook discovery ------------------------------

# `make convert-workbook` writes `<name>.intake.xlsx` NEXT TO its source, so
# an intake-form workbook can legitimately appear anywhere under `input/`.
# Every glob in this suite that means "a shipped legacy workbook" must skip
# those, or a user who converts one of their own workbooks breaks their own
# test run -- the tests would hand an intake workbook to a legacy-only code
# path. Route such globs through here rather than re-deriving the rule.
INTAKE_SUFFIX = ".intake.xlsx"


def is_intake_workbook(path):
    """True for a converted intake-form workbook (ADR-0064)."""
    return str(path).endswith(INTAKE_SUFFIX)


def legacy_workbooks(paths):
    """Filter a workbook iterable down to legacy-format workbooks."""
    return [p for p in paths if not is_intake_workbook(p)]


# --- the frozen legacy sample ----------------------------------------------

# `convert_workbook` goes legacy -> intake, and the shipped workbooks became
# the intake form (ADR-0064), so there is no longer a legacy workbook in the
# tree to feed it. This is the last shipped legacy 2-8-9-800 default, kept
# verbatim -- formatting, data validations and all, because the converter is
# asserted to preserve them.
#
# It is frozen rather than generated, and it cannot drift: nothing emits the
# legacy format any more, so there is no source for it to fall behind. That is
# what makes it unlike the per-arch seed workbooks, which had a generator
# behind them and diverged from it silently. It retires with the converter at
# nc-v10 (ADR-0064 D2).
LEGACY_SAMPLE = Path(__file__).parent / "fixtures" / "legacy-2-8-9-800.xlsx"
LEGACY_SAMPLE_ARCH = "2-8-9-800"


# ---------------------------------------------------------------------------
# internal_only: tests of material that never ships (ADR-0027 boundary)
# ---------------------------------------------------------------------------
#
# `@pytest.mark.internal_only("data-models/models", ...)` names monorepo paths
# (relative to the monorepo root, outside net-configurator/) that a test reads.
# Outside the monorepo -- the public tree, wherever it is built or unpacked --
# the test is DESELECTED, not skipped: it tests something that is not part of the public artifact. In the
# monorepo every named path must exist and lie outside the public folder, so a
# typo or a public path cannot quietly drop a test anywhere.
#
# ERA_NO_SKIP=1 (the public-artifact gate) turns every remaining skip into a
# failure: a skip there means a missing build, dependency or fixture.

TOOL_ROOT = Path(__file__).resolve().parent.parent
MONOREPO_ROOT = TOOL_ROOT.parent
# Recognised by the monorepo's own layout, never by what sits beside the tree:
# an artifact built inside a checkout must not borrow the checkout's siblings.
IN_MONOREPO = (TOOL_ROOT.name == "net-configurator"
               and (MONOREPO_ROOT / "release" / "build-public-tree.sh").is_file())


def _internal_paths(item):
    marker = item.get_closest_marker("internal_only")
    if marker is None:
        return None
    if not marker.args:
        raise pytest.UsageError(f"{item.nodeid}: internal_only needs at least one path")
    paths = [MONOREPO_ROOT / p for p in marker.args]
    for p in paths:
        if p.resolve().is_relative_to(TOOL_ROOT):
            raise pytest.UsageError(
                f"{item.nodeid}: internal_only path {p} is inside the public tool root")
    return paths


def pytest_collection_modifyitems(config, items):
    keep, internal = [], []
    for item in items:
        paths = _internal_paths(item)
        if paths is None:
            keep.append(item)
        elif IN_MONOREPO:
            missing = [str(p.relative_to(MONOREPO_ROOT)) for p in paths if not p.exists()]
            if missing:
                raise pytest.UsageError(
                    f"{item.nodeid}: internal_only path(s) {missing} do not exist in the monorepo")
            keep.append(item)
        else:
            internal.append(item)
    if internal:
        config.hook.pytest_deselected(items=internal)
        items[:] = keep
    config.stash[_INTERNAL_KEY] = len(internal)


_INTERNAL_KEY = pytest.StashKey[int]()


def _no_skip():
    return os.environ.get("ERA_NO_SKIP") == "1"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if _no_skip() and report.skipped and not hasattr(report, "wasxfail"):
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        report.outcome = "failed"
        report.longrepr = f"ERA_NO_SKIP=1: skips are failures in the public-artifact gate ({reason})"


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    n = config.stash.get(_INTERNAL_KEY, 0)
    if n:
        terminalreporter.write_line(
            f"internal_only: {n} test(s) deselected -- they test internal monorepo "
            f"material that is not part of this tree")


def pytest_sessionfinish(session, exitstatus):
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if _no_skip() and reporter is not None and reporter.stats.get("skipped"):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
