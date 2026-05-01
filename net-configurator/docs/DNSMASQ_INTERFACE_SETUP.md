<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# dnsmasq Interface Configuration

One of the most common issues when setting up the ZTP server is **wrong network interface** configuration for dnsmasq.

## The Problem

**Error**: `unknown interface eth0`

**Cause**: Modern Linux systems use predictable network interface names like `ens3`, `ens4`, `enp0s3` instead of the traditional `eth0`, `eth1`.

## Quick Fix

Edit `output/<arch>/<site>/inventory/group_vars/all/main.yml`:

```yaml
# Change from:
dnsmasq_interface: "eth0"  # ❌ Doesn't exist

# To your actual interface:
dnsmasq_interface: "ens3"  # ✅ Or whatever yours is
```

Then re-run:
```bash
make ztp-setup ARCH=<type>
```

---

## How to Find Your Interface

### Option 1: Detection Script

We provide a helper script:

```bash
ssh netadmin@10.0.0.20 "bash -s" < scripts/detect-interface.sh
```

This shows:
- All available interfaces
- IP addresses
- Network states
- Recommended interface

### Option 2: Manual Check

SSH to your ZTP server:
```bash
ssh netadmin@10.0.0.20
```

Show all interfaces:
```bash
ip addr show
```

Output example:
```
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN
    inet 127.0.0.1/8 scope host lo

2: ens3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP
    inet 192.168.1.10/24 brd 192.168.1.255 scope global ens3

3: ens4: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP
    inet 10.0.0.20/24 brd 10.0.0.255 scope global ens4
```

### Option 3: Quick One-Liner

```bash
ssh netadmin@10.0.0.20 "ip -o addr show | awk '/inet / && !/127.0.0.1/ {print \$2, \$4}'"
```

Output:
```
ens3 192.168.1.10/24
ens4 10.0.0.20/24
```

---

## Which Interface to Choose?

### Simple Rule

**Use the interface where switches and servers will connect to get their DHCP leases.**

### Common Scenarios

#### Scenario 1: Single Network
- All devices (management, switches, servers) on same network
- **Use**: The interface with your primary IP

#### Scenario 2: Separate Management Network (Common)
- `ens4` or `eth0`: OOB management (how you SSH to the server)
- `ens3` or `eth1`: Data/provisioning network (where switches connect)
- **Use**: The data/provisioning interface (`ens3`)

#### Scenario 3: Multiple VLANs
- Use the interface or VLAN where switches boot
- Often the "native" or "untagged" VLAN

### Your Case (from error message)

You described:
- `ens4`: OOB management
- `ens3`: Default gateway, where servers connect

**Answer**: Use `ens3` for dnsmasq (where devices will request DHCP)

---

## Common Interface Names

