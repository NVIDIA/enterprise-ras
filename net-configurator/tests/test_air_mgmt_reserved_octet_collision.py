# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""No switch eth0 may land on an air-mgmt octet that infrastructure owns.

excel_parser walks the air-mgmt /24 handing eth0 addresses to switches, skipping
`oob_reserved.AIR_MGMT_RESERVED_OCTETS`. Anything that takes an address on that
plane WITHOUT being in that set gets silently double-assigned.

That happened: `airlib/ext_storage_config.py` privately defined
`EXT_STORAGE_FIRST_OCTET = 79` and put ext-storage eth0 on 172.20.0.79+, while
`oob_reserved` omitted .79 from the air-mgmt set -- its comment asserted ".79
external-conn does not live on that plane", which is true of external-conn and
false of the octet. At SU32 the walk reached .79 and handed it to
`gs-plane2-08`, so that switch and `ext-storage-01` both answered for
172.20.0.79.

The failure is near-invisible. ICMP works (whichever host wins the ARP replies,
and the switch itself can still ping the .254 SVI from its own eth0), BGP
converges, and 75 of 76 switches validate clean. The only symptom is one switch
that is inexplicably "unreachable" to SSH, because the connection lands on an
Ubuntu storage node instead of a Cumulus switch.

These tests pin BOTH halves: the registry must cover every air-mgmt consumer,
and no generated site may put a switch on a reserved octet.
"""
import ipaddress
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from oob_reserved import (  # noqa: E402
    AIR_MGMT_RESERVED_OCTETS,
    AIR_MGMT_RESERVED_OWNERS,
    EXT_STORAGE_FIRST_OCTET,
    EXT_STORAGE_MAX_NODES,
)


def _committed_sites():
    out = subprocess.run(
        ["git", "ls-files", "net-configurator/input/*/*/*.xlsx"],
        cwd=REPO.parent, capture_output=True, text=True, check=True,
    ).stdout.split()
    return sorted((Path(r).parts[-3], Path(r).parts[-2]) for r in out)


SITES = _committed_sites()


@pytest.mark.parametrize("arch,site", SITES)
def test_ext_storage_addresses_never_collide_with_a_switch(arch, site):
    """THE test: what the allocator actually assigns vs what switches got.

    Derived from the real topology by calling the allocator, NOT from
    EXT_STORAGE_FIRST_OCTET/MAX_NODES -- comparing the registry against itself
    is what let this ship. Shrinking the reserved band must fail HERE.
    """
    import json

    from airlib.ext_storage_config import discover_ext_storage_targets

    topology = REPO / "output" / arch / site / "topology" / f"{arch}-topology.json"
    host_vars = REPO / "output" / arch / site / "inventory" / "host_vars"
    if not topology.exists() or not host_vars.is_dir():
        pytest.skip(f"{arch}/{site} not generated in this working tree")

    targets = discover_ext_storage_targets(json.loads(topology.read_text()))
    if not targets:
        pytest.skip(f"{arch}/{site} has no ext-storage nodes")
    storage_ips = {t["eth0_ip"]: t["node_name"] for t in targets}

    collisions = []
    for path in sorted(host_vars.glob("*.yml")):
        for line in path.read_text().splitlines():
            match = re.match(r"\s*ansible_host:\s*(\S+)\s*$", line)
            if match and match.group(1) in storage_ips:
                collisions.append(
                    f"{path.stem} and {storage_ips[match.group(1)]} "
                    f"both hold {match.group(1)}"
                )

    assert not collisions, (
        f"{arch}/{site}: duplicate air-mgmt address(es): {'; '.join(collisions)}. "
        f"ICMP still answers and BGP still converges -- the only symptom is a "
        f"switch that is unreachable over SSH."
    )


def test_reserved_band_covers_every_shipped_ext_storage_node():
    """EXT_STORAGE_MAX_NODES must be >= what shipped topologies actually use."""
    import json

    from airlib.ext_storage_config import discover_ext_storage_targets

    worst = 0
    for arch, site in SITES:
        topology = REPO / "output" / arch / site / "topology" / f"{arch}-topology.json"
        if not topology.exists():
            continue
        worst = max(worst, len(discover_ext_storage_targets(json.loads(topology.read_text()))))
    assert worst <= EXT_STORAGE_MAX_NODES, (
        f"a shipped topology has {worst} ext-storage nodes but only "
        f"{EXT_STORAGE_MAX_NODES} octets are reserved from the switch walk."
    )
    for i in range(EXT_STORAGE_MAX_NODES):
        assert EXT_STORAGE_FIRST_OCTET + i in AIR_MGMT_RESERVED_OCTETS


def test_ext_storage_config_shares_the_registry_constant():
    """ext_storage_config must not carry its own copy of the octet.

    The collision existed precisely because it did: two modules disagreed and
    nothing compared them.
    """
    from airlib import ext_storage_config

    assert ext_storage_config.EXT_STORAGE_FIRST_OCTET is EXT_STORAGE_FIRST_OCTET
    source = (REPO / "scripts" / "airlib" / "ext_storage_config.py").read_text()
    assert not re.search(r"^EXT_STORAGE_FIRST_OCTET\s*=\s*\d", source, re.M), (
        "ext_storage_config redefines EXT_STORAGE_FIRST_OCTET instead of "
        "importing it from oob_reserved; the two can drift apart again."
    )


def test_every_reserved_octet_names_an_owner():
    """An operator who collides must be told who they collided with."""
    assert set(AIR_MGMT_RESERVED_OCTETS) == set(AIR_MGMT_RESERVED_OWNERS), (
        "AIR_MGMT_RESERVED_OCTETS and AIR_MGMT_RESERVED_OWNERS disagree; the "
        "squatter message would print a bare octet number."
    )


def test_gateway_octet_is_not_described_as_the_air_mgmt_gateway():
    """.1 is an unowned hole-punch here; the gateway is the .254 SVI.

    Naming .1 "air-mgmt gateway" misdirected at the one moment the string is
    shown -- when an operator has pinned a switch onto a reserved octet.
    """
    assert "gateway" not in AIR_MGMT_RESERVED_OWNERS[1].split(";")[0].lower() or \
        "no owner" in AIR_MGMT_RESERVED_OWNERS[1].lower(), (
            f"octet 1 is labelled {AIR_MGMT_RESERVED_OWNERS[1]!r}; nothing "
            f"assigns 172.20.0.1 and the real gateway is the .254 SVI."
        )
    assert "gateway" in AIR_MGMT_RESERVED_OWNERS[254].lower()


@pytest.mark.parametrize("arch,site", SITES)
def test_no_switch_on_a_reserved_air_mgmt_octet(arch, site):
    """No generated switch eth0 may sit on an octet infrastructure owns."""
    host_vars = REPO / "output" / arch / site / "inventory" / "host_vars"
    if not host_vars.is_dir():
        pytest.skip(f"{arch}/{site} not generated in this working tree")

    offenders = []
    for path in sorted(host_vars.glob("*.yml")):
        for line in path.read_text().splitlines():
            match = re.match(r"\s*ansible_host:\s*(\d+\.\d+\.\d+\.\d+)\s*$", line)
            if not match:
                continue
            addr = ipaddress.IPv4Address(match.group(1))
            # Only the air-mgmt plane walks octets; the OOB plane has its own set.
            if not str(addr).startswith("172.20.0."):
                continue
            if int(str(addr).rsplit(".", 1)[1]) in AIR_MGMT_RESERVED_OCTETS:
                owner = AIR_MGMT_RESERVED_OWNERS.get(
                    int(str(addr).rsplit(".", 1)[1]), "infrastructure"
                )
                offenders.append(f"{path.stem} -> {addr} (owned by {owner})")

    assert not offenders, (
        f"{arch}/{site}: switch eth0 collides with air-mgmt infrastructure: "
        + "; ".join(offenders)
    )


@pytest.mark.parametrize("arch,site", SITES)
def test_no_duplicate_air_mgmt_address(arch, site):
    """Two hosts on one air-mgmt address is an ARP war, not an error anywhere."""
    host_vars = REPO / "output" / arch / site / "inventory" / "host_vars"
    if not host_vars.is_dir():
        pytest.skip(f"{arch}/{site} not generated in this working tree")

    seen = {}
    for path in sorted(host_vars.glob("*.yml")):
        for line in path.read_text().splitlines():
            match = re.match(r"\s*ansible_host:\s*(172\.20\.0\.\d+)\s*$", line)
            if match:
                seen.setdefault(match.group(1), []).append(path.stem)

    dupes = {ip: hosts for ip, hosts in seen.items() if len(hosts) > 1}
    assert not dupes, f"{arch}/{site}: duplicate air-mgmt addresses {dupes}"
