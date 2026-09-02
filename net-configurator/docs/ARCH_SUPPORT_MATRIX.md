<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Architecture Support Matrix

This document records **what has been tested in NVIDIA Air using this
repository** — the topologies, features, and scales that were generated and
deployed with these tools and passed `make validate-all`.

> It is a record of testing performed with this tool. It is **not** an official
> product support statement, and it **must not be used in lieu of the official
> NVIDIA ERA reference architecture documents** — consult those for authoritative
> topology, scale, and design guidance.

## Architectures

Each architecture is named `{CPUs}-{GPUs}-{NICs}-{B}` per compute node, where
`B` is the average per-GPU East/West bandwidth in Gbps (for `2-4-3-200` and
`2-8-5-200`, which run a 1:2 NIC:GPU ratio, `200` is the per-NIC link speed).

| Arch | Fabric | Default (tested) | Largescale (tested) |
|------|--------|------------------|---------------------|
| `2-4-3-200` | Converged core (E/W + N/S on one fabric) | 1 SU / 4 nodes / 16 GPU | 8 SU / 32 nodes / 128 GPU |
| `2-8-5-200` | Converged core; dedicated CSL (N/S) + GSL (E/W) split at larger deployments | 1 SU / 4 nodes / 32 GPU | 8 SU / 32 nodes / 256 GPU |
| `2-4-5-400` | **Depopulated `2-8-5-200`** (ERA-00004-001 v04) — same chassis, same five adapters, half the GPUs. Identical fabric; only the per-GPU external uplink capacity differs (ADR-0050) | 1 SU / 4 nodes / 16 GPU | 8 SU / 32 nodes / 128 GPU |
| `2-8-9-400` | Converged core; dedicated-GPU CSL + GSL 2-tier at larger deployments | 1 SU / 4 nodes / 32 GPU | 16 SU / 64 nodes / 512 GPU |
| `2-4-5-800` | Multi-tier dedicated-GPU dual-plane (GB300 NVL72 Mini-Cloud) | 1 SU / 18 nodes / 72 GPU | 8 SU / 144 nodes / 576 GPU |
| `2-8-9-800` | Dedicated-GPU dual-plane (CSL + GSL plane1 + plane2) | 2 SU / 8 nodes / 64 GPU | 32 SU / 128 nodes / 1024 GPU |
| `2-8-9-400-SP` | Dedicated-GPU single-plane (`2-8-9-800` minus GPU plane 2) | 2 SU / 8 nodes / 64 GPU | 32 SU / 128 nodes / 1024 GPU |

**Largescale** = the largest scale verified in Air with this repo — not
necessarily an architecture's maximum. Refer to the official ERA reference
architecture documents for the full supported scale of each design.

## Tested features

| Feature | `2-4-3-200` | `2-8-5-200` / `2-4-5-400` | `2-8-9-400` | `2-4-5-800` | `2-8-9-800` | `2-8-9-400-SP` |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|
| Collapsed core (single switch pair for E/W + N/S) | ✅ | ✅ | ✅ | — | — | — |
| Dedicated GPU (CSL N/S split from GSL E/W) | — | ✅ at scale | ✅ at scale | ✅ | ✅ | ✅ |
| Multi-tier (dedicated spine switches) | — | — | ✅ at scale | ✅ | ✅ at scale | ✅ at scale |
| Single-plane GPU fabric | — | ✅ at scale | ✅ at scale | — | — | ✅ |
| Dual-plane GPU fabric | — | — | — | ✅ | ✅ | — |
| L3 OOB underlay + EVPN | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| L3 OOB outbound NAT + HA | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| STORAGE VRF as first-class | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| EVPN multihoming + anycast gateway | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Inter-VRF DHCP relay (OOB + EXIT) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Air deploy — NOZTP (Node Instructions) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Air deploy — ZTP (DHCP server in sim) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Switches-only deploy (server VMs omitted) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Controller-from-node (deploy driven from a mgmt node; see [MANUAL_FALLBACK_GUIDE](MANUAL_FALLBACK_GUIDE.md)) | untested | untested | untested | untested | ✅ | untested |
| LDAP (auto-detected from Excel) | ✅ | ✅ | ✅ | untested | ✅ | untested |
| Status page (HTTP report dashboard) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `gpu_vlan_mode=per_rail` / `per_rail_per_plane` | ✅ | ✅ | ✅ | untested | ✅ | untested |

Legend: **✅** tested · **✅ at scale** = present/tested only at largescale (not
the default) · **untested** = not exercised with this tool · **—** not applicable.

## Resource sizing (NVIDIA Air)

The Air footprint of each architecture at the default and largescale sizes
shipped with this repo. Figures are summed from the generated topology
(`output/<arch>/<site>/topology/`), which is what Air is actually asked to
allocate. `2-4-5-400` shares `2-8-5-200`'s figures **by construction**: it is
the same topology with the same node and switch counts — depopulating GPUs
changes no VM sizing.

Per-node allocation: fabric switches 4 vCPU / 4 GB; **OOB switches 2 vCPU /
4 GB**; server nodes 1 vCPU / 1 GB; storage 20 GB on every node.

> **The OOB figure is a floor, not a preference.** Air enforces each image's
> published `minimum_resources` on cpu, memory *and* storage, and
> `cumulus-vx-5.18.0` declares 2 / 4096 / 20. A node below it on any single
> axis causes Air to reject the **entire simulation** into state `INVALID`
> with zero nodes — after returning HTTP 200 on import, with no reason
> recorded. Do not trim these values. See ADR-0054.

Size your Air budget above these sums to allow for per-sim overhead.
Figures are summed from each arch's generated topology and re-measured
on 2026-09-02; regenerate and re-measure after any change that adds or
removes nodes, since the customer-edge count now scales with the
fabric's EXIT uplink load rather than being fixed at two.

| Arch | Default — nodes / vCPU / mem | Largescale — nodes / vCPU / mem |
|------|-----------------------------:|--------------------------------:|
| `2-4-3-200` | 53 / 69 / 77 GB | 53 / 69 / 77 GB |
| `2-8-5-200` | 40 / 55 / 61 GB | 55 / 77 / 85 GB |
| `2-4-5-400` | 40 / 55 / 61 GB | 55 / 77 / 85 GB |  <!-- identical to 2-8-5-200 by construction -->
| `2-8-9-400` | 32 / 47 / 53 GB | 113 / 189 / 221 GB |
| `2-4-5-800` | 55 / 107 / 115 GB | 237 / 429 / 465 GB |
| `2-8-9-800` | 31 / 57 / 61 GB | 221 / 429 / 461 GB |
| `2-8-9-400-SP` | 29 / 49 / 53 GB | 197 / 333 / 365 GB |

Switch VMs dominate at largescale, so a **switches-only** simulation (server VMs
omitted — `make deploy-switches-only`) needs far less, which helps under tighter
Air quotas.

## Related documentation

- [`README.md`](../README.md) — quick start and deployment workflows
- [`EXCEL_CONFIGURATION_GUIDE.md`](EXCEL_CONFIGURATION_GUIDE.md) — Excel field reference
- [`ROLES.md`](ROLES.md) — switch role taxonomy per architecture
- The official NVIDIA ERA reference architecture documents — authoritative topology and scale