| Name | Typically Means |
|------|-----------------|
| `eth0`, `eth1` | **Old naming** - Legacy systems |
| `ens3`, `ens4` | **Modern naming** - Most common on VMs |
| `enp0s3`, `enp0s8` | **Modern naming** - Some physical/VM systems |
| `ens160`, `ens192` | **Modern naming** - VMware VMs |
| `bond0`, `bond1` | Bonded interfaces |
| `br0`, `br1` | Bridge interfaces |
| `wlan0`, `wlan1` | Wireless interfaces (don't use for DHCP server!) |

---

## Testing dnsmasq Configuration

After updating the interface, test the configuration:

```bash
# SSH to ZTP server
ssh netadmin@10.0.0.20

# Test configuration syntax
sudo dnsmasq --test

# Should output:
# dnsmasq: syntax check OK.
```

Check if it's running:
```bash
sudo systemctl status dnsmasq
```

Should show:
```
● dnsmasq.service - dnsmasq - A lightweight DHCP and caching DNS server
   Loaded: loaded (/lib/systemd/system/dnsmasq.service; enabled)
   Active: active (running) since ...
```

View logs:
```bash
sudo journalctl -u dnsmasq -f
```

Test DHCP:
```bash
# From a client/switch, should see DHCP offer
sudo dhclient -v eth0
```

---

## Troubleshooting

### Error: "unknown interface X"

**Problem**: Interface name doesn't exist

**Fix**: 
1. Check actual interface names: `ip addr show`
2. Update `dnsmasq_interface` in `output/<arch>/<site>/inventory/group_vars/all/main.yml`
3. Re-run: `make ztp-setup`

### Error: "failed to create listening socket for port 53: Address already in use"

**Problem**: Something else is using port 53 (usually `systemd-resolved`)

**Fix**:
```bash
ssh netadmin@10.0.0.20
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved
sudo systemctl restart dnsmasq
```

### Error: "dnsmasq: failed to bind DHCP server socket: Cannot assign requested address"

**Problem**: IP address in config doesn't match interface IP

**Fix**:
1. Check interface IP: `ip addr show ens3`
2. Verify DHCP range matches that subnet
3. Update `output/<arch>/<site>/inventory/group_vars/all/main.yml`:
   ```yaml
   dhcp_range_start: "192.168.1.100"  # Match your subnet!
   dhcp_range_end: "192.168.1.200"
   dhcp_gateway: "192.168.1.1"
   ```

### dnsmasq not listening on port 67 (DHCP)

**Problem**: `netstat` shows port 53 (DNS) but NOT port 67/68 (DHCP)

**Most Common Cause**: **Subnet mismatch**

Example:
```bash
# Your interface
ip addr show ens3
# Shows: 192.168.1.8/24

# But your config has
dhcp_range_start: "192.168.200.100"  # Wrong subnet!
```

**dnsmasq will NOT provide DHCP if the DHCP range is on a different subnet than the interface!**

**Fix**:
1. Check your interface subnet:
   ```bash
   ssh server "ip addr show ens3"
   ```
2. Update `output/<arch>/<site>/inventory/group_vars/all/main.yml` to match:
   ```yaml
   ztp_server_ip: "192.168.1.8"      # Match interface IP
   dhcp_range_start: "192.168.1.100" # Match subnet
   dhcp_range_end: "192.168.1.200"
   dhcp_gateway: "192.168.1.1"       # Match gateway
   ```
3. Re-run: `make ztp-setup`
4. Verify:
   ```bash
   ssh server "sudo netstat -plnu | grep 67"
   # Should show: udp 0.0.0.0:67 ... LISTEN ... dnsmasq
   ```

### Switches not getting DHCP

**Check**:
1. **Physical connection**: Is switch connected to correct network?
2. **Interface**: Is dnsmasq listening on the right interface?
3. **Firewall**: Is DHCP (port 67/68 UDP) allowed?
4. **VLAN**: Is switch on the correct VLAN?

**Test**:
```bash
# On ZTP server, watch DHCP requests
sudo tcpdump -i ens3 port 67 or port 68 -v
```

---

## Best Practices

1. **Document your topology**: Know which interface serves which network
2. **Use comments**: Add notes to your inventory files
3. **Test before production**: Verify DHCP works in lab first
4. **Monitor logs**: `sudo journalctl -u dnsmasq -f` during initial setup
5. **Plan for changes**: Network topology changes? Update dnsmasq config!

---

## Automated Detection (Future Enhancement)

You can automate interface detection in your playbook:

```yaml
# In playbooks/setup-ztp-server.yml
- name: Detect network interface
  shell: ip route | grep default | awk '{print $5}'
  register: detected_interface
  changed_when: false

- name: Display detected interface
  debug:
    msg: "Detected default interface: {{ detected_interface.stdout }}"

# Use it:
- name: Configure dnsmasq
  template:
    src: dnsmasq.conf.j2
    dest: /etc/dnsmasq.conf
  vars:
    dnsmasq_interface: "{{ ansible_default_interface | default('ens3') }}"
```

---

## See Also

- [ZTP Setup Guide](ZTP_MODES.md)
- [Multi-Interface ZTP](MULTI_INTERFACE_ZTP.md)
- [Troubleshooting Script](../scripts/debug-dnsmasq.sh)
- [Interface Detection Script](../scripts/detect-interface.sh)

