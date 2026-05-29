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

The Excel file has four sheets you fill out, plus three supporting sheets:

| Sheet | Purpose |
|-------|---------|
| **Settings** | Global deployment parameters (IPs, ASN, features) |
| **Nodes** | Every device in the deployment (switches, servers, storage) |
| **VLANs & Profiles** | VLAN definitions, VRF assignments, and port profiles |
| **Wire Map** | Physical cabling: which port on which device connects to which switch port |
| **Loopbacks** | *Optional.* Per-switch / per-VRF loopback overrides. Blank cells fall back to `Settings.loopback_base`. See `docs/LOOPBACKS.md`. |
| **Air_Only** | Cumulus version → NVIDIA Air image name map, plus the Air management subnet. Only relevant for Air deployments. |
| **Reference** | Read-only quick reference embedded in the workbook. Do not edit. |

---

## Sheet 1: Settings

The Settings sheet is a key-value table organized into sections. Column A (`Setting`) is the field name and column B (`Value`) is the value you edit. Columns C–E (`Description`, `Required`, `Default Value`) are read-only guidance shipped in the template — you don't need to change them. Section headers (GENERAL, NETWORK, etc.) appear in column A with no value in column B -- do not delete them.

### GENERAL

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `site_name` | No | String | A label for this deployment instance. Defaults to `default` if omitted. Use it to distinguish multiple deployments of the same architecture (e.g., `lab-east`, `prod-dc2`). | `default` |
| `architecture` | **Yes** | Enum | The ERA architecture identifier. Must be exactly one of the four valid values. This determines which templates and topology rules are applied. | `2-8-5-200` |
| `scalable_units` | No | Integer | Number of scalable units in the deployment. Each SU is a group of compute nodes that share a common cabling pattern. | `8` |
| `nodes_per_su` | No | Integer | Number of nodes per scalable unit. Combined with `scalable_units`, this determines the total compute node count. | `4` |

Valid architectures and what they represent. Naming follows the
`{CPUs}-{GPUs}-{NICs}-{B}` convention where **B = average per-GPU
bandwidth on the East/West network (Gbps)**.

| Architecture | CPUs | GPUs | NICs | Per-GPU E/W bandwidth | OOB Switches |
|-------------|------|------|------|----------------------|--------------|
| `2-4-3-200`* | 2 | 4 | 3 | 200 Gbps | 2 |
| `2-8-5-200`* | 2 | 8 | 5 | 200 Gbps | 3 |
| `2-8-9-400` | 2 | 8 | 9 | 400 Gbps | 3 |
| `2-8-9-800` | 2 | 8 | 9 | 800 Gbps | 2 |

\* In archs where the E/W NIC:GPU ratio is 1:2 (`2-4-3-200`, `2-8-5-200`),
   strict per-GPU arithmetic gives 100 Gbps; the label `200` follows the
   per-NIC link speed convention — a documented exception, not a bug.

**Choosing an architecture:** match the row above to your compute node's CPU/GPU/NIC
count and East/West link speed. If you're unsure which arch your hardware maps to,
see the [Architecture Support Matrix](ARCH_SUPPORT_MATRIX.md) for the authoritative
arch × scale × feature breakdown.

### AIR DEPLOYMENT

These fields control NVIDIA Air simulation deployment. If you are deploying to physical hardware only, you can leave these blank.

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `deploy_in_air` | No | Yes/No | Whether to deploy this configuration in an NVIDIA Air virtual simulation. | `Yes` |
| `air_username` | No | String | NGC username for legacy Air authentication. Not needed for NGC Air 2.0 (bearer token). | `jsmith@company.com` |
| `air_org` | No | String | NGC organization name. Required if deploying to Air. | `my-org` |
| `status_page_enabled` | No | Yes/No | When enabled, creates an HTTP service in Air for the ZTP status page with basic auth. Allows viewing ZTP status and validation reports via a web browser. Credentials come from `status_page_username` and `status_page_password` in `secrets.yml` (default username: `era`, default password: same as `switch_password`). | `No` |

