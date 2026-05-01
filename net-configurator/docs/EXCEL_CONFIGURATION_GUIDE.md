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

The Excel file has four main sheets:

| Sheet | Purpose |
|-------|---------|
| **Settings** | Global deployment parameters (IPs, ASN, features) |
| **Nodes** | Every device in the deployment (switches, servers, storage) |
| **VLANs & Profiles** | VLAN definitions, VRF assignments, and port profiles |
| **Wire Map** | Physical cabling: which port on which device connects to which switch port |

---

## Sheet 1: Settings

The Settings sheet is a two-column key-value table organized into sections. Column A is the field name; column B is the value. Section headers (GENERAL, NETWORK, etc.) appear in column A with no value in column B -- do not delete them.

### GENERAL

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `site_name` | No | String | A label for this deployment instance. Defaults to `default` if omitted. Use it to distinguish multiple deployments of the same architecture (e.g., `lab-east`, `prod-dc2`). | `default` |
| `architecture` | **Yes** | Enum | The ERA architecture identifier. Must be exactly one of the three valid values. This determines which templates and topology rules are applied. | `2-8-5-200` |
| `scalable_units` | No | Integer | Number of scalable units in the deployment. Each SU is a group of compute nodes that share a common cabling pattern. | `8` |
| `nodes_per_su` | No | Integer | Number of nodes per scalable unit. Combined with `scalable_units`, this determines the total compute node count. | `4` |

Valid architectures and what they represent:

| Architecture | CPUs | GPUs | NICs | NIC Speed | OOB Switches |
|-------------|------|------|------|-----------|--------------|
| `2-4-3-200` | 2 | 4 | 3 | 200G | 2 |
| `2-8-5-200` | 2 | 8 | 5 | 200G | 3 |
| `2-8-9-400` | 2 | 8 | 9 | 400G | 3 |

### AIR DEPLOYMENT

These fields control NVIDIA Air simulation deployment. If you are deploying to physical hardware only, you can leave these blank.

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `deploy_in_air` | No | Yes/No | Whether to deploy this configuration in an NVIDIA Air virtual simulation. | `Yes` |
| `air_username` | No | String | NGC username for legacy Air authentication. Not needed for NGC Air 2.0 (bearer token). | `jsmith@company.com` |
| `air_org` | No | String | NGC organization name. Required if deploying to Air. | `my-org` |

The Air instance URL is **not** an Excel field. Run `make air-setup` once per checkout
to pick public NGC Air vs. internal air-inside (or enter a custom URL); the wizard
stores your choice in the shared vault at `.era-secrets/air-secrets.yml`. See the
[Air Deployment Guide](AIR_DEPLOYMENT_GUIDE.md) for the wizard walkthrough.
| `status_page_enabled` | No | Yes/No | When enabled, creates an HTTP service in Air for the ZTP status page with basic auth. Allows viewing ZTP status and validation reports via a web browser. Credentials come from `status_page_username` and `status_page_password` in `secrets.yml` (default username: `era`, default password: same as `switch_password`). | `No` |

### NETWORK

Core network parameters that define the fabric topology.

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `mgmt_subnets` | **Yes** | CIDR (CSV) | Management subnet(s) for OOB network. Comma-separated if multiple. All OOB switches share this subnet. | `192.168.200.0/24` |
| `management_switches` | **Yes** | Integer | Number of OOB management switches. Must match the architecture (2 for `2-4-3-200`, 3 for `2-8-5-200` and `2-8-9-400`). | `3` |
| `tiers` | No | Integer | Number of network tiers. Currently only `1` is supported. | `1` |
| `convergence` | No | String | Network convergence type. Use `full` for converged fabric. | `full` |
| `bgp_asn` | **Yes** | Integer | BGP Autonomous System Number for the fabric. Must be a valid ASN (positive integer). Private ASN range 64512-65534 is typical for internal fabrics. | `65100` |
| `loopback_base` | **Yes** | IP prefix | First three octets of the loopback IP range. The fourth octet is auto-assigned per switch and VRF. | `172.16.176` |
| `disabled_ports` | No | CSV of integers | Physical port numbers on core switches that should be administratively disabled. Comma-separated. | `50,52,60,62,64` |
| `exit_dhcp_servers` | No | CSV of IPs | DHCP relay server IPs for the EXIT VRF. Only needed if your design uses DHCP relay on the exit network. | `10.0.0.1,10.0.0.2` |
| `air_mgmt_subnet` | No | CIDR | Management subnet for Air virtual nodes (dhcp-oob, oob-server-01, dhcp-edge). Used to assign IPs to the Air management infrastructure. If omitted, defaults to `172.20.0.0/24`. Only relevant for Air deployments. | `172.20.0.0/24` |

