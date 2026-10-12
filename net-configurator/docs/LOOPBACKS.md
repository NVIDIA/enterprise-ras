<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Per-switch / per-VRF loopback overrides

> **Intake-form workbooks (ADR-0064):** there is no separate `Loopbacks`
> sheet. The same per-switch overrides live in the **Switch Data** sheet's
> `Loopback IP`, `OOB lo`, `INBAND (N-S) lo`, `EXIT lo`, `GPU lo`,
> `STORAGE lo` and `ASN` columns, and `loopback_base` is a `Deployment`
> setting. The tool builds the `Loopbacks & ASNs` view described below from
> those columns in memory, so the column semantics here apply unchanged.

By default the parser computes loopback IPs from `loopback_base`
(`Deployment` sheet; `Settings` in the legacy view)
(default `172.16.176`) using an offset pattern per switch and per VRF.
That works for single-plane archs but breaks down for **dual-plane GSL
designs**, where each plane lives in its own /24 (e.g. plane1
`10.1.1.0/24`, plane2 `10.2.1.0/24`) and there's no formula relating
one plane's loopbacks to the other.

Fill the per-switch loopback columns to drive every loopback explicitly.
When present, those values win over the computed defaults — but they are
fully optional and workbooks that leave them blank keep generating
byte-identical output.

## Sheet schema (legacy `Loopbacks & ASNs` view)

This is the shape the parser consumes. Shipped intake-form workbooks do not
contain this sheet: `intake_to_legacy` builds it from the `Switch Data`
columns listed above, one column to one column. **Precedence:** if a workbook
*does* carry a literal `Loopbacks & ASNs` sheet, that sheet is used as-is and
the `Switch Data` loopback / `ASN` columns are ignored for loopback purposes
(`intake_to_legacy.py`: the view is only built when the sheet is absent).
Keep one source — use the `Switch Data` columns and do not add this sheet.

Sheet name: **`Loopbacks & ASNs`** (the legacy name `Loopbacks` is still
accepted). Matched by any sheet whose name starts with `Loopbacks`.

One row per switch. The header row is the first row whose column-1
cell starts with `Switch` (case-insensitive). Column headers are
matched case-insensitively; unknown headers are warned and ignored.

| Switch | Default | OOB | INBAND | EXIT | GPU | STORAGE | ASN |
|---|---|---|---|---|---|---|---|
| core-01 | 172.16.176.11/32 | 172.16.176.151/32 | 172.16.176.167/32 | 172.16.176.183/32 | 192.168.110.5/32 | 172.16.176.199/32 | 4260394788 |
| core-02 | 172.16.176.12/32 | 172.16.176.152/32 | 172.16.176.168/32 | 172.16.176.184/32 | 192.168.110.6/32 | 172.16.176.200/32 | 4260394788 |
| gsl-plane1-01 | 10.1.1.1/32 | | | | 10.1.1.21/32 | | 4260395888 |
| gsl-plane1-02 | 10.1.1.2/32 | | | | 10.1.1.22/32 | | 4260395888 |
| gsl-plane2-01 | 10.2.1.1/32 | | | | 10.2.1.21/32 | | 4260396888 |
| gsl-plane2-02 | 10.2.1.2/32 | | | | 10.2.1.22/32 | | 4260396888 |

