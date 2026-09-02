<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Playbooks Directory

This directory contains Ansible playbooks for ERA network automation.

## Active Playbooks

### Switch Configuration

#### `generate-cli-configs.yml` — Generate Switch Configs

**Purpose**: Generate NVUE CLI configurations for all switches
**What it does**:
- Renders Jinja2 templates with inventory variables
- Generates `.sh` files with NVUE CLI commands
- Outputs to `output/<arch>/<site>/configs/`

**Usage**:
```bash
# Via Makefile (recommended — runs full pipeline: Excel → inventory → configs → topology)
make generate ARCH=2-8-5-200

# Direct execution (configs only, requires inventory to already exist)
ansible-playbook playbooks/generate-cli-configs.yml \
  -i output/2-8-5-200/default/inventory/hosts \
  -e "config_output_dir=../output/2-8-5-200/default/configs"
```

---

#### `setup-ztp-server.yml` — ZTP Server Setup

**Purpose**: Set up ZTP server for automatic switch provisioning
**What it does**:
- Installs nginx web server
- Configures dnsmasq (DHCP + DNS)
- Generates unified ZTP script (`ztp.sh`)
- Copies CLI switch configurations to `/var/www/ztp/configs/`
- Configures DHCP with hostname-based IP assignment
- Creates ZTP status web page

**Usage**:
```bash
make ztp-setup ARCH=2-8-5-200     # Initial setup
make ztp-update ARCH=2-8-5-200    # Update configs after changes
```

---

#### `setup-oob-server.yml` — OOB Server Setup

**Purpose**: Configure OOB server as gateway/router for management networks
**What it does**:
- Enables IP forwarding
- Configures netplan for static IPs on OOB interfaces
- Sets up routing between isolated management subnets

**Usage**:
```bash
make oob-setup ARCH=2-8-5-200
```

---

#### `era-servers.yml` — Server Configuration

**Purpose**: Deploy configurations to compute, storage, and support servers
**What it does**:
- Configures network interfaces (bonds, VLANs)
- Sets up DNS, LLDP, and node-specific settings
- Optionally configures LDAP (with `--tags ldap`)

**Usage**:
```bash
make deploy-servers ARCH=2-8-5-200              # Direct SSH
make deploy-servers-via-jump ARCH=2-8-5-200   # Via the OOB jump host (for Air)
```

---

### Validation

#### `validate-ztp-direct.yml` — Validate ZTP on Switches

**Purpose**: SSH to switches directly and verify configuration was applied

```bash
make validate-ztp-direct ARCH=2-8-5-200
```

#### `validate-ztp.yml` — Validate ZTP via Server

**Purpose**: Test ZTP deployment by SSHing through the ZTP server

```bash
make validate-ztp ARCH=2-8-5-200
```

#### `validate-config.yml` — Compare Running vs Generated Config

**Purpose**: Compare running switch config against generated config via ZTP server

```bash
make validate-config ARCH=2-8-5-200
```

#### `validate-switch-health.yml` — Switch Operational Health

**Purpose**: Tier-1 switch health — clean config apply + BGP sessions Established + EVPN ES/VNI + interface state, in one per-switch SSH session (also runs as phase 4 of `validate-all`)

```bash
make validate-switch-health ARCH=2-8-5-200
```

#### `validate-oob-bgp.yml` — OOB↔CSL BGP Check

**Purpose**: Gating check that every OOB-switch BGP neighbor is Established (L3 OOB only; N/A otherwise). Runs as part of `validate-ztp`.

```bash
make validate-oob-bgp ARCH=2-8-5-200
```

#### `validate-servers.yml` — Validate Server Config

**Purpose**: Verify server bonds, VLANs, LLDP, gateway/internet connectivity via the jump host

```bash
make validate-servers ARCH=2-8-5-200
```

#### `validate-ping-matrix.yml` — Server-to-Server Ping Matrix

**Purpose**: Full server-to-server ping matrix across all VLANs

```bash
make validate-ping-matrix ARCH=2-8-5-200
```

#### `push-switch-configs.yml` — Push Configs to Switches

**Purpose**: Push and apply generated NVUE CLI configs to core and OOB switches.

If `switch_ansible_password` already works, the playbook skips the
password-change step and does copy / run generated CLI / stage
`nv set system aaa user … password` (last, so apply cannot drop
Linux SSH) / `nv config apply` / confirm.