The Air instance URL is **not** an Excel field. Run `make air-setup` once per checkout
to pick public NGC Air vs. internal air-inside (or enter a custom URL); the wizard
stores your choice in the shared vault at `.era-secrets/air-secrets.yml`. See the
[Air Deployment Guide](AIR_DEPLOYMENT_GUIDE.md) for the wizard walkthrough.

### NETWORK

Core network parameters that define the fabric topology.

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `mgmt_subnets` | **Yes** | CIDR (CSV) | Management subnet(s) for OOB network. Comma-separated if multiple. All OOB switches share this subnet. | `192.168.200.0/24` |
| `management_switches` | **Yes** | Integer | Number of OOB management switches. Must match the architecture (2 for `2-4-3-200` and `2-8-9-800`, 3 for `2-8-5-200` and `2-8-9-400`). | `2` |
| `tiers` | No | Integer | Number of network tiers. Currently only `1` is supported. | `1` |
| `convergence` | No | String | Network convergence type. Use `full` for converged fabric. | `full` |
| `bgp_asn` | **Yes** | Integer | BGP Autonomous System Number for the fabric. Must be a valid ASN (positive integer). Private ASN range 64512-65534 is typical for internal fabrics. | `65100` |
| `loopback_base` | **Yes** | IP prefix | First three octets of the loopback IP range. The fourth octet is auto-assigned per switch and VRF. | `172.16.176` |
| `disabled_ports` | No | CSV of integers | Physical port numbers on core switches that should be administratively disabled. Comma-separated. | `50,52,60,62,64` |
| `exit_dhcp_servers` | No | CSV of IPs | DHCP relay server IPs for the EXIT VRF. Only needed if your design uses DHCP relay on the exit network. | `10.0.0.1,10.0.0.2` |
| `air_mgmt_subnet` | No | CIDR | Management subnet for Air virtual nodes (dhcp-oob, oob-server-01, dhcp-edge). Used to assign IPs to the Air management infrastructure. If omitted, defaults to `172.20.0.0/24`. Only relevant for Air deployments. | `172.20.0.0/24` |
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
| `telemetry_enabled` | No | Yes/No | Enable telemetry collection on switches (WJH, histogram, etc.). | `Yes` |
| `netq_ip` | No | IP address | NetQ server IP address for streaming telemetry data. Only relevant if NetQ is deployed. | `10.0.1.50` |

### ADVANCED

These fields have sensible defaults. Only change them if your deployment diverges from the standard ERA design.

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `timezone` | No | String | Timezone for all switches. Uses tz database format. | `Etc/Zulu` |
| `mh_mac` | No | MAC address | EVPN Multihoming system MAC. Must be in `xx:xx:xx:xx:xx:xx` format. Shared across the MLAG/MH domain. | `44:38:39:ff:00:01` |
| `anycast_mac` | No | MAC address | Anycast gateway MAC address for VXLAN SVIs. Must be in `xx:xx:xx:xx:xx:xx` format. | `44:38:39:ff:00:aa` |
| `ztp_enabled` | No | Yes/No | Enable Zero Touch Provisioning. When `Yes`, switches pull their config automatically on boot via DHCP + HTTP. | `Yes` |
| `ztp_server` | No | IP address | IP address of the ZTP server (typically oob-server-01). Must be a valid IPv4 address. | `192.168.200.1` |
| `ntp_servers` | No | String | NTP server addresses for time synchronization. Can be IPs or hostnames. | `0.cumulusnetworks.pool.ntp.org` |
| `num_physical_ports` | No | Integer | Number of physical front-panel ports on core switches (e.g., SN5610 has 64). Used for port range calculations. | `64` |
| `oob_uplink_mode` | No | `l2` or `l3` | OOB switch uplink mode. `l2` (default) keeps OOB switches as flat L2 bridges (legacy ERA design); `l3` makes them L3 EVPN VTEPs with BGP underlay + OOB VRF SVI + VRR (matches a production L3-OOB design). L3 mode also flips the Air topology to use `cust-net-edge-01` as the mgmt-VLAN bridge and replaces `dhcp-oob`/`oob-server-01` with `external-conn`/`external-dhcp`/`utility`. | `l2` |
| `pre_login_message` | No | Multi-line text | SSH banner displayed **before** authentication. Empty cell → no banner line emitted (any existing banner on the switch persists untouched). Placeholders `{hostname}`, `{site}`, `{arch}` are substituted per-switch at config-render time. Newlines in the cell are preserved. Single quotes in the operator's text are safely escaped. Default Excels ship pre-populated with the NVIDIA Cumulus VX welcome message, so existing deploys see the same banner unless you edit the cell. | `Authorized access only — site {site}` |
| `post_login_message` | No | Multi-line text | Login MOTD displayed **after** successful authentication. Same placeholder + empty-cell semantics as `pre_login_message`. Default Excels ship with the "successfully logged in to: `{hostname}`" message. | `Welcome to {hostname} ({arch})` |

