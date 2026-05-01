<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Multi-Interface ZTP Configuration Guide

> **Note:** The ERA automation tool uses an Excel-driven workflow. The network configuration
> described below (interfaces, DHCP ranges, VLAN assignments) is automatically generated
> from your Excel template when you run `make generate`. You do NOT need to manually
> configure these settings. This document is provided as a reference for understanding
> the underlying ZTP architecture.

## Overview

This guide explains how to configure a ZTP server with **multiple network interfaces** to support **staged ZTP provisioning**:

1. **Stage 1**: OOB switches ZTP first (via dedicated ZTP network)
2. **Stage 2**: Core switches ZTP later (via their respective OOB networks)

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     ZTP SERVER (dhcp-oob)                     │
│                                                               │
│  ens3:  DHCP/External (no ZTP)                               │
│  ens4:  192.168.1.8     ─┐                                   │
│  ens5:  192.168.200.8    │                                   │
│  ens6:  192.168.210.8    │  dnsmasq listens here            │
│  ens7:  192.168.220.8   ─┘                                   │
│                                                               │
└───────────────────────────────────────────────────────────────┘
         │              │                │              │
         │              │                │              │
         ▼              ▼                ▼              ▼
    ens4 network   oob1 network    oob2 network   oob3 network
    192.168.1.x    192.168.200.x   192.168.210.x  192.168.220.x
         │              │                │              │
         │              │                │              │
         ▼              ▼                ▼              ▼
    OOB switch     oob-switch-01   oob-switch-02  oob-switch-03
      ZTP          & core-01        & core-02      (OOB only)
    (all OOB)      
```

## Network Breakdown

### ens4: OOB Switch ZTP Network
- **Purpose**: Initial ZTP for all OOB switches
- **IP**: 192.168.1.8
- **Network**: 192.168.1.0/24
- **DHCP Range**: 192.168.1.100 - 192.168.1.200
- **Connects to**: All OOB switch eth0 interfaces

### ens5: OOB1 Network
- **Purpose**: Operational network for oob-switch-01 and core-01
- **IP**: 192.168.200.8 (ZTP server)
- **Network**: 192.168.200.0/24
- **DHCP Range**: 192.168.200.100 - 192.168.200.200
- **Devices**:
  - oob-switch-01: 192.168.200.2
  - core-01: 192.168.200.201

### ens6: OOB2 Network
- **Purpose**: Operational network for oob-switch-02 and core-02
- **IP**: 192.168.210.8 (ZTP server)
- **Network**: 192.168.210.0/24
- **DHCP Range**: 192.168.210.100 - 192.168.210.200
- **Devices**:
  - oob-switch-02: 192.168.210.2
  - core-02: 192.168.210.201

### ens7: OOB3 Network
- **Purpose**: Operational network for oob-switch-03
- **IP**: 192.168.220.8 (ZTP server)
- **Network**: 192.168.220.0/24
- **DHCP Range**: 192.168.220.100 - 192.168.220.200
- **Devices**:
  - oob-switch-03: 192.168.220.2

## Configuration Steps

### 1. Import Your Excel File

> **Note:** Steps 1-3 below describe the configuration inputs. In the current workflow,
> all of these settings (interfaces, DHCP ranges, MAC addresses, LDAP, credentials) are
> configured in the Excel template and applied automatically. The Excel import handles
> everything.

```bash
make import EXCEL=your-config.xlsx
```

### 2. ZTP Server Interfaces (Reference)

The following interface layout is generated automatically from the Excel Wire Map. This
section is kept as a reference for understanding the network topology:

```
Interface 1 (ens4): 192.168.1.0/24   - OOB Switch ZTP network
Interface 2 (ens5): 192.168.200.0/24 - OOB1 network
Interface 3 (ens6): 192.168.210.0/24 - OOB2 network
Interface 4 (ens7): 192.168.220.0/24 - OOB3 network
```

### 3. Additional Settings (Reference)

These are configured in the Excel Settings tab (not via interactive prompts):
- **Management Networks**: Set in Excel Settings tab
- **Data Networks**: VLANs configured in the VLANs & Profiles tab
- **Device Counts**: Derived from the Nodes tab
- **LDAP**: `ldap_enabled` field in Settings tab
- **Switch Credentials**: Set in Settings tab or `secrets.yml`
- **MAC Addresses**: MAC Address column in the Nodes tab
- **IP Assignment Mode**: DHCP is the default for ZTP

### 4. Apply Configuration

```bash
make generate ARCH=<type>
```

This generates:
- `output/<arch>/<site>/inventory/group_vars/all/main.yml` - Global config including `ztp_interfaces`
- `output/<arch>/<site>/inventory/host_vars/` - Per-switch configurations
- `output/<arch>/<site>/inventory/group_vars/` - Group-level settings

### 5. Setup ZTP Server

```bash
make ztp-setup ARCH=<type>
```

This will:
1. Load `ztp_interfaces` from the generated inventory
2. Configure dnsmasq to listen on **all specified interfaces**
3. Create per-interface DHCP ranges
4. Deploy the unified `ztp.sh` script
5. Copy switch configurations

## How It Works

### Stage 1: OOB Switch ZTP

1. OOB switch powers on, connects eth0 to ens4 network
2. Sends DHCP discover on 192.168.1.x network
3. dnsmasq assigns IP from 192.168.1.100-200 range
4. Switch downloads and executes `ztp.sh`
5. Script extracts hostname, downloads `oob-switch-XX.yaml`
6. Configuration applied, switch reboots with operational IP on oob1/2/3 network

### Stage 2: Core Switch ZTP

1. Core switch powers on, connects eth0 to respective OOB network (via OOB switch)
2. Sends DHCP discover on 192.168.200.x (or 210.x) network
3. dnsmasq (listening on ens5/ens6) assigns IP
4. Switch downloads and executes `ztp.sh`
5. Script extracts hostname, downloads `core-XX.yaml`
6. Configuration applied, switch reboots

## Generated dnsmasq Configuration

The generated `/etc/dnsmasq.conf` looks like this:

```ini
# Multi-interface listening
interface=ens4  # oob_switch_ztp - 192.168.1.0/24
interface=ens5  # oob1 - 192.168.200.0/24
interface=ens6  # oob2 - 192.168.210.0/24
interface=ens7  # oob3 - 192.168.220.0/24
bind-interfaces

