<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# ERA Canonical Node Roles

## Why this exists

Every node in an ERA deployment has two pieces of identity:

- A **Role** (the *Function* column in the Nodes tab, the *System Role* column
  in the Wire Map) — describes *what the node does*.
- A **Hostname** (the *Name* column in both tabs) — the per-instance identifier.

Historically the Role column has held the hostname itself (e.g.
`Function=core-01, Name=core-01`), and the parser derived the role-category by
prefix-matching on the string (`classify_node()` in `scripts/utils.py`). That
couples spreadsheet content to classifier code: a new naming convention
(e.g. `b100-N`, `mi300-N`) requires a code change before the spreadsheet
will work.

This document is the source of truth for the **role vocabulary**. The
spreadsheet should declare the role directly; the parser should believe what
the spreadsheet says.

## The 11 canonical roles

### `gpu`

GPU-accelerated worker node — the AI training / inference workhorse. Has
multiple high-speed NICs into the GPU fabric (split across planes in
dual-plane architectures) and a CPU bond into the in-band CPU network for
management traffic and CPU-side workloads. Multi-GPU host (typically
DGX/HGX class).

**Members:** `su-01-node-01`, `gpu-01`.

### `support`

Cluster control-plane / support server. CPU-only — no GPU fabric NICs.
Provides services like Base Command Manager, Slurm head, Kubernetes control
plane, monitoring, or generic support tooling. Has a bond on the support
VLAN (typically tagged sub-interface for VLAN segmentation).

**Members:** `support-01`, `bcm-01`, `slurm-01`, `k8s-01`.
`bcme-NN` is a legacy member name retained for backward compatibility with
earlier Excels — the parser still maps it to `support`.

### `storage`

Storage server (parallel-filesystem node). CPU-only with one or two bonds
on the storage VLAN; carries dedicated storage traffic separate from
in-band CPU traffic.

**Members:** `storage-01`.

### `core`

Converged core (spine) switch. In collapsed-fabric architectures, carries
both the CPU/storage fabric and the GPU fabric on the same physical
switches via VLAN separation. EVPN-multihoming endpoints for compute /
storage / support bonds.

**Members:** `core-01`, `core-02`.

### `csl`

Converged compute spine-leaf switch (1-tier; `ns_tiers=1`). In dual-plane
architectures, replaces the converged `core` for everything *except* the
GPU fabric — handles CPU/in-band, storage, and support VLANs. One box
that is genuinely both spine and leaf (the "S-L" name is accurate).

**Members:** `csl-01`, `csl-02`.

### `cl`

Compute Leaf switch (2-tier; `ns_tiers=2`). The dedicated leaf in a split
compute fabric, used when a dedicated `cs` spine sits above. Renders the
same template as `csl` but stays a distinct role so per-tier group_vars
(QoS pools, monitoring tags) can diverge later.

**Members:** `cl-01`, `cl-02`.

### `gsl-plane1` / `gsl-plane2`

GPU Spine/Leaf switch. In dual-plane architectures, dedicated to one GPU
plane. Each plane has its own pair, completely L3-isolated from the other
plane (same VLAN ID, different L2 broadcast domain). Plane membership is
part of the routing-design identity (per-plane underlay loopback subnet,
own EVPN scope, separate BGP graph) — hence `gsl-plane1` and `gsl-plane2`
are distinct canonical roles rather than `gsl` with a plane sub-attribute.

The bare canonical `gsl` is still accepted for backward-compat with
earlier Excels; when present, the parser promotes it to `gsl-plane1` or
`gsl-plane2` by inspecting the Name column's plane suffix
(`gsl-plane1-01` -> `gsl-plane1`). Operators authoring new sheets should
declare the plane-specific canonical directly.

**Members:** `gsl-plane1-01`, `gsl-plane1-02`, `gsl-plane2-01`, `gsl-plane2-02`.

### `gl-plane1` / `gl-plane2`

