<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Architecture Support Matrix

Authoritative reference for what the ERA automation supports today,
arch by arch. Sourced from the NVIDIA ERA architecture PDFs
(ERA-000{08,10,11,16}), the scaling table in `scripts/arch_scaling.py`,
and the default-template shipping configurations in
`input/<arch>/default/<arch>.xlsx`.

When the spec and the implementation disagree, both are listed
side-by-side. The codebase is the truth for what runs today; the
spec column says what the operator could reasonably expect to ask
for.

## Architectures

| Arch | ERA doc | Topology | Default-template SU | `arch_scaling.py` max single-tier | Notes |
|------|---------|----------|---------------------|-----------------------------------|-------|
| `2-4-3-200` | ERA-00008-001 v03 | Collapsed `core` (E/W + N/S converged) | 1–8 SU shipped | **8 SU** | Reference architecture for L3 OOB E2E verification (`l3-smoke` site). |
| `2-8-5-200` | ERA-00016-001 v03 | Collapsed `core` only | 1–5 SU shipped | **5 SU** | Doc explicitly defines this arch as collapsed across its full range. |
| `2-8-9-400` | ERA-00010-001 v03 | Collapsed `core` (≤3 SU) <br> *Doc also defines:* dedicated-GPU CSL+GSL (SU≥4) <br> *Doc also defines:* super-spine (≥64 nodes) | 1–3 SU shipped | **3 SU** | **Gap:** doc supports up to 32 SU with dedicated-GPU + super-spine; codebase only implements collapsed up to 3 SU. |
| `2-8-9-800` | ERA-00011-001 v04 | Dedicated-GPU dual-plane (CSL + GSL plane1 + GSL plane2) | 1–2 SU shipped | **4 SU** (arch) / **2 SU** (template) | **Gap:** template only ships GSL fan-out for SU≤2 (plane1↔plane2 ISLs consume plane2 high-port range). SU=3–4 requires ISL rebalance — see `scripts/scale_sample_excel.py` NOTE. |

## Feature × Arch matrix

| Feature | `2-4-3-200` | `2-8-5-200` | `2-8-9-400` | `2-8-9-800` |
|---------|:---:|:---:|:---:|:---:|
| **Collapsed core** (single switch pair for E/W + N/S) | ✅ default | ✅ default | ✅ default | — (not architecturally valid) |
| **Dedicated GPU** (CSL N/S split from GSL E/W) | — | — | ⚠️ doc-only, **not implemented** | ✅ default |
| **Single plane** (one GSL pair) | n/a (collapsed) | n/a (collapsed) | n/a (collapsed) | ⚠️ doc-supportable, **not implemented** (suppressing plane2 on 2-8-9-800 is off-spec) |
| **Dual plane** (plane1 + plane2 GSL pairs) | — | — | — | ✅ default |
| **Super-spine** (≥64 nodes) | — | — | ⚠️ doc-only | — |
| **L3 OOB uplink** (`oob_uplink_mode=l3`) | ✅ live-verified (`l3-smoke`) | ✅ codebase supports, untested | ✅ codebase supports, untested | ✅ codebase supports, untested *(this MR / `s2` site)* |
| **L3 OOB outbound NAT + HA** | ✅ live-verified 2026-05-23 | untested | untested | untested |
| **STORAGE VRF first-class** | ✅ | ✅ | ✅ | ✅ (shipped 2026-05-19) |
| **EVPN MH + anycast** | ✅ | ✅ | ✅ | ✅ |
| **Air NOZTP mode** (Node Instructions before sim boot) | ✅ | ✅ | ✅ | ✅ |
| **Air ZTP mode** (DHCP server inside sim) | ✅ | ✅ | ✅ | ✅ |
| **LDAP (auto-detected from Excel)** | ✅ | ✅ | ✅ | ✅ |
| **Status page (HTTP on `dhcp-oob`)** | ✅ | ✅ | ✅ | ✅ |
| **`gpu_vlan_mode=per_rail` / `per_rail_per_plane`** | ✅ | ✅ | ✅ | ✅ |

Legend: ✅ supported & exercised · ⚠️ partial/gap · — not applicable

## ERA-doc citations