# Per-interface DHCP ranges
dhcp-range=interface:ens4,192.168.1.100,192.168.1.200,12h
dhcp-option=interface:ens4,3,192.168.1.8  # Gateway

dhcp-range=interface:ens5,192.168.200.100,192.168.200.200,12h
dhcp-option=interface:ens5,3,192.168.200.8  # Gateway

dhcp-range=interface:ens6,192.168.210.100,192.168.210.200,12h
dhcp-option=interface:ens6,3,192.168.210.8  # Gateway

dhcp-range=interface:ens7,192.168.220.100,192.168.220.200,12h
dhcp-option=interface:ens7,3,192.168.220.8  # Gateway
```

## Verifying Configuration

### Check ZTP Server Interfaces

```bash
ssh netadmin@dhcp-oob
ip addr show
```

Expected output:
```
ens4: inet 192.168.1.8/24
ens5: inet 192.168.200.8/24
ens6: inet 192.168.210.8/24
ens7: inet 192.168.220.8/24
```

### Check dnsmasq is Listening

```bash
sudo netstat -tulpn | grep dnsmasq
```

Expected output:
```
udp  0.0.0.0:67   0.0.0.0:*  LISTEN  <pid>/dnsmasq  # DHCP
udp  0.0.0.0:53   0.0.0.0:*  LISTEN  <pid>/dnsmasq  # DNS
```

### Check dnsmasq Configuration

```bash
cat /etc/dnsmasq.conf
cat /etc/dnsmasq.d/ztp.conf
```

### Test ZTP Script Access

From each network:

```bash
# From ens4 network
curl http://192.168.1.8/scripts/ztp.sh

# From ens5 network
curl http://192.168.200.8/scripts/ztp.sh

# From ens6 network
curl http://192.168.210.8/scripts/ztp.sh
```

## Troubleshooting

### dnsmasq Not Listening on Interface

**Symptom**: `unknown interface ens4`

**Solution**: Verify interface exists and is UP:
```bash
ip link show ens4
sudo ip link set ens4 up
```

### DHCP Not Working on Interface

**Symptom**: Switches not getting IPs

**Solution**: Check subnet matches:
```bash
# Interface IP and DHCP range must be in same subnet
ip addr show ens4  # Should show 192.168.1.8
cat /etc/dnsmasq.conf | grep ens4  # Should show 192.168.1.100-200
```

### Switches Can't Reach ZTP Server

**Symptom**: `curl: (7) Failed to connect`

**Solution**: Check routing and firewall:
```bash
# On ZTP server
sudo iptables -L
sudo ufw status

# On switch
ping 192.168.1.8
traceroute 192.168.1.8
```

### Wrong Gateway Configured

**Symptom**: OOB switches have wrong gateway

**Solution**: Check generated config:
```bash
cat output/<arch>/<site>/inventory/host_vars/oob-switch-01.yml
# Verify: default_gateway: '192.168.200.8'
```

## Benefits of Multi-Interface ZTP

1. **Isolation**: OOB switch ZTP on dedicated network
2. **Scalability**: Multiple OOB networks for many switches
3. **Flexibility**: Each switch can ZTP independently
4. **Troubleshooting**: Easy to identify which network has issues
5. **Security**: Separate ZTP network from production

## Comparison with Single-Interface ZTP

| Feature | Single-Interface | Multi-Interface |
|---------|------------------|-----------------|
| **Interfaces** | 1 (e.g., eth0) | Multiple (ens4, ens5, ens6, ens7) |
| **Networks** | 1 subnet | Multiple subnets |
| **Staged ZTP** | No | Yes (OOB first, then core) |
| **Isolation** | All on same network | Separate networks per switch group |
| **Complexity** | Low | Medium |
| **Scalability** | Limited | High |

## Advanced Configuration

### Custom DHCP Ranges per Interface

Edit `output/<arch>/<site>/inventory/group_vars/all/main.yml` after generation (advanced):

```yaml
ztp_interfaces:
  - name: ens4
    ip: 192.168.1.8
    network: 192.168.1.0/24
    purpose: oob_switch_ztp
    dnsmasq_listen: true
    dhcp_start: 100  # Custom range start
    dhcp_end: 150    # Custom range end
```

### Disable dnsmasq on Specific Interface

Set `dnsmasq_listen: false` in the generated inventory:

```yaml
  - name: ens7
    ip: 192.168.220.8
    network: 192.168.220.0/24
    purpose: oob3
    dnsmasq_listen: false  # Don't listen on this interface
```

### Add More Interfaces

Add more interface entries to the Wire Map in your Excel template and re-run
`make generate`. The additional interfaces will be picked up automatically.

## Summary

Multi-interface ZTP enables:
- ✅ **Staged provisioning** (OOB switches first, then core)
- ✅ **Network isolation** (separate subnets)
- ✅ **Scalability** (support many switches)
- ✅ **Flexibility** (configure per-interface DHCP)
- ✅ **Maintainability** (Excel-driven configuration)

The Excel-driven workflow makes it easy to set up multi-interface ZTP without manually editing configuration files!

