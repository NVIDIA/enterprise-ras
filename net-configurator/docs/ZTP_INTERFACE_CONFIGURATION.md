<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# ZTP Interface Configuration Guide

This guide explains how IP addresses are configured on the ZTP server interfaces that serve DHCP to switches.

## Overview

The ZTP server needs IP addresses on each network interface where switches will request DHCP. These interfaces and their IPs are automatically generated from your Excel template when you run `make generate`.

The generated configuration lives in `output/<arch>/<site>/inventory/group_vars/all/main.yml` under the `ztp_interfaces` key:

```yaml
configure_ztp_ips: true
ztp_interfaces:
- name: eth1
  ip: 172.20.0.77
  network: 172.20.0.0/24
  gateway: 172.20.0.1
  purpose: air-mgmt
  dnsmasq_listen: true
```

## How It Works

When `configure_ztp_ips: true` (the default for generated inventories), `make ztp-setup` or `make switch-ztp-deploy` will:

1. **Check interfaces exist** -- verifies each interface in `ztp_interfaces` exists on the server
2. **Configure IPs** -- assigns the IP addresses using `ip addr add`
3. **Bring interfaces up** -- ensures interfaces are in UP state
4. **Make it persistent** -- creates `/etc/netplan/99-ztp-interfaces.yaml` (Ubuntu)
5. **Configure dnsmasq** -- sets up DHCP on each interface with `dnsmasq_listen: true`

You typically don't need to touch this. The Excel Wire Map and Settings tabs drive everything.

## When to Edit Manually

If you need to override the auto-generated interface configuration after `make generate`:

1. Edit `output/<arch>/<site>/inventory/group_vars/all/main.yml`
2. Modify the `ztp_interfaces` list
3. Re-run `make ztp-setup` or `make ztp-update`

Note: re-running `make generate` will overwrite your manual changes. For persistent overrides, edit the Excel template instead.

## Manual IP Configuration (Alternative)

If you prefer to configure IPs manually, keep `configure_ztp_ips: false` and configure each interface:

### Ubuntu/Netplan

Edit `/etc/netplan/01-netcfg.yaml`:

```yaml
network:
  version: 2
  ethernets:
    ens4:
      addresses:
        - 192.168.1.8/24
      dhcp4: false
    ens5:
      addresses:
        - 192.168.200.8/24
      dhcp4: false
```

Apply:
```bash
sudo netplan apply
```

### Debian/interfaces

Edit `/etc/network/interfaces`:

```
auto ens4
iface ens4 inet static
    address 192.168.1.8
    netmask 255.255.255.0

auto ens5
iface ens5 inet static
    address 192.168.200.8
    netmask 255.255.255.0
```

Apply:
```bash
sudo systemctl restart networking
```

## Verification

After configuration (automatic or manual), verify:

### 1. Check Interface IPs

```bash
ip addr show
```

Expected output:
```
4: ens4: <BROADCAST,MULTICAST,UP,LOWER_UP>
    inet 192.168.1.8/24 brd 192.168.1.255 scope global ens4
5: ens5: <BROADCAST,MULTICAST,UP,LOWER_UP>
    inet 192.168.200.8/24 brd 192.168.200.255 scope global ens5
```

### 2. Check Interface Status

```bash
ip link show
```

All ZTP interfaces should show `state UP`.

### 3. Test Connectivity

From each interface:
```bash
ping -I ens4 192.168.1.1
ping -I ens5 192.168.200.1
```

### 4. Check dnsmasq is Listening

```bash
sudo netstat -tuln | grep :67  # DHCP
sudo netstat -tuln | grep :69  # TFTP
```

Expected: Should show listening on each interface IP.

## Troubleshooting

### Error: Interface does not exist

**Problem:** Ansible reports "⚠️ WARNING: Interface X does not exist!"

**Solutions:**
1. Create the interface on your server first (e.g., add a network adapter in hypervisor)
2. Change the interface name in the generated `group_vars/all/main.yml` to match existing interfaces
3. Set `configure_ztp_ips: false` and configure manually

**Check available interfaces:**
```bash
ip link show
```

### Error: IP already configured

**Problem:** `ip addr add` fails with "File exists"

**Solution:** This is expected if the IP is already configured. The task will show as not changed.

To remove existing IP:
```bash
sudo ip addr del 192.168.1.8/24 dev ens4
```

### IPs Lost After Reboot

**Problem:** IPs are gone after server reboot

