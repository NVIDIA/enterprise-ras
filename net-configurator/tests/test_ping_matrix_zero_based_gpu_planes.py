# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Pins the invariant that validate-ping-matrix.yml derives its GPU gateway
probes from the resolved per-interface data, not from LOGICAL plane key names.

Incident: ADR-0044 made logical GPU plane/rail identifiers zero-based, so an
aggregate dual-plane workbook now emits `common.gpu_plane0_*` /
`common.gpu_plane1_*` instead of `gpu_plane1_*` / `gpu_plane2_*`. The playbook's
GPU-gateway block guarded on `gpu_plane1_gateway is defined and
gpu_plane2_gateway is defined`; with `gpu_plane2_gateway` gone the branch went
dead, and because aggregate dual-plane archs have no `common.gpu_gateway` the
legacy `elif` did not catch it either. Result: every GPU gateway ping silently
disappeared from the matrix while the report still declared success — the
"fails open and reports green" shape from AGENT-GUIDE §9. The report legend had
the mirror-image bug: it fell back to `gpu_plane1_vlan`, which under zero-based
naming is the SECOND plane, so it advertised the GPU VRF as VLAN 920.

What is pinned:
  * a GPU gateway probe is emitted for each of the first two GPU NICs, aimed at
    that NIC's own resolved gateway, under zero-based aggregate, legacy
    one-based aggregate, and per-rail naming alike;
  * the legacy single-NIC `common.gpu_gateway` path still works;
  * the report legend names the FIRST GPU plane's VLAN.

What is deliberately NOT constrained: the ping/label wording, the ordering of
the emitted lines, cross-plane pings (architecturally skipped), and which
physical plane a logical plane maps to — that boundary belongs to the parser
and is covered by tests/test_zero_based_gpu_indexing.py.
"""
import re
import shlex
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment

REPO = Path(__file__).resolve().parent.parent
PLAYBOOK = REPO / "playbooks" / "validate-ping-matrix.yml"

FIRE_TASK = "Push and fire ping scripts (parallel)"
REPORT_TASK = "Generate ping matrix report"


def _env():
    """Jinja2 environment with the Ansible filters this playbook uses."""
    env = Environment(extensions=["jinja2.ext.do"])
    env.filters["regex_replace"] = lambda v, p, r: re.sub(p, r, str(v))
    env.filters["quote"] = lambda s: shlex.quote(str(s))
    return env


def _tasks():
    play = yaml.safe_load(PLAYBOOK.read_text())[0]
    return {t["name"]: t for t in play["tasks"]}


def _fire_script(common, devices):
    """Render the fire task's shell body for the first compute node."""
    mod = _tasks()[FIRE_TASK]["ansible.builtin.shell"]
    cmd = mod["cmd"] + mod["stdin"]
    hosts = sorted(devices)
    return _env().from_string(cmd).render(
        item=hosts[0],
        server_groups=hosts,
        devices=devices,
        common=common,
        hostvars={h: {"ansible_host": f"172.16.180.{i + 1}"}
                  for i, h in enumerate(hosts)},
        server_ansible_password="unused-in-render",
    )


def _legend_vlan(common):
    """Render the report legend's GPU VRF line and return the VLAN it names."""
    content = _tasks()[REPORT_TASK]["copy"]["content"]
    line = next(l for l in content.splitlines()
                if "Compute GPU interfaces (VLAN" in l)
    rendered = _env().from_string(line).render(common=common)
    return re.search(r"VLAN\s+(\S+?)\)", rendered).group(1)


def _probes(script):
    """Extract (target, source_ip) for every `_p` probe the script emits."""
    return set(re.findall(r"^\s*_p (\S+) (\S+) ", script, re.MULTILINE))


def _gpu_gw_targets(script):
    """Gateways that a `gpu-gw*` labelled probe actually aims at."""
    return set(re.findall(r'\|gpu-gw[^|]*\|(\S+?)\|GPU-gw', script))


def _compute_pair(gpu_ifaces_a, gpu_ifaces_b):
    return {
        "gpu-01": {
            "role": "compute",
            "bond_ip": "172.16.178.201/24",
            "interfaces": {"gpu": [i["iface"] for i in gpu_ifaces_a]},
            "gpu_interfaces": gpu_ifaces_a,
        },
        "gpu-02": {
            "role": "compute",
            "bond_ip": "172.16.178.202/24",
            "interfaces": {"gpu": [i["iface"] for i in gpu_ifaces_b]},
            "gpu_interfaces": gpu_ifaces_b,
        },
    }


BASE_COMMON = {
    "cpu_vlan": 100,
    "cpu_vrf": "INBAND",
    "cpu_gateway": "172.16.178.1",
    "support_vlan": 300,
    "support_gateway": "172.16.179.1",
}

# Aggregate dual-plane node NICs. The `plane` field is the PHYSICAL ordinal in
# aggregate mode and each entry carries its own resolved gateway, which is what
# the fixed playbook keys off. Identical in both naming modes by construction —
# only the `common.gpu_plane*` key names differ.
AGG_IFACES = [
    [{"iface": "eth3", "plane": "plane1", "ip": "192.168.0.201/20",
      "gateway": "192.168.0.1", "table": 900},
     {"iface": "eth4", "plane": "plane2", "ip": "192.168.16.201/20",
      "gateway": "192.168.16.1", "table": 1020}],
    [{"iface": "eth3", "plane": "plane1", "ip": "192.168.0.202/20",
      "gateway": "192.168.0.1", "table": 900},
     {"iface": "eth4", "plane": "plane2", "ip": "192.168.16.202/20",
      "gateway": "192.168.16.1", "table": 1020}],
]

