# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Unit tests for scripts/oob_bgp_classify.py (design C1).

The OOB↔CSL BGP gate is deliberately STRICTER than switch_health_probe.sh: on
an OOB switch in L3 mode every BGP neighbor is a required CSL-facing uplink, so
there is NO carrier-down suppression — a down `swpN` peer is always a FAIL.
That suppression is exactly what let switch-health false-pass the live-troubleshooting
copper-uplink miscable, so this classifier must not have it.
"""
import importlib.util
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "scripts" / "oob_bgp_classify.py"
spec = importlib.util.spec_from_file_location("oob_bgp_classify", _MOD)
obc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(obc)


def _summary(peers_by_vrf_af):
    """Build a `show bgp vrf all summary json`-shaped dict."""
    out = {}
    for (vrf, af), peers in peers_by_vrf_af.items():
        out.setdefault(vrf, {})[af] = {"peers": {n: {"state": s} for n, s in peers.items()}}
    return out


def test_all_established_passes():
    data = _summary({
        ("default", "ipv4Unicast"): {"swp49": "Established", "swp51": "Established"},
        ("default", "l2VpnEvpn"): {"172.16.176.11": "Established", "172.16.176.12": "Established"},
    })
    fail, line = obc.classify(data)
    assert fail is False
    assert line == "OOB_BGP|PASS|neighbors=4 established=4"


def test_down_swp_uplink_is_fail_no_carrier_suppression():
    """The key property: a down unnumbered swp peer is a FAIL here (unlike
    switch-health, which would suppress it if the carrier is down)."""
    data = _summary({
        ("default", "ipv4Unicast"): {"swp49": "Idle", "swp51": "Established"},
        ("default", "l2VpnEvpn"): {"172.16.176.11": "Established", "172.16.176.12": "Established"},
    })
    fail, line = obc.classify(data)
    assert fail is True
    assert line.startswith("OOB_BGP|FAIL|established=3/4 down=")
    assert "default/ipv4Unicast/swp49=Idle" in line


def test_noneg_af_is_skipped_not_counted():
    """A peer whose address-family was not negotiated (NoNeg) is not a down
    session and must not count toward the total or fail the check."""
    data = _summary({
        ("default", "ipv4Unicast"): {"swp49": "Established"},
        ("default", "l2VpnEvpn"): {"swp49": "NoNeg", "172.16.176.11": "Established"},
    })
    fail, line = obc.classify(data)
    assert fail is False
    assert line == "OOB_BGP|PASS|neighbors=2 established=2"


def test_no_neighbors_is_fail():
    fail, line = obc.classify({})
    assert fail is True
    assert line == "OOB_BGP|FAIL|no BGP neighbors found"


def test_numbered_overlay_down_is_fail():
    data = _summary({
        ("default", "ipv4Unicast"): {"swp49": "Established", "swp51": "Established"},
        ("default", "l2VpnEvpn"): {"172.16.176.11": "Active", "172.16.176.12": "Established"},
    })
    fail, line = obc.classify(data)
    assert fail is True
    assert "default/l2VpnEvpn/172.16.176.11=Active" in line