### MANAGEMENT

LDAP configuration for centralized authentication on switches. If `ldap_enabled` is `No`, the remaining LDAP fields are ignored.

| Field | Required | Type | Description | Example |
|-------|----------|------|-------------|---------|
| `ldap_enabled` | No | Yes/No | Enable LDAP authentication on switches. When enabled, LDAP config is generated alongside local auth. | `No` |
| `ldap_domain` | Conditional | String | LDAP domain name. Required if `ldap_enabled` is `Yes`. | `example.com` |
| `ldap_base_dn` | Conditional | String | LDAP base distinguished name for user searches. | `dc=example,dc=com` |
| `ldap_root_dn` | Conditional | String | LDAP bind DN (the admin account used to query LDAP). | `cn=admin,dc=example,dc=com` |
| `ldap_servers` | Conditional | CSV of IPs | LDAP server IP addresses, comma-separated. | `10.0.1.10,10.0.1.11` |
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
| A | `Function` | **Yes** | String | The canonical role identifier. This is the primary key used throughout the pipeline. Must be unique per row. See naming conventions below. |
| B | `Name` | No | String | OEM-specific device name. This is the human-readable label your organization uses. If blank, defaults to the Function value. |
| C | `MAC Address for ZTP` | No | MAC | MAC address used for DHCP reservation during ZTP. Required for physical switches. Format: `aa:bb:cc:dd:ee:ff`. If left blank for Air deployments, a deterministic MAC is auto-generated from the node name. |
| D | `Mgmt IP Address` | **Yes** | IP address | Management IP address on the OOB network. Do NOT include the prefix length here (put that in the Prefix column). Must be unique across all nodes. |
| E | `Prefix` | No | Integer | CIDR prefix length for the management subnet. Typically `24`. Defaults to 24 if blank. |
| F | `Gateway` | No | IP address | Default gateway for management traffic. Typically the oob-server-01 IP (e.g., `192.168.200.1`). |
| G | `ZTP` | No | Yes/No | Whether this node participates in ZTP. Switches should be `Yes`. Servers are typically `No` (configured via other means). |
| H | `Enabled` | No | Yes/No | Whether to include this node in the generated inventory. Set to `No` to exclude a node without deleting its row. Defaults to `Yes` if the column is missing or blank. |

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
| A | VRF Name | **Yes** | String | VRF identifier (e.g., `OOB`, `INBAND`, `GPU`, `EXIT`). |
| B | Description | No | String | What this VRF is for. |
| C | L3 VNI | **Yes** | Integer | Layer 3 VNI for inter-VLAN routing within this VRF. |
| D | VLAN | **Yes** | Integer | VLAN used to carry the L3 VNI (a "transit" VLAN). |

### Section 3: Port Profiles

Below the VRFs section, a row with `Port Profiles` in column A marks the start of port profile definitions. These define how each type of network connection is configured on the core switches.

| Column | Header | Required | Type | Description |
|--------|--------|----------|------|-------------|
| A | Profile | **Yes** | String | Profile name. Must match the `Network Profile` values used in the Wire Map sheet. |
| B | Port Mode | **Yes** | String | L2 mode: `Access`, `Trunk`, or `L3`. |
| C | Native/Access VLAN | Conditional | Integer | For Access mode: the access VLAN. For Trunk mode: the native (untagged) VLAN. |
| D | Allowed VLANs | Conditional | String | For Trunk mode: comma-separated list of allowed VLAN IDs. |
| E | Untagged VLAN | No | Integer | Untagged VLAN (if different from native). |
| F | VRF | No | String | VRF assignment for this port profile. |
| G | LACP Bypass | No | Yes/No | Enable LACP bypass on bonded interfaces using this profile. |
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

