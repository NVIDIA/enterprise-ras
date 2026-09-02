# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-52: filter EVPN macip origination into the OOB VNI.

The leak vector is the support-server bonds on core/csl, which trunk the OOB
VLAN alongside the data VLANs on a single EVPN-MH bond:

    nv set interface bond25s0..bond28s1 bridge domain br_default vlan 200,300,400

A misconfigured multihomed node that puts a non-OOB address on VLAN 200 makes
core/csl originate an EVPN type-2 macip into VNI 4200, which lands in the OOB
VRF. `EVPN_OOB_OUT` permits macip whose IP is a real OOB address, denies every
other IPv4 macip, and permits everything else (type-3 IMET, type-5 prefixes,
mac-only, IPv6 ND).

Two things this is NOT:

* **Not already covered by `OOB_FILTER`.** That is a `route-import from-vrf`
  policy on ipv4-unicast — it governs what the OOB VRF IMPORTS from other VRFs
  and never sees a type-2 macip this fabric originates itself.
* **Not an oob-switch change.** The OOB switch's VLAN-200 role is the SVI/VRR
  gateway plus single-VLAN BMC access ports, which cannot mix a foreign subnet
  the way a 200/300/400 trunk can. It also runs Cumulus 5.15.1 against the
  fabric's 5.16.1, and `match evpn-route-type` is new to this codebase.

The failure mode is asymmetric and worth stating plainly: rule 20 denies every
macip not matched by `OOB_HOSTS`, so an `OOB_HOSTS` that is too NARROW makes OOB
hosts unreachable. That is why the list is derived from the workbook's own OOB
subnets rather than a hardcoded range, why it is one rule per subnet (per-switch
OOB VLANs are supported), and why it is in OVERRIDABLE_PREFIX_LISTS so a site
can widen it from the Prefix lists sheet.
"""
import re
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
_SHIPPED = ("default", "largescale")
_NS_ROLES = ("core", "csl", "cl")

_ATTACH = ("nv set vrf default router bgp peer-group overlay "
           "address-family l2vpn-evpn policy outbound route-map EVPN_OOB_OUT")


def _shipped_configs(prefixes):
    out = []
    for site in _SHIPPED:
        for pref in prefixes:
            out += sorted(NC.glob(f"output/*/{site}/configs/{pref}-*-config.sh"))
    return out


NS_CONFIGS = _shipped_configs(_NS_ROLES)
OOB_CONFIGS = _shipped_configs(("oob-switch",))


def test_configs_exist():
    """An empty glob would make the parametrised tests vacuously pass."""
    assert NS_CONFIGS, "no shipped core/csl/cl configs found"
    assert OOB_CONFIGS, "no shipped oob-switch configs found"


@pytest.mark.parametrize("cfg", NS_CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
def test_ns_fabric_applies_the_filter(cfg):
    """Every N/S switch that can originate into the OOB VNI must filter."""
    txt = cfg.read_text()
    assert _ATTACH in txt, (
        f"{cfg.relative_to(NC)}: EVPN_OOB_OUT is not applied outbound on the "
        f"overlay peer-group — a misconfigured node on VLAN 200 could leak a "
        f"non-OOB macip into the OOB VRF")


@pytest.mark.parametrize("cfg", OOB_CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
def test_oob_switches_are_untouched(cfg):
    """Deliberately not the OOB switch — wrong vector, and older NVUE."""
    assert "EVPN_OOB_OUT" not in cfg.read_text(), (
        f"{cfg.relative_to(NC)}: the filter reached an OOB switch. Those run "
        f"Cumulus 5.15.1 and `match evpn-route-type` is unverified there")


@pytest.mark.parametrize("cfg", NS_CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
def test_rule_semantics_are_intact(cfg):
    """Order and actions carry the whole meaning; a reordering inverts it."""
    txt = cfg.read_text()
    rules = {}
    for m in re.finditer(
            r"route-map EVPN_OOB_OUT rule (\d+) action (permit|deny)", txt):
        rules[m.group(1)] = m.group(2)
    assert rules.get("10") == "permit", "rule 10 must permit real OOB macip"
    assert rules.get("20") == "deny", (
        "rule 20 must DENY every other ipv4 macip — a permit here makes the "
        "whole filter a no-op while still looking configured")
    assert rules.get("100") == "permit", (
        "rule 100 must permit everything else, or type-3 IMET / type-5 OOB "
        "prefixes / IPv6 ND are dropped and the OOB overlay breaks entirely")

    assert re.search(r"rule 10 match ip-prefix-list OOB_HOSTS", txt), \
        "rule 10 must match OOB_HOSTS"
    for rid in ("10", "20"):
        assert re.search(rf"rule {rid} match evpn-route-type macip", txt), \
            f"rule {rid} must be scoped to macip, not all EVPN routes"


@pytest.mark.parametrize("cfg", NS_CONFIGS, ids=lambda p: f"{p.parts[-4]}/{p.parts[-3]}/{p.name}")
def test_oob_hosts_is_derived_not_hardcoded(cfg):
    """OOB_HOSTS must describe this deployment's own OOB subnets.

    The ticket's sample carries 10.184.177.0/24. Shipping that literal would
    deny every real OOB macip on every one of our archs.
    """
    txt = cfg.read_text()
    matches = re.findall(
        r"prefix-list OOB_HOSTS rule \d+ match (\S+) max-prefix-len (\d+)", txt)
    assert matches, f"{cfg.relative_to(NC)}: OOB_HOSTS has no rules"
    assert "10.184.177.0/24" not in [m[0] for m in matches], (
        "OOB_HOSTS carries the ticket's sample literal instead of the "
        "workbook's own OOB subnet")
    for net, maxlen in matches:
        assert maxlen == "32", (
            f"OOB_HOSTS {net} has max-prefix-len {maxlen}; a macip host route "
            f"is a /32 and would not match")

    # Every OOB_HOSTS entry must correspond to an OOB subnet this switch
    # actually knows about — OOB_PREFIXES is built from the same resolution.
    oob_prefixes = set(re.findall(
        r"prefix-list OOB_PREFIXES rule \d+ match (\S+)", txt))
    if oob_prefixes:
        for net, _ in matches:
            assert net in oob_prefixes, (
                f"OOB_HOSTS carries {net}, which is not among this switch's "
                f"OOB prefixes {sorted(oob_prefixes)} — the two are resolved "
                f"from the same source and disagreeing means one is stale")
