<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# ZTP and MAC Addresses

> MAC addresses are provided in the Excel **Nodes** tab (column C, "MAC Address for ZTP")
> or auto-generated deterministically when left blank. See the
> [Excel Configuration Guide](EXCEL_CONFIGURATION_GUIDE.md) for details.

**Why MAC addresses matter for Zero Touch Provisioning**

---

## 🔑 **The Problem**

For ZTP to work correctly, each switch needs to:
1. Get the **correct IP address** from DHCP
2. Receive **DHCP option 239** pointing to **its specific ZTP script**

Without MAC addresses, DHCP can't distinguish between switches and might give them random IPs or the wrong ZTP script!

---

## 📡 **How ZTP Works**

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│  Switch     │         │  DHCP Server │         │  ZTP Script │
│  (boots)    │         │  (dnsmasq)   │         │  (nginx)    │
└──────┬──────┘         └──────┬───────┘         └──────┬──────┘
       │                       │                        │
       │ DHCP Discover         │                        │
       │ (MAC: AA:BB:CC:DD)    │                        │
       ├──────────────────────>│                        │
       │                       │                        │
       │                  ┌────┴─────┐                  │
       │                  │ Look up  │                  │
       │                  │ MAC in   │                  │
       │                  │ config   │                  │
       │                  └────┬─────┘                  │
       │                       │                        │
       │ DHCP Offer            │                        │
       │ IP: 192.168.200.201   │                        │
       │ Option 239:           │                        │
       │ http://.../core-01.sh │                        │
       │<──────────────────────┤                        │
       │                       │                        │
       │ Request IP            │                        │
       ├──────────────────────>│                        │
       │                       │                        │
       │ ACK                   │                        │
       │<──────────────────────┤                        │
       │                       │                        │
       │ Download ZTP script                            │
       │ http://.../ core-01.sh                         │
       ├───────────────────────────────────────────────>│
       │                       │                        │
       │ Receive core-01.sh                             │
       │<───────────────────────────────────────────────┤
       │                       │                        │
       │ Execute script        │                        │
       │ (applies config)      │                        │
       │                       │                        │
```

---

## 🎯 **dnsmasq Configuration**

The ZTP server uses `dnsmasq` to assign IPs based on MAC addresses:

```bash
# /etc/dnsmasq.d/ztp.conf (auto-generated)

# core-01 (192.168.200.201)
dhcp-host=AA:BB:CC:DD:EE:01,192.168.200.201,core-01,12h,set:core_01
dhcp-option=tag:core_01,239,http://192.168.200.1/scripts/core-01.sh

# core-02 (192.168.210.202)
dhcp-host=AA:BB:CC:DD:EE:02,192.168.210.202,core-02,12h,set:core_02
dhcp-option=tag:core_02,239,http://192.168.200.1/scripts/core-02.sh

# oob-switch-01 (192.168.200.2)
dhcp-host=AA:BB:CC:DD:EE:11,192.168.200.2,oob-switch-01,12h,set:oob_switch_01
dhcp-option=tag:oob_switch_01,239,http://192.168.200.1/scripts/oob-switch-01.sh
```

**Without MAC addresses**, dnsmasq can't create these static reservations!

---

## 🛠️ **Providing MAC Addresses**

### **Physical Hardware (Real MACs)**

For physical switches, enter the real MAC addresses in the Excel **Nodes** tab, column C ("MAC Address for ZTP"). You can find switch MACs from:
- The label on the back/bottom of the switch
- Console access: `cat /sys/class/net/eth0/address`
- Switch documentation or inventory system

### **Simulation / NVIDIA Air (Auto-generated MACs)**

For Air simulations, leave the MAC column blank in the Excel Nodes tab. The parser auto-generates deterministic MACs using an MD5 hash of the node name and interface. These MACs are consistent between the inventory and the Air topology JSON, so ZTP DHCP reservations match.

---

## 📂 **Where MACs Are Stored**

### **1. Inventory Files**

**`output/<arch>/<site>/inventory/group_vars/all/main.yml`**:
```yaml
devices:
  core-01:
    eth0_ip: 192.168.200.201
    mac: '50:6B:4B:12:34:01'
  core-02:
    eth0_ip: 192.168.210.202
    mac: '50:6B:4B:12:34:02'
  # ...
```

**`output/<arch>/<site>/inventory/host_vars/core-01.yml`**:
```yaml
ansible_host: "192.168.200.201"
hostname: "core-01"
mac_address: "50:6B:4B:12:34:01"  # Used by dnsmasq
# ...
```

### **3. ZTP Server Configuration**

The `setup-ztp-server.yml` playbook reads these MACs and generates:

**`/etc/dnsmasq.d/ztp.conf`** (on ZTP server):
```bash
# Auto-generated from inventory

dhcp-host=50:6B:4B:12:34:01,192.168.200.201,core-01,12h,set:core_01
dhcp-option=tag:core_01,239,http://192.168.200.1/scripts/core-01.sh