The values above are also what the parser computes when the cells are left
blank — see [Computed defaults](#computed-defaults--block-map).

- **Switch** — hostname, must match the `Name` column on the Switch Data sheet.
- **Default** — the underlay loopback (`lo_ip` + underlay BGP router-id).
- **OOB / INBAND / EXIT / GPU / STORAGE** — per-VRF loopbacks.
- **ASN** — the switch's BGP autonomous-system number (see
  [Per-node BGP ASN](#per-node-bgp-asn) below).
- Blank cells fall back to the computed default — override only the
  values you care about.
- `/32` mask is auto-appended when omitted (loopback columns).
- Header aliases accepted: `Default` / `lo` / `Loopback`; `In-Band` for
  INBAND; `ASN` / `BGP ASN` / `Autonomous System` for the ASN column.

## Computed defaults — block map

Where a cell is blank, the parser allocates from a **declared block** whose
capacity is checked. Each role and each VRF owns a contiguous range, so a
series can never grow into its neighbour; outgrowing a block raises a
parse-time error naming the block rather than silently issuing a duplicate
/32. Both tables live in `scripts/excel_parser.py`.

**N/S fabric**, within `Settings.loopback_base`'s /24 (`VRF_LOOPBACK_BLOCKS`,
`n` = switch index):

| Range | Contents |
|---|---|
| `.11 - .60` | N/S leaf switch loopbacks |
| `.61 - .100` | N/S spine switch loopbacks |
| `.101 - .150` | OOB switch loopbacks |
| `.151 - .166` | OOB VRF loopback — `.150 + n` |
| `.167 - .182` | INBAND VRF loopback — `.166 + n` |
| `.183 - .198` | EXIT VRF loopback — `.182 + n` |
| `.199 - .214` | STORAGE VRF loopback — `.198 + n` |
| `.215 - .230` | GPU VRF loopback — `.214 + n` |
| `.231 - .254` | spare |

The GPU row applies to switches that actually run the GPU VRF on the N/S
fabric — the cores of a collapsed or converged arch. A `csl` in a dedicated-GPU
arch has no GPU VRF at all (the E/W switches own it), so it gets no GPU
loopback.

> **GPU used to be the exception here.** It took its loopback from the first GPU
> VLAN's subnet, at `<gpu-subnet>.4 + n`, so `core-01` landed on `192.168.0.5`.
> That is a tenant subnet with two other allocators in it — per-switch SVIs
> counting up from `.2`, and host addresses from `.50` — and at four cores
> `core-04`'s SVI and `core-01`'s loopback were both `.5`. It is the same
> duplicate-`/32` failure that motivated the `.151+` re-space, on the one VRF
> that re-space skipped. If you pinned a GPU loopback inside a rail subnet to
> match the old default, move it into the block above; `make validate-excel`
> now reports it as an error.

**E/W plane fabric**, within each plane's own /24 (`PLANE_LOOPBACK_BLOCKS`,
`n` = the switch's trailing index):

| Range | Contents |
|---|---|
| `.1 - .20` | `gl` / `gsl` leaf switch loopback — `.0 + n` |
| `.21 - .40` | `gl` / `gsl` GPU VRF loopback — `.20 + n` |
| `.41 - .50` | `gs` spine switch loopback — `.40 + n` |
| `.51 - .60` | `gs` GPU VRF loopback — `.50 + n` |
| `.61 - .254` | spare |

Leaf capacity is 20 and spine capacity 10, both above the largest shipped
plane (16 leaves, 8 spines), so a plane can grow without a re-space.

> **Upgrading from an older workbook.** Both layouts previously used narrow
> strides — N/S VRFs at `.n`/`.2 + n`/`.4 + n`, and on a plane the GPU VRF at
> `.10 + n` with `gs` spines at `.4 + n`. Those only stay disjoint on a small
> fabric; at scale they overlapped each other and the switch loopbacks. If you
> hand-authored a sheet against the old pattern, move it onto the blocks above.
> `make validate-excel` reports any pinned value that lands outside its block,
> so you can fix them one at a time until it reports clean.

## Behavior

| Sheet state | Behavior |
|---|---|
| Sheet absent | Computed defaults (current behavior). |
| Sheet present, no row for switch | Computed defaults for that switch. |
| Sheet present, row exists, cell blank | Computed default for that VRF. |
| Sheet present, row exists, cell populated | Excel value wins. |

Fully backward-compatible — existing Excels without a Loopbacks sheet
produce byte-identical output.

## Validation

`make validate-excel` runs these checks when the sheet is present:

- **Format** — every populated cell must parse as a valid IPv4 address
  (`/mask` optional; defaults to `/32`).
- **Switch cross-reference** — switch names should appear in the
  Switch Data sheet (warn on unknowns).
- **Unknown columns** — warned and ignored.
- **Duplicate IPs** — no two switches may share a Default loopback or
  the same per-VRF loopback (error).
- **VLAN-subnet overlap** — no loopback IP may fall inside a VLAN
  subnet owned by a *different* VRF (error), and a GPU loopback may not
  fall inside a GPU rail subnet either. That case was previously allowed
  because the parser computed exactly that address; it now allocates from
  the block map above, so a rail-subnet loopback is the collision this
  check exists to catch.
- **`loopback_base` sanity** — if `Settings.loopback_base` is set,
  Default IPs outside it produce one warning per divergent /24. The
  expected dual-plane layout is exempt: `gl-planeN-*` / `gs-planeN-*`
  switches inside their own plane block `10.N.1.0/24`, and `gsl-planeN-*`
  / `csl-*` switches. A plane switch in another plane's block, or in any
  other /24, still warns. It is a warning, not an error, because a
  custom plan may diverge on purpose.

## Per-node BGP ASN

The **ASN** column is the home for each switch's BGP autonomous-system
number. The shipped default workbooks populate it explicitly (one value per
switch), and `Settings.bgp_asn` has been **removed** — the tab is the single
source. Edit any cell to assign an arbitrary ASN to that switch (e.g. a
pre-allocated customer plan). A blank cell falls back to the derived value;
an older workbook that still carries `Settings.bgp_asn` keeps working (that
value is the derivation base). The parser recovers the fabric base from the
tab when `Settings.bgp_asn` is absent.

All BGP sessions are unnumbered (`remote-as external`/`internal`), so an
override only changes that switch's *local* ASN; neighbors auto-adapt. The
one constraint is numeric, and `validate_excel` enforces it:

- **Equal-within** — switches the tool requires to *share* an ASN must all
  get the same value (or all be left blank). These shared groups are:
  - converged core/csl (single-tier `ns_tiers=1`) — one iBGP fabric;
  - each collapsed GPU plane (≤2 leaves) — the leaf-mate pair peers iBGP;
  - each `gs` spine pair.
  Splitting a shared group (e.g. two collapsed-plane mates with different
  ASNs) is a **hard error** — their iBGP sessions would go Idle.
- **Distinct-across** — no two different groups may share an ASN (eBGP peers
  must differ; duplicate leaf ASNs also cause EVPN AS-path loop drops). A
  collision is a **hard error**.
- **Range** — a positive 4-byte integer (`1 … 2³²−1`), not the reserved
  `23456`.
- Setting an ASN on *some* members of a shared group but not others is a
  **warning** — set all or none.

Value semantics per the table above: converged core/csl rows all carry the
base ASN; collapsed-plane mates share one per-plane ASN; `oob-switch-*`,
`cs`, spined GPU leaves, and dedicated `cl` leaves each take a unique value.

## What this does NOT change

- `Settings.loopback_base` still works as a project-wide default. The
  Loopbacks sheet layers on top of it.
- BGP / EVPN topology, VRF semantics, and GSL plane numbering are
  unchanged — only the loopback IPs and (optionally) each switch's BGP ASN.

## Known limitation — supernet prefix-list rules

When the Loopbacks sheet overrides individual loopback IPs, the
per-VRF prefix-list rules (`EXIT_LOCAL_IF`, `INBAND_LOCAL_IF`,
`INBAND_PREFIXES`, `LOCAL_OOB_LOOPBACK`, `OOB_LOCAL_IF`,
`OOB_PREFIXES`) automatically track the override IPs — they read
the post-override loopbacks. However, the **supernet** rules stay
tied to `Settings.loopback_base`:

- `ERA_PREFIXES rule 10` = `{loopback_base}.0/21`
- `ERA_PREFIXES rule 20` = `{loopback_base}.0/24`
- `VTEP_PREFIXES rule 5` = `{loopback_base}.8/29`

If your overrides put loopbacks in a different subnet from
`loopback_base`, those supernet rules won't cover the actual
loopback IPs and the corresponding `OUTBOUND_ERA_PREFIXES` /
inter-AS advertisement may not match. Two ways to handle this:

1. **Set `Settings.loopback_base` to a subnet that covers the
   overrides** (works when all overridden loopbacks share a /21
   or /24).
2. **Override the prefix lists explicitly** via the `Prefix lists`
   Excel sheet (Option C) — that path replaces the whole rule list
   for the named prefix-list and bypasses computation entirely.

For dual-plane GSL archs where loopbacks span multiple /24s
(plane1 `10.1.1.0/24`, plane2 `10.2.1.0/24`, core `10.187.4.0/24`)
the supernet rules can't cover all three from a single
`loopback_base`. In that case the Prefix lists sheet override is
the right tool.

## Deferred — anycast loopbacks

The Loopbacks sheet covers per-switch, single-IP overrides only. Some
customer deployments layer an additional anycast
VRF loopback shared across the spine pair, used as a stable service IP
inside an L3-routed OOB design. That whole feature — L3 OOB switch
support plus anycast-aware schema — is **not in v1**.
