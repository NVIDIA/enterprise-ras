# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Tests for issue #32 — keep secrets out of ZTP-server logs and the status page.

  * Surface 1 — roles/ztp-server/templates/ztp.sh.j2 runs with global `set -x`
    and `source`s the generated switch config (which contains LDAP secrets,
    the cumulus password, hashed-password lines). The source MUST be wrapped in
    `set +x` ... `set -x` so bash does not xtrace those lines into
    /var/log/autoprovision. The existing password-command scoping must remain.

  * Surface 2 — playbooks/upload-reports.yml must NOT publish the per-host
    raw/ files (full generated + running configs) to the nginx status page.
    Only the no-secret summary reports may be uploaded.
"""
import re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ZTP_TEMPLATE_DIR = PROJECT_ROOT / "roles" / "ztp-server" / "templates"
UPLOAD_REPORTS = PROJECT_ROOT / "playbooks" / "upload-reports.yml"


def _render_ztp():
    env = Environment(loader=FileSystemLoader(str(ZTP_TEMPLATE_DIR)))
    env.filters["quote"] = lambda s: "'%s'" % str(s).replace("'", "'\\''")
    return env.get_template("ztp.sh.j2").render()


# ---------------------------------------------------------------------------
# Surface 1 — ztp.sh.j2 set -x scoping
# ---------------------------------------------------------------------------

def test_config_source_is_wrapped_in_set_plus_x():
    """`source ...config.sh` must run with xtrace OFF (a preceding `set +x`
    with no intervening `set -x`)."""
    lines = _render_ztp().splitlines()
    src_idx = [i for i, ln in enumerate(lines)
               if re.search(r"source\s+/tmp/\$\{hostname\}-config\.sh", ln)]
    assert len(src_idx) == 1, f"expected exactly one config source, got {src_idx}"
    i = src_idx[0]
    # Walk backwards to the nearest xtrace toggle — it must be `set +x`.
    for ln in reversed(lines[:i]):
        s = ln.strip()
        if s == "set +x":
            break
        if s == "set -x":
            raise AssertionError("config source runs with xtrace ON (set -x)")
    else:
        raise AssertionError("no `set +x` found before the config source")


def test_set_x_reenabled_after_source_in_both_branches():
    """xtrace is restored after the source (so the rest of ZTP still traces)."""
    text = _render_ztp()
    # The source sits inside an if/else; both arms must re-enable set -x.
    block = text[text.index("source /tmp/${hostname}-config.sh"):]
    block = block[:block.index("function ping_until_reachable")] \
        if "function ping_until_reachable" in block else block
    assert block.count("set -x") >= 2, "set -x not re-enabled in both branches"


def test_password_commands_still_scoped():
    """Regression: the pre-existing password/chpasswd scoping must survive."""
    lines = _render_ztp().splitlines()
    for needle in ("nv set system aaa user", "| chpasswd"):
        idx = [i for i, ln in enumerate(lines) if needle in ln]
        assert idx, f"missing expected command containing {needle!r}"
        for i in idx:
            prev = [ln.strip() for ln in lines[max(0, i - 3):i]]
            assert "set +x" in prev, f"{needle!r} not preceded by set +x"


def test_config_load_log_not_catted_to_journal():
    """The failure path must not `cat` config-load.log back into the journal
    (it can contain a failed secret-bearing command)."""
    text = _render_ztp()
    assert "cat /tmp/config-load.log" not in text


# ---------------------------------------------------------------------------
# Surface 2 — upload-reports.yml
# ---------------------------------------------------------------------------

def test_upload_reports_does_not_publish_raw():
    doc = yaml.safe_load(UPLOAD_REPORTS.read_text())
    tasks = doc[0]["tasks"]
    blob = yaml.safe_dump(tasks)
    assert "/raw/" not in blob, "upload-reports still references a raw/ path"
    assert "reports_dir }}/raw" not in blob
    # The destination dir must not pre-create reports/raw either.
    assert "/var/www/ztp/reports/raw" not in blob


def test_upload_reports_still_uploads_summary():
    doc = yaml.safe_load(UPLOAD_REPORTS.read_text())
    blob = yaml.safe_dump(doc)
    assert "{{ reports_dir }}/*" in blob, "summary upload task was lost"