If it does not (brand-new Cumulus `cumulus`, or an expired first-login
password), it completes that forced change from
`switch_bootstrap_password` (default `cumulus`) to
`switch_ansible_password`, then continues. Requires `pexpect` and
`sshpass` on the controller.

```bash
make push-switch-configs ARCH=2-8-5-200
```

---

### LDAP

#### `restart-ldap-switches.yml` — Restart LDAP via OOB

```bash
make restart-ldap ARCH=2-8-5-200
```

#### `restart-ldap-switches-direct.yml` — Restart LDAP Direct SSH

```bash
make restart-ldap-direct ARCH=2-8-5-200
```

---

### Status Page & Reports

#### `setup-status-page.yml` — Status / Report Page

**Purpose**: Stand up the HTTP status + validation-report page (basic-auth from `status_page_username`/`status_page_password`) when `status_page_enabled=Yes`. Invoked automatically by the deploy pipeline; not a standalone Make target.

#### `upload-reports.yml` — Upload Validation Reports

**Purpose**: Publish the `validate-all` reports to `/reports/` on the status page. Invoked by the validation pipeline when the status page is enabled.

---

## Deployment Workflows

### Option 1: ZTP-Based Deployment (Recommended)

Automatic switch provisioning when switches first boot:

```bash
# 1. Import filled Excel (sets context automatically)
make import EXCEL=my-config.xlsx

# 2. Full deployment (OOB setup → Excel parse → config gen → ZTP server)
make switch-ztp-deploy
```

**How ZTP works**:
1. Switch boots and requests DHCP
2. dnsmasq assigns IP based on MAC address and provides hostname
3. Switch downloads unified `ztp.sh` script (DHCP option 239)
4. Script auto-detects hostname and downloads switch-specific config
5. Configuration is applied automatically

---

### Option 2: Manual Configuration Apply

For existing configured switches or manual control:

```bash
# 1. Generate configurations
make generate ARCH=2-8-5-200

# 2. Copy config to switch
scp output/2-8-5-200/default/configs/core-01-config.sh cumulus@core-01:/tmp/

# 3. SSH to switch and apply
ssh cumulus@core-01
bash /tmp/core-01-config.sh
```

---

### Option 3: Update Existing ZTP Server

After making configuration changes:

```bash
make ztp-update ARCH=2-8-5-200
```

---

## Playbook Summary

| Playbook | Purpose | Makefile Target |
|----------|---------|-----------------|
| `generate-cli-configs.yml` | Generate NVUE CLI configs | `make generate` |
| `setup-ztp-server.yml` | Configure ZTP server | `make ztp-setup` |
| `setup-oob-server.yml` | Configure OOB gateway | `make oob-setup` |
| `era-servers.yml` | Deploy server configs | `make deploy-servers` |
| `validate-ztp-direct.yml` | Validate switch configs | `make validate-ztp-direct` |
| `validate-ztp.yml` | Validate via ZTP server | `make validate-ztp` |
| `validate-config.yml` | Compare running vs generated config | `make validate-config` |
| `validate-switch-health.yml` | Switch operational health (apply/BGP/EVPN/interfaces) | `make validate-switch-health` |
| `validate-oob-bgp.yml` | OOB↔CSL BGP Established check | `make validate-oob-bgp` |
| `validate-servers.yml` | Server bonds/VLANs/LLDP/connectivity | `make validate-servers` |
| `validate-ping-matrix.yml` | Server-to-server ping matrix | `make validate-ping-matrix` |
| `push-switch-configs.yml` | Push NVUE configs to switches (bootstraps factory/expired password if needed) | `make push-switch-configs` |
| `restart-ldap-switches.yml` | Restart LDAP (via OOB) | `make restart-ldap` |
| `restart-ldap-switches-direct.yml` | Restart LDAP (direct) | `make restart-ldap-direct` |
| `setup-status-page.yml` | Status / validation-report page | *(pipeline)* |
| `upload-reports.yml` | Publish reports to the status page | *(pipeline)* |

---

## Related Documentation

- [Air Deployment Guide](../docs/AIR_DEPLOYMENT_GUIDE.md)
- [ZTP Setup Guide](../docs/MULTI_INTERFACE_ZTP.md)
- [ZTP Validation](../docs/ZTP_VALIDATION.md)
- [Main README](../README.md)
