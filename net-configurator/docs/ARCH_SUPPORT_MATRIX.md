<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Architecture Support Matrix

This document records **what has been tested in NVIDIA Air using this
repository**, together with offline implementation checks and explicitly
untested features. Checkmarks describe the named check, not certification of
every feature combination.

The October 7–9, 2026 campaign passed all **48 final runs**: eight architectures
× two shipped scales × NOZTP, DHCP ZTP and switches-only. The 32 full-server
runs also passed all-rail connectivity checks. All used Cumulus Linux 5.18.3
and L3 OOB; LDAP and the status page were disabled in these workbooks.
Physical switches, ASIC behavior, RDMA, throughput and storage I/O were not
tested. Some runs required retries; passing health gates can include
non-failing external-storage BGP warnings.

These are historical results, not a claim that every subsequent commit was
rerun in Air. The campaign used a streaming ping-validator fix whose runtime
playbook was subsequently merged unchanged.

> It is a record of testing performed with this tool. It is **not** an official
> product support statement, and it **must not be used in lieu of the official
> NVIDIA ERA reference architecture documents** — consult those for authoritative
> topology, scale, and design guidance.

## Architectures

Each architecture is named `{CPUs}-{GPUs}-{NICs}-{B}` per compute node, where
`B` is the average per-GPU East/West bandwidth in Gbps.

| Arch | Fabric | Default (tested) | Largescale (tested) |
|------|--------|------------------|---------------------|
| `2-4-3-200` | Converged core (E/W + N/S on one fabric) | 5 SU / 20 nodes / 80 GPU | 8 SU / 32 nodes / 128 GPU |
| `2-8-5-200` | Converged core; dedicated CSL (N/S) + GSL (E/W) split at larger deployments | 5 SU / 20 nodes / 160 GPU | 8 SU / 32 nodes / 256 GPU |
| `2-4-5-400` | **Depopulated `2-8-5-200`** (ERA-00004-001 v04) — same chassis, same five adapters, half the GPUs. Identical fabric; only the per-GPU external uplink capacity differs (ADR-0050) | 5 SU / 20 nodes / 80 GPU | 8 SU / 32 nodes / 128 GPU |
| `2-8-9-400` | Converged core; dedicated-GPU CSL + GSL 2-tier at larger deployments | 3 SU / 12 nodes / 96 GPU | 16 SU / 64 nodes / 512 GPU |
| `2-8-5-400` | Converged core through SU 3; dedicated N/S CSL pair from SU 4; E/W leaf + spine tier from SU 5 (ERA-00014-001). The intermediate SU 4 GSL stage was not a campaign cell. | 3 SU / 12 nodes / 96 GPU | 8 SU / 32 nodes / 256 GPU |
| `2-4-5-800` | Multi-tier dedicated-GPU dual-plane (GB300 NVL72 Mini-Cloud) | 1 SU / 18 nodes / 72 GPU | 8 SU / 144 nodes / 576 GPU |
| `2-8-9-800` | Dedicated-GPU dual-plane (CSL + GSL plane1 + plane2) | 2 SU / 8 nodes / 64 GPU | 32 SU / 128 nodes / 1024 GPU |
| `2-8-9-400-SP` | Dedicated-GPU single-plane (`2-8-9-800` minus GPU plane 2) | 2 SU / 8 nodes / 64 GPU | 32 SU / 128 nodes / 1024 GPU |

The architecture table counts **compute nodes and GPUs**, not all server or
switch VMs. Resource sizing below counts every VM.

**Largescale** = the largest scale verified in Air with this repo — not
necessarily an architecture's maximum. Refer to the official ERA reference
architecture documents for the full supported scale of each design.

## Tested features