dhcp-host=50:6B:4B:12:34:02,192.168.210.202,core-02,12h,set:core_02
dhcp-option=tag:core_02,239,http://192.168.200.1/scripts/core-02.sh

# ... etc ...
```

---

## 🔍 **Finding Switch MAC Addresses**

### **Physical Switches**

1. **Check the label** on the back/bottom of the switch
2. **Via console cable** (if accessible):
   ```bash
   # On Cumulus Linux
   cat /sys/class/net/eth0/address
   ```
3. **From switch documentation/inventory**
4. **Network discovery tools** (if switches are already on network)

### **NVIDIA Air**

Air assigns MAC addresses automatically when you create the simulation. You can:
1. **Use auto-generated MACs** (recommended for Air)
2. **Check Air console** after simulation is created to see assigned MACs

---

## 🧪 **Testing ZTP**

### **1. Verify DHCP Configuration**

On the ZTP server:

```bash
# Check dnsmasq config
cat /etc/dnsmasq.d/ztp.conf

# Test dnsmasq syntax
dnsmasq --test

# Check dnsmasq is running
systemctl status dnsmasq

# View DHCP leases
cat /var/lib/misc/dnsmasq.leases
```

### **2. Test DHCP from Switch**

On a switch (via console):

```bash
# Release current DHCP lease
sudo dhclient -r eth0

# Request new lease with verbose output
sudo dhclient -v eth0

# Should see:
# - IP address assigned
# - DHCP option 239 received
# - ZTP script URL
```

### **3. Test ZTP Manually**

```bash
# On the switch (via console)
sudo /usr/lib/cumulus/ztp -v -r http://192.168.200.1/scripts/core-01.sh
```

### **4. Monitor ZTP Server Logs**

```bash
# On ZTP server
tail -f /var/log/syslog | grep dnsmasq
tail -f /var/log/nginx/access.log
```

---

## 🆘 **Troubleshooting**

### **Problem**: Switch gets wrong IP

**Cause**: MAC address mismatch

**Solution**:
1. Verify switch's actual MAC: `cat /sys/class/net/eth0/address`
2. Update the MAC in the Excel Nodes tab (column C)
3. Run: `make generate ARCH=<type>`
4. Update ZTP server: `make ztp-update`

---

### **Problem**: Switch gets IP but no ZTP script

**Cause**: DHCP option 239 not configured for that MAC

**Solution**:
1. Check `/etc/dnsmasq.d/ztp.conf` on ZTP server
2. Verify MAC-to-hostname mapping exists
3. Restart dnsmasq: `sudo systemctl restart dnsmasq`

---

### **Problem**: Multiple switches get same IP

**Cause**: MACs not provided or duplicate MACs

**Solution**:
1. Ensure each switch has unique MAC in config
2. Re-run: `make import EXCEL=your-config.xlsx` and provide correct MACs
3. Apply: `make generate ARCH=<type> && make ztp-setup`

---

### **Problem**: Can't find switch MAC addresses

**Workarounds**:
1. **For testing**: Use auto-generated MACs and don't worry about ZTP
2. **Manual config**: Skip ZTP, use `# Manual switch configuration via SSH` instead
3. **For Air**: Use auto-generated MACs (Air handles it)

---

## 📋 **Workflow Comparison**

### **With Real MACs (Physical Hardware)**

```bash
# 1. Find switch MACs (via labels, console, etc.)

# 2. Configure network
make import EXCEL=your-config.xlsx
# Answer: y to provide MACs
# Enter each switch's MAC

# 3. Apply configuration
make generate ARCH=<type>

# 4. Setup ZTP server
make ztp-setup ARCH=<type>

# 5. Power on switches → auto-configure via ZTP! ✅
```

### **With Auto-Generated MACs (Simulation)**

```bash
# 1. Configure network
make import EXCEL=your-config.xlsx
# Answer: n to auto-generate MACs

# 2. Apply configuration
make generate ARCH=<type>

# 3. Setup ZTP server
make ztp-setup ARCH=<type>

# 4. Start Air simulation → auto-configure via ZTP! ✅
```

### **Without ZTP (Manual)**

```bash
# 1. Configure network (MACs optional)
make import EXCEL=your-config.xlsx

# 2. Apply configuration
make generate ARCH=<type>

# 3. Manual switch configuration
# Manual switch configuration via SSH

# 4. Manual server configuration
make deploy-servers ARCH=<type>
```

---

## 💡 **Best Practices**

1. **Physical Hardware**: Always provide real MAC addresses for ZTP
2. **NVIDIA Air**: Use auto-generated MACs
3. **Testing**: Use auto-generated MACs initially, replace with real MACs later
4. **Documentation**: Keep a spreadsheet of switch hostnames and MACs
5. **Reconfiguration**: If MACs change, update the Excel Nodes tab and rerun `make generate` then `make ztp-update`

---

## 📚 **Related Documentation**

- **ZTP Setup**: `docs/MULTI_INTERFACE_ZTP.md`
- **Playbooks**: `playbooks/README.md`

---

**Last Updated**: 2025-11-12

