<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# ERA Excel Configuration Guide

This guide explains how to fill out the ERA intake form, the workbook that drives the entire switch configuration pipeline. Every sheet and every convention is documented here so you can complete it confidently before running `make import`.

---

## How the intake form works

The ERA automation follows a single-source-of-truth model:

1. Copy a ready-to-use sample for your architecture (`input/sample-<arch>.xlsx`, or `input/largescale-<arch>.xlsx`) to your own path. The committed defaults under `input/<arch>/default/` are reference templates — do not edit them directly.
2. Fill in site-specific values: IPs, VLANs, node names, cabling.
3. Run `make import EXCEL=<path>` to import and `make generate ARCH=<type>` to produce Ansible inventory, NVUE CLI switch configs, and an NVIDIA Air topology.
4. Deploy the generated configs via ZTP or push them straight to the switches.

The **intake form is the only input format** (ADR-0064). It has seven sheets:

| Sheet | You fill in | Purpose |
|-------|-------------|---------|
| **Read Me** | no | Pointers to the docs. Read-only. |
| **Wiremap** | **yes** | Physical cabling — every link, both ends |
| **Network Data** | **yes** | VLANs, plus VRFs, Port Profiles and DHCP Relay as sub-tables |
| **Switch Data** | **yes** | One row per switch: management IP, loopbacks, ASN, ZTP MAC |
| **Host Data** | **yes** | One row per non-switch device and its interfaces |
| **Deployment** | **yes** | Global settings, Cumulus versions, Air image map |
| **Derived** | no | What the tool computed from the wiremap, and from what. Read-only. |