| Feature | `2-4-3-200` | `2-8-5-200` / `2-4-5-400` | `2-8-9-400` | `2-8-5-400` | `2-4-5-800` | `2-8-9-800` | `2-8-9-400-SP` |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Collapsed core (single switch pair for E/W + N/S) | ✅ | ✅ | ✅ | ✅ | — | — | — |
| Dedicated GPU (CSL N/S split from GSL E/W) | — | ✅ at scale | ✅ at scale | ✅ at scale | ✅ | ✅ | ✅ |
| Multi-tier (dedicated spine switches) | — | — | ✅ at scale | ✅ at scale | ✅ | ✅ at scale | ✅ at scale |
| Single-plane GPU fabric | — | ✅ at scale | ✅ at scale | ✅ at scale | — | — | ✅ |
| Dual-plane GPU fabric | — | — | — | — | ✅ | ✅ | — |
| L3 OOB underlay + EVPN | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| L3 OOB outbound NAT + HA configuration (not failover) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| STORAGE VRF configuration (Air) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| External storage (STORAGE BGP to the storage peers, storage I/O) | untested | untested | untested | untested | untested | untested | untested |
| EVPN multihoming + anycast gateway | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Inter-VRF DHCP relay configuration (OOB + EXIT) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SSH login banner configuration | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Air deploy — NOZTP (Node Instructions) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Air deploy — ZTP (DHCP server in sim) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Physical ZTP (`deploy_in_air=No`: workbook MAC reservation, no Air infra; see [ZTP_MODES](ZTP_MODES.md#physical-ztp)) | offline tested | implemented | implemented | implemented | implemented | implemented | implemented |
| Switches-only deploy (server VMs omitted) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Controller-from-node (deploy driven from a mgmt node; see [MANUAL_FALLBACK_GUIDE](MANUAL_FALLBACK_GUIDE.md)) | untested | untested | untested | untested | untested | partial: fan-out from utility | untested |
| LDAP (auto-detected from Excel) | ✅ | ✅ | ✅ | untested | ✅ default, L3 OOB, NOZTP | ✅ | untested |
| Status page (HTTP report dashboard) | ✅ | ✅ | ✅ | untested | ✅ | ✅ | ✅ |
| Shipped GPU VLAN mode (all-rail connectivity) | ✅ per_rail | ✅ per_rail | ✅ per_rail | ✅ per_rail | ✅ per_rail_per_plane | ✅ per_rail_per_plane | ✅ per_rail |

Legend: **✅** tested · **✅ at scale** = present/tested only at largescale (not
the default) · **offline tested** = configuration/stub checks, no hardware run
· **implemented** = shared implementation available, no per-architecture
physical deployment evidence · **untested**
= not exercised with this tool · **—** not applicable. Text after a ✅
names the only size, OOB mode or deploy mode that was tested.

Configuration rows mean generated settings were deployed and compared with
running switch configuration. They do not establish NAT failover, multihoming
failure recovery, DHCP leases across every VRF, or every custom banner value.
LDAP and status-page checkmarks retain earlier feature-specific testing; the
October full-scale campaign did not retest those enabled features. For
controller-from-node, the recorded `2-8-9-800` check proved fan-out from
`utility`, not the complete install-and-run-on-node workflow. Physical-ZTP
checks exercised generated configuration and stubbed execution (including
L2/L3 on `2-4-3-200`), not an all-architecture hardware campaign.

**STORAGE VRF configuration (Air)** means the `STORAGE` VRF is generated and
deployed, and the running config matches it in Air. It does not cover the
external storage side: some recorded Air runs end with the `STORAGE` BGP
sessions to the storage peers Idle (a `bgp_storage` WARN; see
`make fix-ext-storage`), and no run measured storage I/O. An earlier
`2-8-9-800` check established the external-storage BGP sessions and exercised `make fix-ext-storage`; that is
not storage-I/O validation, so the combined end-to-end feature remains
listed as untested.

## Resource sizing (NVIDIA Air)

The Air footprint of each architecture at the default and largescale sizes
shipped with this repo. Figures are summed from the generated topology
(`output/<arch>/<site>/topology/`), which is what Air is actually asked to
allocate. `2-4-5-400` shares `2-8-5-200`'s figures **by construction**: it is
the same topology with the same node and switch counts — depopulating GPUs
changes no VM sizing.

Per-node allocation: fabric switches 4 vCPU / 4 GiB; **OOB switches 2 vCPU /
4 GiB**; server nodes 1 vCPU / 1 GiB; storage 20 GB on every node.

> **The OOB figure is a floor, not a preference.** Air enforces each image's
> published `minimum_resources` on cpu, memory *and* storage, and
> `cumulus-vx-5.18.0` and the shipped `cumulus-vx-5.18.3` both declare
> 2 / 4096 / 20 (5.18.3 read back from public Air, 2026-10-06). A node
> below that floor on any single axis causes Air to reject the **entire
> simulation** into state `INVALID`
> with zero nodes — after returning HTTP 200 on import, with no reason
> recorded. Do not trim these values. See ADR-0054.

Size your Air budget above these sums to allow for per-sim overhead.
Figures were re-summed from all 16 shipped topologies on 2026-10-12 and
match the October 7–9 Air campaign allocations. Memory is **GiB** (Air's
MiB values divided by 1024). These are full-server simulations; regenerate
and re-measure after changing node counts, VM resources or the workbook.
The customer-edge count scales with the fabric's EXIT uplink load.

| Arch | Default — nodes / vCPU / mem | Largescale — nodes / vCPU / mem |
|------|-----------------------------:|--------------------------------:|
| `2-4-3-200` | 40 / 55 / 61 GiB | 53 / 69 / 77 GiB |
| `2-8-5-200` | 40 / 55 / 61 GiB | 55 / 77 / 85 GiB |
| `2-4-5-400` | 40 / 55 / 61 GiB | 55 / 77 / 85 GiB |  <!-- identical to 2-8-5-200 by construction -->
| `2-8-9-400` | 32 / 47 / 53 GiB | 113 / 189 / 221 GiB |
| `2-8-5-400` | 31 / 45 / 49 GiB | 59 / 93 / 101 GiB |
| `2-4-5-800` | 55 / 107 / 115 GiB | 237 / 429 / 465 GiB |
| `2-8-9-800` | 31 / 57 / 61 GiB | 221 / 429 / 461 GiB |
| `2-8-9-400-SP` | 29 / 49 / 53 GiB | 197 / 333 / 365 GiB |

Switch VMs dominate at largescale, so a **switches-only** simulation (server VMs
omitted — `make deploy-switches-only`) needs far less, which helps under tighter
Air quotas.

## Related documentation

- [`README.md`](../README.md) — quick start and deployment workflows
- [`EXCEL_CONFIGURATION_GUIDE.md`](EXCEL_CONFIGURATION_GUIDE.md) — Excel field reference
- [`ROLES.md`](ROLES.md) — switch role taxonomy per architecture
- The official NVIDIA ERA reference architecture documents — authoritative topology and scale
