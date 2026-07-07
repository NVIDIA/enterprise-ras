# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Regression tests: the server data-plane netplan templates must PRESERVE the
eth0 OOB management address.

Root cause (found 2026-07-01 on ERA-maxscale-2-8-9-800): air-deploy writes the
complete server netplan (incl. eth0 OOB static IP) to /etc/netplan/10-netcfg.yaml
via the Node Instruction. `make deploy-servers[-via-jump]` then OVERWRITES that
same file with roles/<nodes|storage|support>/templates/interfaces.j2 — which
excluded eth0 entirely. `netplan apply` therefore dropped eth0's 192.168.200.x
management IP, severing the very OOB path Ansible was riding over the jump, and
every processed server went permanently unreachable.

The authoritative Air renderer (scripts/air-deploy.py::_render_server_netplan)
ALWAYS emits eth0 as a static-IP management interface. These templates must do
the same so overwriting 10-netcfg.yaml is non-destructive.

eth0 must be a standalone addressed interface — NOT a bond member.
"""
import jinja2
import pytest
import yaml
from pathlib import Path

ROLES = Path(__file__).resolve().parent.parent / "roles"

# Value parity with scripts/air-deploy.py::_render_server_netplan
OOB_PREFIX = "/24"
OOB_GATEWAY = "192.168.200.1"


def _render(rel_template, ctx):
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROLES)),
        trim_blocks=False,
        lstrip_blocks=False,
    )
    return env.get_template(rel_template).render(**ctx)


def _common():
    return {
        "cpu_network": "172.16.178.0/24",
        "cpu_vlan": 300,
        "cpu_gateway": "172.16.178.1",
        "gpu_vlan": 900,
        "gpu_gateway": "192.168.0.1",
        "storage_vlan": 500,
        "storage_gateway": "172.16.180.1",
        "support_vlan": 400,
        "support_gateway": "172.16.179.1",
    }


NODE_CTX = {
    "inventory_hostname": "su-01-node-01",
    "common": _common(),
    "devices": {
        "su-01-node-01": {
            "eth0_ip": "192.168.200.89",
            "interfaces": {"cpu": ["eth0", "eth1", "eth2"], "gpu": ["eth3", "eth4"]},
            "bond_ip": "172.16.178.201/24",
            "gpu_ips": [],
            "gpu_interfaces": [],
        }
    },
}

STORAGE_CTX = {
    "inventory_hostname": "storage-01",
    "common": _common(),
    "devices": {
        "storage-01": {
            "eth0_ip": "192.168.200.220",
            "interfaces": {"storage": ["eth0", "eth1", "eth2"]},
            "bond_ip1": "172.16.180.201/24",
        }
    },
}

SUPPORT_CTX = {
    "inventory_hostname": "support-01",
    "common": _common(),
    "devices": {
        "support-01": {
            "eth0_ip": "192.168.200.250",
            "interfaces": {"support": ["eth0", "eth1", "eth2"]},
            "bond_ip1": "172.16.179.201/24",
        }
    },
}

CASES = [
    ("nodes/templates/interfaces.j2", NODE_CTX, "192.168.200.89"),
    ("storage/templates/interfaces.j2", STORAGE_CTX, "192.168.200.220"),
    ("support/templates/interfaces.j2", SUPPORT_CTX, "192.168.200.250"),
]


@pytest.mark.parametrize("tmpl,ctx,eth0_ip", CASES)
def test_eth0_management_interface_is_emitted(tmpl, ctx, eth0_ip):
    """Each server netplan must define eth0 with its OOB management IP so a
    netplan-apply overwrite doesn't strip the address Ansible connects over."""
    out = _render(tmpl, ctx)
    doc = yaml.safe_load(out)
    eth = doc["network"]["ethernets"]
    assert "eth0" in eth, f"{tmpl}: eth0 management stanza missing"
    assert f"{eth0_ip}{OOB_PREFIX}" in eth["eth0"]["addresses"]
    # eth0 must carry a default route via the OOB gateway (parity with NI)
    routes = eth["eth0"].get("routes", [])
    assert any(
        r.get("to") == "0.0.0.0/0" and r.get("via") == OOB_GATEWAY for r in routes
    ), f"{tmpl}: eth0 missing default route via {OOB_GATEWAY}"


@pytest.mark.parametrize("tmpl,ctx,eth0_ip", CASES)
def test_eth0_is_never_a_bond_member(tmpl, ctx, eth0_ip):
    """eth0 is OOB management — it must never be enslaved to a data bond."""
    out = _render(tmpl, ctx)
    doc = yaml.safe_load(out)
    for bond in (doc["network"].get("bonds") or {}).values():
        assert "eth0" not in bond.get("interfaces", []), (
            f"{tmpl}: eth0 was placed in a bond"
        )