---

## Sheet 4: Wire Map

The Wire Map is the physical cabling plan. Each row represents one cable connection between a device port and a switch port.

**Row 1 is the header row.** Data starts at row 2.

### Column Reference

| Column | Header | Required | Type | Description |
|--------|--------|----------|------|-------------|
| A | `Display in Air` | No | Yes/No | Whether to include this connection in the NVIDIA Air virtual topology. Set `No` for physical-only connections that Air cannot simulate. |
| B | `System Role` | **Yes** | String | Function role of the device on the "A" side of the cable. Must match a `Function` value from the Nodes sheet. |
| C | `System Name` | No | String | OEM name of the device (should match the `Name` column in Nodes). |
| D | `NIC/Port/Breakout` | **Yes** | String | Port identifier on the device side. For servers: `eth0`, `eth1`, etc. For switches: `swp1`, `swp1s0`, etc. |
| E | `Port Side (A)` | No | String | Physical port side label for documentation purposes. |
| F | `Port Speed (A)` | No | String | Port speed on the A side (e.g., `200G`, `100G`, `50G`). |
| G | `Network Profile` | **Yes** | String | The network type this connection belongs to. Must match a profile name from the VLANs & Profiles Port Profiles section, or use an `Air - ` prefix for simulation-only connections. |
| H | `Port Mode` | No | String | L2 mode override for this specific connection. |
| I | `Native/Access VLAN` | No | Integer | VLAN override for this specific connection. |
| J | `Allowed VLANs` | No | String | Allowed VLANs override for this specific connection. |
| K | `Switch Role` | **Yes** | String | Function role of the switch on the "B" side of the cable. Must match a `Function` from the Nodes sheet, or `outbound` for internet-access links in Air. |
| L | `Switch Name` | No | String | OEM name of the connected switch. |
| M | `Switch Port` | **Yes** | String | Port on the switch side (e.g., `swp1`, `swp44`). |
| N | `Port Side (B)` | No | String | Physical port side label for the switch. |

### Network Profile Conventions

The `Network Profile` column (G) controls how the connection is classified. Use names that match the Port Profiles defined in the VLANs & Profiles sheet.

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
When `Switch Role` is `outbound`, this creates an internet-access link in the Air topology.

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
3. Use your custom names in `System Name` and `Switch Name` columns of the Wire Map for readability.
4. Always use the Function values in `System Role` and `Switch Role` -- these are the automation keys.

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

- **System Role and Switch Role must match Nodes Function values exactly.** If the Nodes sheet has `core-01`, the Wire Map must use `core-01` (not `Core-01` or `spine01`).
- **System Name and Switch Name are cosmetic.** They appear in documentation and topology labels but are not used for logic. The Role columns are authoritative.
- **eth0 is reserved for OOB management.** When the topology generator assigns interface names, eth0 always maps to the OOB management connection. Data-plane interfaces start at eth1. Do not assign a data-plane profile to eth0.
- **`outbound` is a special Switch Role value.** It creates internet access links in Air simulations. It does not need a matching Nodes entry.
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
- **Architecture**: Value is one of the three valid architectures.
- **Duplicates**: No duplicate Function names, no duplicate management IPs.
- **Port conflicts**: No duplicate switch port assignments in the Wire Map.
- **Cross-sheet consistency**: Wire Map System Roles reference nodes that exist in the Nodes sheet.
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
| `System Role` | Identifies which device this row belongs to. |
| `NIC/Port/Breakout` | Specifies the physical port on the device. |
| `Network Profile` | Determines how the port is configured (VLAN, mode, VRF). |
| `Switch Role` | Identifies the connected switch for topology generation. |
| `Switch Port` | Specifies the physical port on the switch side. |
