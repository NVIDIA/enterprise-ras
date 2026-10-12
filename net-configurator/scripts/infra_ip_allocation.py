#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Sole owner of Air-infrastructure address selection on the management planes.

ERA-134 / ADR-0084. The Air infrastructure nodes the topology generator
auto-injects (``dhcp-oob`` in L2, the ``utility`` jump and ``external-dhcp``
in L3, the ``oob-server-01`` / bridge-SVI gateways) need one address each on
the OOB VLAN subnet and/or the air-mgmt subnet. Those addresses used to be
``network_address + <fixed octet>`` (``+78`` for ``dhcp-oob``, ``+77``/``+78``
for the L3 pair), which is only an address *inside* the subnet when the
subnet is at least a /25. On ``100.82.254.128/26`` the ``+78`` walk produced
``100.82.254.206`` -- outside the /26 -- and every server on the site was
unreachable because the DHCP/jump foot on the OOB VLAN did not exist.

This module follows the ``gpu_ip_allocation.py`` precedent (ADR-0062): pure
functions, one implementation shared by the generator (``excel_parser.py``),
the collision registry (``oob_reserved.py``), the pre-deploy gate
(``validate_excel.py``) and the simulator provisioner (``air-deploy.py``), so
none of them can drift.

Contract of :func:`allocate_infra_ip`:

  * the result is always a usable host address inside ``subnet`` -- network
    and broadcast are never returned, and the function never spills to a
    neighbouring subnet;
  * ``preferred`` (an offset from the network address, or a literal address)
    is returned when it is usable and not in ``taken``. This is what keeps
    every shipped /24 workbook byte-identical: ``dhcp-oob`` stays at ``.78``
    because ``.78`` is free there;
  * otherwise the first free address in ``ip_network(subnet).hosts()`` order
    is returned -- deterministic, so generator and validator agree;
  * exhaustion raises :class:`InfraCapacityError` naming the subnet, the
    claimant and how many free addresses were left. Nothing is skipped
    silently.

