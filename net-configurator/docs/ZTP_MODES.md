<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# ZTP Modes: DHCP vs Static IP

> **Note:** The ERA automation tool uses an Excel-driven workflow. ZTP mode selection,
> MAC addresses, and IP settings described below are configured in the Excel template
> (Settings and Nodes tabs) and applied automatically when you run `make generate`.
> This document is provided as a reference for understanding the ZTP modes and
> troubleshooting.

This repository supports two modes for Zero Touch Provisioning (ZTP), allowing you to provision switches regardless of whether they use DHCP or static IP addresses.

## Table of Contents

- [Overview](#overview)
- [DHCP Mode (Automatic)](#dhcp-mode-automatic)
- [Static IP Mode (Manual)](#static-ip-mode-manual)
- [Mixed Mode](#mixed-mode)
- [Configuration](#configuration)
- [Manual ZTP Execution](#manual-ztp-execution)
- [Troubleshooting](#troubleshooting)

---

## Overview

### DHCP Mode (Default)
- **Use Case**: New switches, lab environments, NVIDIA Air simulations
- **How it works**: Switch boots → DHCP assigns IP → DHCP option 239 provides ZTP script URL → Switch auto-executes script
- **Advantages**: Fully automated, no manual intervention needed
- **Requirements**: Switch MAC address in inventory (for static IP assignment via DHCP)

### Static IP Mode
- **Use Case**: Production switches with pre-configured IPs, manual provisioning workflows
- **How it works**: Switch has static IP → Admin manually triggers ZTP → Switch downloads and applies config
- **Advantages**: Compatible with existing IP schemes, more control over deployment timing
- **Requirements**: Network connectivity to ZTP server

### Mixed Mode
- **Use Case**: Environments with both new and existing switches
- **How it works**: Configure each switch individually as DHCP or static
- **Advantages**: Maximum flexibility

---

## DHCP Mode (Automatic)

### Prerequisites

1. **Switch MAC address** (physical or simulated)
2. **Network connectivity** to ZTP server
3. **DHCP enabled** on switch management interface

### Configuration

Import your Excel file and generate the inventory:

```bash
make import EXCEL=your-config.xlsx
make generate
```

MAC addresses are read from the Nodes tab "MAC Address for ZTP" column. If left blank,
MACs are auto-generated. IP assignment mode defaults to DHCP for ZTP deployments.

> **Note:** MAC addresses and IP assignment mode are configured in the Excel template
> and applied automatically during import and generation.

### Generated Configuration

The pipeline generates `output/<arch>/<site>/inventory/host_vars/{switch-name}.yml` with:

```yaml
ansible_host: "10.0.0.201"
hostname: "core-01"
mac_address: "44:38:39:00:01:01"
ip_assignment_mode: "dhcp"
# ... rest of config
```

### DHCP Server Configuration

The `dnsmasq` configuration will include:

```conf
# core-01 - Static IP with MAC address
dhcp-host=44:38:39:00:01:01,10.0.0.201,core-01,12h,set:core_01
dhcp-option=tag:core_01,239,http://192.168.200.1/scripts/core-01.sh
```

### Workflow

1. **Switch boots** with factory defaults
2. **DHCP request** sent from management interface
3. **ZTP server** recognizes MAC address
4. **IP assigned** (e.g., `10.0.0.201`) via DHCP
5. **DHCP option 239** provides ZTP script URL
6. **Switch downloads** and executes ZTP script
7. **Configuration applied** automatically

---

## Static IP Mode (Manual)

### Prerequisites

1. **Switch has static IP** pre-configured
2. **Network connectivity** to ZTP server
3. **SSH access** to switch (optional, for remote execution)

### Configuration

Configure static IPs in the Excel Nodes tab and import:

```bash
make import EXCEL=your-config.xlsx
make generate
```

> **Note:** Static IP mode is configured per-switch in the Excel template or by
> editing `host_vars` after generation.

### Generated Configuration

The pipeline generates `output/<arch>/<site>/inventory/host_vars/{switch-name}.yml` with:

```yaml
ansible_host: "10.0.0.201"  # Pre-configured static IP
hostname: "core-01"
ip_assignment_mode: "static"
# No MAC address required (but can be provided for documentation)
# ... rest of config
```

### DHCP Server Configuration

For static IP switches, `dnsmasq` provides DHCP information mode:

```conf
# core-01 - Static IP - Switch has pre-configured IP
# ZTP script available at: http://192.168.200.1/scripts/core-01.sh
# If MAC provided, can still query DHCP for option 239:
dhcp-host=44:38:39:00:01:01,ignore,set:core_01
dhcp-option=tag:core_01,239,http://192.168.200.1/scripts/core-01.sh
```

**Note**: The `ignore` option means dnsmasq won't assign an IP, but will still provide DHCP options if the switch queries for them.

### Workflow

1. **Switch boots** with static IP already configured
2. **Admin decides** when to apply configuration
3. **Manual ZTP triggered** (see methods below)
4. **Configuration downloaded** from ZTP server
5. **Configuration applied** by switch

---

## Mixed Mode

### Configuration

Configure per-switch IP mode in the Excel template or edit `host_vars` after generation:

```bash
make import EXCEL=your-config.xlsx
make generate
```

> **Note:** Mixed mode is achieved by setting `ip_assignment_mode` in each switch's
> `host_vars` file after generation.

Each switch gets its own `ip_assignment_mode` setting in `host_vars`.

---

## Manual ZTP Execution

For switches with static IPs, you have multiple options to trigger ZTP:

### Option 1: Helper Script (Recommended)

The ZTP server includes a helper script at `/opt/ztp/manual-ztp.sh`:

```bash
# On ZTP server
/opt/ztp/manual-ztp.sh core-01
```

This script will:
- Check if ZTP script and config exist
- Display manual execution options
- Optionally SSH to switch and execute ZTP

### Option 2: Direct Execution on Switch

SSH to the switch and run:

```bash
# SSH to switch
ssh cumulus@core-01

# Download and execute ZTP script
curl http://192.168.200.1/scripts/core-01.sh | bash

# OR download first, then execute
wget http://192.168.200.1/scripts/core-01.sh
chmod +x core-01.sh
./core-01.sh
```

### Option 3: Cumulus ZTP Command

Use the built-in Cumulus ZTP command:

```bash
# On switch
sudo /usr/lib/cumulus/ztp -v -r http://192.168.200.1/scripts/core-01.sh
```

### Option 4: Remote Execution from ZTP Server

Use `sshpass` to execute remotely:

```bash
# Install sshpass if not present
sudo apt install sshpass

# Execute ZTP on remote switch
sshpass -p 'Cumu1usLinux!' ssh cumulus@core-01 \
  "curl http://192.168.200.1/scripts/core-01.sh | bash"
```

---

## Configuration

### Switching Between Modes

To change a switch from DHCP to static or vice versa:

1. **Edit inventory**:
   ```bash
   vim output/<arch>/<site>/inventory/host_vars/core-01.yml
   ```

2. **Change IP mode**:
   ```yaml
   ip_assignment_mode: "static"  # or "dhcp"
   ```

3. **Regenerate ZTP configuration**:
   ```bash
   make ztp-setup ARCH=<type>
   ```

### Manual Configuration

You can also manually edit `output/<arch>/<site>/inventory/host_vars/{switch}.yml`:

```yaml
---
ansible_host: "10.0.0.201"
hostname: "core-01"
mac_address: "44:38:39:00:01:01"  # Optional for static mode
ip_assignment_mode: "dhcp"         # or "static"

# Rest of switch configuration...
post_login_message: |
  #####################################################################################
  #                  You are successfully logged in to: core-01                     #
  #####################################################################################

lo_ip: "172.16.176.11/32"
router_id: "172.16.176.11"
# ... more config ...
```

---

## Troubleshooting

### DHCP Mode Issues

**Problem**: Switch not getting IP from DHCP

**Solutions**:
1. Check MAC address is correct in inventory
   ```bash
   # On switch
   ip link show eth0
   ```
2. Check dnsmasq is running
   ```bash
   # On ZTP server
   sudo systemctl status dnsmasq
   sudo journalctl -u dnsmasq -f
   ```
3. Check DHCP range and interface
   ```bash
   # On ZTP server
   cat /etc/dnsmasq.conf | grep -E 'dhcp-range|interface'
   ```
4. Test DHCP manually
   ```bash
   # On switch
   sudo dhclient -v eth0
   ```

**Problem**: Switch gets IP but doesn't run ZTP

**Solutions**:
1. Check DHCP option 239 is configured
   ```bash
   # On ZTP server
   cat /etc/dnsmasq.d/ztp.conf | grep -A2 "core-01"
   ```
2. Check ZTP script exists
   ```bash
   # On ZTP server
   ls -la /var/www/ztp/scripts/core-01.sh
   ```
3. Test ZTP script manually
   ```bash
   # On switch
   curl http://192.168.200.1/scripts/core-01.sh
   ```

### Static Mode Issues

**Problem**: Cannot reach ZTP server

**Solutions**:
1. Verify network connectivity
   ```bash
   # On switch
   ping 192.168.200.1
   curl http://192.168.200.1/
   ```
2. Check firewall rules
   ```bash
   # On ZTP server
   sudo iptables -L -n
   sudo ufw status
   ```
3. Check nginx is running
   ```bash
   # On ZTP server
   sudo systemctl status nginx
   ```

**Problem**: ZTP script fails

**Solutions**:
1. Download and inspect script
   ```bash
   # On switch
   curl http://192.168.200.1/scripts/core-01.sh -o /tmp/ztp.sh
   bash -x /tmp/ztp.sh  # Run with debug output
   ```
2. Check configuration file exists
   ```bash
   # Test from switch
   curl http://192.168.200.1/configs/core-01.yaml
   ```
3. Validate YAML syntax
   ```bash
   # On switch
   python3 -c "import yaml; yaml.safe_load(open('/tmp/core-01.yaml'))"
   ```

### General Debugging

**Check ZTP status page**:
```bash
curl http://192.168.200.1/
# Or open in browser: http://192.168.200.1/
```

**View dnsmasq logs**:
```bash
# On ZTP server
sudo journalctl -u dnsmasq -f
```

**Enable dnsmasq query logging**:
```bash
# On ZTP server
sudo vim /etc/dnsmasq.conf
# Uncomment: log-queries
sudo systemctl restart dnsmasq
```

**Check switch ZTP status**:
```bash
# On switch
ls -la /var/lib/cumulus/ztp-complete
cat /var/lib/cumulus/ztp-complete
```

---

## Best Practices

1. **Use DHCP mode** for:
   - New deployments
   - Lab/testing environments
   - NVIDIA Air simulations
   - Environments where you control IP addressing

2. **Use static mode** for:
   - Production environments with established IP schemes
   - Security-sensitive environments
   - Manual deployment workflows
   - Switches behind firewalls or NAT

3. **Use mixed mode** for:
   - Hybrid deployments
   - Migration scenarios (old switches static, new switches DHCP)
   - Multi-tenant environments

4. **Always test** in a lab environment before production deployment

5. **Document** which switches use which mode in your inventory comments

6. **Keep backups** of switch configurations before applying ZTP

---

## See Also

- [Multi-Interface ZTP Setup](./MULTI_INTERFACE_ZTP.md)
- [ZTP MAC Addresses Guide](./ZTP_MAC_ADDRESSES.md)
- [ZTP Validation](./ZTP_VALIDATION.md)

