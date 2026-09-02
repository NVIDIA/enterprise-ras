<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# ERA Excel Configuration Guide

This guide explains how to fill out the ERA Excel template that drives the entire switch configuration pipeline. Every field, every sheet, and every convention is documented here so you can complete the template confidently before running `make import`.

---

## How the Excel Template Works

The ERA automation follows a single-source-of-truth model:

1. Start with the pre-configured template for your architecture from `input/<arch>/default/<arch>.xlsx`.
2. You fill in site-specific values: IPs, VLANs, node names, cabling.
3. You run `make import EXCEL=<path>` to import and `make generate ARCH=<type>` to produce Ansible inventory, NVUE CLI switch configs, and an NVIDIA Air topology.
4. The generated configs are deployed via ZTP or pushed directly to switches.

The Excel file has four sheets you fill out, plus six supporting sheets:

| Sheet | Purpose |
|-------|---------|
| **Settings** | Global deployment parameters (IPs, ASN, features) |
| **Nodes** | Every device in the deployment (switches, servers, storage) |
| **VLANs & Profiles** | VLAN definitions, VRF assignments, and port profiles |
| **Wire Map** | Physical cabling: which port on which device connects to which switch port |
| **Loopbacks** | *Optional.* Per-switch / per-VRF loopback overrides, plus an optional per-node BGP **ASN** column. Blank cells fall back to the computed defaults. See `docs/LOOPBACKS.md`. |
| **Prefix lists** | *Optional.* Override, add, or suppress BGP prefix-list rules. See [Sheet 5: Routing Policy Overrides](#sheet-5-routing-policy-overrides-optional). |
| **Route policy** | *Optional.* Override or add route-map entries (Core-family switches only — `core.yml`, and `csl.yml`/`cl.yml` where those roles exist). See [Sheet 5: Routing Policy Overrides](#sheet-5-routing-policy-overrides-optional). |
| **Community lists** | *Optional.* Override or add BGP community-list entries (Core-family switches only — `core.yml`, and `csl.yml`/`cl.yml` where those roles exist). See [Sheet 5: Routing Policy Overrides](#sheet-5-routing-policy-overrides-optional). |
| **ACLs** | *Optional.* Override, add, or suppress inbound control-plane ACL rules (all switches). Blank = tool defaults. See [Sheet 5: Routing Policy Overrides](#sheet-5-routing-policy-overrides-optional). |
| **Air_Only** | Cumulus version → NVIDIA Air image name map, plus the Air management subnet. Only relevant for Air deployments. |
| **Reference** | Read-only quick reference embedded in the workbook. Do not edit. |

An empty or absent optional sheet is always safe: the generator falls back to its computed defaults and produces byte-identical output to a workbook that never had the sheet at all.

---

## Sheet 1: Settings

The Settings sheet is a key-value table organized into sections. Column A (`Setting`) is the field name and column B (`Value`) is the value you edit. Columns C–E (`Description`, `Required`, `Default Value`) are read-only guidance shipped in the template — you don't need to change them. Section headers (GENERAL, NETWORK, etc.) appear in column A with no value in column B -- do not delete them.

### GENERAL

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `site_name` | No | String | A label for this deployment instance. Defaults to `default` if omitted. Use it to distinguish multiple deployments of the same architecture (e.g., `lab-east`, `prod-dc2`). | `default` |
| `architecture` | **Yes** | Enum | The ERA architecture identifier. Must be exactly one of the six valid values. This determines which templates and topology rules are applied. | `2-8-5-200` |

Valid architectures and what they represent. Naming follows the
`{CPUs}-{GPUs}-{NICs}-{B}` convention where **B = average per-GPU
bandwidth on the East/West network (Gbps)**.

| Architecture | CPUs | GPUs | NICs | Per-GPU E/W bandwidth | OOB Switches |
|-------------|------|------|------|----------------------|--------------|
| `2-4-3-200`* | 2 | 4 | 3 | 200 Gbps | 2 |
| `2-8-5-200`* | 2 | 8 | 5 | 200 Gbps | 3 |
| `2-8-9-400` | 2 | 8 | 9 | 400 Gbps | 3 |
| `2-8-9-800` | 2 | 8 | 9 | 800 Gbps | 2 |
| `2-4-5-800`† | 2 | 4 | 5 | 800 Gbps | varies |
| `2-8-9-400-SP` | 2 | 8 | 9 | 400 Gbps | 2 |

`2-8-9-400-SP` is the dedicated-GPU **single-plane** variant of `2-8-9-800`
(GSL plane 1 only — the dual-plane default minus GPU plane 2).

\* In archs where the E/W NIC:GPU ratio is 1:2 (`2-4-3-200`, `2-8-5-200`),
   strict per-GPU arithmetic gives 100 Gbps; the label `200` follows the
   per-NIC link speed convention — a documented exception, not a bug.

† `2-4-5-800` is the GB300 NVL72 mini-cloud (multi-tier dedicated-GPU dual-plane
   with separate N/S, GPU E/W, and OOB fabrics). It uses strict canonical-role
   validation and a per-rack (NVL72) SU rather than the 4-node HGX SU of the
   other archs; the OOB switch count is materialized per deployment, not a fixed
   value.

**Choosing an architecture:** match the row above to your compute node's CPU/GPU/NIC
count and East/West link speed. If you're unsure which arch your hardware maps to,
see the [Architecture Support Matrix](ARCH_SUPPORT_MATRIX.md) for the
arch × scale × feature breakdown (what has been tested with this tool).

### AIR DEPLOYMENT

These fields control NVIDIA Air simulation deployment. If you are deploying to physical hardware only, you can leave these blank.

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `deploy_in_air` | No | Yes/No | Whether this deployment targets an NVIDIA Air virtual simulation. `Yes` (default): switches get auto-assigned air-mgmt (`172.20.0.x`) eth0 IPs for ZTP, and a Nodes-tab Mgmt IP is optional for switches. **`No`: local push to real hardware** — each switch's inventory `ansible_host` uses its **real Nodes-tab Mgmt IP** (statically addressed), so `make generate` + a local config push can reach the switches. With `No`, a Mgmt IP is **required** on every switch row. | `Yes` |
| `air_username` | No | String | **Inert — no consumer in the current pipeline** (`make validate-excel` warns if set). Air credentials come from the `.era-secrets` vault (`make air-setup`), not the Excel. Safe to omit. | *(omit)* |
| `air_org` | No | String | **Inert — no consumer in the current pipeline** (`make validate-excel` warns if set). Air credentials come from the vault, not the Excel. Safe to omit. | *(omit)* |
| `status_page_enabled` | No | Yes/No | When enabled, creates an HTTP service in Air for the ZTP status page with basic auth. Allows viewing ZTP status and validation reports via a web browser. The same basic-auth credentials also protect the validation-report page (`/reports/`). Credentials come from `status_page_username` and `status_page_password` in `secrets.yml` (default username: `era`; default password: `CHANGE_ME` — you **must** set a real password in `secrets.yml` before deploying, it does not default to any other secret). | `No` |

The Air instance URL is **not** an Excel field. Run `make air-setup` once per checkout
to pick public Air vs. internal `inside.dsx-air` (or enter a custom URL); the wizard
stores your choice in the shared vault at `.era-secrets/air-secrets.yml`. See the
[Air Deployment Guide](AIR_DEPLOYMENT_GUIDE.md) for the wizard walkthrough.

### NETWORK

Core network parameters that define the fabric topology.

> The OOB (management) network is **not** declared here — it is declared by
> the OOB VLAN row(s) on the "VLANs & Profiles" sheet plus each OOB switch's
> `OOB VLAN` column on the Nodes sheet. See
> [Sheet 3: VLANs & Profiles → OOB VLAN (management network)](#oob-vlan-management-network).

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `ns_tiers` | No | Integer (1-2) | Compute (North-South) fabric tier count. `1` = converged spine-leaf (role `csl`), `2` = dedicated split (roles `cl` + `cs`). The validator checks that the spine role count matches. Default `1`. | `1` |
| `ew_tiers` | No | Integer (1-2) | GPU (East-West) fabric tier count, per plane. `1` = converged spine-leaf (role `gsl-plane*`), `2` = dedicated split (roles `gl-plane*` + `gs-plane*`). Default `1`; the `2-4-5-800` default ships `2`. | `1` |
| `tiers` | No | Integer | **Deprecated** — legacy single tier count. Seeds both `ns_tiers` and `ew_tiers` if either is missing; prints a deprecation warning. New Excels should use `ns_tiers` / `ew_tiers`. | `1` |
| `convergence` | No | String | Network convergence type. `full` for the converged-core archs (`2-4-3-200`, `2-4-5-400`, `2-8-5-200`, `2-8-9-400`); `dedicated_gpu` for the dedicated-GPU archs (`2-4-5-800`, `2-8-9-800`, `2-8-9-400-SP`). Matches the shipped default per arch. | `full` |
| `gpu_planes` | No | Integer (1-2) | Number of GPU fabric planes. `1` for single-plane archs; `2` for the dual-plane archs (`2-4-5-800`, `2-8-9-800`). The default per arch already matches its topology — only change it if you know why. | `1` |
| `bgp_asn` | Legacy | Integer | **Removed from the Settings tab.** Per-node BGP ASNs now live in the Loopbacks **ASN** column (the shipped workbooks populate it explicitly). Still *recognized* if present in an older workbook — it then acts as the derivation base — but new/shipped workbooks source ASNs from the tab. See `docs/LOOPBACKS.md`. | (in Loopbacks) |
| `loopback_base` | **Yes** | IP prefix | First three octets of the loopback IP range. The fourth octet is auto-assigned per switch and VRF. (The `2-4-5-800` default uses `172.16.1`; the others use `172.16.176`.) | `172.16.176` |
| `disabled_ports` | No | CSV of integers | Physical port numbers on core switches that should be administratively disabled. Comma-separated. | `50,52,60,62,64` |
| `exit_dhcp_servers` | No | CSV of IPs | DHCP relay server IPs for the EXIT VRF. Only needed if your design uses DHCP relay on the exit network. | `10.0.0.1,10.0.0.2` |
| `air_mgmt_subnet` | No | CIDR | The **switch-management plane** — where every switch `eth0` lands, plus the Air infrastructure nodes. This is the plane Ansible reaches switches on. Set it to your site's real switch-management network to mirror an on-prem deployment. If omitted, defaults to `172.20.0.0/24`. Authored on the **`Air_Only`** sheet ("Air Management Subnet" row), not in `Settings`. See [Using your own management subnets](#using-your-own-management-subnets). | `172.20.0.0/24` |
| `gpu_vlan_mode` | No | enum | GPU VLAN topology. Three values: `single` (default — one GPU VLAN), `per_rail` (one VLAN per rail; requires `gpu_rail<N>` VLAN rows + `GPU Rail <N>` Wire Map profiles), `per_rail_per_plane` (one VLAN per (rail, plane); requires `gpu_rail<R>_plane<P>` VLAN rows + `GPU Rail R Plane P` Wire Map profiles). See [Section 1: VLANs → GPU VLAN topology modes](#gpu-vlan-topology-modes). | `single` |

### MANAGEMENT

LDAP configuration for centralized authentication on switches. If `ldap_enabled` is `No`, the remaining LDAP fields are ignored.

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `ldap_enabled` | No | Yes/No | Enable LDAP authentication on switches. When enabled, LDAP config is generated alongside local auth. | `No` |
| `ldap_domain` | Conditional | String | LDAP domain name. Required if `ldap_enabled` is `Yes`. | `example.com` |
| `ldap_base_dn` | Conditional | String | LDAP base distinguished name for user searches. | `dc=example,dc=com` |
| `ldap_root_dn` | Conditional | String | LDAP bind DN (the admin account used to query LDAP). | `cn=admin,dc=example,dc=com` |
| `ldap_servers` | Conditional | CSV of IPs | LDAP server IP addresses, comma-separated, in priority order. **The shipped default Excels pre-fill this with `172.20.0.78`** — the `utility` node IP used by the Air L3-OOB lab so LDAP works out of the box in a simulation. **For production you must replace it with your real LDAP server(s).** (In Air, use `172.20.0.78` for L3 OOB or `172.20.0.77` for L2 OOB.) | `10.0.1.10,10.0.1.11` |
| `ldap_organization` | Conditional | String | LDAP organization name. Used in the LDAP directory structure. | `Example Org` |

### TELEMETRY

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `telemetry_enabled` | No | Yes/No | **Inert — no consumer in the current pipeline** (`make validate-excel` warns if set). Switch telemetry is not driven from this field today. Safe to omit. | *(omit)* |
| `netq_ip` | No | IP address | **Inert — no consumer in the current pipeline** (`make validate-excel` warns if set). Safe to omit. | *(omit)* |

### ADVANCED

These fields have sensible defaults. Only change them if your deployment diverges from the standard ERA design.

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `timezone` | No | String | Timezone for all switches. Uses tz database format. | `Etc/Zulu` |
| `mh_mac` | No | MAC address | EVPN Multihoming system MAC. Must be in `xx:xx:xx:xx:xx:xx` format. Shared across the MLAG/MH domain. | `44:38:39:ff:00:01` |
| `anycast_mac` | No | MAC address | Anycast gateway MAC address for VXLAN SVIs. Must be in `xx:xx:xx:xx:xx:xx` format. | `44:38:39:ff:00:aa` |
| `ztp_enabled` | No | Yes/No | **Inert — no consumer in the current pipeline** (`make validate-excel` warns if set). ZTP is not a Settings flag: it is opt-in by which target you run (`make ztp-setup` / `make switch-ztp-deploy`). Setting this to `No` does **not** disable ZTP. Safe to omit. | *(omit)* |
| `ztp_server` | No | IP address | **Currently inert** — validated as an IPv4 address but not applied. The effective ZTP server address is mode-dependent and set outside the workbook (L2: the ZTP host on the OOB subnet; L3: the `external-dhcp` interface on the Air-management subnet). Being reworked so this field is authoritative — until then, changing it has no effect. | *(omit)* |
| `ntp_servers` | No | String | NTP server addresses for time synchronization. Can be IPs or hostnames, one per line (or comma-separated). Each entry may set its NVUE **association type** by appending `association-type pool` (or the shorthand `pool`); valid types are `server` (default), `pool` and `peer`, and an unrecognised type falls back to `server` with a warning. Every switch role emits the type explicitly, so the generated config shows where to change it. | `0.cumulusnetworks.pool.ntp.org`<br>`2.pool.ntp.org association-type pool` |
| `num_physical_ports` | No | Integer | Number of physical front-panel ports on core switches (e.g., SN5610 has 64). Used for port range calculations. | `64` |
| `oob_uplink_mode` | No | `l2` or `l3` | OOB switch uplink mode. **All shipped default templates set `l3`** (the current production L3-OOB design): OOB switches are L3 EVPN VTEPs with BGP underlay + OOB VRF SVI + VRR, the Air topology uses `cust-net-edge-*` as the mgmt-VLAN bridge, and the OOB infra nodes are `external-conn`/`external-dhcp`/`utility`. `l2` is the legacy flat-L2-bridge design (`dhcp-oob`/`oob-server-01`); the parser falls back to `l2` only if this field is left blank. **Important:** when changing this setting, you must also update the "OOB Uplink" Port Profile on the VLANs & Profiles sheet -- set it to `Access` with VLAN 200 for L2 mode, or `L3` for L3 mode. See the Port Profile table below. | `l3` (shipped); `l2` if blank |
| `pre_login_message` | No | Multi-line text | SSH banner displayed **before** authentication. Empty cell → no banner line emitted (any existing banner on the switch persists untouched). Placeholders `{hostname}`, `{site}`, `{arch}` are substituted per-switch at config-render time. Newlines in the cell are preserved. Single quotes in the operator's text are safely escaped. Default Excels ship pre-populated with the NVIDIA Cumulus VX welcome message, so existing deploys see the same banner unless you edit the cell. | `Authorized access only — site {site}` |
| `post_login_message` | No | Multi-line text | Login MOTD displayed **after** successful authentication. Same placeholder + empty-cell semantics as `pre_login_message`. Default Excels ship with the "successfully logged in to: `{hostname}`" message. | `Welcome to {hostname} ({arch})` |

### VERSIONS

This section appears below the key-value settings, formatted as a small table with a `Switch Function` header row.

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `core` | Yes | Version string | Target Cumulus Linux version for core switches. | `5.18.0` |
| `oob` | Yes | Version string | Target Cumulus Linux version for OOB switches. Can differ from core if OOB runs an older release. | `5.18.0` |
| `csl` | Yes | Version string | Target Cumulus Linux version for collapsed spine-leaf switches. | `5.18.0` |
| `gsl` | Yes | Version string | Target Cumulus Linux version for GPU spine-leaf switches. | `5.18.0` |

All four rows are present in every shipped workbook and all four are marked
required, including on architectures that do not deploy a `csl` or `gsl` switch.

Every version listed here must have a matching row in the `Air_Only` sheet's
version → Air image table, and the image's published `minimum_resources` must
be met by the node's vCPU/memory/storage. A version with no image row is a hard
error: generation stops rather than substituting a different image, because a
simulation that quietly boots the wrong release invalidates whatever was
validated on it (ADR-0054).

---

## Sheet 2: Nodes

The Nodes sheet is a table listing every device in the deployment -- core switches, OOB switches, compute nodes, storage nodes, support nodes, and any other infrastructure.

**Row 1 is the header row.** Data starts at row 2.

### Column Reference

| Column | Header | Required | Type | Description |
|--------|--------|----------|------|-------------|
| A | `Function` | **Yes** | String | The canonical role identifier. This is a role *class*, not a unique key — many devices can share the same Function (e.g. eight rows with `gpu`). It drives which templates and port rules apply, and it is **authoritative** — the tool trusts `Function`, not the Name. `make validate-excel` *warns* (does not block) when a row's Name prefix implies a different role than its Function (e.g. a `gs-plane1-*` spine given Function `gl-plane1`), and when GPU planes have asymmetric per-role switch counts — both usually signal a mislabeled Function. If a mislabel slips through, `make generate` hard-fails rather than emitting a broken config. See naming conventions below. |
| B | `Name` | No | String | OEM-specific device name. This is the unique per-device identifier (must be unique across all rows) and the value the Wire Map joins against. If blank, defaults to the Function value — so leave it blank only when a Function has exactly one device. |
| C | `Type` | No | `switch` / `node` | Optional. Distinguishes Cumulus VX switches (`switch`) from Ubuntu / Cumulus host nodes (`node`). When present, the validator enforces consistency with `Function` (switch-role Functions must have `Type=switch`, server/compute Functions must have `Type=node`). Older Excels without this column still validate. |
| D | `MAC Address for ZTP` | No | MAC | MAC address used for DHCP reservation during ZTP. Required for physical switches. Format: `aa:bb:cc:dd:ee:ff`. If left blank for Air deployments, a deterministic MAC is auto-generated from the node name. |
| E | `Mgmt IP Address` | **Yes** | IP address | Management IP address on the OOB network. Do NOT include the prefix length here (put that in the Prefix column). Must be unique across all nodes. |
| F | `Prefix` | No | Integer | CIDR prefix length for the management subnet. Typically `24`. Defaults to 24 if blank. |
| G | `Gateway` | No | IP address | Default gateway for management traffic. Typically the oob-server-01 IP (e.g., `192.168.200.1`). |
| H | `ZTP` | No | Yes/No | Whether this node participates in ZTP. Switches should be `Yes`. Servers are typically `No` (configured via other means). |
| I | `Enabled` | No | `Yes` / `No` / `Air` | Whether to include this node in the generated inventory. `No` excludes the row without deleting it; `Air` marks the row as a **documentary entry for auto-injected Air-only infrastructure** (parser skips provisioning, validator enforces Name + Type match an allowed Air node). Defaults to `Yes` if the column is missing or blank. |
| J | `Notes` | No | Free text | Optional per-row notes (e.g. "Air-only documentary — auto-injected by topology generator"). Purely informational; parser ignores. |
| K | `OOB VLAN` | Conditional | Integer | **OOB switches only.** Names the VLAN ID (from the VLANs sheet, VRF `OOB`) this switch serves. Blank ⇒ the sole/default OOB VLAN when there's only one. Required only when the sheet defines more than one OOB VLAN (distinct-subnet-per-switch designs) — see [OOB VLAN (management network)](#oob-vlan-management-network). Ignored for non-OOB-switch rows. |

### Air-only documentary rows (`Enabled = Air`)

The topology generator automatically injects several Ubuntu / Cumulus VX nodes into every Air sim that aren't operator-provisioned hosts — they simulate customer-edge equipment, NAT, DHCP, and jumpboxes. Operators are encouraged to keep documentary rows for these nodes on the Nodes tab so they're visible at-a-glance.

| Name | Type | Used in | Purpose |
|---|---|---|---|
| `cust-net-edge-01` | switch | L3 OOB | Customer-edge sim — air-mgmt L2 bridge hub + EXIT-VRF eBGP underlay |
| `cust-net-edge-02` | switch | L3 OOB | Second EXIT egress edge + air-mgmt bridge spoke |
| `external-conn` | node | L3 OOB | NAT host on routed EXIT egress legs (172.20.1.1/172.20.2.1) — routes outbound through Air |
| `external-dhcp` | node | L3 OOB | ZTP DHCP server + inter-VRF EXIT relay target |
| `utility` | node | L3 OOB | Jumpbox + status page + OOB-side DHCP relay target |
| `ext-storage-01` | node | L3 OOB (2-8-9-800 only) | STORAGE VRF eBGP peer + simulated customer storage |
| `ext-storage-02` | node | L3 OOB (2-8-9-800 only) | STORAGE VRF eBGP peer (HA) |
| `dhcp-oob` | node | L2 OOB (legacy) | ZTP DHCP server on OOB |
| `oob-server-01` | node | L2 OOB (legacy) | OOB jumpbox |
| `dhcp-edge` | node | L2 OOB (legacy) | Edge-side DHCP |
| `air-oob-switch` | switch | L2 OOB (legacy) | OOB L2 bridge |

Documentary rows have `Enabled = Air`; leave `Mgmt IP`, `MAC Address for ZTP`, `Prefix`, `Gateway` blank. The validator will reject `Enabled = Air` rows whose `Name` is not in this list, and will reject Type mismatches (e.g., labeling `utility` as `switch`).

#### Where these nodes attach (and why they are not in the Wire Map)

These connections are **derived, not authored**. Older workbooks carried them as
`Air - *` rows at the top of the Wire Map; they are now created by the topology
generator instead, so there is nothing to fill in and nothing to keep in sync by
hand. The table below is documentation only — it describes what the generator
builds so you can reason about the resulting sim.

| Link | Plane | Address |
|---|---|---|
| every cluster switch `eth0` → a `cust-net-edge-*` port | air-mgmt L2 bridge | from the switch's Nodes-tab row |
| `cust-net-edge-02..NN` → `cust-net-edge-01` (one trunk each) | air-mgmt L2 | — (loop-free star, hub is `-01`) |
| `utility:eth1` → `oob-switch-01:swp1` | OOB VLAN | `192.168.200.78` |
| `utility:eth2` → `cust-net-edge-01` | air-mgmt L2 | `172.20.0.78` |
| `external-dhcp:eth1` → `cust-net-edge-01` | air-mgmt L2 | `172.20.0.77` |
| `external-dhcp:eth2` → `cust-net-edge-01` | routed EXIT (relay test) | `10.88.88.88` |
| `external-conn:eth1` → `cust-net-edge-01` | routed EXIT egress | `172.20.1.1` ↔ edge `.254` |
| `external-conn:eth2..N` → each further EXIT edge | routed EXIT egress | `172.20.N.1` ↔ edge `.254` |
| `ext-storage-NN:eth0` → `cust-net-edge-01` | air-mgmt L2 | `172.20.0.79`, `.80`, … |
| `cust-net-edge-01` bridge SVI | air-mgmt L2 | `172.20.0.254` (the plane's gateway) |

The switch-side port numbers are **not fixed**: the generator allocates the next
free `swp` on the target edge, after every port your Wire Map already claims. So
adding or removing Wire Map rows shifts which port these land on, which is
expected and harmless.

> **If you re-use a port these need, generation fails — by design.** One
> `(node, interface)` may be wired by exactly one link. If your Wire Map already
> wires a port that a derived link also needs, `make generate` stops with a
> duplicate-interface error naming the node and interface, and you must move
> your row to a free port ("evacuate" it) before generating again.
>
> This is a hard failure on purpose. Air validates the same rule server-side and
> rejects the **entire** topology: the import returns `200` with a simulation id,
> then flips to `INVALID` a moment later with no nodes, no links, and no error
> field. An `INVALID` simulation never appears in the Air UI, so the only symptom
> is `make air-deploy` reporting "Node X not found in simulation" for every node
> in turn, with nothing explaining why. Failing at generation puts the error
> where the fix is.



### Function Naming Conventions

The `Function` column value determines how the automation classifies each device. Use these patterns:

| Pattern | Device Type | Examples |
|---------|-------------|---------|
| `core-01`, `core-02` | Collapsed-core switches (single-tier `2-4-3-200` / `2-4-5-400` / `2-8-5-200` / `2-8-9-400`) | `core-01`, `core-02` |
| `csl` *(or hostname `cl-*`)* | Compute Spine-Leaf — **converged 1-tier** compute (`ns_tiers=1`) | Function `csl`, Name `cl-01` |
| `cl` | Compute **Leaf** in a **2-tier** compute fabric (`ns_tiers=2`); pair with `cs` spine | `cl-01`, `cl-02` |
| `cs` | Compute **Spine** in a 2-tier compute fabric (`ns_tiers=2`) | `cs-01`, `cs-02` |
| `gsl-plane1`, `gsl-plane2` | GPU Spine-Leaf — **converged 1-tier** GPU per plane (`ew_tiers=1`) | `gsl-plane1`, `gsl-plane2` |
| `gl-plane1`, `gl-plane2` | GPU **Leaf** in a **2-tier** GPU fabric (`ew_tiers=2`); pair with `gs-plane*` spine | `gl-plane1-01..04` |
| `gs-plane1`, `gs-plane2` | GPU **Spine** in a 2-tier GPU fabric (`ew_tiers=2`); per plane | `gs-plane1-01`, `gs-plane1-02` |
| `oob-switch-01`, `oob-switch-02`, `oob-switch-03` | OOB management switches | `oob-switch-01` through `oob-switch-03` |
| `su-XX-node-YY` | Compute nodes in Scalable Unit XX | `su-01-node-01`, `su-02-node-04` |
| `storage-XX` | Storage nodes | `storage-01`, `storage-02` |
| `support-XX` | Support/infrastructure nodes | `support-01`, `support-02` |
| `k8s-XX` | Kubernetes nodes | `k8s-01`, `k8s-02` |
| `bcme-XX` | BCME (BMC) nodes | `bcme-01` |

Generated architecture workbooks use seven dual-homed `support-XX` nodes and
two dual-homed `storage-XX` nodes. Dedicated DPU-BMC cables are not generated.

### Name Column (OEM Naming)

The `Name` column lets you use your organization's own device naming scheme. For example:

| Function | Name |
|----------|------|
| `core-01` | `spine01` |
| `core-02` | `spine02` |
| `oob-switch-01` | `mgmt-sw-1` |
| `su-01-node-01` | `gpu-node-a1` |

The Function column is used internally by the automation. The Name column appears in generated hostnames and topology labels. Both values are preserved in the inventory.

### IP Address Planning

All management IPs must be within the OOB VLAN subnet that the node's switch serves (see [OOB VLAN (management network)](#oob-vlan-management-network)). A typical allocation for `192.168.200.0/24`:

| Range | Usage |
|-------|-------|
| `.1` | oob-server-01 (gateway) |
| `.2` - `.4` | OOB switches |
| `.5` - `.6` | Core switches |
| `.10` - `.99` | Infrastructure / support |
| `.100` - `.199` | Storage nodes |
| `.200` - `.254` | Compute nodes |

This is a convention, not a hard requirement. The only rules are: IPs must be unique, valid IPv4, and within the management subnet.

---

## Sheet 3: VLANs & Profiles

This sheet contains three sections stacked vertically:

1. **VLANs** (top) -- VLAN definitions
2. **VRFs** (middle) -- VRF-to-VNI mappings
3. **Port Profiles** (bottom) -- Per-network-role port settings

### Section 1: VLANs

**Row 2 is the header row** (row 1 may contain a title). Data starts at row 3.

| Column | Header | Required | Type | Description |
|--------|--------|----------|------|-------------|
| A | `VLAN ID` | **Yes** | Integer | Numeric VLAN identifier. Must be unique. |
| B | `Name` | **Yes** | String | Short name describing the VLAN purpose. Used to match network profiles in the Wire Map. |
| C | `Purpose` | No | String | Longer description of what this VLAN carries. |
| D | `Subnet` | **Yes** | CIDR | IP subnet for this VLAN (e.g., `192.168.200.0/24`). |
| E | `Gateway` | No | IP address | Gateway IP for the SVI on core switches. |
| F | `VRF` | **Yes** | String | VRF this VLAN belongs to. Common values: `OOB`, `INBAND`, `GPU`, `EXIT`. |
| G | `VNI` | No | Integer | VXLAN Network Identifier. If blank, automatically calculated as `VLAN_ID + 4000`. |

#### Standard VLANs

A typical ERA deployment uses these VLANs (IDs and subnets vary by site):

| VLAN ID | Name | VRF | Purpose |
|---------|------|-----|---------|
| 200 | OOB | OOB | Out-of-band management |
| 300 | CPU/In-Band | INBAND | CPU/host in-band traffic |
| 400 | Support | INBAND | Support infrastructure |
| 500 | Storage | INBAND | Storage network |
| 900 | GPU | GPU | GPU-to-GPU RDMA traffic |

#### OOB VLAN (management network)

The OOB (out-of-band management) network is declared entirely on this sheet
and the Nodes sheet — there is no separate `mgmt_subnets` Settings field.

1. **VLANs & Profiles** — one row per OOB VLAN, `VRF = OOB`. The `Subnet`
   and `Gateway` columns on that row *are* the OOB network's subnet and
   gateway. The default templates ship a single row: `VLAN ID 200`,
   `Name OOB`, `Subnet 192.168.200.0/24`, `Gateway 192.168.200.1`,
   `VRF OOB`.
2. **Nodes** — each `oob-switch-*` row's `OOB VLAN` column (K) names which
   OOB VLAN ID that switch serves. Leave it **blank** when there is only
   one OOB VLAN row — it defaults to that sole VLAN. The invariant is
   **1 switch : 1 OOB VLAN** (a switch cannot serve two OOB VLANs).

Two supported shapes:

- **Single shared subnet (default).** All OOB switches reference the
  *same* OOB VLAN ID (anycast gateway across the switches) — e.g. all
  `oob-switch-*` rows set `OOB VLAN = 200`, or leave it blank. One VLAN
  row, one subnet, `192.168.200.0/24`.
- **Distinct subnet per switch.** Add one OOB VLAN row per subnet (e.g.
  `VLAN 200` → `192.168.200.0/24` and `VLAN 201` → `192.168.201.0/24`),
  then set each switch's `OOB VLAN` column to the ID it serves. This shape
  **requires L3 OOB** (`oob_uplink_mode = l3`) — `make validate-excel`
  fails the workbook if it detects more than one distinct OOB VLAN subnet
  without L3 OOB enabled.

The switch's own management IP (Nodes `Mgmt IP Address` / `Gateway`
columns, i.e. its eth0) is a separate concern from the OOB subnet it
*serves* — a switch's eth0 address doesn't have to sit inside the VLAN it
terminates for other devices.

### Using your own management subnets

ERA has **two independent management planes**, and both are yours to set:

| Plane | Carries | Declared on |
|---|---|---|
| **Switch management** (`air_mgmt_subnet`) | every switch `eth0`; the plane Ansible reaches switches on | `Air_Only` sheet → "Air Management Subnet" |
| **OOB VLAN** | node BMC / iDRAC / LOM ports | `VLANs & Profiles` → the row with `VRF = OOB` |

They are separate on purpose. In a brownfield deployment the switches usually
answer on the site's existing management network while the BMCs sit on a
purpose-built OOB VLAN. Point each at the real subnet and the tool follows.

#### 1. Set the switch-management subnet

On the **`Air_Only`** sheet, set **Air Management Subnet** to your CIDR:

| Air Management Subnet | `10.78.255.0/24` |
|---|---|

Everything on that plane derives from it — switch `eth0`, the DHCP listener,
the jump host's interface and the bridge gateway. Leave it blank for the
`172.20.0.0/24` default.

#### 2. Set the OOB VLAN subnet

On **`VLANs & Profiles`**, the `VRF = OOB` row defines the BMC plane:

| VLAN ID | Name | Subnet | Gateway | VRF |
|---|---|---|---|---|
| `200` | `OOB` | `10.78.220.128/25` | `10.78.220.129` | `OOB` |

Switch SVIs, the anycast gateway, the server `eth0` prefix and its default route
are all derived from this row. Any prefix length works — it does not have to be
a `/24`.

#### 3. (Optional) Pin static switch management IPs

By default the tool auto-assigns switch `eth0` addresses from `.201` upward
inside `air_mgmt_subnet`. To reproduce the addresses your switches **already
answer on**, fill the Nodes tab `Mgmt IP Address` column:

| Function | Name | Mgmt IP Address | Prefix | Gateway |
|---|---|---|---|---|
| `core` | `core-site-01` | `10.78.255.21` | `24` | `10.78.255.1` |
| `core` | `core-site-02` | `10.78.255.22` | `24` | `10.78.255.1` |
| `oob-switch` | `oob-switch-site-01` | *(blank)* | | |

- **Filled** → honoured verbatim.
- **Blank** → auto-assigned from `.201`, skipping anything already pinned.
- **Mixed is fine** — pin the ones you know, leave the rest blank. Common in
  brownfield, where only some real addresses are on hand.

`make validate-excel` enforces three rules on a pin:

1. It must sit **inside `air_mgmt_subnet`**. Outside both that and every OOB
   VLAN subnet, the switch would be unreachable — hard error.
2. It must not take an address Air provisions for infrastructure —
   `.1` (gateway), `.77` (external-dhcp), `.78` (utility), `.254`
   (cust-net-edge bridge SVI). The error names the owner.
3. Two switches must not pin the same address.

> **Hostnames are yours.** Role comes from the `Function` column, never from the
> name, so `mysite-prod-gpu-01` is configured exactly like `gpu-01`. See
> [Roles](ROLES.md).

> **Servers are not pinned this way.** Their `Mgmt IP Address` belongs on the
> **OOB VLAN** subnet, not `air_mgmt_subnet`. A non-switch host inside
> `air_mgmt_subnet` collides with an auto-assigned switch `eth0` and is
> rejected.

#### Worked example — an on-prem brownfield site

```
Air_Only     Air Management Subnet   10.78.255.0/24     <- switch eth0 plane
VLANs        VLAN 200 / VRF OOB      10.78.220.128/25   <- BMC plane
                                     gw 10.78.220.129
Nodes        core-...-01   10.78.255.21   (pinned)
             core-...-02   10.78.255.22   (pinned)
             gpu-01        10.78.220.141  (BMC, on the OOB VLAN)
```

Result: switches reachable at their pinned addresses, BMCs on the OOB VLAN,
and the two planes routed independently — matching the physical site.

**Sizing (hard-fail).** `make validate-excel` fails the workbook if an OOB
subnet can't hold the deployment:

- **Containment** — every Nodes-tab management IP must be reachable on *a*
  management plane. For servers that means inside an OOB VLAN subnet. For
  **switches** it means inside an OOB VLAN subnet **or** inside
  `air_mgmt_subnet` (see [Using your own management subnets](#using-your-own-management-subnets)),
  because a switch's `eth0` legitimately lives on the switch-management plane.
  An IP outside every declared plane would be unreachable and is a hard error.
- **Capacity** — each OOB subnet must have room for the hosts on it *plus* the
  auto-derived infrastructure the tool places there: the gateway
  (`oob-server-01`) and `dhcp-oob` in L2, and additionally the EXIT-VRF trio
  (`external-dhcp` / `utility` / `external-conn`) and `ztp_server` in L3. So a
  `/27` (30 usable) that must host 31 nodes + 2 infra = 33 is rejected — widen
  the subnet or split hosts across multiple OOB VLANs (L3 OOB). Rule of thumb:
  usable addresses ≥ (active hosts on the subnet) + (2 in L2, 6 in L3).

#### Dual-plane GPU (2-8-9-800 only)

In dual-plane architectures, the GPU fabric is split across two
L3-isolated planes. Each plane is a separate VLAN entry in this sheet:

| VLAN Name | VRF | Purpose |
|-----------|-----|---------|
| `gpu_plane1` | GPU | GPU east-west on plane 1 (`gsl-plane1-*` switches) |
| `gpu_plane2` | GPU | GPU east-west on plane 2 (`gsl-plane2-*` switches) |

Both planes share VLAN ID 900 but live on separate underlay loopback
subnets, separate EVPN scopes, and separate BGP graphs — they're
physically isolated. The parser detects dual-plane mode from the
`gpu_plane1` / `gpu_plane2` names; do not use the plain `gpu` name in
2-8-9-800 sheets. Converged architectures (2-4-3-200 / 2-4-5-400 / 2-8-5-200 /
2-8-9-400) use the single `gpu` VLAN instead.

The GPU plane is intentionally excluded from CSL switches in the
generated configs — only `gsl-plane{1,2}-*` switches carry it.

#### GPU VLAN topology modes

The Settings field `gpu_vlan_mode` controls how GPU traffic is partitioned:

| Mode | VLAN rows | Wire Map profile | Use case |
|---|---|---|---|
| `single` (default) | `GPU` | `GPU Network` | One VLAN for all GPU traffic |
| `per_rail` | `gpu_rail<N>` | `GPU Rail N` | One VLAN per rail (B300 4-rail isolation) |
| `per_rail_per_plane` | `gpu_rail<R>_plane<P>` | `GPU Rail R Plane P` | One VLAN per (rail, plane) (large B300 dual-plane deployments) |

##### `per_rail`

For deployments that isolate each GPU NIC (rail) on its own VLAN and
subnet — common in 4-rail B300 designs — set `gpu_vlan_mode = per_rail`
and replace the single `GPU` VLAN row with one row per rail named
`gpu_rail<N>`:

| VLAN ID | Name | Purpose | Gateway | Subnet | VRF |
|---------|------|---------|---------|--------|-----|
| 901 | `gpu_rail1` | GPU rail 1 east-west | 192.168.128.1 | 192.168.128.0/24 | GPU |
| 902 | `gpu_rail2` | GPU rail 2 east-west | 192.168.129.1 | 192.168.129.0/24 | GPU |
| 903 | `gpu_rail3` | GPU rail 3 east-west | 192.168.130.1 | 192.168.130.0/24 | GPU |
| 904 | `gpu_rail4` | GPU rail 4 east-west | 192.168.131.1 | 192.168.131.0/24 | GPU |

Wire Map — each GPU NIC's row uses Network Profile = `GPU Rail N`:

```
System Name (A) | Port (A)      | Network Profile | System Name (B) | Port (B)
gpu-01          | B3140 Port 1  | GPU Rail 1      | spine-01        | swp3s0
gpu-01          | B3140 Port 2  | GPU Rail 2      | spine-02        | swp4s0
gpu-01          | B3140 Port 3  | GPU Rail 3      | spine-01        | swp5s0
gpu-01          | B3140 Port 4  | GPU Rail 4      | spine-02        | swp6s0
```

IP allocation: same host octet on every rail — `gpu-01` lands at `.201`
on every rail, `gpu-02` at `.202`, and so on. Fits ~53 GPU compute
nodes per rail in a /24.

##### `per_rail_per_plane`

Combines per-rail isolation with multi-plane physical separation. Each
(rail, plane) combination gets its own VLAN and subnet:

| VLAN ID | Name | Subnet | VRF |
|---------|------|--------|-----|
| 901 | `gpu_rail1_plane1` | 192.168.0.0/24 | GPU |
| 902 | `gpu_rail2_plane1` | 192.168.1.0/24 | GPU |
| 903 | `gpu_rail3_plane1` | 192.168.2.0/24 | GPU |
| 904 | `gpu_rail4_plane1` | 192.168.3.0/24 | GPU |
| 901 | `gpu_rail1_plane2` | 192.168.16.0/24 | GPU |
| 902 | `gpu_rail2_plane2` | 192.168.17.0/24 | GPU |
| 903 | `gpu_rail3_plane2` | 192.168.18.0/24 | GPU |
| 904 | `gpu_rail4_plane2` | 192.168.19.0/24 | GPU |

VLAN ID strategy is flexible:
- **Reused across planes** (as shown above — 901-904 on both planes): relies on physical plane isolation. Matches the existing dual-plane VLAN 900 convention.
- **Unique per plane** (e.g., plane1=901-904, plane2=905-908): no L2 dependency on physical isolation; easier to debug a single switch's bridge table.

Wire Map — each GPU NIC's row uses Network Profile = `GPU Rail R Plane P`:

```
System Name (A) | Port (A)     | Network Profile         | System Name (B)
gpu-01          | B3140 Port 1 | GPU Rail 1 Plane 1      | gsl-plane1-01
gpu-01          | B3140 Port 2 | GPU Rail 2 Plane 1      | gsl-plane1-01
gpu-01          | B3140 Port 5 | GPU Rail 1 Plane 2      | gsl-plane2-01
gpu-01          | B3140 Port 6 | GPU Rail 2 Plane 2      | gsl-plane2-01
```

IP allocation: same host octet across every (rail, plane). `gpu-01`
lands at `.201` on all 8 (rail, plane) subnets, `gpu-02` at `.202`,
etc.

Per-rail-per-plane on dedicated_gpu architectures (CSL + GSL split,
2-8-9-800-style) emits one SVI + VRR per (rail, plane) on the GSL
switches, filtered to that switch's plane. GSL-plane1 switches carry
plane1 rails; GSL-plane2 switches carry plane2 rails.

##### Constraints (all modes)

- All GPU VLAN rows must have **VRF = `GPU`**.
- Duplicate VLAN IDs are tolerated across plane-suffixed names (the
  validator allows the convention).
- Pick one mode. The three modes don't combine on a single deployment.
- GPU VRF VLANs cannot have DHCP Relay Client set (validator hard-fails).

#### VNI Convention

The VNI (VXLAN Network Identifier) is conventionally `VLAN_ID + 4000`:

| VLAN ID | VNI |
|---------|-----|
| 200 | 4200 |
| 300 | 4300 |
| 500 | 4500 |
| 900 | 4900 |

You can override this by putting an explicit VNI in column G. If column G is blank, the parser auto-calculates it.

**Multi-plane GPU fabrics reuse the VLAN ID but not the VNI.** On a dual-plane
architecture both `gpu_plane1` and `gpu_plane2` carry VLAN `900` — the planes
own disjoint sets of switches, so the VLAN ID is locally significant to each.
Their VNIs are held apart instead:

| Plane | VLAN | VNI |
|-------|------|-----|
| `gpu_plane1` | 900 | 4900 |
| `gpu_plane2` | 900 | 4901 |

Because the VLAN ID alone does not distinguish the planes, **the VNI column is
load-bearing on plane 2 and later** — leave it populated. Blanking it makes the
parser fall back to `VLAN_ID + 4000`, collapsing plane 2 onto `4900`.

Sharing one VNI across planes is also valid — it is what the NVIDIA reference
configurations do — so `make validate-excel` permits a duplicate VNI across
plane-suffixed VLAN rows (and only those). If you want that numbering, blank the
plane-2 VNI or set both cells to the same value.

### Section 2: VRFs

Below the VLANs section, a row with `VRFs` in column A marks the start of the VRF definitions. The header row follows, then VRF data.

| Column | Header | Required | Type | Description |
|--------|--------|----------|------|-------------|
| A | VRF Name | **Yes** | String | VRF identifier (e.g., `OOB`, `INBAND`, `GPU`, `EXIT`, `STORAGE`). |
| B | Description | No | String | What this VRF is for. |
| C | L3 VNI | **Yes** | Integer | Layer 3 VNI for inter-VLAN routing within this VRF. |
| D | VLAN | **Yes** | Integer | VLAN used to carry the L3 VNI (a "transit" VLAN). |

### Section 3: Port Profiles

Below the VRFs section, a row with `Port Profiles` in column A marks the start of port profile definitions. These define how each type of network connection is configured on the core switches.

| Column | Header | Required | Type | Description |
|--------|--------|----------|------|-------------|
| A | Profile | **Yes** | String | Profile name. Must match the `Network Profile` values used in the Wire Map sheet. |
| B | Port Mode | **Yes** | String | `Access` or `Trunk` (switched), `L3` (routed, e.g. uplinks), or `L2` (bare L2 link, e.g. ISL). |
| C | Native/Access VLAN | Conditional | Integer | For Access mode: the access VLAN. For Trunk mode: the native (untagged) VLAN. |
| D | Allowed VLANs | Conditional | String | For Trunk mode: comma-separated list of allowed VLAN IDs. |
| E | Untagged VLAN | No | Integer | Untagged VLAN (if different from native). |
| F | VRF | No | String | VRF assignment for this port profile (used by `L3` profiles). |
| G | LACP Bypass | No | Yes/No | Enable LACP bypass on bonded interfaces using this profile. |
| H | Speed | No | String | Link speed for ports using this profile (e.g. `1G`, `100G`, `400G`). |
| I | Breakout | No | Integer | Number of breakout sub-ports (e.g., 4 for 4x100G from a 400G port). |
| J | Lanes | No | Integer | Physical lanes per sub-port (determines sub-port speed). |

Common port profiles:

| Profile | Mode | Typical Use |
|---------|------|-------------|
| CPU/In-Band Network | Trunk | Compute node uplinks (bonded, LACP bypass) |
| GPU Network | Access | GPU NIC direct connections (high bandwidth) |
| OOB / IPMI | Access | Management/IPMI ports on OOB switches |
| Storage | Trunk | L2 storage-server attachment links |
| Storage Uplink | L3 | Routed fabric-to-external-storage links |
| Support | Trunk | Support infrastructure uplinks |
| ISL | Trunk | Inter-switch link between core-01 and core-02 |
| OOB Uplink | Access (L2) or L3 | Core-to-OOB switch uplinks. Use `Access` with VLAN 200 when `oob_uplink_mode = l2`; use `L3` when `oob_uplink_mode = l3`. Must match the Settings value. |
| Edge Uplink | L3 | Routed core/leaf-to-customer-edge links |

### Section 4: DHCP Relay (optional)

Below the Port Profiles section, a row with `DHCP Relay` in column A marks
the start of the VRF-aware DHCP relay table. Each row defines one
server-group: the DHCP server(s) for one VRF and the L3 interface the
relay uses to reach them.

Per the ERA Network Architecture Principals deck, DHCP relay is the
mechanism for letting hosts in one VRF obtain leases from a DHCP server
in another VRF (e.g., compute hosts in `INBAND` getting addresses from a
DHCP server in `OOB` or `EXIT`).

| Column | Header | Required | Type | Description |
|--------|--------|----------|------|-------------|
| A | Server IP | **Yes** | String | DHCP server IPv4 address. Comma-separated list for multiple servers in the same server-group (failover). |
| B | VRF | **Yes** | String | VRF where the relay daemon runs (= the VRF where the DHCP server is reachable). Allowed values: `OOB`, `EXIT`, `INBAND`. One row per VRF. |
| C | Upstream Interface | **Yes** | String | L3 interface in the declared VRF, used as the relay's path toward the server. Examples: `vlan200`, `vlan3004_l3`, `swp61s0`, `bond1`. |

Leave the table empty (header rows only, no data) when no DHCP relay is
needed. This is the default for all bundled architectures.

To enable DHCP relay on a per-VLAN basis, also set the `DHCP Relay Client`
column on each client VLAN row in the VLANs subsection:

| `DHCP Relay Client` value | Meaning |
|---|---|
| `No` (or blank) | VLAN does not participate in DHCP relay |
| `OOB`, `EXIT`, `INBAND`, … | VLAN's SVI becomes a downstream-interface under the matching server-group |
| `OOB,EXIT` (comma-list) | VLAN opts into multiple server-groups simultaneously |

The referenced VRF must have a row in the DHCP Relay table.

**Validation rules:**

- VLANs in `GPU`, `EXIT`, or `default` VRF must have `DHCP Relay Client = No` (per architecture principles; GPU traffic does not transit a DHCP relay path, EXIT is a transit/server VRF).
- Duplicate VRF rows in the DHCP Relay table are rejected — combine multiple servers into a comma-list on a single row.
- Upstream Interface must be a syntactically valid Cumulus L3 interface (`swpN`, `swpNsM`, `vlanN`, `vlanN_l3`, or `bondN`).
- A VLAN's `DHCP Relay Client` value must match a configured VRF in the DHCP Relay table — referencing an unconfigured VRF is an error.

**Inter-VRF relay (the common case):** a client VLAN's VRF *may* differ from
its `DHCP Relay Client` target. Example: VLAN 400 lives in `INBAND` but has
`DHCP Relay Client = EXIT` — the dhcrelay daemon runs in `EXIT`, reaches the
client subnet via the cores' `route-import from-vrf INBAND` leak (emitted
automatically by the core template), and forwards to the EXIT-VRF DHCP
server. This is the headline use case in the ERA Network Architecture
Principals deck.

**Air-sim test targets:** the bundled L3 OOB Air infrastructure exposes two
DHCP servers operators can target from the DHCP Relay table when verifying
the path end-to-end in `make air-deploy`:

| Target VRF | Server IP        | Air node             | Upstream interface |
|------------|------------------|----------------------|--------------------|
| `OOB`      | `192.168.200.78` | `utility:eth1`       | `vlan3001_l3`      |
| `EXIT`     | `10.88.88.88`    | `external-dhcp:eth2` | `vlan3004_l3`      |

For production deployments, replace these IPs with the customer's real DHCP
server addresses. The Air-sim IPs are only intended for verifying that the
relay path is wired correctly in the simulation.

**Generated NVUE config** (one block per DHCP Relay table row):

```
nv set service dhcp-relay <VRF> server-group <vrf>-dhcp-servers server <ip>
nv set service dhcp-relay <VRF> server-group <vrf>-dhcp-servers upstream-interface <upstream>
nv set service dhcp-relay <VRF> downstream-interface <vlan> server-group-name <vrf>-dhcp-servers
nv set service dhcp-relay <VRF> source-ip giaddress
```

Emitted on `core` (and `csl` in dedicated-GPU designs) since those switches have SVIs in every service VRF. OOB switches do not currently host relay daemons.

---

## Sheet 4: Wire Map

The Wire Map is the physical cabling plan. Each row represents one cable connection between a device port and a switch port.

**Row 1 is the header row.** Data starts at row 2.

### VLANs & Profiles is authoritative

**All port settings — Port Mode, Native/Access VLAN, Allowed VLANs,
Port Speed, breakout, lanes — are derived exclusively from the
VLANs & Profiles tab via the `Network Profile` lookup.** The Wire Map
maps physical cabling and references profiles by name; it doesn't
re-declare port settings. This is the single source of truth.

If you mistype a `Network Profile` value (e.g., `CPU/InBand Netork`
instead of `CPU/In-Band Network`), `make validate-excel` errors out
before generation.

### Column Reference

| Column | Header | Required | Type | Description |
|--------|--------|----------|------|-------------|
| A | `Display in Air` | No | Yes/No | Whether to include this connection in the NVIDIA Air virtual topology. Set `No` for physical-only connections that Air cannot simulate (real-HW LOM Port 1, iLO, iDRAC, XCC). **CRA OOB rule**: each active server must have exactly ONE Display=Yes OOB row (the BMC). Air's plain Ubuntu can't bond two OOB links — a second Display=Yes OOB row will be flagged by `validate-excel`. |
| B | `System Name (A)` | **Yes** | String | Hostname of the device on the "A" side of the cable (matches `Name` from the Nodes sheet). Older Excels' `System Role` / `Function (A)` headers also accepted via aliases. |
| C | `Port (A)` | **Yes** | String | Port identifier on the device side. For servers: `eth0`, `eth1`, …. For switches: `swp1`, `swp1s0`, …. |
| D | `Port Side (A)` | No | String | Physical port side label for cabling crew documentation. Parser ignores. |
| E | `Cable Split (A)` | No | String | Physical cable assembly notation for the A-side (e.g., `8 splits`, `2x100G to QSFP56`). Parser ignores. |
| F | `System Name (B)` | **Yes** | String | Hostname of the switch / peer on the "B" side (matches `Name` from the Nodes sheet). Older Excels' `Switch Role` / `Function (B)` also accepted via aliases. |
| G | `Port (B)` | **Yes** | String | Port on the switch side (`swp1`, `swp44`, etc.). |
| H | `Port Side (B)` | No | String | Physical port side label for cabling crew. Parser ignores. |
| I | `Cable Split (B)` | No | String | Physical cable assembly notation for the B-side. Parser ignores. |
| J | `Network Profile` | **Yes** | String | The network type this connection belongs to. Must match exactly one of: a `Profile` row in VLANs & Profiles → Port Profiles; a `gpu_rail<N>` or `gpu_rail<R>_plane<P>` VLAN row (rail modes); a `gpu_plane<N>` VLAN row (dual-plane mode); the literal prefix `Air -`; or contain `Disabled` / `Neighbor` / `Unused` for disable markers. Validator errors on anything else. |

> **Removed 2026-05-19:** the prior columns `Port Speed (A)`,
> `Port Speed (B)`, `Port Mode`, `Native/Access VLAN`, `Allowed VLANs`
> were deleted from the schema because their values duplicated
> VLANs & Profiles data and tended to drift. If you're migrating an
> older Excel, just delete those columns by hand — the parser was
> already ignoring them.

### 8× breakout convention

Spectrum switches configure 8-way breakout on a single physical cage,
which consumes the lanes of the *next-higher* cage. By convention:

* Configure 8× breakout on an **ODD** base port (`swp1`, `swp3`, …,
  `swp61`, `swp63`)
* The adjacent **EVEN** port (`swp2`, `swp4`, …, `swp62`, `swp64`)
  is then unusable independently — either omit it from the Wire Map
  entirely (implicit disable), or list it with a `Disabled by Neighbor`
  / `Unused` Network Profile (explicit disable)

The validator (`validate_8x_breakout_odd_ports`) detects 8× breakout
when any sub-port index `s4`–`s7` is present for a base port (4×
breakout only exposes `s0`–`s3`). It errors when:

1. The 8× base port number is even
2. The adjacent (base + 1) port has any live `Display = Yes` row
   with a non-disabled Network Profile

### Network Profile Conventions

The `Network Profile` column (J) controls how the connection is classified. Use names that match the Port Profiles defined in the VLANs & Profiles sheet.

Standard physical profiles:

| Profile Name | Usage |
|-------------|-------|
| `CPU/In-Band` or `CPU/In-Band Network` | Compute node CPU NICs to core switch |
| `GPU` or `GPU Network` | Compute node GPU NICs to core switch |
| `OOB / IPMI` | Device management ports to OOB switch |
| `Storage` | Storage node NICs to core switch |
| `Storage Uplink` | L3 STORAGE-VRF links to external storage peers |
| `Support` | Support node NICs to core switch |
| `ISL` | Inter-switch links between core-01 and core-02 |
| `OOB Uplink` | Core switch uplinks to OOB switches |
| `Edge Uplink` | Core switch uplinks to edge/exit switches |

Air-specific profiles (prefixed with `Air - `):

| Profile Name | Usage |
|-------------|-------|
| `Air - Management` | Virtual OOB management connections (eth0 to oob-switch) |
| `Air - OOB Network` | Virtual OOB infrastructure connections |
| `Air - Edge Network` | Virtual edge connections |

### Wire Map Row Types

**Node-to-switch connections** (most common):
```
su-01-node-01 | eth1 | CPU/In-Band | core-01 | swp1s0
```
A compute node's eth1 connects to core-01 port swp1 sub-port 0 for CPU/In-Band traffic.

**Switch-to-switch connections** (ISL, uplinks):
```
core-01 | swp49s0 | ISL | core-02 | swp49s0
```
An inter-switch link between core-01 and core-02.

**Core-as-system connections** (core switch own ports):
```
core-01 | swp57s0 | OOB Uplink | oob-switch-01 | swp49
```
Core switch port connecting as an uplink to an OOB switch.

**Outbound connections** (Air internet access):
```
oob-server-01 | eth0 | Air - Management | outbound | 
```
When `System Name (B)` is `outbound`, this creates an internet-access link in the Air topology.

### Port Naming

**Switch ports** use Cumulus notation:
- `swp1` -- simple port 1
- `swp1s0` -- port 1, sub-port 0 (after breakout)
- `swp1s0` through `swp1s3` -- 4-way breakout of port 1

**Server ports** use Linux interface names:
- `eth0` -- typically the OOB management interface
- `eth1`, `eth2` -- data-plane interfaces (CPU, GPU, etc.)

In the Wire Map, server interfaces get sequential `ethN` names in the generated topology. The order of rows determines the interface numbering: `eth0` is reserved for OOB management, and data-plane NICs start at `eth1`.

---

## Sheet 5: Routing Policy Overrides (Optional)

Three optional sheets let you override or extend the BGP prefix-lists,
route-maps, and community-lists the generator computes by default.
All three are **derive-by-default**: leave a sheet out of
the workbook (or leave it empty below the header) and generation is
byte-identical to a workbook that never had the sheet. None of these
sheets are in the required-sheets list checked by `make validate-excel`.

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

## Common Configurations

### Minimal Setup (Physical Deployment)

For a basic physical deployment without Air or LDAP:

**Settings:**
- Set `architecture` to your arch (e.g., `2-8-5-200`)
- Set per-node BGP ASNs in the **Loopbacks** tab's `ASN` column; the shipped workbook already has them
- Set `loopback_base` to your loopback range
- Leave AIR DEPLOYMENT fields blank
- Set `ldap_enabled` to `No`
- Leave `ztp_enabled` blank — it is inert; run `make ztp-setup` / `make switch-ztp-deploy` to use ZTP

**Nodes:** Fill in all switches and servers with management IPs. Leave MAC blank for auto-generation.

**VLANs & Profiles:** Use the default VLAN layout provided in the template. Set the OOB VLAN row's `Subnet`/`Gateway` to your OOB network (see [OOB VLAN (management network)](#oob-vlan-management-network)).

**Wire Map:** Document all physical cabling.

### Air Simulation Deployment

Same as above, plus:
- Set `deploy_in_air` to `Yes`
- Run `make air-setup` once to pick the Air instance (public Air or internal `inside.dsx-air`) and store credentials — no Excel field needed (`air_org`/`air_username` in the Excel are inert and can be omitted)
- Add `Air - Management` rows in Wire Map for each node's eth0-to-OOB-switch connection
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
3. Use those same `Name` values in the Wire Map `System Name (A)` and `System Name (B)` columns. The parser looks up each row's role/Function from the Nodes sheet by matching this name, so the names must agree exactly across both sheets.

---

## Tips and Gotchas

### General

- **Always validate before importing.** Run `make validate-excel EXCEL=<path>` before `make import`. The validator checks sheet structure, IP formats, duplicate ports, VLAN integrity, and cross-sheet consistency.
- **Section headers matter.** Do not delete or rename the section header rows (GENERAL, NETWORK, etc.) in the Settings sheet. The parser skips them by name.
- **Blank rows end sections.** In the VLANs table, a blank row or non-integer in the VLAN ID column signals the end of the VLAN list. Do not leave gaps between VLAN rows.

### Settings

- **`loopback_base` is three octets, not a full IP.** Write `172.16.176`, not `172.16.176.0` or `172.16.176.0/32`. The fourth octet is assigned per-switch and per-VRF automatically.
- **`disabled_ports` uses physical port numbers**, not breakout sub-ports. If port 50 is disabled, all its sub-ports (swp50s0, swp50s1, etc.) are disabled.
- **`mgmt_subnets` is retired.** `make validate-excel` hard-fails if a workbook still has it set — the OOB subnet now lives on the OOB VLAN row (VRF `OOB`) in "VLANs & Profiles". See [OOB VLAN (management network)](#oob-vlan-management-network).
- **`management_switches` is retired.** The OOB switch count is derived from the Active `oob-switch-*` rows on the Nodes tab — there's no separate count field to keep in sync. If a workbook still has `management_switches` set, `make validate-excel` only warns that it's ignored; it no longer truncates or pads the OOB switch list.

### Nodes

- **Function names must be unique.** No two rows can share the same Function value.
- **Management IPs must be unique.** The validator flags duplicate IPs as errors.
- **MAC addresses are optional for Air.** When deploying to NVIDIA Air, MACs are auto-generated using a deterministic hash of the node name. For physical deployments, switches need real MACs for ZTP DHCP reservations.
- **The Enabled column is forgiving.** If the column is missing entirely, all nodes default to enabled. If present, `Yes`, `True`, `1`, or blank all mean enabled.
- **Mgmt IP should NOT include the prefix.** Put the bare IP in column D (e.g., `192.168.200.5`) and the prefix length in column E (e.g., `24`). Some older templates accepted `192.168.200.5/24` in one column, but the current format separates them.
- **`OOB VLAN` (column K) only matters for `oob-switch-*` rows.** Leave it blank unless the workbook defines more than one OOB VLAN — see [OOB VLAN (management network)](#oob-vlan-management-network).

### VLANs & Profiles

- **VNI = VLAN ID + 4000 by convention.** If you leave the VNI column blank, the parser calculates it automatically. Only specify VNI explicitly if you need to deviate from this convention.
- **VLAN names must be consistent with Wire Map profiles.** The parser uses fuzzy matching (e.g., `CPU/In-Band` matches profiles containing "cpu" or "in-band"), but exact matches are safer.
- **Port Profiles define the default config for each network type.** Individual Wire Map rows can override port mode and VLAN settings, but the profile is the baseline.
- **VRF names are case-sensitive.** Use `OOB`, `INBAND`, `GPU`, `EXIT` consistently.
- **A second OOB VLAN row requires L3 OOB.** Two or more VRF=`OOB` rows with distinct subnets are only valid when `oob_uplink_mode = l3`; `make validate-excel` fails otherwise.

### Wire Map

- **`System Name (A)` and `System Name (B)` must match a Nodes `Name` value exactly.** If the Nodes sheet has `core-01`, the Wire Map must use `core-01` (not `Core-01` or `spine01`). The parser derives each row's role/Function by looking this name up in the Nodes sheet.
- **eth0 is reserved for OOB management.** When the topology generator assigns interface names, eth0 always maps to the OOB management connection. Data-plane interfaces start at eth1. Do not assign a data-plane profile to eth0.
- **`outbound` is a special `System Name (B)` value.** It creates internet access links in Air simulations. It does not need a matching Nodes entry.
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
against the `Function` and `Name` columns of your own Nodes tab, and anything that
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

**What you may write.** `nv` commands only:

- ✅ `nv set …`, `nv unset …`, `nv show …`
- ❌ `nv config …` — applying or replacing the configuration is the tool's job. A
  mid-script `nv config apply` would apply a half-built config and leave the rest
  staging against live state.
- ❌ `nv action …` — actions are imperative, leave no configuration state, and are not
  idempotent when ZTP re-runs the file.
- ❌ anything not starting with `nv ` — this is not a shell.
- ❌ shell metacharacters (`` ` ``, `$( )`, `;`, `&&`, `||`, `|`, `>`, `<`). Values with
  spaces are fine and get quoted for you: `nv set system message pre-login "Authorized
  use only"`.

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

The switch still passes. This is necessary because NVUE re-quotes values — a banner you
write with `"double quotes"` comes back from the switch in `'single quotes'` — and
because overriding a setting the tool also configures makes the tool's own line look
absent. Settings you do **not** touch are compared exactly as before, so real drift is
still caught.

Example:

| Switch_Location | Config |
|---|---|
| `ALL` | `nv set system message pre-login "Authorized use only"` |
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

- **Sheet structure**: All required sheets present (Settings, Nodes, VLANs & Profiles).
- **Required fields**: Mandatory Settings keys have values.
- **IP format**: All IPs and CIDRs are syntactically valid IPv4.
- **MAC format**: MAC addresses use `xx:xx:xx:xx:xx:xx` notation.
- **Architecture**: Value is one of the seven valid architectures (`2-4-3-200`,
  `2-4-5-400`, `2-4-5-800`, `2-8-5-200`, `2-8-9-400`, `2-8-9-800`, `2-8-9-400-SP`).
- **Duplicates**: No duplicate Function names, no duplicate management IPs.
- **Port conflicts**: No duplicate switch port assignments in the Wire Map.
- **Cross-sheet consistency**: Wire Map `System Name (A)` / `System Name (B)` values reference nodes that exist in the Nodes sheet.
- **Subnet sanity**: Gateways are within their node's management subnet (warning if not).
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

### Settings -- Required

| Field | Why It Is Required |
|-------|--------------------|
| `architecture` | Determines which templates, port mappings, and topology rules to apply. |
| Loopbacks `ASN` column | Per-node BGP ASN source; BGP will not converge without an ASN. (Legacy `Settings.bgp_asn` also accepted.) |
| `loopback_base` | Loopback IPs are derived from this base for all VRFs. |

### Settings -- Optional (with Defaults)

| Field | Default If Omitted |
|-------|-------------------|
| `site_name` | `default` |
| `deploy_in_air` | `No` |
| `ns_tiers` | `1` (compute converged; `2` = split `cl`+`cs`) |
| `ew_tiers` | `1` (GPU converged; `2` = split `gl`+`gs` per plane) |
| `tiers` | *(deprecated)* — seeds both `ns_tiers` / `ew_tiers` if missing |
| `convergence` | `full` |
| `ldap_enabled` | `No` |
| `telemetry_enabled` | *(inert — omit)* |
| `ztp_enabled` | *(inert — omit)* |
| `timezone` | `Etc/Zulu` |

### Nodes -- Required Columns

| Column | Why It Is Required |
|--------|--------------------|
| `Function` | Primary key for all cross-references. |
| `Mgmt IP Address` | Every node needs a management IP for ZTP and SSH access. |
| `OOB VLAN` | Conditional — only required on `oob-switch-*` rows once the workbook defines more than one OOB VLAN (VRF `OOB`) row; otherwise blank defaults to the sole OOB VLAN. |

### Wire Map -- Required Columns

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
management-IP conventions. These are **not** Settings fields — they
apply uniformly to every arch/site and can't be set from the Excel
except where a "Settings escape hatch" is called out below.

| Constant | Value | Meaning | Excel escape hatch |
|----------|-------|---------|---------------------|
| `LOOPBACK_BASE` (`excel_parser.py:87`) | `172.16.176` | First 3 octets of the underlay loopback / router-id supernet used when `Settings.loopback_base` is blank. | **Yes** — `Settings.loopback_base` (read at `excel_parser.py:4153`). |
| `OOB_ASN_OFFSET` (`:100`) | `0` | OOB switch ASN = `base_asn + 0 + oob_idx`. | No. |
| `CSL_LEAF_ASN_OFFSET` (`:101`) | `400` | Dedicated N/S leaf (`cl`) ASN = `base_asn + 400 + core_num`, only when `ns_tiers > 1`. | No. |
| `CSL_SPINE_ASN_OFFSET` (`:108`) | `500` | Dedicated N/S spine (`cs`) ASN = `base_asn + 500 + spine_idx`. | No. |
| `GSL_PLANE_ASN_STRIDE` (`:109`) | `1000` | ASN spacing between GPU planes; shared by GSL leaf and spine formulas. | No. |
| `GSL_SPINE_ASN_OFFSET` (`:110`) | `1099` | Dedicated E/W (GPU) spine ASN = `base_asn + 1099 + (plane-1)*1000`. | No. |
| `GSL_LEAF_ASN_OFFSET` (`:111`) | `1100` | GPU leaf ASN = `base_asn + 1100 + (plane-1)*1000 + (leaf_idx-1)`. Unique per leaf in spined (>2-leaf) planes; collapsed 2-leaf planes intentionally share one plane ASN across both leaf mates (they iBGP-peer each other). | No. |
| `ROLE_HOST_BASE` (`:118-121`) | `compute=11, support=51, storage=61, k8s=71, bcme=81, unknown=91` | Documented as role-based host-octet ranges for management-IP assignment. | No — and see caveat below. |
| `switch_user` (`:4972`) | `'cumulus'` | The SSH/ZTP username written into generated inventory for all switches. | No. |
| `air_mgmt_subnet` default (`:1191`, `:4157`) | `172.20.0.0/24` | Base subnet for switch `eth0` IPs in Air. | **Yes** — but via a *different* sheet: the `Air_Only` sheet's "Air Management Subnet" row (`parse_air_settings()`, `excel_parser.py:1187`), not a `Settings` field. |

The full ASN formula (per-tier base + fixed, non-overlapping offset
block) is the single-source `scripts/asn_allocation.py` — the offsets
above are intentionally disjoint and considered stable; changing one
would silently renumber every already-shipped arch.

These offsets are the **derived defaults**. To assign an arbitrary ASN to
an individual switch, use the optional Loopbacks **ASN** column,
which overrides the derived value per node. `validate_excel` enforces the
BGP invariants on any overrides (shared iBGP/plane groups must stay uniform;
every group's ASN must be distinct) — see `docs/LOOPBACKS.md`.

`Settings.loopback_base` is the **only** constant above with a direct
Settings-sheet override. Everything else — the ASN offsets,
`ROLE_HOST_BASE`, and `switch_user` — is a fixed tool default with no
Excel field at all. `air_mgmt_subnet` is the one exception with an
override, but it lives on `Air_Only`, not `Settings`, and only matters
for Air deployments.

**Caveat on `ROLE_HOST_BASE`**: as of this writing it is defined but
not referenced anywhere else in `excel_parser.py` — management IPs
are read verbatim from the Nodes sheet's `Mgmt IP Address` column
rather than computed from a role-based octet range. Treat this table
row as documentation of an unused constant, not as an active
IP-assignment rule; if you see a management IP that doesn't follow
this scheme, that's expected.

The GPU VRF loopback (used by the `Prefix lists` sheet's per-VRF match
rules, see [Sheet 5](#sheet-5-routing-policy-overrides-optional)) is a
related but separate formula — it is **not** tied to `loopback_base`
at all. It's computed per-switch as
`{GPU VLAN subnet base}.{4 + core_num}/32`, i.e. the fourth octet of
the GPU VLAN's own subnet (`generate_vrf_loopbacks()`,
`scripts/excel_parser.py:3565-3569`). Override it per-switch via the
`Loopbacks` sheet's `GPU` column (`docs/LOOPBACKS.md`), not via
`loopback_base`.