GPU Leaf switch (2-tier; `ew_tiers=2`). The dedicated leaf when a `gs`
spine sits above per plane. Same template as `gsl-plane*`; distinct role
for future per-tier divergence.

**Members:** `gl-plane1-01..04`, `gl-plane2-01..04`.

### `cs`

Compute Spine switch (2-tier; `ns_tiers=2`). Sits above `cl` leaves; pure
EVPN relay (no VTEPs, bridge, or VRFs). Renders the merged
`roles/spine/templates/spine_nvue_cli.j2` (with `weighted_ecmp` /
`smn_ports` / `isl_core_ports` as optional, group_vars-gated blocks).

**Members:** typically `cs-01`, `cs-02`.

### `gs-plane1` / `gs-plane2`

GPU Spine switch (2-tier; `ew_tiers=2`). Sits above `gl-plane*` leaves
per plane; pure EVPN relay with RoCE lossless QoS (the `roce_traffic_pool`
flag enables the memory-percent carve in the merged spine template).
Each plane's spines peer only with their own plane's leaves.

**Members:** `gs-plane1-01`, `gs-plane1-02` (plane 1), `gs-plane2-01`,
`gs-plane2-02` (plane 2).

### `oob-switch`

Out-of-Band management switch. Every node's `eth0` management interface
terminates here. Provides the flat `192.168.200.0/24` OOB plane. Typically
a 1U 1G access switch (SN2201).

**Members:** `oob-switch-01`.

### `oob-server`

OOB gateway / NAT server. Sits between the OOB plane and the upstream /
customer network. Provides default-route egress for the OOB subnet and
acts as a bastion host for SSH-via-jump deploys.

**Members:** `oob-server-01`.

### `dhcp`

DHCP / ZTP server. Runs dnsmasq for switch ZTP (TFTP boot, DHCP
reservations) and optionally for server-side DHCP on the OOB plane. In
split deployments, separate hosts may serve the OOB plane vs a
customer-edge plane.

**Members:** `dhcp-oob`, `dhcp-edge`.

### `edge`

Customer-network edge node. Bridges the customer's external network to the
OOB plane for inbound management / external access. Not part of any
compute fabric.

**Members:** `cust-net-edge-01`.

### `air-oob`

Virtual OOB bridge node, auto-created by the topology generator for the
Air simulation. Carries the air-mgmt VLAN inside the sim so OOB switches
can talk to the OOB server and `dhcp-oob`. **Air-only** — does not
represent any physical hardware. Always exactly one per sim.

**Members:** `air-oob-switch`.

## Wire Map annotation rows (not roles)

**`SPARE ISL`** — Wire Map rows that document reserved or unused
inter-switch-link ports. The topology generator explicitly skips these
(`topology_generator.py`, `_build_connected_links` — rows whose system name is not a valid hostname are skipped); they generate no Air node, no inventory
entry, and no config. They exist purely as OEM-facing port-plan
documentation. Today only `2-4-3-200` uses them.

`SPARE ISL` is **not** part of the role vocabulary and should not be
emitted by the parser as a node role.

## Per-arch presence

Fabrics change shape with scale: the converged archs ship a collapsed `core`
at their **default** and split into dedicated / 2-tier switch roles at
**largescale**. In the tables below, ✓ means the role is used by that
architecture at some tested scale (default or largescale); — means it is not
used. See [`ARCH_SUPPORT_MATRIX.md`](ARCH_SUPPORT_MATRIX.md) for the scale each
was tested at.

### Compute / server roles — every architecture

| Role | 2-4-3-200 | 2-8-5-200 / 2-4-5-400 | 2-8-9-400 | 2-4-5-800 | 2-8-9-800 | 2-8-9-400-SP |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `gpu` (compute worker) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `support` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `storage` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

### Switch fabric roles — per arch

