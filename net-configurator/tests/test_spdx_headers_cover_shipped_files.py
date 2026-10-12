# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Every shipped file carries licensing information (GitLab #96 / H8).

The REUSE Specification 3.3 rule, checked without the `reuse` tool: a
tracked file either carries `SPDX-FileCopyrightText` and
`SPDX-License-Identifier` itself, or a `REUSE.toml` annotation covers it,
and every license named has its text under `LICENSES/`. CI also runs
`reuse lint` on the built public tree; this test is the guard a contributor
hits first, for every file type rather than the `*.sh` that
`release/stamp-spdx-headers.sh` stamps.
"""
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HEAD_BYTES = 4000
# REUSE-IgnoreStart
COPYRIGHT = "SPDX-FileCopyrightText:"
LICENSE = "SPDX-License-Identifier:"
# REUSE-IgnoreEnd
# REUSE 3.3 exempts license texts themselves.
EXEMPT = re.compile(r"^(LICENSE|LICENSES/.+)$")


def _tracked():
    proc = subprocess.run(["git", "ls-files", "-z", "--", "."], cwd=REPO,
                          capture_output=True)
    assert proc.returncode == 0, (
        "net-configurator must be a git checkout (the release gate commits "
        f"the public tree before testing it): {proc.stderr.decode()}")
    return sorted(p for p in proc.stdout.decode().split("\0") if p)


def _glob_to_re(pattern):
    """REUSE.toml glob: `**` crosses directories, `*` does not."""
    out = ""
    for token in re.split(r"(\*\*|\*)", pattern):
        out += {"**": ".*", "*": "[^/]*"}.get(token, re.escape(token))
    return re.compile(f"^{out}$")


def _annotations():
    data = tomllib.loads((REPO / "REUSE.toml").read_text(encoding="utf-8"))
    assert data.get("version") == 1
    return [([_glob_to_re(p) for p in ann["path"]], ann)
            for ann in data["annotations"]]


def _annotated(path, annotations):
    return any(rx.match(path) for rxs, _ in annotations for rx in rxs)


def test_reuse_toml_and_license_texts_exist():
    assert (REPO / "REUSE.toml").is_file()
    assert (REPO / "LICENSES" / "MIT.txt").read_text() == (REPO / "LICENSE").read_text()
    for _, ann in _annotations():
        assert ann["SPDX-License-Identifier"] == "MIT", ann
        assert "NVIDIA CORPORATION" in ann["SPDX-FileCopyrightText"], ann


def test_generated_output_and_workbooks_are_annotated():
    """The two big groups that cannot carry their own header (#96)."""
    annotations = _annotations()
    for path in ("output/2-8-9-800/default/inventory/host_vars/leaf-su01-r1.yml",
                 "output/2-8-9-800/default/generated-manifest.json",
                 "input/2-8-9-800/default/2-8-9-800.xlsx",
                 "input/sample-2-8-9-800.xlsx",
                 "tests/fixtures/legacy-2-8-9-800.xlsx"):
        assert _annotated(path, annotations), path
    assert not _annotated("scripts/excel_parser.py", annotations)


def test_every_shipped_file_has_licensing_information():
    annotations = _annotations()
    files = _tracked()
    assert len(files) > 1000, "git ls-files found too few files to be the tree"
    missing = []
    for rel in files:
        if EXEMPT.match(rel) or _annotated(rel, annotations):
            continue
        head = (REPO / rel).read_bytes()[:HEAD_BYTES].decode("utf-8", "replace")
        if COPYRIGHT not in head or LICENSE not in head:
            missing.append(rel)
    assert not missing, (
        "add the two-line SPDX header (AGENTS.md 'Licensing Requirements'), "
        "or a REUSE.toml annotation if the format cannot carry a comment:\n  "
        + "\n  ".join(missing))


def test_annotation_globs_are_not_dead():
    """An annotation that matches nothing hides a typo, not a file."""
    files = _tracked()
    for rxs, ann in _annotations():
        for rx in rxs:
            assert any(rx.match(f) for f in files), (rx.pattern, ann["path"])


@pytest.mark.parametrize("pattern, path, hit", [
    ("output/**", "output/a/b/c.yml", True),
    ("input/**.xlsx", "input/sample.xlsx", True),
    ("input/**.xlsx", "input/a/b/c.xlsx", True),
    ("NOTICE", "docs/NOTICE", False),
    ("input/*.xlsx", "input/a/b.xlsx", False),
])
def test_glob_semantics(pattern, path, hit):
    assert bool(_glob_to_re(pattern).match(path)) is hit
