# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Keep public coverage and sizing claims consistent with retained Air evidence."""
import json
import re
import shlex
import subprocess
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
pytestmark = pytest.mark.internal_only(
    'internal-docs/validation-evidence/2026-10-09-fullscale-air-closeout',
)
EVIDENCE = REPO / 'internal-docs/validation-evidence/2026-10-09-fullscale-air-closeout/results.json'
ARCHS = sorted(p.name for p in (ROOT / 'input').iterdir() if (p / 'default').is_dir())


def table_rows(text):
    return [[c.strip() for c in line.strip().strip('|').split('|')]
            for line in text.splitlines() if line.startswith('|')]


@pytest.mark.parametrize('arch', ARCHS)
def test_documented_resources_match_topologies_and_air(arch):
    text = (ROOT / 'docs/ARCH_SUPPORT_MATRIX.md').read_text().split('## Resource sizing', 1)[1]
    row = next(r for r in table_rows(text) if r[0] == f'`{arch}`')
    cells = json.loads(EVIDENCE.read_text())['cells']
    for index, site in enumerate(('default', 'largescale'), 1):
        topology = json.loads((ROOT / f'output/{arch}/{site}/topology/{arch}-topology.json').read_text())
        nodes = topology['content']['nodes']
        expected = (len(nodes), sum(n['cpu'] for n in nodes.values()),
                    sum(n['memory'] for n in nodes.values()) // 1024)
        assert tuple(map(int, re.findall(r'\d+', row[index]))) == expected
        assert 'GiB' in row[index]
        cell = next(c for c in cells if (c['arch'], c['scale'], c['mode']) == (arch, site, 'noztp'))
        assert (cell['nodes'], cell['resources']['cpu'], cell['resources']['memory'] // 1024) == expected


@pytest.mark.parametrize('arch', ARCHS)
def test_role_chart_matches_both_shipped_scales(arch):
    text = (ROOT / 'docs/ROLES.md').read_text().split('### Switch fabric roles', 1)[1]
    rows = table_rows(text.split('### OOB / management roles', 1)[0])
    column = rows[0].index(f'`{arch}`')
    roles = {}
    for site in ('default', 'largescale'):
        wb = openpyxl.load_workbook(ROOT / f'input/{arch}/{site}/{arch}.xlsx', read_only=True)
        data = list(wb['Switch Data'].values)
        header = next(r for r in data if 'Function' in r)
        index = header.index('Function')
        roles[site] = {r[index] for r in data[data.index(header) + 1:] if r[index]}
        wb.close()
    for row in rows[2:]:
        names = set(row[0].strip('`').split(' / '))
        expected = '/'.join(label for site, label in [('default', 'D'), ('largescale', 'L')]
                            if names <= roles[site]) or '—'
        assert row[column] == expected, (arch, row[0])


def test_air_modes_and_rail_coverage_match_passed_campaign():
    data = json.loads(EVIDENCE.read_text())
    assert len(data['cells']) == data['passed'] == 48
    assert all(c['status'] == 'passed' for c in data['cells'])
    text = (ROOT / 'docs/ARCH_SUPPORT_MATRIX.md').read_text()
    rows = table_rows(text)
    for name in ('Air deploy — NOZTP', 'Air deploy — ZTP', 'Switches-only deploy'):
        row = next(r for r in rows if r[0].startswith(name))
        assert row[1:] == ['✅'] * 7
    row = next(r for r in rows if r[0].startswith('Shipped GPU VLAN mode'))
    assert row[1:] == ['✅ per_rail'] * 4 + ['✅ per_rail_per_plane'] * 2 + ['✅ per_rail']


@pytest.mark.parametrize('relative', [
    'README.md', 'docs/ARCH_SUPPORT_MATRIX.md',
    'docs/NVUE_VERSION_COMPAT.md', 'docs/AIR_DEPLOYMENT_GUIDE.md',
])
def test_docs_do_not_repeat_superseded_air_coverage(relative):
    text = (ROOT / relative).read_text()
    assert 'not yet deployed' not in text
    assert 'has not yet been run on\n5.18.3' not in text


def test_role_enforcement_table_includes_every_architecture(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    from validate_excel import ROLE_ENFORCEMENT
    text = (ROOT / 'docs/ROLES.md').read_text().split('### Per-arch validation enforcement', 1)[1]
    rows = table_rows(text.split('### Default-IP', 1)[0])
    for arch in ARCHS:
        row = next(r for r in rows if r[0] == f'`{arch}`')
        assert ROLE_ENFORCEMENT.get(arch, 'warn') in row[1]


@pytest.mark.internal_only('release/README.md', 'Makefile.internal')
def test_documented_audit_command_has_a_report_directory():
    text = (REPO / 'release/README.md').read_text()
    commands = [line for line in text.splitlines()
                if line.startswith('make ') and 'audit-configs ARCH=' in line]
    assert commands, 'No executable audit example found'
    for command in commands:
        result = subprocess.run(['make', '-n', *shlex.split(command)[1:]],
                                cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        lines = result.stdout.splitlines()
        mkdir = next(shlex.split(line) for line in lines if line.startswith('mkdir -p'))
        assert len(mkdir) == 3, result.stdout
        audit = next(shlex.split(line) for line in lines if '--report-dir' in line)
        assert audit[audit.index('--report-dir') + 1] == mkdir[2]