| Role | 2-4-3-200 | 2-8-5-200 / 2-4-5-400 | 2-8-9-400 | 2-4-5-800 | 2-8-9-800 | 2-8-9-400-SP |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `core` (collapsed fabric) | ✓ | ✓ | ✓ | — | — | — |
| `csl` (converged CPU/storage leaf) | — | ✓ | ✓ | — | ✓ | ✓ |
| `cl` / `cs` (2-tier CPU leaf / spine) | — | — | — | ✓ | ✓ | ✓ |
| `gsl-plane1` (converged GPU spine/leaf) | — | ✓ | — | — | ✓ | ✓ |
| `gsl-plane2` | — | — | — | — | ✓ | — |
| `gl-plane1` / `gs-plane1` (2-tier GPU) | — | — | ✓ | ✓ | ✓ | ✓ |
| `gl-plane2` / `gs-plane2` (plane 2) | — | — | — | ✓ | ✓ | — |
| `oob-switch` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

### OOB / management roles — L3 (default)

The default OOB mode is **L3** (routed OOB with an EXIT/OOB VRF). Every
architecture uses the same L3 management set:

| Role | Node | Purpose |
|---|---|---|
| `utility` | `utility` | L3 OOB jump host / gateway; hosts the status page; OOB-side DHCP relay target |
| `external-dhcp` | `external-dhcp` | ZTP DHCP + web server; inter-VRF EXIT relay target |
| `external-conn` | `external-conn` | NAT host (`172.20.0.1`) — outbound routing + eBGP into the OOB VRF |
| `cust-net-edge` | `cust-net-edge-01` / `-02` | Customer-edge switch: air-mgmt bridge + EXIT-VRF eBGP underlay (`-02` = HA NAT return path) |
| `oob-switch` | `oob-switch-NN` | OOB access switches — every node's `eth0` terminates here (`192.168.200.0/24`) |

> **Legacy L2 OOB.** When `oob_uplink_mode=l2`, the older node set applies
> instead: `oob-server-01` (jump/NAT), `dhcp-oob` / `dhcp-edge` (DHCP), and
> `air-oob-switch` (Air L2 bridge). These do not appear in an L3 deployment —
> see [`OOB_SERVER_SETUP.md`](OOB_SERVER_SETUP.md).

## Role declaration & validation

A node's role can be declared directly in the **Function** cell (Nodes tab) /
**System Role** cell (Wire Map). The parser is Excel-first with a name-pattern
fallback:

```text
1. Read the Function / System Role cell.
2. If it matches a canonical role string (case-insensitive), use it directly.
3. Otherwise, fall back to name-pattern classification (legacy prefix matching).
```

This lets new Excels declare roles explicitly while older Excels that put the
hostname in the Role column keep working unchanged.

### Per-arch validation enforcement

`make validate-excel` enforces canonical roles per architecture:

| Arch | Policy |
|---|---|
| `2-4-3-200` | warn on non-canonical roles |
| `2-8-5-200` | warn on non-canonical roles |
| `2-8-9-400` | warn on non-canonical roles |
| `2-4-5-800` | **strict — error on non-canonical roles** |
| `2-8-9-800` | **strict — error on non-canonical roles** |
| `2-8-9-400-SP` | **strict — error on non-canonical roles** |

`warn` architectures ship Excels that still use hostname-as-role in some cells
and migrate to canonical roles gradually; `strict` architectures must use
canonical role names in the Function / System Role cells.

### Default-IP stride limit

Auto-assigned OOB/INBAND/EXIT VRF loopbacks collide at more than 3 core/CSL
switches per role. If you hit that, set explicit loopbacks on the **Loopbacks**
sheet (see [`LOOPBACKS.md`](LOOPBACKS.md)).

## Adding a new role

1. Open a PR against this file. Justify why an existing role can't be
   re-used (e.g., "support covers it" / "this is just a GPU naming
   variant").
2. Add the role string to the canonical list in `validate_excel.py` and to
   any classifier mapping in `scripts/utils.py`.
3. Document it here with description + members + per-arch presence.
4. New role becomes valid only after the doc lands.