### VERSIONS

This section appears below the key-value settings, formatted as a small table with a `Switch Function` header row.

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `core` | No | Version string | Target Cumulus Linux version for core switches. | `5.16.1` |
| `oob` | No | Version string | Target Cumulus Linux version for OOB switches. Can differ from core if OOB runs an older release. | `5.15.0` |

---

## Sheet 2: Nodes

The Nodes sheet is a table listing every device in the deployment -- core switches, OOB switches, compute nodes, storage nodes, support nodes, and any other infrastructure.

**Row 1 is the header row.** Data starts at row 2.

### Column Reference

| Column | Header | Required | Type | Description |
|--------|--------|----------|------|-------------|
| A | `Function` | **Yes** | String | The canonical role identifier. This is a role *class*, not a unique key — many devices can share the same Function (e.g. eight rows with `gpu`). It drives which templates and port rules apply. See naming conventions below. |
| B | `Name` | No | String | OEM-specific device name. This is the unique per-device identifier (must be unique across all rows) and the value the Wire Map joins against. If blank, defaults to the Function value — so leave it blank only when a Function has exactly one device. |
| C | `Type` | No | `switch` / `node` | Optional. Distinguishes Cumulus VX switches (`switch`) from Ubuntu / Cumulus host nodes (`node`). When present, the validator enforces consistency with `Function` (switch-role Functions must have `Type=switch`, server/compute Functions must have `Type=node`). Older Excels without this column still validate. |
| D | `MAC Address for ZTP` | No | MAC | MAC address used for DHCP reservation during ZTP. Required for physical switches. Format: `aa:bb:cc:dd:ee:ff`. If left blank for Air deployments, a deterministic MAC is auto-generated from the node name. |
| E | `Mgmt IP Address` | **Yes** | IP address | Management IP address on the OOB network. Do NOT include the prefix length here (put that in the Prefix column). Must be unique across all nodes. |
| F | `Prefix` | No | Integer | CIDR prefix length for the management subnet. Typically `24`. Defaults to 24 if blank. |
| G | `Gateway` | No | IP address | Default gateway for management traffic. Typically the oob-server-01 IP (e.g., `192.168.200.1`). |
| H | `ZTP` | No | Yes/No | Whether this node participates in ZTP. Switches should be `Yes`. Servers are typically `No` (configured via other means). |
| I | `Enabled` | No | `Yes` / `No` / `Air` | Whether to include this node in the generated inventory. `No` excludes the row without deleting it; `Air` marks the row as a **documentary entry for auto-injected Air-only infrastructure** (parser skips provisioning, validator enforces Name + Type match an allowed Air node). Defaults to `Yes` if the column is missing or blank. |
| J | `Notes` | No | Free text | Optional per-row notes (e.g. "Air-only documentary — auto-injected by topology generator"). Purely informational; parser ignores. |

### Air-only documentary rows (`Enabled = Air`)

The topology generator automatically injects several Ubuntu / Cumulus VX nodes into every Air sim that aren't operator-provisioned hosts — they simulate customer-edge equipment, NAT, DHCP, and jumpboxes. Operators are encouraged to keep documentary rows for these nodes on the Nodes tab so they're visible at-a-glance.