| Arch | Spec verdict | Citation |
|------|-------------|----------|
| `2-4-3-200` | Collapsed; ≤8 SU | ERA-00008-001 v03 §"4-32 Nodes" + Table 10 (p26) |
| `2-8-5-200` | Collapsed only; ≤5 SU | ERA-00016-001 v03 p25 ("Compute Fabric is merged with the Converged Fabric for smaller design points"); p29 ("collapsed Spine-Leaf design"); p33 ("collapsed and converged spine-leaf design for all the required fabrics"); p48 single SN5610 pair port layout |
| `2-8-9-400` | Collapsed (≤3 SU) → dedicated-GPU CSL+GSL (4–48 SU) → super-spine (≥64 nodes) | ERA-00010-001 v03 p31 ("collapsed spine-leaf design for all fabrics except for the GPU Compute (E/W) Fabric"); p32 (super-spine for 64+ nodes); Table 10 (p28) |
| `2-8-9-800` | Dedicated-GPU dual-plane from SU=1 | ERA-00011-001 v04 §Architecture; Table 15 (p44) |

## SU scaling cheat sheet

```
arch_scaling.py — single-tier maxes (from ARCH_SCALING):
  2-4-3-200 : 1-4 SU (2 OOB),  5-6 SU (3 OOB),  7-8 SU (4 OOB, ISL active)
  2-8-5-200 : 1-4 SU (2 OOB),  5-5 SU (3 OOB)
  2-8-9-400 : 1-2 SU (2 OOB),  3-3 SU (3 OOB) — narrative treats ≥4 SU as multi-tier
  2-8-9-800 : 1-4 SU (2 OOB, dual-plane, no spine) — template only supports ≤2 SU
```

## Known gaps (worth their own MR)

| Gap | Arch | Effort | Tracking |
|-----|------|--------|----------|
| **2-8-9-400 dedicated-GPU variant** (CSL + GSL split, SU≥4) | `2-8-9-400` | High — new ScalingTier, new `csl.yml`/`gsl.yml` group_vars + 4 new host_vars, parser+template adjustments | (none yet) |
| **2-8-9-800 single-plane variant** (suppress plane2) | `2-8-9-800` | Medium — needs `gpu_planes=1` path through topology generator, validator changes, OEM-audit found this is confusing | (none yet — discussed in OEM audit; user agreed this should be its own MR) |
| **2-8-9-800 SU=3–4 template fan-out** (rebalance plane1↔plane2 ISLs or add GSL leaves) | `2-8-9-800` | Medium — adjust default-template Wire Map, retest `validate_excel` tier-mismatch warning | NOTE in `scripts/scale_sample_excel.py` |
| **Super-spine deployments (≥64 nodes)** | `2-8-9-400` | Very high — new tier in arch_scaling, new spine role, multi-MR rollout | (none yet) |
| **Multi-subnet OOB in L3 mode** (`mgmt_subnets` list when `oob_uplink_mode=l3`) | All | Medium — L2 path works today; L3 path has 3 hardcoded single-subnet assumptions (oob-switch SVI in template, `_inject_l3_oob_nodes` puts utility:eth1 on one switch only, dnsmasq scope ↔ broadcast-domain). Three-MR rollout: per-host SVI in template, DHCP-relay on OOB switches forwarding to utility, topology-generator wiring. | (none yet — note added to `mgmt_subnets` Excel description in all 4 default Excels; multi-subnet L2 is tested + works, L3 use 1 subnet only) |

## How to use this matrix

- **Before adding a new feature to an Excel template**, check the
  Feature × Arch table. If the feature is "—" for the arch, the
  parser/templates will most likely reject it (or silently produce
  wrong output).
- **Before promising a customer an SU count**, check
  `arch_scaling.py`'s single-tier max AND the default-template SU
  shipped (the latter is the practical max without code changes).
- **When closing a Known Gap**, update both the Feature × Arch
  table and the Known Gaps section in the same MR. The matrix is
  meant to stay current — stale rows are worse than missing ones.

## Related references

- `scripts/arch_scaling.py` — code authoritative source for SU caps
- The NVIDIA ERA architecture PDFs (ERA-000{08,10,11,16}) — the spec source-of-truth
- `docs/EXCEL_CONFIGURATION_GUIDE.md` — Excel field reference
- `README.md` § "Architecture naming" — naming conventions
