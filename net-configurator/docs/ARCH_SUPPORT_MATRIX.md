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
| `2-8-9-400` | Converged core; dedicated-GPU CSL + GSL 2-tier at larger deployments | 1 SU / 4 nodes / 32 GPU | 16 SU / 64 nodes / 512 GPU |
| `2-4-5-800` | Multi-tier dedicated-GPU dual-plane (GB300 NVL72 Mini-Cloud) | 1 SU / 18 nodes / 72 GPU | 8 SU / 144 nodes / 576 GPU |
| `2-8-9-800` | Dedicated-GPU dual-plane (CSL + GSL plane1 + plane2) | 2 SU / 8 nodes / 64 GPU | 32 SU / 128 nodes / 1024 GPU |
| `2-8-9-400-SP` | Dedicated-GPU single-plane (`2-8-9-800` minus GPU plane 2) | 2 SU / 8 nodes / 64 GPU | 32 SU / 128 nodes / 1024 GPU |

**Largescale** = the largest scale verified in Air with this repo — not
necessarily an architecture's maximum. Refer to the official ERA reference
architecture documents for the full supported scale of each design.

## Tested features

| Feature | `2-4-3-200` | `2-8-5-200` | `2-8-9-400` | `2-4-5-800` | `2-8-9-800` | `2-8-9-400-SP` |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|
| Collapsed core (single switch pair for E/W + N/S) | ✅ | ✅ | ✅ | — | — | — |
| Dedicated GPU (CSL N/S split from GSL E/W) | — | ✅ at scale | ✅ at scale | ✅ | ✅ | ✅ |
| Multi-tier (dedicated spine switches) | — | — | ✅ at scale | ✅ | ✅ at scale | ✅ at scale |
| Single-plane GPU fabric | — | ✅ at scale | ✅ at scale | — | — | ✅ |
| Dual-plane GPU fabric | — | — | — | ✅ | ✅ | — |
| L3 OOB underlay + EVPN | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| L3 OOB outbound NAT + HA | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| STORAGE VRF as first-class | — | — | — | ✅ | ✅ | ✅ |
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

The Air footprint measured for each architecture at the default and largescale
sizes tested with this repo. Per-node allocation is the platform minimum
(switches 4 vCPU / 4 GB; OOB/edge nodes 1–2 vCPU / 2 GB; server nodes
1 vCPU / 1 GB). Size your Air budget above these sums to allow for per-sim
overhead.

| Arch | Default — nodes / vCPU / mem | Largescale — nodes / vCPU / mem |
|------|-----------------------------:|--------------------------------:|
| `2-4-3-200` | 20 / 32 / 34 GB | 46 / 58 / 62 GB |
| `2-8-5-200` | 24 / 36 / 39 GB | 49 / 67 / 71 GB |
| `2-8-9-400` | 24 / 36 / 39 GB | 109 / 169 / 185 GB |
| `2-4-5-800` | 46 / 94 / 96 GB | 232 / 406 / 422 GB |
| `2-8-9-800` | 30 / 54 / 56 GB | 220 / 409 / 425 GB |
| `2-8-9-400-SP` | 28 / 46 / 48 GB | 196 / 313 / 329 GB |

Switch VMs dominate at largescale, so a **switches-only** simulation (server VMs
omitted — `make deploy-switches-only`) needs far less, which helps under tighter
Air quotas.

## Related documentation

- [`README.md`](../README.md) — quick start and deployment workflows
- [`EXCEL_CONFIGURATION_GUIDE.md`](EXCEL_CONFIGURATION_GUIDE.md) — Excel field reference
- [`ROLES.md`](ROLES.md) — switch role taxonomy per architecture
- The official NVIDIA ERA reference architecture documents — authoritative topology and scale