| Name | Type | Used in | Purpose |
|---|---|---|---|
| `cust-net-edge-01` | switch | L3 OOB | Customer-edge sim — air-mgmt L2 bridge + EXIT-VRF eBGP underlay |
| `cust-net-edge-02` | switch | L3 OOB | HA pair for NAT return path |
| `external-conn` | node | L3 OOB | NAT host (172.20.0.1) — routes outbound through Air |
| `external-dhcp` | node | L3 OOB | ZTP DHCP server + inter-VRF EXIT relay target |
| `utility` | node | L3 OOB | Jumpbox + status page + OOB-side DHCP relay target |
| `ext-storage-01` | node | L3 OOB (2-8-9-800 only) | STORAGE VRF eBGP peer + simulated customer storage |
| `ext-storage-02` | node | L3 OOB (2-8-9-800 only) | STORAGE VRF eBGP peer (HA) |
| `dhcp-oob` | node | L2 OOB (legacy) | ZTP DHCP server on OOB |
| `oob-server-01` | node | L2 OOB (legacy) | OOB jumpbox |
| `dhcp-edge` | node | L2 OOB (legacy) | Edge-side DHCP |
| `air-oob-switch` | switch | L2 OOB (legacy) | OOB L2 bridge |

Documentary rows have `Enabled = Air`; leave `Mgmt IP`, `MAC Address for ZTP`, `Prefix`, `Gateway` blank. The validator will reject `Enabled = Air` rows whose `Name` is not in this list, and will reject Type mismatches (e.g., labeling `utility` as `switch`).



### Function Naming Conventions

The `Function` column value determines how the automation classifies each device. Use these patterns:

| Pattern | Device Type | Examples |
|---------|-------------|---------|
| `core-01`, `core-02` | Core/spine switches (always exactly 2) | `core-01`, `core-02` |
| `oob-switch-01`, `oob-switch-02`, `oob-switch-03` | OOB management switches | `oob-switch-01` through `oob-switch-03` |
| `su-XX-node-YY` | Compute nodes in Scalable Unit XX | `su-01-node-01`, `su-02-node-04` |
| `storage-XX` | Storage nodes | `storage-01`, `storage-02` |
| `support-XX` | Support/infrastructure nodes | `support-01`, `support-02` |
| `k8s-XX` | Kubernetes nodes | `k8s-01`, `k8s-02` |
| `bcme-XX` | BCME (BMC) nodes | `bcme-01` |

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