Five further sheets are optional and read only if present — `Prefix lists`, `Route policy`, `Community lists`, `ACLs`, `Custom_Config`. They are omitted from the standard workbooks; see [Optional override sheets](#optional-override-sheets).

### Two settings you cannot declare

`gpu_planes` and `convergence` are **derived from the Wiremap**, not authored. A declared value could contradict the cabling, which is the bug class this removes — so there is nowhere to declare one. The read-only `Derived` sheet shows what was computed and which rows it came from.

### If you have an older workbook

Workbooks in the pre-2026-09 layout — the ones with `Settings`, `Nodes`, `VLANs & Profiles` and `Wire Map` sheets — are no longer read. Convert once:

```bash
make convert-workbook EXCEL=/path/to/legacy.xlsx     # writes <name>.intake.xlsx
make convert-workbook ARCH=2-8-9-800 [SITE=default]  # or by architecture
```

Then point `make import` / `make generate` at the converted file. The converter is transitional and is removed at `nc-v10`, so migrate rather than relying on it. See [Migrating a legacy workbook](#migrating-a-legacy-workbook).

---

## Sheet 1: Read Me

A table of links to the documentation. Nothing to fill in.

---

## Sheet 2: Wiremap

The physical cabling, one row per link, both ends on the same row. This is the most important sheet: the topology, the port configuration and two derived settings all come from it.

Columns are grouped under two banners, **Source** (the `(A)` side) and **Destination** (the `(Z)` side), with the header on row 2:

| Column | Side | Required | Notes |
|--------|------|----------|-------|
| `DC Location`, `Rack`, `RU` | both | no | Physical placement. Recorded, not consumed. |
| `System Name` | both | **yes** | Device name. Must match a `Switch Data` or `Host Data` row. |
| `Interface Type` | both | no | Free text |
| `Port` | both | **yes** | Switch ports are `swpN` / `swpNsM`; host ports are the vendor's label (`OCP 3.0 SL1 Port 1`, `CX8 Baseboard 1 Port 1`, `XCC`) |
| `Transceiver` | both | no | Recorded, not consumed |
| `Port Side` | both | no | Switch breakout sub-port: which of the cable's two cages it is in (`1` or `2`). Unsplit switch port: `NA`. Host end: the E/W plane, or `NA`. Recorded, not consumed |
| `Cable Split` | both | no | Switch breakout sub-port: which lane of that cage (`1`–`4`). `NA` for an unsplit port or a host end. Recorded, not consumed |
| `Network Profile` | — | **yes** | Must match a `Port Profiles` row or a VLAN's fabric name |
| `Cable Length (m)`, `Cable Type`, `Cable SKU` | — | no | Recorded, not consumed |
| `Display in Air` | — | **yes** | `Yes` puts the link in the Air topology, `No` omits it |

**`Display in Air` is load-bearing.** A blank cell is not treated as `Yes`: the link silently vanishes from the Air topology and the OOB cabling check fails with no obvious cause.

**All-`No` GPU/CPU links on an SU draw a warning.** If every GPU and CPU/in-band row of an SU's compute nodes is `No`, the Air sim builds those nodes with an OOB link and no data-plane at all — almost always a copy-paste slip. `validate-excel` / `generate` warn once per SU (only when `deploy_in_air` is `Yes`) and, when run interactively, ask `Set Display in Air = Yes on these N GPU/CPU rows? [y/N]`. Answering `y` backs the workbook up to `archive/<date>/` and flips exactly those rows to `Yes`, then re-validates. For scripted runs pass `AIR_DISPLAY_FIX=yes` (or `no`) — e.g. `make generate ARCH=2-8-5-200 AIR_DISPLAY_FIX=yes`; a non-interactive run without it only warns and never touches the file. A single `Yes` anywhere in the SU is enough — hiding *some* links is fine.

**Port Side and Cable Split follow the breakout.** A W-way breakout cable leaves the switch in two cages of W/2 lanes each, so sub-port `swpNsM` is Port Side `M // (W/2) + 1` and Cable Split `M % (W/2) + 1`:

| Breakout | `s0` | `s1` | `s2` | `s3` | `s4` | `s5` | `s6` | `s7` |
|----------|------|------|------|------|------|------|------|------|
| 2x | 1 / 1 | 2 / 1 | | | | | | |
| 4x | 1 / 1 | 1 / 2 | 2 / 1 | 2 / 2 | | | | |
| 8x | 1 / 1 | 1 / 2 | 1 / 3 | 1 / 4 | 2 / 1 | 2 / 2 | 2 / 3 | 2 / 4 |

(Port Side / Cable Split.) Write whole numbers. `validate-excel` warns, naming the cell, when a value disagrees with the port's breakout; a blank or `NA` value is not checked. No switch or host configuration is generated from either column.

**Row order matters for hosts.** Host interfaces are numbered in the order their rows appear — `eth0` is reserved for OOB management and data-plane NICs start at `eth1`.

---

## Sheet 3: Network Data

One sheet, four stacked tables. The first starts at row 1; the others are found by their title cell in column A, so you can add or remove rows without breaking anything.

### VLANs (rows from row 2)

| Column | Required | Notes |
|--------|----------|-------|
| `Fabric Name` | **yes** | Referenced by `Network Profile` in the Wiremap |
| `Use` | no | Human description |
| `VLAN` | **yes** | VLAN ID |
| `VNI(D)` | **yes** | EVPN VNI |
| `VRF` | **yes** | Must match a `VRFs` row |
| `IP Subnet` | **yes** | CIDR |
| `Gateway Addr` | **yes** | Must sit inside `IP Subnet` |
| `Comments` | no | |
| `DHCP Relay Client` | no | VRF name to relay into, or `No` |

### VRFs

`VRF Name` · `Description` · `L3 VNI` · `VLAN`

The L3 VNI and its VLAN are per-VRF and must not collide with an L2 VLAN.

### Port Profiles

`Profile` · `Port Mode` · `Native/Access VLAN` · `Allowed VLANs` · `Untagged VLAN` · `VRF` · `LACP Bypass` · `Speed` · `Breakout` · `Lanes` · `Auto-Negotiate`

`Profile` is what the Wiremap's `Network Profile` column refers to. `Speed`, `Breakout` and `Lanes` are authoritative — they override the tool's per-role hardware defaults, so a wrong value here silently produces wrong port config.

### DHCP Relay

`Server IP` · `VRF` · `Upstream Interface`

The VRF must be one the relay server is actually reachable in.

---

## Sheet 4: Switch Data

One row per switch. Grouped headers on row 1 (`Switch`, `Switch IP's`, `L3`, `L2`) with the real header on row 2.

| Column | Required | Notes |
|--------|----------|-------|
| `Function` | **yes** | Role: `csl`, `gsl-plane1`, `core`, `oob-switch`, … Drives which template applies. |
| `Name` | **yes** | Hostname |
| `ZTP MAC Address` | for ZTP | The switch's MAC, how ZTP identifies it |
| `Mgmt IP`, `Mgmt Gateway` | **yes** | OOB management address |
| `Loopback IP` | **yes** | Router loopback |
| `Router-ID` | no | Defaults to the loopback |
| `ASN` | **yes** | BGP ASN. A pair sharing an MLAG/ES shares an ASN. |
| `OOB lo`, `INBAND (N-S) lo`, `EXIT lo`, `GPU lo`, `STORAGE lo` | per-VRF | Per-VRF loopbacks. Blank = the tool's computed default from `loopback_base`. |
| `OOB in`, `CPU (N-S) int`, `Support int`, `Storage int`, `GPU (E-W) int` | no | Per-VRF SVI addresses where the switch needs one |
| `OOB VLAN`, `Prefix` | **yes** | The management VLAN and its mask length |
| `ZTP` | **yes** | `Yes` to provision via ZTP |
| `Enabled` | **yes** | `No` keeps the row as a placeholder — ports stay provisioned, no config is generated |
| `Notes` | no | |

**A device is a switch because it has a `Switch Data` row**, not because of its `Function`. `edge` and `air-oob` devices are switch-like but live in `Host Data`, because they carry no loopback.

---

## Sheet 5: Host Data

One row per interface of every non-switch device — servers, storage, and the Air-only infrastructure nodes.

| Column | Required | Notes |
|--------|----------|-------|
| `System Name` | **yes** | Must match the Wiremap |
| `Physical Interface` | **yes** for addressed rows | The NIC port |
| `Logical Interface` | no | Bond or VLAN interface the address sits on |
| `IP`, `Prefix`, `Gateway` | for addressed rows | |
| `NICOSName` | no | The name the host OS gives the NIC |
| `Mac Address` | for ZTP/Air | |
| `Profile` | no | Port profile for this interface |
| `Function` | **yes** | `edge`, `external-conn`, `utility`, `dhcp`, … |
| `Type` | **yes** | `switch` or `node` |
| `ZTP` | **yes** | |
| `Enabled` | **yes** | `Yes`, `No`, or **`Air`** — `Air` means the row exists only in Air simulations |
| `OOB VLAN` | no | |
| `Notes` | no | |

`Enabled = Air` is how the Air-only infrastructure (`external-conn`, `external-dhcp`, `utility`, `cust-net-edge-*`) stays out of a physical deployment while remaining in the simulation.

### Data-plane addresses: declared if filled, allocated if blank (ADR-0034)

The `eth0` row of a host (or its single blank-`Logical Interface` row in the
one-row-per-host form) is the **management** row; its `IP` is the OOB address.
Every other row of that host is a **data-plane** interface:

| `Logical Interface` | Host `Function` | Address it carries |
|---------------------|-----------------|--------------------|
| `bond0` | `GPU` (compute) | CPU/In-Band bond |
| `bond0` / `bond1` | `Storage` | Storage bond 1 / bond 2 |
| `bond0` / `bond1` | `Support`, `k8s`, `bcme` | Support bond 1 / bond 2 |
| `ethN` (matches `NICOSName`) | `GPU` | that GPU NIC, on its rail/plane VLAN per the Wire Map profile |

- **Blank `IP`** — the tool allocates the address exactly as it always has.
  Every shipped workbook is blank here, so nothing changes for existing sites.
- **Filled `IP`** — the address is used as written (with or without `/prefix`;
  a prefix must equal the VLAN's). It must sit inside that interface's VLAN,
  and must not be the network/broadcast address, the VLAN gateway, a switch
  SVI the fabric reserves, or (GPU VLANs) an address below the fixed GPU host
  start. Every row of the same bond that is filled must hold the same address.
  Two rows may not declare one address, and a declaration may not equal an
  address the tool allocated to a host whose cell is blank — that is reported
  as a collision naming both hosts, not silently shuffled.
- `make validate-excel` and `make generate` apply the same rules, and
  `generate` refuses to write anything until every declaration passes.

The completed workbook produced by `emit_complete_workbook.py` fills every
data-plane `IP`. Feeding it back in freezes that allocation: each filled cell
is then a declaration under the rules above.

---

## Sheet 6: Deployment

Key/value settings, one per row: name in column A, value in column B. Rows in **UPPERCASE** with no value are section headers — `GENERAL`, `AIR DEPLOYMENT`, `NETWORK`, `MANAGEMENT`, `TELEMETRY`, `ADVANCED`, `VERSIONS`. Lines beginning `#` are instructions and are skipped.

| Setting | Notes |
|---------|-------|
| `site_name`, `architecture` | Identify the deployment. `architecture` must match a supported arch. |
| `deploy_in_air`, `status_page_enabled` | Air behaviour. `deploy_in_air` defaults to `Yes` when the row is absent. A row that is present but blank is not `Yes`: it builds the physical variant, so write `Yes` or `No`; set `No` for a physical site ([physical ZTP](ZTP_MODES.md#physical-ztp)). `status_page_enabled` defaults to `No`. |
| `ns_tiers`, `ew_tiers` | Fabric tier counts |
| `loopback_base` | The /24 loopbacks are computed from when a per-switch cell is blank |
| `disabled_ports` | Comma-separated physical port numbers (1–64) to shut down, e.g. `60, 62, 64`; blank uses the arch default |
| `gpu_vlan_mode` | e.g. `per_rail_per_plane` |
| `oob_uplink_mode` | `L2` or `L3` — selects which OOB infrastructure is built |
| `ldap_*` | LDAP, when `ldap_enabled` is `Yes` |
| `netq_ip` | *(inert — omit)* no NetQ agent configuration exists in the tool; `make validate-excel` warns if set |
| `timezone`, `ntp_servers` | |
| `pre_login_message`, `post_login_message` | Banners. `{hostname}`, `{site}`, `{arch}` are substituted. |
| `mh_mac`, `anycast_mac` | EVPN multihoming and anycast MACs |
| `ztp_server` | *(inert)* nothing reads it in either OOB uplink mode — the OOB-subnet ZTP reservation is fixed at `.100` and inventory `ztp_server_ip` comes from `scripts/inventory_defaults.yml`; `make validate-excel` warns if set to anything else |
| `num_physical_ports` | Ports on the switch model |

Two further blocks live at the bottom of the same sheet:

- **VERSIONS** — Cumulus version per switch role (`core`, `oob`, `csl`, `gsl`).
- **AIR DEPLOYMENT** — Cumulus version → Air image name, plus `Air Management Subnet`.

### Where the Air infrastructure gets its addresses

The Air-only nodes (`dhcp-oob`, `oob-server-01`/`utility`, the L3
`external-dhcp` foot, switch `eth0`s and ext-storage `eth0`s) are **not**
Excel rows; `make import` places them on the OOB VLAN subnet(s) and on the
`Air Management Subnet` from the addresses that are still free after every
declared host, gateway and switch SVI has been claimed (ADR-0084). On the
default `/24`s that is the historical `.78` / `.77` / `.201+` / `.79+`; on a
smaller subnet (a `/26` OOB VLAN, say) they take the first free host instead
of overflowing past the broadcast. The result is written to
`group_vars/all/main.yml` as `infra_addresses:` (one `oob` entry per OOB
subnet with its gateway and infra nodes, plus `air_mgmt`) and is what `air-deploy` configures, so the inventory is the
place to look for what the sim actually uses.

---

## Sheet 7: Derived (read-only)

`Setting` · `Derived value` · `Derived from`.

What the tool computed from the Wiremap rather than reading from Deployment, and the evidence for each. Editing it has no effect — it is regenerated on every import. It exists so a reviewer can see *why* a value is what it is without reading the parser.

---

## Optional override sheets

Three of the five optional sheets let you override or extend the BGP prefix-lists,
route-maps, and community-lists the generator computes by default.
All three are **derive-by-default**: leave a sheet out of
the workbook (or leave it empty below the header) and generation is
byte-identical to a workbook that never had the sheet. The standard workbooks
do not include these five sheets (ADR-0064 D6); the converter carries yours
across if they contain data; empty optional sheets are omitted. None of these
sheets are in the required-sheets list checked by `make validate-excel`.

### Downloadable sample

[optional-overrides.xlsx](optional-overrides.xlsx) contains populated examples
of all five optional sheets, plus a Read Me tab. It is a **sheet library**, not
a complete deployment workbook: do not pass it directly to `make import`.

1. Open the sample and a copy of your intake workbook in Excel.
2. Use **Move or Copy → Create a copy** to copy the desired sheet into your
   workbook, preserving its exact name and column order. If that sheet already
   exists, merge the example rows into it rather than creating a suffixed tab.
3. Adapt the rows to your deployment. The routing examples define a new prefix
   list, community list and route-map; the route-map is deliberately **not bound
   to a BGP neighbor**, so it does not change route selection merely by existing.
   The route-map matches community `65000:100` and sets `65000:200`.
   The ACL example adds an inbound TCP/22 permit ACL. Custom_Config runs last:
   its lab banner **overrides the workbook's `pre_login_message` on ALL managed
   switches**. Omit or adapt that row to retain your workbook banner. These
   ACL and banner examples change config.
4. Run `make validate-excel EXCEL=/path/to/your-workbook.xlsx`, then import and
   generate it. Review the generated configuration before deploying.

The sample adds new names instead of replacing default routing lists or ACLs.
When adapting it to override a default, include every rule you intend to retain:
an override replaces the whole named rule set. The detailed semantics follow.

### What the defaults are (and when you'd override)

You almost never need these sheets — the generator computes everything below
from your VLAN subnets, loopbacks, and `loopback_base`. This reference exists so
you can see *what* is deployed and *what a row would change*. (The literal
values are per-deployment; to see the exact rules for a given build, run
`make generate` and grep the generated `core.yml`/`csl.yml` config.)

**Prefix lists** — named *sets of subnets*. Five are **overridable**; four are
per-switch and **derived-only** (a directive naming them is ignored with a warning):

| List | What it is (derived from) | Typical default content |
|------|---------------------------|-------------------------|
| `ERA_PREFIXES` | everything the fabric owns — the `loopback_base` aggregate + the OOB subnet | `<loopback_base>/21` + `/24`, OOB subnet `/24` |
| `INBAND_PREFIXES` | the in-band / compute VLAN subnets + the in-band loopback | each CPU/In-Band + Support VLAN subnet `/24`; inband loopback `/32` |
| `OOB_PREFIXES` | the OOB management subnet + the OOB gateway loopback | OOB subnet `/24`; OOB loopback `/32` |
| `VTEP_PREFIXES` | the VTEP (EVPN tunnel-endpoint) loopback range | e.g. `<loopback_base>.8/29` |
| `ALL_PREFIXES` | catch-all | `0.0.0.0/0` |
| **derived-only:** `EXIT_LOCAL_IF`, `INBAND_LOCAL_IF`, `OOB_LOCAL_IF`, `LOCAL_OOB_LOOPBACK` | each switch's **own** loopbacks/SVIs as `/32`s — computed per switch, auto-tracking | — (not overridable) |

**Route maps** — BGP *filters* that reference the prefix-lists/communities **by
name**. Overridable: `OOB_FILTER`, `BLOCK_VTEPS`, `OUTBOUND_ERA_PREFIXES`. For example:
- `BLOCK_VTEPS`: deny `VTEP_PREFIXES`, then permit `ALL_PREFIXES` (keeps VTEP loopbacks out of the adjacency).
- `OUTBOUND_ERA_PREFIXES`: permit `ERA_PREFIXES` (what the fabric advertises outbound).
- `OOB_FILTER`: deny community `11`, deny `INBAND_PREFIXES`, … (what the OOB peering accepts).

(Route-maps whose names aren't in the overridable set — e.g. `INBAND_FILTER` — are
derived-only, same rule as the per-switch prefix-lists.)

**Community lists** — BGP route tags. The one default is community `11` = `11:11`
(the ERA fabric tag). Override via the `Community lists` sheet by its id.

**When you'd actually touch a sheet:**
- **Add** an external/extra subnet to advertise or filter → new `Prefix lists` row
  (a `List name` not in the default set is *added*).
- **Replace** a default list's rules (e.g. tighten `OOB_PREFIXES`) → `Prefix lists`
  rows using the existing name (they *replace* the whole list).
- **Remove** a default list entirely → one row with `Action = suppress`.
- **Change a filter's behavior** (what a route-map denies/permits) → `Route policy` rows for that route-map name.
- Blank sheet ⇒ all of the above are derived automatically.

#### Worked examples: adding a prefix and using it

A prefix-list is just a **named set of subnets** — on its own it does nothing. It
only takes effect when a **route-map references it by name** and that route-map is
already bound to BGP. So "add a prefix" is really two questions: *which set does
it belong in*, and *is that set already wired into a filter*. The three cases:

**Example 1 — Advertise one extra subnet (the common case).**
Goal: make the fabric advertise an external service block, `10.60.0.0/16`, out of
the fabric. The set the fabric advertises is `ERA_PREFIXES`, and it's *already*
referenced by the `OUTBOUND_ERA_PREFIXES` route-map that's bound to BGP — so you
just add your subnet to that existing set. **Overriding a list replaces its whole
rule set**, so you must re-list the derived rules *and* your new one. Get the
derived rules first (`make generate` once, then grep the generated `core.yml` for
`ERA_PREFIXES`), then in the **`Prefix lists`** sheet:

| List name | Rule id | Match (CIDR) | Max prefix length | Action |
|-----------|---------|--------------|-------------------|--------|
| `ERA_PREFIXES` | 10 | `10.1.0.0/21` | 24 | |
| `ERA_PREFIXES` | 20 | `10.1.0.0/24` | 32 | |
| `ERA_PREFIXES` | 30 | `192.168.200.0/24` | 32 | |
| `ERA_PREFIXES` | 40 | `10.60.0.0/16` | 24 | |

Rows 10–30 reproduce the derived default (yours will differ — copy the real
values from `make generate`); row 40 is your addition. No `Route policy` change is
needed — `OUTBOUND_ERA_PREFIXES` already permits everything in `ERA_PREFIXES`.
> ⚠️ If you list `ERA_PREFIXES` with **only** row 40, you *replace* the whole list
> and drop the fabric's own prefixes. Always include the derived rules.

**Example 2 — A brand-new list, wired into a filter.**
Goal: block a lab range `10.99.0.0/16` from being accepted. A new list name is
*added* (not replacing anything), but nothing references it yet — so you also
override a route-map that's already bound to BGP to point at it. In **`Prefix
lists`**, define the set (any unused name = a new list):

| List name | Rule id | Match (CIDR) | Max prefix length | Action |
|-----------|---------|--------------|-------------------|--------|
| `BLOCK_LAB` | 10 | `10.99.0.0/16` | 32 | |

Then in **`Route policy`**, override `BLOCK_VTEPS` (already applied to the fabric)
to deny your new list before its normal rules. Override replaces the whole
route-map, so re-list its derived rules too:

| Route-map | Rule | Action | Match type | Match value | Set type | Set value |
|-----------|------|--------|------------|-------------|----------|-----------|
| `BLOCK_VTEPS` | 5 | `deny` | `ip-prefix-list` | `BLOCK_LAB` | | |
| `BLOCK_VTEPS` | 10 | `deny` | `ip-prefix-list` | `VTEP_PREFIXES` | | |
| `BLOCK_VTEPS` | 20 | `permit` | `ip-prefix-list` | `ALL_PREFIXES` | | |

Rows 10–20 reproduce the derived `BLOCK_VTEPS`; row 5 is your addition. (A new
route-map name that *no* BGP neighbor uses would still do nothing — that's why
this hooks into an existing, already-bound filter rather than inventing a new one.)

**Example 3 — Remove a default list.**
One row in **`Prefix lists`** with `Action = suppress` (the `Match` cell is ignored):

| List name | Rule id | Match (CIDR) | Max prefix length | Action |
|-----------|---------|--------------|-------------------|--------|
| `VTEP_PREFIXES` | | | | `suppress` |

Column numbers below are 1-indexed as read by the parser
(`scripts/excel_parser.py`); the header row is auto-detected by
scanning the first few rows for the sheet's key column header
(case-insensitive), so a merged note row above the header is fine.

### Prefix lists

Sheet name (case-sensitive): **`Prefix lists`**. Parsed by
`parse_prefix_lists_sheet()` (`scripts/excel_parser.py:2998`).

| Column | Header | Description |
|--------|--------|--------------|
| 1 | `List name` | Prefix-list id, e.g. `ERA_PREFIXES`. Also the header-row anchor cell. |
| 2 | `Rule id` | Rule sequence number within the list (positive integer). |
| 3 | `Match (CIDR)` | The CIDR to match, optionally with a trailing `le N` / `ge N`. |
| 4 | `Max prefix length` | Optional `max_len` for the rule. |
| 5 | `Action` | Blank, or `suppress` (case-insensitive). |

**Action semantics** (`scripts/excel_parser.py:3006-3011`):

- Blank — the row's rule is collected under its `List name`.
- `suppress` — the whole list named in that row is removed/kept out of
  generation. Any `Match` value on a suppress row is ignored.
  **Suppress always wins**, regardless of row order relative to other
  rows for the same list name.

**Override vs. add vs. ignored** is decided by `generate_prefix_lists()`
(`scripts/excel_parser.py:3283`, directive application at
`3473-3507`), based on two fixed classification sets (defined at
`3268-3282`):

| Constant | Members | Meaning |
|----------|---------|---------|
| `OVERRIDABLE_PREFIX_LISTS` | `ERA_PREFIXES`, `INBAND_PREFIXES`, `OOB_PREFIXES`, `VTEP_PREFIXES`, `ALL_PREFIXES` | Global-subnet lists. A sheet directive **replaces** the computed rule list (override) if the id already exists, or is appended as a brand-new list (add) if it doesn't — same charset/naming rule either way. |
| `DERIVED_ONLY_PREFIX_LISTS` | `EXIT_LOCAL_IF`, `INBAND_LOCAL_IF`, `OOB_LOCAL_IF`, `LOCAL_OOB_LOOPBACK` | Per-switch `/32` lists computed from that switch's own loopback IPs. **Never overridable, addable, or suppressable** — a directive naming one of these prints a warning during `make generate` and is otherwise ignored. |

A `List name` that is in neither set is not rejected: `generate_prefix_lists()`
(`scripts/excel_parser.py:3491-3494`) appends it as a brand-new,
entirely operator-defined prefix-list, exactly like the "add" case for
a not-yet-existing `OVERRIDABLE_PREFIX_LISTS` id — so any list name
passing the `validate-excel` charset check can be used to create a
custom list, not just the five named ones.

The `*_LOCAL_IF` / `LOCAL_OOB_LOOPBACK` lists are derived-only because
each one is a single `/32` tied to *this specific switch's* interface
address — there's no meaningful "operator override" for a value the
tool must compute per-host to stay correct; an override sheet has no
way to express "one rule per switch, computed from that switch's own
loopback."

Directives apply **per-switch**: `generate_prefix_lists()` is called
once per switch across every role in the deployment (core/csl, oob,
cl/cs, gl/gs), not just Core. A `Prefix lists` sheet directive is
applied identically on every switch that generates a list by that
name.

`make validate-excel` (`validate_prefix_lists()`,
`scripts/validate_excel.py:3646`) enforces, as a security backstop
(these values are interpolated into root-executed NVUE CLI lines):

- **List name**: must match `^[A-Za-z0-9_-]+$` — no spaces or shell
  metacharacters.
- **Rule id**: must be a positive integer when present.
- **Match**: must be a valid CIDR (`ge`/`le` suffix stripped before
  the check) and must not contain shell metacharacters.

### Route policy

Sheet name (case-sensitive): **`Route policy`**. Parsed by
`parse_route_policy_sheet()` (`scripts/excel_parser.py:3070`).

| Column | Header | Description |
|--------|--------|--------------|
| 1 | `Route-map` | Route-map id, e.g. `EXIT_FILTER`. Also the header-row anchor cell. |
| 2 | `Rule` | Rule id within the route-map. |
| 3 | `Action` | The route-map rule's own action — `permit` or `deny`. **Not** an override directive (unlike the `Prefix lists` sheet's `Action` column of the same name). |
| 4 | `Match type` | e.g. `ip-prefix-list`, `type`, `community-list`. Blank ⇒ no match entry added for this row. |
| 5 | `Match value` | Value for the match type in column 4. |
| 6 | `Set type` | e.g. `community`. Blank ⇒ no set entry added for this row. |
| 7 | `Set value` | Value for the set type in column 6. |

A rule can span multiple rows (repeat the same `Route-map` + `Rule`)
to add additional `match`/`set` entries; rows for the same
(route-map, rule id) pair are collected into one rule entry regardless
of row order.

**Override vs. add, no suppress**: applied by `_apply_named_overrides()`
(`scripts/excel_parser.py:3188`) — a route-map id already present in
the generated defaults is **replaced in place**; an id not already
present is **appended**. There is no suppress action and, unlike
`Prefix lists`, **no derived-only protection list** — any route-map id
in the source inventory (e.g. `EXIT_FILTER`, `INBAND_FILTER`,
`OOB_FILTER`, `BLOCK_VTEPS`, `OUTBOUND_ERA_PREFIXES`) can be
overridden. Replacing a route-map that a generated BGP neighbor or VRF
filter references (most of the ones above) changes fabric-wide
forwarding/filtering behavior — get the replacement rule content
right, since nothing in the tool stops an operator from overriding an
internal one.

**Scope**: Route policy directives are merged into `core_vars['route_map']`
during `generate_group_vars()` (`scripts/excel_parser.py:4819`,
merge at `5250-5252`) — a merge that happens *before* `core_vars` is
written out to `group_vars/core.yml` (`:5287`) and, via `_strip_gpu_plane()`
(`:3518`), reused to derive `group_vars/csl.yml` (`:5323`) and
`group_vars/cl.yml` (`:5337`) in dedicated-GPU / split-role (dedicated
N/S leaf) archs. `_strip_gpu_plane()` only removes GPU-plane VLAN/VRF/VNI
entries — it does not touch `route_map`, so an override lands in all
three files whenever `csl.yml`/`cl.yml` are generated. It does **not**
apply to `oob.yml`, the GSL/GL GPU-leaf plane files, or the `cs`/GS
spine files — those are generated independently (`oob.yml` from Excel +
source-inventory merge; `cs.yml`/`gs_plane*.yml`/`gsl_plane*.yml`/
`gl_plane*.yml` copied verbatim from the source inventory, `:5348-5412`).

### Community lists

Sheet name (case-sensitive): **`Community lists`**. Parsed by
`parse_community_lists_sheet()` (`scripts/excel_parser.py:3143`).

| Column | Header | Description |
|--------|--------|--------------|
| 1 | `Community-list` | Community-list id, e.g. `11`. Also the header-row anchor cell. |
| 2 | `Rule` | Rule id within the community-list. |
| 3 | `Action` | The rule's own action — `permit` or `deny`. Same caveat as `Route policy`'s `Action` column: this is rule content, not an override directive. |
| 4 | `Community` | The BGP community string, e.g. `11:11`. |

Same override/add-only semantics as `Route policy` (via the same
`_apply_named_overrides()`), same "no suppress, no derived-only
protection" caveat, and the same scope: merged into
`core_vars['community_list']` (`scripts/excel_parser.py:5253-5255`) and
therefore written to `group_vars/core.yml` and, where those roles
exist, `csl.yml`/`cl.yml` — see the Route policy scope note above.

### ACLs

Sheet name (case-sensitive): **`ACLs`**. Parsed by `parse_acls_sheet()`
(`scripts/excel_parser.py`). Controls the inbound control-plane ACLs
every switch applies. Optional and **derive-by-default** — a blank sheet
leaves the tool-owned defaults untouched (byte-identical output).

| Column | Header | Description |
|--------|--------|--------------|
| 1 | `ACL name` | ACL name, e.g. `acl-default-whitelist` or a new name like `mgmt-allow`. Header-row anchor. Charset `[A-Za-z0-9_-]+`. |
| 2 | `Rule id` | Positive integer rule id within the ACL. |
| 3 | `Protocol` | `tcp`, `udp`, `ip`, or `icmp`. |
| 4 | `Dest port` | Destination port, `1..65535`. |
| 5 | `Action` | Blank = add/override the rule; `suppress` = remove the named ACL. |

**Derived defaults (tool-owned).** Every switch binds `acl-default-dos`
and `acl-default-whitelist` inbound. The spine role (`cs` / `gs`)
additionally defines `acl-default-whitelist rule 200` (tcp/8251). These
render from the parser, not the templates.

**Directive semantics** (mirrors `Prefix lists`):

- **Override** — rows whose `ACL name` matches a default ACL **replace**
  that ACL's rule set (a rule set implies `type ipv4`). To *add* a rule
  while keeping the default, list the default rule(s) too. Overrides are
  fabric-wide (applied to every switch).
- **Add** — an unknown `ACL name` creates a new ACL, bound inbound.
- **Suppress** — `Action = suppress` removes the named ACL. Suppressing
  `acl-default-dos` / `acl-default-whitelist` is honored but raises a
  `validate-excel` **warning** — they are the baseline control-plane
  protections.

Example — open TCP/9000 on the whitelist and add an SSH-allow ACL:

| ACL name | Rule id | Protocol | Dest port | Action |
|----------|---------|----------|-----------|--------|
| acl-default-whitelist | 200 | tcp | 8251 | |
| acl-default-whitelist | 201 | tcp | 9000 | |
| mgmt-allow | 10 | tcp | 22 | |

`validate-excel` charset/protocol/port-checks every populated cell.

### What's NOT covered by these sheets

Per-switch loopback IPs are a separate, already-documented mechanism —
see `docs/LOOPBACKS.md`. The `Prefix lists` sheet's per-VRF match rules
(`EXIT_LOCAL_IF`, `INBAND_LOCAL_IF`, `INBAND_PREFIXES`,
`LOCAL_OOB_LOOPBACK`, `OOB_LOCAL_IF`, `OOB_PREFIXES`) automatically
track whatever loopback IPs are in effect (computed or
Loopbacks-sheet-overridden) — you don't need to touch `Prefix lists`
just because you changed a loopback.

---

## Migrating a legacy workbook

Workbooks authored before 2026-09 have a different set of sheets — `Settings`, `Nodes`, `VLANs & Profiles`, `Wire Map`, `Loopbacks & ASNs`, `Air_Only`, `Reference`. The tool no longer reads them: `make validate-excel` and `make generate` both refuse one and tell you to convert it.

```bash
make convert-workbook EXCEL=/path/to/legacy.xlsx
```

This writes `<name>.intake.xlsx` beside the source (override with `OUT=`). Nothing is changed in place. The converter:

- maps `Wire Map` → `Wiremap`, `VLANs & Profiles` → `Network Data`, and splits `Nodes` + `Loopbacks & ASNs` into `Switch Data` and `Host Data`;
- folds `Settings` and `Air_Only` into `Deployment`;
- carries any of the five override sheets you had, verbatim;
- writes the `Derived` sheet, showing which settings it computed from your cabling instead of copying;
- warns about anything it could not carry — for example a workbook old enough to predate the `ASN` column converts those cells blank and says so.

A device is sorted into `Switch Data` or `Host Data` by whether it has a loopback, not by its declared type. That is why `edge` and `air-oob` rows land in `Host Data` despite being switches.

The converter is transitional and is **removed at `nc-v10`**. Convert once and keep the intake workbook as your source; do not re-convert from a legacy original as a workflow.

### Where the old layout is documented

It is not documented here any more, deliberately — a description of a format the tool refuses would rot unread. If you need it, `scripts/convert_workbook.py` is the executable specification of what every legacy sheet and column meant, and the pre-migration version of this guide is in git history before ADR-0064 was accepted.

---

## Common Configurations

### Minimal Setup (Physical Deployment)

For a basic physical deployment without Air or LDAP:

**Deployment:**
- Set `architecture` to your arch (e.g., `2-8-5-200`)
- Set `loopback_base` to your loopback range
- Leave AIR DEPLOYMENT fields blank
- Set `ldap_enabled` to `No`
- There is no ZTP toggle in the workbook; run `make ztp-setup` / `make switch-ztp-deploy` to use ZTP

**Switch Data / Host Data:** Fill in all switches and servers with management IPs. Leave `ZTP MAC Address` / `Mac Address` blank for auto-generation. Per-switch BGP ASNs go in the **Switch Data** `ASN` column; the shipped workbook already has them.

**Network Data:** Use the default VLAN layout provided in the template. Set the OOB VLAN row's `IP Subnet`/`Gateway Addr` to your OOB network (see [OOB VLAN (management network)](#oob-vlan-management-network)).

**Wiremap:** Document all physical cabling.

### Air Simulation Deployment

Same as above, plus:
- Set `deploy_in_air` to `Yes`
- Run `make air-setup` once to pick the Air instance (public Air or internal `inside.dsx-air`) and store credentials — no Excel field needed (`air_org`/`air_username` in the Excel are inert and can be omitted)
- Add an `OOB / IPMI` row in the Wiremap for each node's eth0-to-OOB-switch connection
- Set `Display in Air` to `Yes` for all connections you want simulated

### LDAP Enabled

Same as minimal, plus:
- Set `ldap_enabled` to `Yes`
- Fill in `ldap_domain`, `ldap_base_dn`, `ldap_root_dn`, `ldap_servers`
- LDAP passwords are NOT stored in the Excel -- they go in `secrets.yml` after import

### Custom OEM Naming

If your organization uses different device names than the ERA convention:

1. Keep the `Function` column as-is (e.g., `core-01`, `su-01-node-01`) -- the automation depends on these patterns.
2. Put your custom names in the `Name` column (e.g., `spine01`, `gpu-rack1-node1`).
3. Use those same `Name` values in the Wiremap `System Name (A)` and `System Name (Z)` columns. The parser looks up each row's Function from `Switch Data` / `Host Data` by matching this name, so the names must agree exactly across sheets. A Wiremap name that matches no Switch Data / Host Data row is only a **warning** in `make validate-excel` (it allows cabling to not-yet-installed or external devices), so read the warnings: a typo there still generates a config cabled to the misspelled name.

---

## Tips and Gotchas

### General

- **Always validate before importing.** Run `make validate-excel EXCEL=<path>` before `make import`. The validator checks sheet structure, IP formats, duplicate ports, VLAN integrity, and cross-sheet consistency.
- **Section headers matter.** Do not delete or rename the section header rows (GENERAL, NETWORK, etc.) on the Deployment sheet. The parser skips them by name.
- **Do not leave gaps in the VLAN table.** On Network Data, `make validate-excel` reports a blank row, or a malformed VLAN ID, followed by more VLAN rows as an error naming the Network Data row.

### Deployment

- **`loopback_base` is three octets, not a full IP.** Write `172.16.176`, not `172.16.176.0` or `172.16.176.0/32`. The fourth octet is assigned per-switch and per-VRF automatically.
- **`disabled_ports` uses physical port numbers**, not breakout sub-ports. If port 50 is disabled, all its sub-ports (swp50s0, swp50s1, etc.) are disabled.
- **`mgmt_subnets` is retired.** `make validate-excel` hard-fails if a workbook still has it set — the OOB subnet now lives on the OOB VLAN row (VRF `OOB`) in Network Data. See [OOB VLAN (management network)](#oob-vlan-management-network).
- **`management_switches` is retired.** The OOB switch count is derived from the Enabled `oob-switch-*` rows on Switch Data — there's no separate count field to keep in sync. If a workbook still has `management_switches` set, `make validate-excel` only warns that it's ignored; it no longer truncates or pads the OOB switch list.

### Switch Data / Host Data

- **Names must be unique.** No two rows can share the same `Name` (Switch Data) / `System Name` (Host Data) value.
- **Management IPs must be unique.** The validator flags duplicate IPs as errors.
- **MAC addresses are optional for Air.** When deploying to NVIDIA Air, MACs are auto-generated using a deterministic hash of the node name. For physical deployments, switches need real MACs for ZTP DHCP reservations.
- **Enabled takes `Yes`, `No` or `Air`.** If the column is missing entirely, all nodes default to enabled. `True`/`1` and blank also mean enabled, `False`/`0` disabled; anything else (for example `Y`) is an error naming the cell, because the generator would otherwise drop the node silently.
- **Mgmt IP should NOT include the prefix.** On Switch Data, put the bare IP in `Mgmt IP` (column D, e.g. `192.168.200.5`) and the prefix length in `Prefix` (column T, e.g. `24`).
- **`OOB VLAN` (Switch Data column S) only matters for `oob-switch-*` rows.** Leave it blank unless the workbook defines more than one OOB VLAN — see [OOB VLAN (management network)](#oob-vlan-management-network).

### Network Data

- **VNI = VLAN ID + 4000 by convention.** If you leave the VNI column blank, the parser calculates it automatically. Only specify VNI explicitly if you need to deviate from this convention.
- **VLAN names must be consistent with Wiremap profiles.** The parser uses fuzzy matching (e.g., `CPU/In-Band` matches profiles containing "cpu" or "in-band"), but exact matches are safer.
- **Port Profiles define the default config for each network type.** Individual Wiremap rows can override port mode and VLAN settings, but the profile is the baseline.
- **VRF names are case-sensitive.** Use `OOB`, `INBAND`, `GPU`, `EXIT` consistently.
- **A second OOB VLAN row requires L3 OOB.** Two or more VRF=`OOB` rows with distinct subnets are only valid when `oob_uplink_mode = l3`; `make validate-excel` fails otherwise.

### Wiremap

- **`System Name (A)` and `System Name (Z)` must match a `Switch Data` / `Host Data` `Name` value exactly.** If `Switch Data` has `core-01`, the Wiremap must use `core-01` (not `Core-01` or `spine01`). The parser derives each row's Function by looking this name up.
- **eth0 is reserved for OOB management.** When the topology generator assigns interface names, eth0 always maps to the OOB management connection. Data-plane interfaces start at eth1. Do not assign a data-plane profile to eth0.
- **`outbound` is a special `System Name (B)` value.** It creates internet access links in Air simulations. It does not need a matching Switch Data / Host Data entry.
- **Duplicate endpoints are deduplicated.** If the same (node, interface) pair appears more than once, the first row wins and subsequent duplicates are silently dropped.
- **`Air - ` prefixed profiles are simulation-only.** These rows create infrastructure connections that exist in the Air virtual topology but not on physical hardware (e.g., eth0 management wiring that is handled by physical OOB cabling in real deployments).
- **Breakout notation matters.** `swp1s0` means port 1 sub-port 0 (a breakout port). `swp1` means the full-width port with no breakout. Use the notation that matches your physical cabling and switch configuration.

### Prefix lists / Route policy / Community lists

- **Leave these sheets out unless you need them.** They're derive-by-default: an absent or empty sheet produces byte-identical output to a workbook without the sheet.
- **The `Action` column means different things on different sheets.** On `Prefix lists`, `Action` is the override directive (blank or `suppress`). On `Route policy` and `Community lists`, `Action` is the rule's own BGP action (`permit`/`deny`) — there is no suppress directive on those two sheets.
- **Per-switch `*_LOCAL_IF` / `LOCAL_OOB_LOOPBACK` prefix lists can never be overridden.** They're computed per-switch `/32`s; a directive naming one is ignored with a console warning during `make generate`.
- **`Route policy` / `Community lists` have no derived-only protection.** Any route-map or community-list id in the source inventory (e.g. `EXIT_FILTER`, `OOB_FILTER`) can be replaced — there's nothing in the tool stopping you from overriding one that a generated BGP policy still references. Get the replacement content right.
- **`Route policy` / `Community lists` apply to Core-family switches only.** They're merged into `group_vars/core.yml` and, in dedicated-GPU / split-role archs, also `csl.yml` and `cl.yml` (both derived from the same post-override `core_vars` data) — not `oob.yml`, the GSL/GL GPU-leaf planes, or the `cs`/GS spine roles.

### Custom_Config

Optional sheet for switch configuration the tool does not generate — a login banner, an
SNMP target, a local user. Leave it out and nothing changes: an absent or empty sheet
produces byte-identical output.

Two columns:

| `Switch_Location` | `Config` |
|---|---|
| `ALL` | one or more `nv` commands, **one per line, in a single cell** (Alt+Enter for a new line) |
| `Function: gl-plane1, gl-plane2` | |
| `Host: cl-01, cl-02` | |

**Targeting must match what your workbook actually declares.** Every name is checked
against the `Function` and `Name` columns of your own Switch Data / Host Data sheets, and anything that
matches nothing **fails `make import`** naming the bad value and listing the valid ones.
That is deliberate: a typo that silently applied your config to zero switches would be
worse than a failed import.

- Matching is **exact** — no abbreviations. `gl` is rejected; write
  `gl-plane1, gl-plane2`.
- Names are **case-sensitive**. `CSL` is rejected; write `csl`.
- Only switches that receive a generated config can be targeted. Servers (`gpu`,
  `support`, …) and Air-only nodes (`edge`, `air-oob`) are rejected.
- Valid functions differ per architecture and scale. A collapsed-core arch has `csl`;
  a largescale arch has `cl` and `cs`. A workbook cannot carry one block covering both.

**What you may write.** `nv set` and `nv unset` commands only, in a fixed grammar
(ADR-0090):

- ✅ `nv set …`, `nv unset …`
- ❌ `nv show …` — read-only output has no place in a config script.
- ❌ `nv config …` — applying or replacing the configuration is the tool's job. A
  mid-script `nv config apply` would apply a half-built config and leave the rest
  staging against live state.
- ❌ `nv action …` — actions are imperative, leave no configuration state, and are not
  idempotent when ZTP re-runs the file.
- ❌ anything not starting with `nv ` — this is not a shell.

After `nv set` / `nv unset`, each space-separated word must be either:

- a **bare word** of letters, digits and `_ . : / , @ + = -`
  (`swp1`, `10.0.0.1/32`, `vrf-mgmt`), or
- a **single-quoted value** for anything with spaces or other punctuation:
  `nv set system message pre-login 'Authorized use only'`. It may not contain a
  single quote, a line break or a control character.

Everything else is refused, naming the row and line: double quotes, backslashes, `$`,
`` ` ``, `;`, `&`, `|`, `<`, `>`, parentheses, braces, glob characters (`* ? [ ]`), `#`,
and `{{ … }}` / `{% … %}` (workbook text is never a template). The tool rebuilds each
line from the approved words, so the switch runs exactly the command you wrote, and the
switch templates re-check the grammar so a hand-edited inventory cannot bypass it.

**Your lines are emitted last**, after everything the tool generates. On any setting the
tool also configures, **yours wins** — including `nv unset` to remove something the tool
would otherwise set. That is the point of the sheet, and it is also the risk: nothing
stops you from breaking a fabric this way, exactly as editing a template would.

Rows accumulate. A switch matched by three rows gets all three blocks, in sheet order.

**Verification.** `make validate-config` compares each switch against its generated
config. Any setting your custom config writes to is reported as a warning rather than a
mismatch:

```
Missing on switch:   0
Custom_Config override: 4 generated line(s) removed by nv-unset (warning, not a mismatch)
Extra on switch:     0
RESULT:MATCH
```

The switch still passes. This is necessary because NVUE may re-quote values on read-back — and
because overriding a setting the tool also configures makes the tool's own line look
absent. Settings you do **not** touch are compared exactly as before, so real drift is
still caught.

Example:

| Switch_Location | Config |
|---|---|
| `ALL` | `nv set system message pre-login 'Authorized use only'` |
| `Function: csl` | `nv set system snmp-server listening-address any` |
| `Host: oob-switch-01` | `nv set system timezone Etc/UTC` |

---

---

## Validation

Before importing, always validate your Excel file:

```bash
make validate-excel EXCEL=/path/to/your-config.xlsx
```

The validator checks:

- **Sheet structure**: All required sheets present (Wiremap, Network Data, Switch Data, Host Data, Deployment). A legacy-format workbook is refused here with a pointer to `make convert-workbook`.
- **Required fields**: Mandatory Deployment keys have values.
- **IP format**: All IPs and CIDRs are syntactically valid IPv4.
- **MAC format**: MAC addresses use `xx:xx:xx:xx:xx:xx` notation.
- **Architecture**: Value is one of the eight valid architectures (`2-4-3-200`,
  `2-4-5-400`, `2-4-5-800`, `2-8-5-200`, `2-8-5-400`, `2-8-9-400`, `2-8-9-800`, `2-8-9-400-SP`).
- **Duplicates**: No duplicate Function names, no duplicate management IPs.
- **Port conflicts**: No duplicate switch port assignments in the Wiremap.
- **Cross-sheet consistency**: Wiremap `System Name (A)` / `System Name (Z)` values reference devices that exist in `Switch Data` or `Host Data`.
- **Subnet sanity**: Gateways are within their node's management subnet (warning if not).
- **Air infrastructure addresses** (ADR-0084): every address the import will
  generate for `dhcp-oob` / `utility` / `external-dhcp`, the OOB and air-mgmt
  gateways, switch `eth0`s and ext-storage `eth0`s must be a usable host of its
  declared subnet and unique against every Nodes-tab host, gateway and switch
  SVI. An OOB VLAN too small to fit its hosts plus the infrastructure fails
  with the subnet, the usable-host count and the claimant that could not be
  placed — widen the subnet or move hosts to another OOB VLAN (L3 OOB).
- **Declared data-plane IPs** (ADR-0034): every filled `IP` on a non-`eth0` `Host Data` row must bind to a known interface of that host, sit inside that interface's VLAN, avoid the gateway / switch SVIs / GPU fabric range, agree with the other rows of its bond, and be unique fabric-wide — including against addresses allocated to hosts whose cells are blank. Workbooks with no such cell skip this check.
- **Fabric optic integrity** (warning): switch-to-switch links — the `ISL` and
  `N/S Leaf Peer` port profiles — must be cabled in whole transceivers. Two
  warnings can appear. A **partial cage** means a broken-out port carries fewer
  cables than its breakout factor, so one transceiver is only half wired; cable
  the remaining sub-ports or move the link to a full cage. A **shared cage**
  means one transceiver is split across both fabric profiles, which charges a
  single cage against two separately-sized populations so neither can be
  reconciled against the faceplate; give each population its own cage. These
  compare the workbook against itself, so unlike the arch-model ISL check they
  also run in the public distribution.
- **Prefix lists charset**: when the optional `Prefix lists` sheet is present, list names must match `[A-Za-z0-9_-]+`, rule ids must be positive integers, and `Match` values must be valid CIDRs free of shell metacharacters (`validate_prefix_lists()`). This is a security backstop — these values are interpolated into root-executed switch config lines. **Note:** the optional `Route policy` and `Community lists` sheets have no equivalent dedicated validator today — review overrides to those sheets carefully before importing.

Fix all errors before running `make import`. Warnings are advisory but worth reviewing.

---

## Full Workflow

```bash
# 1. Validate the filled-out Excel
make validate-excel EXCEL=/path/to/2-8-5-200.xlsx

# 2. Import into the project (copies to input/<arch>/<site>/)
make import EXCEL=/path/to/2-8-5-200.xlsx

# 3. Generate configs, inventory, and topology
make generate ARCH=2-8-5-200

# 4. Review generated output
ls output/2-8-5-200/default/inventory/
ls output/2-8-5-200/default/configs/

# 5. Deploy (Air simulation or physical ZTP)
make air-full-deploy ARCH=2-8-5-200    # Air
make switch-ztp-deploy ARCH=2-8-5-200  # Physical
```

---

## Reference: Required vs Optional Fields Summary

### Deployment -- Required

| Field | Why It Is Required |
|-------|--------------------|
| `architecture` | Determines which templates, port mappings, and topology rules to apply. |
| Switch Data `ASN` column | Per-node BGP ASN source; BGP will not converge without an ASN. (A Deployment `bgp_asn` row is also accepted as the base.) |
| `loopback_base` | Loopback IPs are derived from this base for all VRFs. |

### Deployment -- Optional (with Defaults)

| Field | Default If Omitted |
|-------|-------------------|
| `site_name` | `default` |
| `deploy_in_air` | `Yes` (an absent row builds the Air variant; a blank value builds the physical one; set `No` for physical) |
| `ns_tiers` | `1` (compute converged; `2` = split `cl`+`cs`) |
| `ew_tiers` | `1` (GPU converged; `2` = split `gl`+`gs` per plane) |
| `tiers` | *(deprecated)* — seeds both `ns_tiers` / `ew_tiers` if missing |
| `convergence` | `full` |
| `ldap_enabled` | `No` |
| `telemetry_enabled` | *(inert — omit)* |
| `ztp_enabled` | *(inert — omit)* |
| `netq_ip` | *(inert — omit)* |
| `ztp_server` | `<oob subnet>.100` *(inert — not read by any generator)* |
| `timezone` | `Etc/Zulu` |

### Switch Data / Host Data -- Required Columns

| Column | Why It Is Required |
|--------|--------------------|
| `Name` (Switch Data) / `System Name` (Host Data) | Primary key for all cross-references; the Wiremap's system names must match it. |
| `Mgmt IP` | Every switch needs a management IP for ZTP and SSH access. |
| `OOB VLAN` | Conditional — only required on `oob-switch-*` rows once the workbook defines more than one OOB VLAN (VRF `OOB`) row; otherwise blank defaults to the sole OOB VLAN. |

### Wiremap -- Required Columns

| Column | Why It Is Required |
|--------|--------------------|
| `System Name (A)` | Identifies the A-side device this row belongs to. |
| `Port (A)` | Specifies the physical port on the A-side device. |
| `System Name (B)` | Identifies the connected switch / peer (B-side) for topology generation. |
| `Port (B)` | Specifies the physical port on the B-side (switch) side. |
| `Network Profile` | Determines how the port is configured (VLAN, mode, VRF). |

---

## Reference: Tool-Default Constants (Not Excel-Configurable)

Beyond the fields above, `scripts/excel_parser.py` hardcodes several
numeric constants that shape ASN allocation, loopback numbering, and
management-IP conventions. These are **not** Deployment fields — they
apply uniformly to every arch/site and can't be set from the Excel
except where a "Deployment escape hatch" is called out below.

| Constant | Value | Meaning | Excel escape hatch |
|----------|-------|---------|---------------------|
| `LOOPBACK_BASE` (`excel_parser.py:87`) | `172.16.176` | First 3 octets of the underlay loopback / router-id supernet used when Deployment `loopback_base` is blank. | **Yes** — Deployment `loopback_base` (read at `excel_parser.py:4153`). |
| `OOB_ASN_OFFSET` (`:100`) | `0` | OOB switch ASN = `base_asn + 0 + oob_idx`. | No. |
| `CSL_LEAF_ASN_OFFSET` (`:101`) | `400` | Dedicated N/S leaf (`cl`) ASN = `base_asn + 400 + core_num`, only when `ns_tiers > 1`. | No. |
| `CSL_SPINE_ASN_OFFSET` (`:108`) | `500` | Dedicated N/S spine (`cs`) ASN = `base_asn + 500 + spine_idx`. | No. |
| `GSL_PLANE_ASN_STRIDE` (`:109`) | `1000` | ASN spacing between GPU planes; shared by GSL leaf and spine formulas. | No. |
| `GSL_SPINE_ASN_OFFSET` (`:110`) | `1099` | Dedicated E/W (GPU) spine ASN = `base_asn + 1099 + (plane-1)*1000`. | No. |
| `GSL_LEAF_ASN_OFFSET` (`:111`) | `1100` | GPU leaf ASN = `base_asn + 1100 + (plane-1)*1000 + (leaf_idx-1)`. Unique per leaf in spined (>2-leaf) planes; collapsed 2-leaf planes intentionally share one plane ASN across both leaf mates (they iBGP-peer each other). | No. |
| `ROLE_HOST_BASE` (`:118-121`) | `compute=11, support=51, storage=61, k8s=71, bcme=81, unknown=91` | Documented as role-based host-octet ranges for management-IP assignment. | No — and see caveat below. |
| `switch_user` (`:4972`) | `'cumulus'` | The SSH/ZTP username written into generated inventory for all switches. | No. |
| `air_mgmt_subnet` default (`:1191`, `:4157`) | `172.20.0.0/24` | Base subnet for switch `eth0` IPs in Air. | **Yes** — but via the Deployment sheet's AIR DEPLOYMENT block, "Air Management Subnet" row (`parse_air_settings()`), not a key/value setting. |

The full ASN formula (per-tier base + fixed, non-overlapping offset
block) is the single-source `scripts/asn_allocation.py` — the offsets
above are intentionally disjoint and considered stable; changing one
would silently renumber every already-shipped arch.

These offsets are the **derived defaults**. To assign an arbitrary ASN to
an individual switch, use the optional Loopbacks **ASN** column,
which overrides the derived value per node. `validate_excel` enforces the
BGP invariants on any overrides (shared iBGP/plane groups must stay uniform;
every group's ASN must be distinct) — see `docs/LOOPBACKS.md`.

Deployment `loopback_base` is the **only** constant above with a direct
key/value override. Everything else — the ASN offsets,
`ROLE_HOST_BASE`, and `switch_user` — is a fixed tool default with no
Excel field at all. `air_mgmt_subnet` is the one exception with an
override, but it lives in Deployment's AIR DEPLOYMENT block, and only matters
for Air deployments.

**Caveat on `ROLE_HOST_BASE`**: as of this writing it is defined but
not referenced anywhere else in `excel_parser.py` — management IPs
are read verbatim from the Switch Data sheet's `Mgmt IP` column
rather than computed from a role-based octet range. Treat this table
row as documentation of an unused constant, not as an active
IP-assignment rule; if you see a management IP that doesn't follow
this scheme, that's expected.

The GPU VRF loopback (used by the `Prefix lists` sheet's per-VRF match
rules, see [Sheet 5](#sheet-5-routing-policy-overrides-optional)) is
allocated like the other per-VRF loopbacks, from one block per VRF
(`scripts/loopback_allocation.py`, `VRF_LOOPBACK_BLOCKS` /
`PLANE_LOOPBACK_BLOCKS`): on the N/S fabric `<loopback_base>.214 + n`, and
on an E/W plane `.20 + n` (leaf) or `.50 + n` (spine) within that plane's
/24. It no longer comes from a GPU VLAN subnet. The ranges are tabled in
[`LOOPBACKS.md`](LOOPBACKS.md); override one per switch with the Switch
Data `GPU lo` column.
