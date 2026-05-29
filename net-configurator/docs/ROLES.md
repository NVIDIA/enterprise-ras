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

CPU/Storage Leaf switch. In dual-plane architectures, replaces the
converged `core` for everything *except* the GPU fabric — handles
CPU/in-band, storage, and support VLANs.

**Members:** `csl-01`, `csl-02`.

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
(`topology_generator.py:827`); they generate no Air node, no inventory
entry, and no config. They exist purely as OEM-facing port-plan
documentation. Today only `2-4-3-200` uses them.

`SPARE ISL` is **not** part of the role vocabulary and should not be
emitted by the parser as a node role.

## Per-arch presence

### Universal roles — present (or planned) in every arch

| Role | 2-4-3-200 | 2-8-5-200 | 2-8-9-400 | 2-8-9-800 |
|---|:-:|:-:|:-:|:-:|
| `gpu` | ✓ | ✓ | ✓ | ✓ |
| `support` | ✓ | ✓ | ✓ | ✓ |
| `storage` | ✓ | ✓ | ✓ | ⌛ planned |
| `oob-switch` | ✓ | ✓ | ✓ | ✓ |
| `oob-server` | ✓ | ✓ | ✓ | ✓ |
| `dhcp` | ✓ | ✓ | ✓ | ✓ |
| `edge` | ⌛ planned | ⌛ planned | ✓ | ⌛ planned |
| `air-oob` | ✓ | ✓ | ✓ | ✓ |

### Fabric-class roles — mutually exclusive per arch

| Role | 2-4-3-200 | 2-8-5-200 | 2-8-9-400 | 2-8-9-800 |
|---|:-:|:-:|:-:|:-:|
| `core` (collapsed fabric) | ✓ | ✓ | ✓ | — |
| `csl` (dual-plane CPU/storage leaf) | — | — | — | ✓ |
| `gsl` (dual-plane GPU spine/leaf) | — | — | — | ✓ |

**Legend:** ✓ present today,  ⌛ planned, — N/A for this fabric class.

## Backward-compatibility policy

The three currently-live archs ship Excels where the Role column holds the
hostname rather than a canonical role. Migrating those is a per-OEM
revision cycle, not a single PR. So:

### Parser behavior — Excel-first, name-pattern fallback

```text
1. Read the Function / System Role cell.
2. If it matches a canonical role string (case-insensitive), use it directly.
3. Otherwise, fall back to classify_node(name) — legacy prefix matching.
```

This keeps every existing Excel working without modification while letting
new Excels (and revised old ones) declare their role explicitly.

### Per-arch validation enforcement

| Arch | Policy | Reason |
|---|---|---|
| 2-4-3-200 | Legacy: warn on non-canonical roles | Live; migrate gradually |
| 2-8-5-200 | Legacy: warn on non-canonical roles | Live; migrate gradually |
| 2-8-9-400 | Legacy: warn on non-canonical roles | Live; migrate gradually |
| 2-8-9-800 | **Strict: error on non-canonical roles** | Not yet live — clean start |

`validate-excel` enforces these modes via an allow-list per arch.

## Migration plan

In order, smallest blast radius first:

1. **Parser flip to Excel-first** ✅ DONE (commit 24bca73). Helper
   `classify_host_role` recognises canonical role strings; falls back to
   `classify_node()` for legacy.

   Then expanded under the canonical-role-validation branch
   (commit 1e03403): added `canonical_category(function, name)` and
   `extract_role_index(name)` helpers, refactored ~25 sites across
   `parse_oob_switch_configs`, `parse_gsl_port_config`,
   `parse_node_mgmt_mapping`, `build_interface_map`, `categorize_nodes`,
   `generate_hosts_file`, `generate_host_vars`,
   `get_oob_nodes_for_inventory`. **Index extraction** now comes from
   the Name column (trailing digits, with order-of-occurrence
   fallback for digitless names) — `dog10` with Function=`core` works
   correctly.

2. **Standardize column naming.** ✅ DONE. Wire Map column 2 header
   `System Role` -> `Function` across all 12 inputs (4 canonical + 4
   sample + 4 fixture). Parsers read column 2 by position.

3. **Validate-excel role enforcement.** ✅ DONE. `ROLE_ENFORCEMENT`
   table in `validate_excel.py`: 2-8-9-800 strict (error on
   non-canonical Function cells), 2-4-3-200/2-8-5-200/2-8-9-400
   warn. Rolled-up reporting (one warn/error summarising rows +
   distinct examples) keeps noise floor down. Duplicate detection
   moved from Function to Name where canonical repeats are
   expected. Wire Map dedup key switched from Switch Role to
   Switch Name.

4. **Convert 2-8-9-800 to canonical.** ✅ DONE for cell content
   (commit c24f05c): 23 Nodes Function cells + 321 Wire Map System
   Role cells + 314 Wire Map Switch Role cells flipped to canonical
   strings.

5. **Live arch cleanup, per revision cycle.** As each of the three
   live Excels gets touched for unrelated reasons, convert it to
   canonical roles. Validator emits a rolled-up warning per arch
   listing the rows that still hold hostname-as-role — that's the
   per-arch punch list. No forced rev.

6. **Promote warning → error globally** once all four are on
   canonical. Change every arch's `ROLE_ENFORCEMENT` entry to
   `strict` in one MR.

### Default-IP stride limit

A known limit: auto-defaults for OOB/INBAND/EXIT VRF loopbacks collide at >3
cores/csl per role (current 4 archs are within bounds). The
Loopbacks sheet (`docs/LOOPBACKS.md`) is the workaround until a
focused MR widens the stride.

## Adding a new role

1. Open a PR against this file. Justify why an existing role can't be
   re-used (e.g., "support covers it" / "this is just a GPU naming
   variant").
2. Add the role string to the canonical list in `validate_excel.py` and to
   any classifier mapping in `scripts/utils.py`.
3. Document it here with description + members + per-arch presence.
4. New role becomes valid only after the doc lands.
