<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Per-switch / per-VRF loopback overrides

By default the parser computes loopback IPs from `Settings.loopback_base`
(default `172.16.176`) using an offset pattern per switch and per VRF.
That works for single-plane archs but breaks down for **dual-plane GSL
designs**, where each plane lives in its own /24 (e.g. plane1
`10.1.1.0/24`, plane2 `10.2.1.0/24`) and there's no formula relating
one plane's loopbacks to the other.

Add an optional **Loopbacks** sheet to the Excel input to drive every
loopback explicitly. When present, its values win over the computed
defaults — but the sheet is fully optional and existing Excels keep
generating byte-identical output.

## Sheet schema

Sheet name (case-sensitive): **`Loopbacks`**.

One row per switch. The header row is the first row whose column-1
cell starts with `Switch` (case-insensitive). Column headers are
matched case-insensitively; unknown headers are warned and ignored.

| Switch | Default | OOB | INBAND | EXIT | GPU |
|---|---|---|---|---|---|
| core-01 | 172.16.176.11/32 | 172.16.176.1/32 | 172.16.176.3/32 | 172.16.176.5/32 | 192.168.110.5/32 |
| core-02 | 172.16.176.12/32 | 172.16.176.2/32 | 172.16.176.4/32 | 172.16.176.6/32 | 192.168.110.6/32 |
| gsl-plane1-01 | 10.1.1.1/32 | | | | 10.1.1.11/32 |
| gsl-plane1-02 | 10.1.1.2/32 | | | | 10.1.1.12/32 |
| gsl-plane2-01 | 10.2.1.1/32 | | | | 10.2.1.11/32 |
| gsl-plane2-02 | 10.2.1.2/32 | | | | 10.2.1.12/32 |

- **Switch** — hostname, must match the `Name` column on the Nodes tab.
- **Default** — the underlay loopback (`lo_ip` + underlay BGP router-id).
- **OOB / INBAND / EXIT / GPU** — per-VRF loopbacks.
- Blank cells fall back to the computed default — override only the
  values you care about.
- `/32` mask is auto-appended when omitted.
- Header aliases accepted: `Default` / `lo` / `Loopback`; `In-Band` for
  INBAND.

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
  Nodes tab (warn on unknowns).
- **Unknown columns** — warned and ignored.
- **Duplicate IPs** — no two switches may share a Default loopback or
  the same per-VRF loopback (error).
- **VLAN-subnet overlap** — no loopback IP may fall inside a VLAN
  subnet owned by a *different* VRF (error). A GPU VRF loopback inside
  the GPU VLAN subnet is allowed because that's how the parser
  computes the default.
- **`loopback_base` sanity** — if `Settings.loopback_base` is set,
  Default IPs outside it produce one warning per divergent /24.
  Dual-plane archs intentionally diverge, hence warn not error.

## What this does NOT change

- `Settings.loopback_base` still works as a project-wide default. The
  Loopbacks sheet layers on top of it.
- BGP / EVPN topology, VRF semantics, and GSL plane numbering are
  unchanged — only the IPs assigned to loopback interfaces.

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
customer deployments (notably prod-285200) layer an additional anycast
VRF loopback shared across the spine pair, used as a stable service IP
inside an L3-routed OOB design. That whole feature — L3 OOB switch
support plus anycast-aware schema — is **not in v1**. See the project
TODO doc for the design notes.
