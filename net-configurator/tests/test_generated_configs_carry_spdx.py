# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Generated NVUE config scripts must carry the SPDX header as real shell comments.

The templates' own `{# #}` SPDX header is stripped at render, so every
`*_nvue_cli.j2` also emits the two lines as `#` comments directly under the
shebang, and every committed `output/**/*.sh` starts the same way
(GitLab #68 / ERA-102). Order matters: `release/stamp-spdx-headers.sh` puts
the header on lines 2-3 of a shebang file, and a regenerated config must
match it byte-for-byte so re-stamping is a no-op.
"""
from pathlib import Path

import pytest
from jinja2 import Environment, nodes

REPO = Path(__file__).resolve().parents[1]
# REUSE-IgnoreStart
SPDX_LINES = [
    "# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.",
    "# SPDX-License-Identifier: MIT",
]
# REUSE-IgnoreEnd

TEMPLATES = sorted(REPO.glob("roles/*/templates/*_nvue_cli.j2"))
CONFIGS = sorted(REPO.glob("output/*/*/configs/*.sh"))


def _first_lines(path: Path, n: int = 3):
    """First `n` lines; short/empty files just return fewer lines."""
    with path.open(encoding="utf-8") as fh:
        return [line.rstrip("\n") for line, _ in zip(fh, range(n))]


def _rendered_head(tpl: Path, n: int = 3):
    """First `n` lines of literal text the template emits, from the Jinja AST.

    Top-level `{# #}` comments, macro definitions and `{% set %}` render
    nothing, so they are skipped; the first `Output` node's leading literal
    text is what a rendered config starts with (leading blank lines are
    trimmed as Ansible's templar does).
    """
    env = Environment(extensions=["jinja2.ext.do"], trim_blocks=True)
    text = ""
    for node in env.parse(tpl.read_text(encoding="utf-8")).body:
        if isinstance(node, (nodes.Macro, nodes.Assign, nodes.AssignBlock)):
            continue
        if not isinstance(node, nodes.Output):
            break
        for child in node.nodes:
            if not isinstance(child, nodes.TemplateData):
                return text.lstrip("\n").splitlines()[:n]
            text += child.data
        if text.strip():
            break
    return text.lstrip("\n").splitlines()[:n]


def test_template_inventory_is_what_we_expect():
    assert len(TEMPLATES) == 4, [t.name for t in TEMPLATES]
    assert CONFIGS, "no committed configs found under output/*/*/configs"


@pytest.mark.parametrize("tpl", TEMPLATES, ids=lambda p: p.parent.parent.name)
def test_template_emits_spdx_as_shell_comments_under_shebang(tpl):
    lines = tpl.read_text(encoding="utf-8").splitlines()
    assert lines.count("#!/bin/bash") == 1, tpl
    assert _rendered_head(tpl) == ["#!/bin/bash", *SPDX_LINES], (
        f"{tpl}: the first rendered line must be the shebang, followed by the "
        f"SPDX header as real '#' lines, not only inside a {{# #}} Jinja "
        f"comment; got {_rendered_head(tpl)}")


def test_every_committed_config_starts_with_shebang_and_spdx():
    bad = [str(c.relative_to(REPO)) for c in CONFIGS
           if _first_lines(c) != ["#!/bin/bash", *SPDX_LINES]]
    assert not bad, f"{len(bad)} of {len(CONFIGS)} configs lack the header: {bad[:10]}"


def test_no_committed_config_has_a_duplicate_header():
    dup = [str(c.relative_to(REPO)) for c in CONFIGS
           if c.read_text(encoding="utf-8").count(SPDX_LINES[1]) != 1]
    assert not dup, dup[:10]