**Cause:** Persistent configuration file was not created properly

**Solution:**

**Ubuntu:**
```bash
# Check if netplan config exists
cat /etc/netplan/99-ztp-interfaces.yaml

# Reapply if needed
sudo netplan apply
```

**Debian:**
```bash
# Check if interfaces config exists
cat /etc/network/interfaces.d/ztp-interfaces

# Restart networking if needed
sudo systemctl restart networking
```

### dnsmasq Not Listening on All Interfaces

**Problem:** dnsmasq only listening on one interface

**Solution:**

Check dnsmasq config:
```bash
cat /etc/dnsmasq.d/ztp.conf
```

Should have:
```
interface=ens4
interface=ens5
interface=ens6
interface=ens7
```

Restart dnsmasq:
```bash
sudo systemctl restart dnsmasq
```

## Best Practices

### ✅ DO

- Use `configure_ztp_ips: true` for automated setups (lab, CI/CD)
- Verify all interfaces exist before running setup
- Use consistent network naming (`192.168.X.8` for ZTP server)
- Test connectivity on each interface after configuration

### ❌ DON'T

- Don't use `configure_ztp_ips: true` if interfaces are managed by other tools (cloud-init, netplan in production)
- Don't forget to bring interfaces up after adding to hypervisor
- Don't mix manual and automatic configuration (pick one method)
- Don't use overlapping networks on different interfaces

## Examples

### Example 1: Lab Environment (Automated)

**Scenario:** NVIDIA Air simulation with 4 pre-configured interfaces

```yaml
configure_ztp_ips: true  # Let Ansible configure everything
ztp_interfaces:
- name: ens4
  ip: 192.168.1.8
  network: 192.168.1.0/24
  purpose: oob_switch_ztp
  dnsmasq_listen: true
```

Run `make ztp-setup` and you're done!

### Example 2: Production Environment (Manual)

**Scenario:** Production server with existing network configuration

```yaml
configure_ztp_ips: false  # IPs already configured by IT/NetOps
ztp_interfaces:
- name: eth1
  ip: 10.100.200.10
  network: 10.100.200.0/24
  purpose: rack1_oob
  dnsmasq_listen: true
```

Configure IPs manually via netplan/interfaces, then run `make ztp-setup`.

### Example 3: Hybrid (Some Automated, Some Manual)

**Scenario:** Some interfaces are pre-configured, need to add new ones

Set `configure_ztp_ips: true`. Ansible will:
- Skip IPs that already exist (no error)
- Add missing IPs only
- Update persistent config with all interfaces

## Advanced Configuration

### Custom Network Mask

Ansible automatically calculates the netmask from the `network` field:

```yaml
- name: ens4
  ip: 192.168.1.8
  network: 192.168.1.0/24  # /24 = 255.255.255.0
```

For different mask sizes:
```yaml
network: 10.0.0.0/16      # /16 = 255.255.0.0
network: 172.16.0.0/12    # /12 = 255.240.0.0
network: 192.168.1.0/25   # /25 = 255.255.255.128
```

### Adding a New Interface

1. Edit `output/<arch>/<site>/inventory/group_vars/all/main.yml` and add to `ztp_interfaces`:

```yaml
- name: ens8
  ip: 192.168.230.8
  network: 192.168.230.0/24
  purpose: rack4_oob
  dnsmasq_listen: true
```

2. Run update:

```bash
make ztp-update ARCH=<type>
```

Ansible will:
- Configure the new IP
- Update persistent config
- Reconfigure dnsmasq to listen on new interface
- No disruption to existing interfaces

### Temporarily Disable an Interface

Change `dnsmasq_listen` to `false`:

```yaml
- name: ens7
  ip: 192.168.220.8
  network: 192.168.220.0/24
  purpose: oob3
  dnsmasq_listen: false  # Don't serve DHCP on this interface
```

The IP will still be configured, but dnsmasq won't listen on it.

## Summary

| Method | configure_ztp_ips | Best For |
|--------|-------------------|----------|
| **Automatic** | `true` | Labs, testing, NVIDIA Air, automated deployments |
| **Manual** | `false` (default) | Production, servers with existing network management |

Choose the method that fits your environment!

---

**Related Documentation:**
- [Multi-Interface ZTP](./MULTI_INTERFACE_ZTP.md)
- [ZTP Modes](./ZTP_MODES.md)
- Main README: [../README.md](../README.md)