Addresses are exchanged as strings so the module composes with the rest of
the parser, which stores every address as text.
"""
import ipaddress

# Offsets (from the network address) each infrastructure claimant PREFERS.
# They are hints, not allocations: the allocator honours them only when the
# address exists inside the subnet and nobody else holds it. Kept here rather
# than in oob_reserved.py so a claimant's preference and a reservation are
# two different things -- conflating them is what let the +78 arithmetic
# masquerade as a reservation.
DHCP_OOB_PREFERRED_OFFSET = 78       # dhcp-oob on the OOB VLAN (L2)
UTILITY_PREFERRED_OFFSET = 78        # utility jump on the OOB VLAN (L3)
EXTERNAL_DHCP_PREFERRED_OFFSET = 77  # external-dhcp / dhcp-oob eth1 on air-mgmt
UTILITY_AIR_MGMT_PREFERRED_OFFSET = 78  # utility eth2 on air-mgmt (L3)


class InfraCapacityError(ValueError):
    """A management subnet has no free host address left for an infra node."""

    def __init__(self, subnet, claimant, free_count, taken_count=None):
        self.subnet = str(subnet)
        self.claimant = claimant
        self.free_count = free_count
        self.taken_count = taken_count
        detail = (f"{taken_count} address(es) already claimed, "
                  if taken_count is not None else "")
        super().__init__(
            f"OOB/air-mgmt subnet {self.subnet} has no free host address for "
            f"'{claimant}' ({detail}{free_count} free). Widen the subnet, or "
            f"move hosts to another OOB VLAN (L3 OOB)."
        )


def parse_network(subnet):
    """Strictly parse ``subnet`` into an ``IPv4Network`` (``strict=False``
    so ``100.82.254.130/26`` is accepted as its containing network)."""
    text = str(subnet or "").strip()
    if not text:
        raise ValueError("infra allocation needs a subnet, got an empty value")
    return ipaddress.IPv4Network(text, strict=False)


def _as_address(value, net):
    """Coerce ``value`` (offset int, dotted string or IPv4Address) into an
    ``IPv4Address``. Offsets are relative to ``net.network_address``."""
    if value is None:
        return None
    if isinstance(value, ipaddress.IPv4Address):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return net.network_address + value
    text = str(value).strip().split('/')[0]
    if not text:
        return None
    try:
        return ipaddress.IPv4Address(text)
    except ValueError:
        return None


def taken_addresses(subnet, *claims):
    """Normalise every claim into the set of ``IPv4Address`` inside ``subnet``.

    Each positional argument is an iterable of offsets, dotted strings or
    ``IPv4Address`` objects (a bare int/str is accepted too). Claims that are
    malformed or fall outside the subnet are dropped: a node on another
    OOB VLAN does not occupy this one, and a reserved offset a small subnet
    does not have (offset 252 on a /26) is not an address anyone can hold.
    Offsets are relative to the network address, matching ``air-deploy.py``.
    """
    net = parse_network(subnet)
    taken = set()
    for claim in claims:
        if claim is None:
            continue
        if isinstance(claim, dict):
            items = claim.keys()
        elif isinstance(claim, (str, bytes, int, ipaddress.IPv4Address)):
            items = [claim]
        else:
            items = claim
        for item in items:
            addr = _as_address(item, net)
            if addr is not None and addr in net:
                taken.add(addr)
    return taken


def usable_hosts(subnet, taken=()):
    """Free host addresses of ``subnet`` in ``hosts()`` order, as strings."""
    net = parse_network(subnet)
    held = taken_addresses(subnet, taken)
    return [str(h) for h in net.hosts() if h not in held]


def allocate_infra_ip(subnet, taken, preferred=None, claimant="infrastructure"):
    """Pick the address ``claimant`` gets on ``subnet``.

    Args:
        subnet: CIDR string (or ``IPv4Network``) of the management plane.
        taken: iterable of addresses already claimed on that plane -- offsets,
            dotted strings, ``IPv4Address``, or a set/dict of them. Build it
            with :func:`taken_addresses`.
        preferred: the claimant's historical address, as an offset from the
            network address or a literal address. Returned iff it is a usable
            host of ``subnet`` and not in ``taken``.
        claimant: human label used in the capacity error.

    Returns:
        The allocated address as a dotted string, always inside ``subnet``.

    Raises:
        InfraCapacityError: no usable host address is free.
        ValueError: ``subnet`` is not a parseable IPv4 CIDR.
    """
    net = parse_network(subnet)
    held = taken_addresses(subnet, taken)
    usable = set(net.hosts())

    want = _as_address(preferred, net)
    if want is not None and want in usable and want not in held:
        return str(want)

    for host in net.hosts():
        if host not in held:
            return str(host)
    raise InfraCapacityError(net, claimant, 0, taken_count=len(held & usable))


def allocate_infra_ips(subnet, taken, claims):
    """Allocate several claimants on one subnet, in order, atomically.

    ``claims`` is an ordered iterable of ``(claimant, preferred)`` pairs. Each
    result is added to the working ``taken`` set before the next claimant is
    placed, so two infra nodes on one subnet never share an address and a
    claimant whose preferred address the previous one took falls through to
    the scan. Raises :class:`InfraCapacityError` for the first claimant that
    cannot be seated; nothing is returned partially.
    """
    held = set(taken_addresses(subnet, taken))
    net = parse_network(subnet)
    out = {}
    for claimant, preferred in claims:
        ip = allocate_infra_ip(net, held, preferred, claimant=claimant)
        out[claimant] = ip
        held.add(ipaddress.IPv4Address(ip))
    return out


def infra_gateway(subnet, declared=None):
    """The gateway address on ``subnet``: the declared Excel gateway when it
    parses and sits inside the subnet, else the first usable host
    (``network + 1`` for every real subnet). Never outside the subnet."""
    net = parse_network(subnet)
    want = _as_address(declared, net)
    if want is not None and want in net and want != net.network_address \
            and want != net.broadcast_address:
        return str(want)
    return str(next(net.hosts()))


DHCP_POOL_PREFERRED_OFFSETS = (100, 200)


def dhcp_pool(subnet, taken, preferred=DHCP_POOL_PREFERRED_OFFSETS,
              claimant="DHCP pool"):
    """Pick the ``(start, end)`` of the dnsmasq pool on ``subnet``.

    The historical pool is ``network + 100 .. network + 200``; when both
    ends are usable hosts of the subnet it is kept, so a /24 renders the
    same ``dhcp-range`` as before. Otherwise the pool is the longest run of
    consecutive usable hosts not in ``taken`` (declared hosts, gateway,
    SVIs, placed infra), so a /26 gets a pool inside ``.129-.190`` instead
    of ``.100-.200``. Raises ``InfraCapacityError`` when no host is free.
    """
    net = parse_network(subnet)
    lo, hi = (_as_address(p, net) for p in preferred)
    hosts = list(net.hosts())
    if lo is not None and hi is not None and lo in hosts and hi in hosts and lo <= hi:
        return str(lo), str(hi)
    held = taken_addresses(subnet, taken)
    best, run = [], []
    for host in hosts:
        if host in held:
            run = []
            continue
        run.append(host)
        if len(run) > len(best):
            best = list(run)
    if not best:
        raise InfraCapacityError(net, claimant, 0, taken_count=len(held & set(hosts)))
    return str(best[0]), str(best[-1])


def assert_inside(subnet, address, claimant="infrastructure"):
    """Raise ``ValueError`` unless ``address`` is a usable host of ``subnet``.

    Used by the validator on every GENERATED infrastructure address so the
    gate fails on the address the generator actually emits, not on a count.
    """
    net = parse_network(subnet)
    addr = _as_address(address, net)
    if addr is None:
        raise ValueError(f"{claimant}: '{address}' is not an IPv4 address")
    if addr not in net or addr == net.network_address or addr == net.broadcast_address:
        raise ValueError(
            f"{claimant}: generated address {addr} is not a usable host of "
            f"{net} (usable {next(net.hosts())}-{list(net.hosts())[-1]})")
    return str(addr)
