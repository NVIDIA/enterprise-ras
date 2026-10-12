# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
ERA-66 / ADR-0045: BGP graceful restart on every BGP-speaking role, and
multipath (aspath-ignore + 128 eBGP paths) on every service VRF.

Two layers:

* every committed `output/<arch>/<site>/configs/*-config.sh` (all seven
  shipped arches, both shipped sites `default` and `largescale`, every role)
  carries the expected lines exactly once;
* the OOB template, which is the only role that can render without BGP
  (L2 uplink mode), emits graceful restart only when BGP exists.
"""
import re
import shlex
import sys
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from _valid_archs import VALID_ARCHS  # noqa: E402

# Roles whose committed configs carried `route-map WEIGHTED_ECMP` before ERA-66
# (core/csl/cl, cs spine, gl-plane, oob). gs-/gsl- never had it; ERA-66 must not
# change either set (verified against every default + largescale snapshot on main).
WECMP_PREFIXES = ("core", "csl", "cl-", "cs-", "gl-", "oob", "rack-oob")

GR_LINES = (
    "nv set router bgp graceful-restart mode full",
    "nv set router bgp graceful-restart restart-time 180",
    "nv set router bgp graceful-restart path-selection-deferral-time 180",
    "nv set router bgp graceful-restart stale-routes-time 180",
)

# Default-VRF 128-path multipath is emitted only where production captures
# carry it (core/csl and cs/gs spine); gl and oob keep aspath-ignore only.
DEFAULT_VRF_128_ROLES = {"core", "spine"}

# cust-net-edge-* is the customer-owned upstream peer used for local tests
# (validate_excel.py `edge` class); it is not an ERA role and not in scope.
SITES = ("default", "largescale")
CONFIGS = sorted(p for site in SITES
                 for p in PROJECT_ROOT.glob(f"output/*/{site}/configs/*-config.sh")
                 if not p.name.startswith("cust-net-edge-"))


def _role(path):
    name = path.name
    if name.startswith(("core", "csl", "cl-", "cl")):
        return "core"
    if name.startswith(("cs-", "gs-", "spine")):
        return "spine"
    if name.startswith(("gl", "gsl")):
        return "gl"
    if name.startswith(("oob", "rack-oob")):
        return "oob"
    return "unknown"


def _bgp_vrfs(text):
    return sorted(set(re.findall(r"^nv set vrf (\S+) router bgp state enabled$", text, re.M)))


@pytest.mark.parametrize("cfg", CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
class TestCommittedConfigs:
    def test_every_bgp_speaker_has_graceful_restart_once(self, cfg):
        text = cfg.read_text()
        assert "nv set router bgp state enabled" in text, "fixture assumption: all shipped configs run BGP"
        for line in GR_LINES:
            assert text.count(line + "\n") == 1, f"{cfg.name}: expected exactly one `{line}`"

    def test_graceful_restart_follows_router_id(self, cfg):
        """The four GR lines are the next commands after the global `router bgp router-id`
        (blank lines ignored)."""
        lines = cfg.read_text().splitlines()
        idx = [i for i, l in enumerate(lines) if l.startswith("nv set router bgp router-id ")]
        assert len(idx) == 1, f"{cfg.name}: expected one global router-id line, got {len(idx)}"
        following = [l for l in lines[idx[0] + 1:] if l.strip()]
        assert tuple(following[:4]) == GR_LINES, (
            f"{cfg.name}: GR block does not immediately follow router-id")

    def test_wecmp_untouched(self, cfg):
        """W-ECMP is kept as-is (ADR-0045 item 1): present exactly where it was before ERA-66."""
        text = cfg.read_text()
        expected = cfg.name.startswith(WECMP_PREFIXES)
        assert ("route-map WEIGHTED_ECMP" in text) is expected, (
            f"{cfg.name}: W-ECMP route-map {'missing' if expected else 'unexpectedly present'}")

    def test_every_bgp_vrf_has_aspath_ignore_multipath(self, cfg):
        text = cfg.read_text()
        vrfs = _bgp_vrfs(text)
        assert vrfs, f"{cfg.name}: no `nv set vrf <x> router bgp state enabled`"
        for vrf in vrfs:
            line = f"nv set vrf {vrf} router bgp path-selection multipath aspath-ignore enabled\n"
            assert text.count(line) == 1, f"{cfg.name}: VRF {vrf} missing aspath-ignore multipath"

    def test_service_vrfs_have_128_ebgp_paths(self, cfg):
        text = cfg.read_text()
        for vrf in _bgp_vrfs(text):
            line = f"nv set vrf {vrf} router bgp address-family ipv4-unicast multipaths ebgp 128\n"
            expected = 1 if (vrf != "default" or _role(cfg) in DEFAULT_VRF_128_ROLES) else 0
            assert text.count(line) == expected, (
                f"{cfg.name}: VRF {vrf} expected {expected} `multipaths ebgp 128` line(s)")

    def test_no_unsupported_settings_landed(self, cfg):
        """ADR-0045 splits these out (aggregate-route → ERA-132, df-preference → ERA-70): no source supports them."""
        text = cfg.read_text()
        assert "df-preference 50000" not in text
        assert "aggregate-route" not in text


@pytest.mark.parametrize("site", SITES)
def test_every_arch_and_role_is_covered(site):
    configs = [p for p in CONFIGS if p.parts[-3] == site]
    arches = {p.parts[-4] for p in configs}
    for a in VALID_ARCHS:
        assert a in arches, f"{a}/{site} has no committed configs"
    roles = {_role(p) for p in configs}
    assert {"core", "spine", "gl", "oob"} <= roles, roles
    assert "unknown" not in roles, sorted(p.name for p in configs if _role(p) == "unknown")


class TestOOBTemplate:
    OOB_L2 = {
        "hostname": "oob-switch-01",
        "ansible_date_time": {"iso8601": "2026-01-01T00:00:00Z"},
        "spine_bond_members": ["swp49", "swp51"],
        "access_ports": "swp1-46",
        "svi_ip": "192.168.200.2/24",
        "ntp_servers": ["0.pool.ntp.org"],
        "ldap": {"enabled": False},
        "timezone": "Etc/UTC",
        "default_gateway": "192.168.200.1",
    }
    OOB_L3 = dict(OOB_L2, **{
        "oob_uplink_mode": "l3",
        "lo_ip": "172.16.176.21/32",
        "router_id": "172.16.176.21",
        "bgp_asn": 4260394789,
        "vrr_ip": "192.168.200.1/24",
        "oob_vni": 289200,
        "oob_vrf_vni": 5001,
        "oob_vrf_vlan": 3001,
        "oob_vrf_loopback": "172.16.176.31/32",
        "overlay_peers": ["172.16.176.11"],
    })

    def _render(self, oob_cli_template, ctx):
        env = Environment(loader=FileSystemLoader(str(oob_cli_template.parent)),
                          undefined=StrictUndefined, extensions=["jinja2.ext.do"])
        env.filters["regex_replace"] = lambda v, p, r: re.sub(p, r, str(v))
        env.filters["quote"] = lambda s: shlex.quote(str(s))
        return env.get_template(oob_cli_template.name).render(**ctx)

    def test_l3_emits_graceful_restart_and_oob_vrf_multipath(self, oob_cli_template):
        out = self._render(oob_cli_template, self.OOB_L3)
        for line in GR_LINES:
            assert out.count(line) == 1
        assert "nv set vrf OOB router bgp path-selection multipath aspath-ignore enabled" in out
        assert "nv set vrf OOB router bgp address-family ipv4-unicast multipaths ebgp 128" in out
        # default VRF on OOB keeps aspath-ignore only (no production capture carries 128 there)
        assert "nv set vrf default router bgp path-selection multipath aspath-ignore enabled" in out
        assert "nv set vrf default router bgp address-family ipv4-unicast multipaths ebgp 128" not in out

    def test_l2_has_no_bgp_and_no_graceful_restart(self, oob_cli_template):
        out = self._render(oob_cli_template, self.OOB_L2)
        assert "router bgp" not in out
        assert "graceful-restart" not in out
