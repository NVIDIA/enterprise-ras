# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Tests for the STORAGE-VRF non-gating WARN reclassification in the `bgp` check of
scripts/switch_health_probe.sh (design C2).

The probe is a streamed bash script with an inline python `bgp` classifier, so
we extract that exact heredoc and run it against captured `show bgp vrf all
summary json` fixtures — this tests the SHIPPED code, no drift.

C2: a down peer whose VRF is STORAGE must be a non-gating WARN (emit a separate
`CHECK|bgp_storage|WARN|...`), NOT counted in the `bgp` FAIL list. Every other
VRF keeps today's behavior (a down numbered / link-up peer still FAILs `bgp`).
"""
import subprocess
import textwrap
from pathlib import Path

import pytest

_PROBE = Path(__file__).resolve().parent.parent / "scripts" / "switch_health_probe.sh"


def _extract_bgp_python() -> str:
    """Pull the `python3 - <<'PY' ... PY` block that contains the bgp classifier
    (identified by `_link_up`) out of the probe script."""
    text = _PROBE.read_text()
    blocks = text.split("<<'PY'")
    for chunk in blocks[1:]:
        body = chunk.split("\nPY", 1)[0]
        if "_link_up" in body:
            return body.lstrip("\n")
    raise AssertionError("bgp python block not found in switch_health_probe.sh")


def _run(fixture_json: str, tmp_path) -> str:
    """Run the extracted bgp classifier with the fixture at its /tmp path."""
    Path("/tmp/_sh_bgp.json").write_text(fixture_json)
    script = tmp_path / "bgp_block.py"
    script.write_text(_extract_bgp_python())
    p = subprocess.run(["python3", str(script)], capture_output=True, text=True, timeout=30)
    return (p.stdout + p.stderr).strip()


# A STORAGE-VRF eBGP peer down (the ext-storage-FRR-down signature) plus a
# healthy default-VRF peer.
STORAGE_DOWN = """
{
  "default": {"ipv4Unicast": {"peers": {"10.0.0.2": {"state": "Established"}}}},
  "STORAGE": {"ipv4Unicast": {"peers": {"swp63s0": {"state": "Idle"}}}}
}
"""

# A non-STORAGE numbered peer down — must still FAIL bgp (regression guard).
DEFAULT_DOWN = """
{
  "default": {"l2VpnEvpn": {"peers": {"10.0.0.9": {"state": "Active"}}}}
}
"""

# Both: STORAGE down (WARN) + non-STORAGE down (FAIL) together.
BOTH_DOWN = """
{
  "default": {"l2VpnEvpn": {"peers": {"10.0.0.9": {"state": "Active"}}}},
  "STORAGE": {"ipv4Unicast": {"peers": {"swp63s0": {"state": "Idle"}}}}
}
"""


def test_storage_down_is_warn_not_fail(tmp_path):
    out = _run(STORAGE_DOWN, tmp_path)
    # STORAGE peer surfaced as a non-gating WARN pointing at the fix
    assert "CHECK|bgp_storage|WARN|" in out
    assert "fix-ext-storage" in out
    # ...and did NOT fail the gating bgp check (the default peer is up)
    assert "CHECK|bgp|PASS|" in out
    assert "CHECK|bgp|FAIL|" not in out


def test_non_storage_numbered_down_still_fails(tmp_path):
    out = _run(DEFAULT_DOWN, tmp_path)
    assert "CHECK|bgp|FAIL|" in out
    assert "10.0.0.9=Active" in out


def test_storage_warn_does_not_mask_other_fail(tmp_path):
    out = _run(BOTH_DOWN, tmp_path)
    assert "CHECK|bgp|FAIL|" in out            # the default peer still fails
    assert "10.0.0.9=Active" in out
    assert "CHECK|bgp_storage|WARN|" in out    # storage still warned separately
    # the storage peer must NOT appear in the gating bgp FAIL down-list
    bgp_fail_line = next(l for l in out.splitlines() if l.startswith("CHECK|bgp|FAIL|"))
    assert "swp63s0" not in bgp_fail_line