ZERO_BASED_AGG = dict(BASE_COMMON, **{
    "gpu_plane0_vlan": 900, "gpu_plane0_gateway": "192.168.0.1",
    "gpu_plane0_network": "192.168.0.0/20", "gpu_plane0_vrf": "GPU",
    "gpu_plane1_vlan": 920, "gpu_plane1_gateway": "192.168.16.1",
    "gpu_plane1_network": "192.168.16.0/20", "gpu_plane1_vrf": "GPU",
})

LEGACY_AGG = dict(BASE_COMMON, **{
    "gpu_plane1_vlan": 900, "gpu_plane1_gateway": "192.168.0.1",
    "gpu_plane1_network": "192.168.0.0/20", "gpu_plane1_vrf": "GPU",
    "gpu_plane2_vlan": 920, "gpu_plane2_gateway": "192.168.16.1",
    "gpu_plane2_network": "192.168.16.0/20", "gpu_plane2_vrf": "GPU",
})

# Per-rail (single physical plane, one VLAN per rail) — no gpu_plane* keys at
# all, so this mode exercises the origin-independent path directly.
PER_RAIL_IFACES = [
    [{"iface": "eth3", "plane": "rail0", "ip": "192.168.0.201/24",
      "gateway": "192.168.0.1", "table": 900},
     {"iface": "eth4", "plane": "rail1", "ip": "192.168.1.201/24",
      "gateway": "192.168.1.1", "table": 901}],
    [{"iface": "eth3", "plane": "rail0", "ip": "192.168.0.202/24",
      "gateway": "192.168.0.1", "table": 900},
     {"iface": "eth4", "plane": "rail1", "ip": "192.168.1.202/24",
      "gateway": "192.168.1.1", "table": 901}],
]

PER_RAIL_COMMON = dict(BASE_COMMON, **{
    "gpu_rail0_vlan": 900, "gpu_rail0_gateway": "192.168.0.1",
    "gpu_rail0_network": "192.168.0.0/24", "gpu_rail0_vrf": "GPU",
    "gpu_rail1_vlan": 901, "gpu_rail1_gateway": "192.168.1.1",
    "gpu_rail1_network": "192.168.1.0/24", "gpu_rail1_vrf": "GPU",
})


@pytest.mark.parametrize(
    "label,common,ifaces,expected_gateways",
    [
        ("zero-based aggregate", ZERO_BASED_AGG, AGG_IFACES,
         {"192.168.0.1", "192.168.16.1"}),
        ("legacy one-based aggregate", LEGACY_AGG, AGG_IFACES,
         {"192.168.0.1", "192.168.16.1"}),
        ("per-rail", PER_RAIL_COMMON, PER_RAIL_IFACES,
         {"192.168.0.1", "192.168.1.1"}),
    ],
)
def test_every_gpu_nic_probes_its_own_gateway(label, common, ifaces,
                                              expected_gateways):
    """Both GPU NICs get a gateway probe regardless of plane/rail numbering."""
    script = _fire_script(common, _compute_pair(*ifaces))
    assert _gpu_gw_targets(script) == expected_gateways, (
        f"{label}: expected gpu-gw probes to {sorted(expected_gateways)}, "
        f"got {sorted(_gpu_gw_targets(script))}"
    )
    # Each probe must be sourced from the NIC that lives in that subnet, or the
    # ping leaves via the wrong interface and fails for the wrong reason.
    for iface in ifaces[0]:
        src = iface["ip"].split("/")[0]
        assert (iface["gateway"], src) in _probes(script), (
            f"{label}: gateway {iface['gateway']} not probed from {src}"
        )


def test_single_plane_legacy_gpu_gateway_still_probed():
    """Archs with one GPU NIC and common.gpu_gateway keep the legacy probe."""
    common = dict(BASE_COMMON, gpu_vlan=900, gpu_gateway="192.168.110.1",
                  gpu_network="192.168.110.0/24", gpu_vrf="GPU")
    devices = {
        "su-01-node-01": {"role": "compute", "bond_ip": "172.16.178.201/24",
                          "interfaces": {"gpu": ["eth3"]},
                          "gpu_ips": ["192.168.110.201/24"]},
        "su-01-node-02": {"role": "compute", "bond_ip": "172.16.178.202/24",
                          "interfaces": {"gpu": ["eth3"]},
                          "gpu_ips": ["192.168.110.202/24"]},
    }
    script = _fire_script(common, devices)
    assert _gpu_gw_targets(script) == {"192.168.110.1"}


@pytest.mark.parametrize(
    "label,common,expected_vlan",
    [
        ("zero-based aggregate", ZERO_BASED_AGG, "900"),
        ("legacy one-based aggregate", LEGACY_AGG, "900"),
        ("single-plane", dict(BASE_COMMON, gpu_vlan=900), "900"),
        ("per-rail (no aggregate keys)", PER_RAIL_COMMON, "900"),
    ],
)
def test_report_legend_names_the_first_gpu_plane_vlan(label, common,
                                                      expected_vlan):
    """The VRF legend must advertise the first GPU plane, not the second."""
    assert _legend_vlan(common) == expected_vlan, (
        f"{label}: legend named VLAN {_legend_vlan(common)}, "
        f"expected {expected_vlan}"
    )
