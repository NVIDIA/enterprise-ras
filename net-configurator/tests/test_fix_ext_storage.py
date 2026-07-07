# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Unit tests for scripts/fix-ext-storage-frr.py — the per-node remediation shell
builder (design C3). The SSH-via-jump orchestration is thin glue verified live;
the drift-critical part is that the remediation carries the SAME FRR config the
shared builder produces, so we test that seam.
"""
import base64
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_FIX = _ROOT / "scripts" / "fix-ext-storage-frr.py"
spec = importlib.util.spec_from_file_location("fix_ext_storage_frr", _FIX)
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)

import sys
sys.path.insert(0, str(_ROOT / "scripts"))
from airlib.ext_storage_config import build_frr_conf, build_daemons

TARGET = {
    "idx": 0,
    "node_name": "ext-storage-01",
    "peer_ifaces": ["eth1", "eth2"],
    "lo_ip": "10.187.5.1",
    "eth0_ip": "172.20.0.79",
}


def test_remediation_embeds_builder_frr_conf_verbatim():
    """The frr.conf the fix script writes must be byte-identical to the shared
    builder's output (so the fix path and air-deploy can't drift)."""
    script = fix.build_node_remediation(TARGET)
    expected_b64 = base64.b64encode(
        build_frr_conf("ext-storage-01", "10.187.5.1", ["eth1", "eth2"]).encode()
    ).decode()
    assert expected_b64 in script
    daemons_b64 = base64.b64encode(build_daemons().encode()).decode()
    assert daemons_b64 in script


def test_remediation_is_idempotent_skip_when_healthy():
    """A healthy node (frr active + config present) must be a no-op skip."""
    script = fix.build_node_remediation(TARGET)
    assert "systemctl is-active --quiet frr" in script
    assert "/etc/frr/frr.conf" in script
    # emits an OK/skip marker without reinstalling
    assert "OK" in script


def test_remediation_gates_on_dns_then_installs():
    """Missing FRR path: gate on outbound DNS, then apt-get install frr."""
    script = fix.build_node_remediation(TARGET)
    assert "getent hosts archive.ubuntu.com" in script
    assert "apt-get install -y" in script and "frr" in script
    assert "systemctl enable frr" in script
    assert "systemctl restart frr" in script


def test_remediation_reports_fail_if_still_down():
    """If frr is still inactive after the attempt, the script must signal FAIL
    (non-zero) so the orchestrator can report the node as unfixed."""
    script = fix.build_node_remediation(TARGET)
    assert "FAIL" in script
    assert "exit 1" in script
