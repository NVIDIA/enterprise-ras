<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# OOB Server Setup for Air/Lab Environments

## Overview

The OOB (Out-of-Band) server acts as a gateway and router for isolated management networks in NVIDIA Air simulations or physical lab environments. It provides routing between multiple OOB networks and can forward traffic to external networks.

## Purpose

In Air simulations and some lab setups, management networks are isolated on separate interfaces (eth1, eth2, eth3, etc.). The OOB server:

- **Enables IP forwarding** between networks
- **Acts as a default gateway** for switches and servers
- **Routes traffic** between isolated management networks
- **Provides connectivity** to external networks

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      OOB Server (oob-server-01)             │
│                                                               │
│  eth0: External/WAN (Air jump box or physical network)      │
│  eth1: 192.168.200.1/24 (OOB Network 1 Gateway)             │
│  eth2: 192.168.210.1/24 (OOB Network 2 Gateway)             │
│  eth3: 192.168.220.1/24 (OOB Network 3 Gateway)             │
│                                                               │
│  IP Forwarding: Enabled                                      │
│  IPv6: Disabled (optional)                                   │
└─────────────────────────────────────────────────────────────┘
         │              │              │
         │              │              │
    ┌───▼────┐    ┌───▼────┐    ┌───▼────┐
    │ core-01│    │ core-02│    │  OOB   │
    │ .200.x │    │ .210.x │    │ .220.x │
    └────────┘    └────────┘    └────────┘
```

## Quick Start

### 1. Configure Connection Settings

Edit the OOB server host variables:

```bash
nano output/<arch>/<site>/inventory/host_vars/oob-server-01.yml
```

Update for your environment:

```yaml
# For Air simulations with jump box
ansible_host: <air-host>
ansible_port: 20561
ansible_user: ubuntu
ansible_password: nvidia

# For physical lab (direct access)
# ansible_host: 10.0.0.50
# ansible_port: 22
```

### 2. Configure Network Interfaces

Update interface configuration in the same file:

```yaml
oob_server_interfaces:
  - name: eth1
    ip: 192.168.200.1
    netmask: 24
    network: 192.168.200.0/24
    purpose: "OOB Network 1 Gateway"
  
  - name: eth2
    ip: 192.168.210.1
    netmask: 24
    network: 192.168.210.0/24
    purpose: "OOB Network 2 Gateway"
  
  - name: eth3
    ip: 192.168.220.1
    netmask: 24
    network: 192.168.220.0/24
    purpose: "OOB Network 3 Gateway"
```

**Important**: Gateway IPs must match what's configured in:
- Switch configurations (default gateway)
- Server configurations (network gateway)
- `output/<arch>/<site>/inventory/group_vars/all/main.yml` (common.X_gateway values)

### 3. Run the Setup

```bash
make oob-setup ARCH=<type>
```

This will:
1. Install required packages (net-tools, iptables, iptables-persistent)
2. Enable IP forwarding in `/etc/sysctl.conf`
3. Configure netplan for static IPs on OOB interfaces
4. Apply network configuration
5. Configure NAT masquerade on eth0 (allows server nodes to reach the internet)

## Configuration Files

### System Configuration

After setup, the following files are configured:

**`/etc/sysctl.conf`**
```
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
```

**`/etc/netplan/01-config.yaml`**
```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth1:
      dhcp4: no
      addresses:
        - 192.168.200.1/24
    eth2:
      dhcp4: no
      addresses:
        - 192.168.210.1/24
    eth3:
      dhcp4: no
      addresses:
        - 192.168.220.1/24
```

## Verification

### Check IP Forwarding

```bash
# On OOB server
sysctl net.ipv4.ip_forward
# Should return: net.ipv4.ip_forward = 1
```

### Check Interface Configuration

```bash
# View configured IPs
ip addr show

# Should show:
#   eth1: 192.168.200.1/24
#   eth2: 192.168.210.1/24
#   eth3: 192.168.220.1/24
```

### Test Gateway Connectivity

From a switch on one of the OOB networks:

```bash
# On switch (e.g., core-01 on 192.168.200.0/24)
ping 192.168.200.1

# From switch, test routing to another network
ping 192.168.210.1
```

### Check Routing Table

```bash
# On OOB server
ip route show

# Should show routes for all configured networks
```

## Use Cases

### NVIDIA Air Simulations

Air creates isolated network segments. The OOB server:
- Connects via Air jump box (custom hostname/port)
- Routes between Air-created network segments
- Allows management access to all devices

**Configuration Example**:
```yaml
ansible_host: <air-host>
ansible_port: 20561
```

### Physical Lab Environments

For labs with physically separated OOB networks:
- Direct connection (no jump box)
- Routes between switch racks or segments
- Provides external connectivity

**Configuration Example**:
```yaml
ansible_host: 10.0.0.50
ansible_port: 22
```

## Troubleshooting

### IP Forwarding Not Working

**Symptom**: Switches can ping their gateway but not other networks

**Solution**:
```bash
# Check current setting
sysctl net.ipv4.ip_forward