All management IPs must be within the `mgmt_subnets` defined in Settings. A typical allocation for `192.168.200.0/24`:

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
2-8-9-800 sheets. Converged architectures (2-4-3-200 / 2-8-5-200 /
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
| Storage | Trunk | Storage node uplinks |
| Support | Trunk | Support infrastructure uplinks |
| ISL | Trunk | Inter-switch link between core-01 and core-02 |
| OOB Uplink | Trunk | Core-to-OOB switch uplinks |
| Edge Uplink | Trunk | Core-to-edge/exit switch uplinks |

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

## Common Configurations

### Minimal Setup (Physical Deployment)

For a basic physical deployment without Air or LDAP:

**Settings:**
- Set `architecture` to your arch (e.g., `2-8-5-200`)
- Set `mgmt_subnets` to your OOB subnet
- Set `management_switches` to match your arch (2 or 3)
- Set `bgp_asn` to your ASN
- Set `loopback_base` to your loopback range
- Leave AIR DEPLOYMENT fields blank
- Set `ldap_enabled` to `No`
- Set `ztp_enabled` to `Yes`

**Nodes:** Fill in all switches and servers with management IPs. Leave MAC blank for auto-generation.

**VLANs & Profiles:** Use the default VLAN layout provided in the template.

**Wire Map:** Document all physical cabling.

### Air Simulation Deployment

Same as above, plus:
- Set `deploy_in_air` to `Yes`
- Set `air_org` to your NGC organization
- Run `make air-setup` once to pick the Air instance (public NGC Air or internal air-inside) and store credentials — no Excel field needed
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
- **`mgmt_subnets` must be CIDR notation.** Write `192.168.200.0/24`, not `192.168.200.0` or `255.255.255.0`.

### Nodes

- **Function names must be unique.** No two rows can share the same Function value.
- **Management IPs must be unique.** The validator flags duplicate IPs as errors.
- **MAC addresses are optional for Air.** When deploying to NVIDIA Air, MACs are auto-generated using a deterministic hash of the node name. For physical deployments, switches need real MACs for ZTP DHCP reservations.
- **The Enabled column is forgiving.** If the column is missing entirely, all nodes default to enabled. If present, `Yes`, `True`, `1`, or blank all mean enabled.
- **Mgmt IP should NOT include the prefix.** Put the bare IP in column D (e.g., `192.168.200.5`) and the prefix length in column E (e.g., `24`). Some older templates accepted `192.168.200.5/24` in one column, but the current format separates them.

### VLANs & Profiles

- **VNI = VLAN ID + 4000 by convention.** If you leave the VNI column blank, the parser calculates it automatically. Only specify VNI explicitly if you need to deviate from this convention.
- **VLAN names must be consistent with Wire Map profiles.** The parser uses fuzzy matching (e.g., `CPU/In-Band` matches profiles containing "cpu" or "in-band"), but exact matches are safer.
- **Port Profiles define the default config for each network type.** Individual Wire Map rows can override port mode and VLAN settings, but the profile is the baseline.
- **VRF names are case-sensitive.** Use `OOB`, `INBAND`, `GPU`, `EXIT` consistently.

### Wire Map

- **`System Name (A)` and `System Name (B)` must match a Nodes `Name` value exactly.** If the Nodes sheet has `core-01`, the Wire Map must use `core-01` (not `Core-01` or `spine01`). The parser derives each row's role/Function by looking this name up in the Nodes sheet.
- **eth0 is reserved for OOB management.** When the topology generator assigns interface names, eth0 always maps to the OOB management connection. Data-plane interfaces start at eth1. Do not assign a data-plane profile to eth0.
- **`outbound` is a special `System Name (B)` value.** It creates internet access links in Air simulations. It does not need a matching Nodes entry.
- **Duplicate endpoints are deduplicated.** If the same (node, interface) pair appears more than once, the first row wins and subsequent duplicates are silently dropped.
- **`Air - ` prefixed profiles are simulation-only.** These rows create infrastructure connections that exist in the Air virtual topology but not on physical hardware (e.g., eth0 management wiring that is handled by physical OOB cabling in real deployments).
- **Breakout notation matters.** `swp1s0` means port 1 sub-port 0 (a breakout port). `swp1` means the full-width port with no breakout. Use the notation that matches your physical cabling and switch configuration.

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
- **Architecture**: Value is one of the four valid architectures.
- **Duplicates**: No duplicate Function names, no duplicate management IPs.
- **Port conflicts**: No duplicate switch port assignments in the Wire Map.
- **Cross-sheet consistency**: Wire Map `System Name (A)` / `System Name (B)` values reference nodes that exist in the Nodes sheet.
- **Subnet sanity**: Gateways are within their node's management subnet (warning if not).

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
| `mgmt_subnets` | Defines the OOB network range for all management IPs. |
| `management_switches` | Tells the automation how many OOB switches to configure. |
| `bgp_asn` | BGP will not converge without an ASN. |
| `loopback_base` | Loopback IPs are derived from this base for all VRFs. |

### Settings -- Optional (with Defaults)

| Field | Default If Omitted |
|-------|-------------------|
| `site_name` | `default` |
| `deploy_in_air` | `No` |
| `tiers` | `1` |
| `convergence` | `full` |
| `ldap_enabled` | `No` |
| `telemetry_enabled` | `No` |
| `ztp_enabled` | `Yes` |
| `timezone` | `Etc/Zulu` |

### Nodes -- Required Columns

| Column | Why It Is Required |
|--------|--------------------|
| `Function` | Primary key for all cross-references. |
| `Mgmt IP Address` | Every node needs a management IP for ZTP and SSH access. |

### Wire Map -- Required Columns

| Column | Why It Is Required |
|--------|--------------------|
| `System Name (A)` | Identifies the A-side device this row belongs to. |
| `Port (A)` | Specifies the physical port on the A-side device. |
| `System Name (B)` | Identifies the connected switch / peer (B-side) for topology generation. |
| `Port (B)` | Specifies the physical port on the B-side (switch) side. |
| `Network Profile` | Determines how the port is configured (VLAN, mode, VRF). |