# If 0, enable it
sudo sysctl -w net.ipv4.ip_forward=1
sudo sysctl -p

# Make permanent (done by oob-setup)
echo "net.ipv4.ip_forward = 1" | sudo tee -a /etc/sysctl.conf
```

### Interface Configuration Not Applied

**Symptom**: Interfaces don't have configured IPs

**Solution**:
```bash
# Check netplan config
cat /etc/netplan/01-config.yaml

# Apply configuration
sudo netplan apply

# If issues persist, debug
sudo netplan --debug apply
```

### Cannot Connect via Jump Box

**Symptom**: `ansible-playbook` fails to connect to OOB server

**Solution**:
1. Verify jump box hostname/port: `ssh -p 20561 ubuntu@<air-host>`
2. Check inventory: `cat output/<arch>/<site>/inventory/host_vars/oob-server-01.yml`
3. Test Ansible connectivity: `ansible oob-server -i output/<arch>/<site>/inventory/hosts -m ping`

### Routing Not Working Between Networks

**Symptom**: Switches can ping gateway but not other networks

**Check**:
1. IP forwarding enabled: `sysctl net.ipv4.ip_forward`
2. All interfaces configured: `ip addr show`
3. Routing table: `ip route show`
4. Firewall rules: `sudo iptables -L -n -v`

**Fix**:
```bash
# If firewall is blocking, add rules
sudo iptables -A FORWARD -j ACCEPT
sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE

# Save rules
sudo netfilter-persistent save
```

## Integration with ZTP Server

The OOB server and ZTP server can run on the same or different hosts:

### Same Host (Typical)
```
oob-server-01 = dhcp-oob (same host)
- eth0: External/WAN
- eth1: 192.168.200.1 (gateway) + 192.168.200.252 (ZTP/DHCP)
- eth2: 192.168.210.1 (gateway) + 192.168.210.252 (ZTP/DHCP)
- eth3: 192.168.220.1 (gateway) + 192.168.220.252 (ZTP/DHCP)
```

### Different Hosts
```
oob-server-01: Gateway only (eth1-3: .1 IPs)
dhcp-oob: ZTP/DHCP only (eth1-3: .252 IPs)
```

## Advanced Configuration

### Add Static Routes

Edit `output/<arch>/<site>/inventory/host_vars/oob-server-01.yml`:

```yaml
oob_server_interfaces:
  - name: eth1
    ip: 192.168.200.1
    netmask: 24
    routes:
      - to: 10.0.0.0/8
        via: 192.168.200.254
```

### Custom Netmask

```yaml
oob_server_interfaces:
  - name: eth1
    ip: 192.168.200.1
    netmask: 25  # Use /25 instead of /24
```

### NAT/Masquerading

For external internet access from OOB networks:

```bash
# On OOB server
sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
sudo netfilter-persistent save
```

## Files Created/Modified

| File | Purpose | Backup |
|------|---------|--------|
| `/etc/sysctl.conf` | IP forwarding settings | `.bak` created |
| `/etc/netplan/01-config.yaml` | Interface configuration | `.backup` created |

## Maintenance

### Update Interface Configuration

1. Edit host_vars: `nano output/<arch>/<site>/inventory/host_vars/oob-server-01.yml`
2. Re-run setup: `make oob-setup`
3. Changes applied automatically

### Disable OOB Server

To revert changes:

```bash
# Disable IP forwarding
sudo sysctl -w net.ipv4.ip_forward=0

# Restore netplan backup
sudo cp /etc/netplan/01-config.yaml.backup /etc/netplan/01-config.yaml
sudo netplan apply
```

## See Also

- [ZTP Setup Guide](MULTI_INTERFACE_ZTP.md) - Configure ZTP server
- [Air Deployment Guide](AIR_DEPLOYMENT_GUIDE.md) - NVIDIA Air deployment
- [ZTP Validation](ZTP_VALIDATION.md) - Testing connectivity

## Summary

The OOB server is essential for Air simulations and isolated lab environments:

✅ **Gateway**: Provides default gateway for management networks  
✅ **Routing**: Enables inter-network communication  
✅ **Flexibility**: Works with jump boxes or direct connections  
✅ **Simple Setup**: One command: `make oob-setup`  

For questions or issues, check the troubleshooting section above.

