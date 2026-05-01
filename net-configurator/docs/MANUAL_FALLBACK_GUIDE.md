<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Manual Fallback Deployment Guide

Step-by-step procedure for deploying ERA in NVIDIA Air **without using the Air API**.

### When to use this guide

Pick the manual fallback when any of the following apply:

- The Air API is down, rate-limiting you, or returning 5xx errors
- You don't have an Air API key (but do have a regular Air login)
- `make air-deploy` fails partway through and you need finer control
- You're running in a restricted environment where outbound API calls are blocked
- You want to watch each step of the deployment and intervene if needed

If `make deploy` works end-to-end for you, use it — it's faster and has fewer
moving parts. This guide exists for when it doesn't.

## Overview

Instead of using the API to create simulations and inject Node Instructions
programmatically, this procedure:

1. Generates everything on your local machine
2. Uses the Air **web GUI** to upload the topology and paste Node Instructions
   for three infrastructure nodes
3. Runs Ansible **from inside the simulation** (on `dhcp-oob`) to configure
   ZTP services and servers — no SSH tunneling bottleneck

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────────────────┐
│  Local Machine  │     │   Air GUI    │     │  Inside Simulation       │
│                 │     │              │     │                          │
│  make generate  │────▶│  Upload      │────▶│  dhcp-oob runs Ansible   │
│  (emits topo +  │     │  topology +  │     │  ├─ make ztp-setup       │
│   3 Node        │     │  paste 3     │     │  ├─ (switches ZTP)       │
│   Instruction   │     │  Node        │     │  └─ make deploy-servers  │
│   scripts)      │     │  Instructions│     │                          │
└─────────────────┘     └──────────────┘     └──────────────────────────┘
```

`make generate` runs the whole local pipeline: Excel → inventory → NVUE
configs → topology JSON → Node Instruction scripts. There is no separate
target for the scripts — they come out as part of `generate`.

### Why Run Ansible from dhcp-oob?

The standard `deploy-servers-via-jump` tunnels all SSH through `oob-server-01`,
which can only handle ~3 concurrent connections. With 14+ servers, connections
get dropped. Running Ansible directly from `dhcp-oob` — which is on the same
OOB network as all servers — eliminates the bottleneck entirely.

---

## Prerequisites

**On your local machine:**

- This repository cloned
- **Python 3.12+** (Ubuntu 22.04's default Python 3.10 is not enough — use `deadsnakes` PPA or a similar source)
- `pip install -r requirements.txt` completed successfully
- A filled-out Excel configuration file
- A valid Air account at https://air-ngc.nvidia.com — request access from your NVIDIA contact if you don't have one
- An SSH key registered in Air (see [AIR_DEPLOYMENT_GUIDE.md](AIR_DEPLOYMENT_GUIDE.md#step-4-register-your-ssh-key-in-air))

**On dhcp-oob** (after the sim boots — the Node Instruction script installs these for you):

- `git`, `python3`, `python3-pip`, `python3-venv`
- Internet access via oob-server-01's NAT masquerade

**No Air API key required** for this flow.

---

## Phase 1: Generate on Your Local Machine

### 1.1 Import and Generate

```bash
# Import the Excel file (auto-detects architecture and site)
make import EXCEL=/path/to/your-config.xlsx

# Generate inventory + switch configs + topology + node instructions
make generate
```

This produces:
- `output/<arch>/<site>/inventory/` — Ansible inventory
- `output/<arch>/<site>/configs/` — switch NVUE config scripts
- `output/<arch>/<site>/topology/<arch>-topology.json` — Air topology
- `output/<arch>/<site>/topology/node-instructions/` — pasteable Node Instruction scripts

The node instructions are three bash scripts:

| Script | Node | What It Does |
|---|---|---|
| `topology/node-instructions/air-oob-switch.sh` | air-oob-switch | VLAN-aware bridge (NVUE commands) |
| `topology/node-instructions/oob-server-01.sh` | oob-server-01 | IP forwarding + static IPs + NAT masquerade |
| `topology/node-instructions/dhcp-oob.sh` | dhcp-oob | Static IPs + git/python/pip install |

Scripts are written to `output/<arch>/<site>/topology/node-instructions/`.

---

## Phase 2: Set Up the Air Simulation (GUI)

### 2.1 Create Simulation

1. Go to [air-ngc.nvidia.com](https://air-ngc.nvidia.com) and log in
2. Click **Create Simulation** → **Upload Topology**
3. Upload the topology JSON from `output/<arch>/<site>/topology/`
4. Name your simulation (e.g., `ERA-285-manual`)
5. Click **Create** — do **NOT** start the simulation yet

### 2.2 Add Node Instructions

**Before starting the simulation**, paste the Node Instruction script for each
infrastructure node. For each node:

1. Click the node in the simulation topology view
2. Go to **Node Instructions** → **Add Instruction**
3. Fill out the form with these **exact settings**:
   - **Name**: a short label (e.g., `oob-bridge-setup`, `oob-server-nat`, `dhcp-oob-init`)
   - **Type**: **Shell** (default is often `ansible` or `cloud-init` — change it to **Shell**)
   - **Wait for network**: **UNCHECK** this box (leaving it checked can hang boot if the node never gets DHCP; our scripts configure the network themselves)
   - **Instruction**: paste the full contents of the corresponding script from
     `output/<arch>/<site>/topology/node-instructions/`
4. Click **Save**

Add instructions for all three nodes:

| Order | Node | Suggested Name | Script to Paste |
|---|---|---|---|
| 1 | **air-oob-switch** | `oob-bridge-setup` | `topology/node-instructions/air-oob-switch.sh` |
| 2 | **oob-server-01** | `oob-server-nat` | `topology/node-instructions/oob-server-01.sh` |
| 3 | **dhcp-oob** | `dhcp-oob-init` | `topology/node-instructions/dhcp-oob.sh` |

> **Important**: Node Instructions must be added **before** starting the simulation.
> Once started, you cannot inject new ones.
>
> **Double-check each instruction**:
> - Type is **Shell** (not ansible/cloud-init)
> - **Wait for network** is **unchecked**
> - Name is set (Air rejects unnamed instructions)

### 2.3 Start Simulation

Click **Start**. Wait for all nodes to show as **Running** (typically 2–3 minutes).

The Node Instructions will execute automatically on boot:
- `air-oob-switch` configures the VLAN bridge (~30 seconds)
- `oob-server-01` sets up gateway routing and NAT (~1 minute)
- `dhcp-oob` configures networking and installs prerequisites (~2–3 minutes)

---

## Phase 3: Run Ansible from dhcp-oob

### 3.1 Access dhcp-oob

**Option A: Air Console** (simplest)

Click **dhcp-oob** in the Air GUI → **Console**. Log in with `ubuntu` / `nvidia`.

**Option B: SSH Service**

1. Click **dhcp-oob** → **Services** → **Add Service**
2. Service Type: **SSH**, Internal Port: **22**
3. Note the external hostname and port
4. SSH in: `ssh -p <port> ubuntu@<hostname>` (password: `nvidia`)

### 3.2 Clone the Repository

```bash
git clone <your-repo-url> era-automation
cd era-automation
```

### 3.3 Set Up the Python Environment

Air's dhcp-oob VM runs **Ubuntu 22.04**, which ships with **Python 3.10**.
Our `requirements.txt` pins `ansible>=13.5.0`, which requires **Python 3.12+**.
Trying to `pip install` on Python 3.10 fails with:

```
ERROR: Could not find a version that satisfies the requirement ansible>=13.5.0
```

**Install Python 3.12 from deadsnakes first**, then build the venv with it:

```bash
# 1. Add the deadsnakes PPA and install 3.12 + venv support
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv

# 2. Verify
python3.12 --version     # expect: Python 3.12.x

# 3. Create the venv with 3.12 (NOT python3 / NOT with sudo — you want the
#    venv owned by ubuntu, otherwise `pip install` later hits permission
#    errors and ansible-playbook from within the venv gets weird failures)
python3.12 -m venv .venv
source .venv/bin/activate

# 4. Verify you're in the 3.12 venv, then install deps
python --version         # expect: Python 3.12.x
pip install --upgrade pip
pip install -r requirements.txt

# 5. Sanity check
ansible --version        # expect: ansible [core 2.20+]
```

> **If `add-apt-repository` fails** with "Unable to fetch" or similar, dhcp-oob
> can't reach the internet yet. That means `oob-server-01`'s Node Instruction
> didn't set up NAT masquerade. Fix `oob-server-01` first (see Troubleshooting
> below), then retry.
>
> **If you see `software-properties-common: command not found`** when running
> `add-apt-repository`, install it: `sudo apt-get install -y software-properties-common`.

### 3.4 Import the Excel File

You need to get the Excel file onto dhcp-oob. Options:

**Option A: SCP from your local machine** (if you set up an SSH service)

```bash
# From your local machine:
scp -P <port> /path/to/config.xlsx ubuntu@<hostname>:~/era-automation/
```

**Option B: Download from a URL** (if hosted somewhere accessible)

```bash
curl -o config.xlsx <url>
```

**Option C: Copy-paste via Air Console** (for small changes, re-fill the template)

Then import and generate:

```bash
make import EXCEL=config.xlsx
make generate
```

### 3.4.1 Fix `ansible_host` for dhcp-oob and oob-server-01

**Required — will not work without this.**

The Excel parser emits `ansible_host` values intended for the *laptop-plus-API* flow:
external Air SSH jump hostnames (or literal `change_me` placeholders) for
`dhcp-oob` and `oob-server-01`. From inside the sim, those routes either
don't exist or are Connection-Refused. You have to override both host_vars
files to use internal addressing before running any Ansible command.

**Note on pasting**: Air's console / some SSH clients add leading spaces to
multi-line pastes, which produces invalid YAML. The snippets below use
base64-encoded single-line commands to avoid that trap. Copy each `echo | base64 -d` as
a single line.

```bash
# dhcp-oob → connect locally (no SSH to itself)
echo 'LS0tCmFuc2libGVfaG9zdDogMTI3LjAuMC4xCmFuc2libGVfY29ubmVjdGlvbjogbG9jYWwKaG9zdG5hbWU6IGRoY3Atb29iCmFuc2libGVfdXNlcjogdWJ1bnR1Cg==' | base64 -d > output/<arch>/<site>/inventory/host_vars/dhcp-oob.yml

# oob-server-01 → reach via its eth1 on the air-mgmt network (172.20.0.0/24)
echo 'LS0tCmFuc2libGVfaG9zdDogMTcyLjIwLjAuMQpob3N0bmFtZTogb29iLXNlcnZlci0wMQphbnNpYmxlX3VzZXI6IHVidW50dQpvb2Jfc2VydmVyX2ludGVyZmFjZXM6Ci0gbmFtZTogZXRoMQogIGlwOiAxNzIuMjAuMC4xCiAgbmV0bWFzazogMjQKICBuZXR3b3JrOiAxNzIuMjAuMC4wLzI0CiAgcHVycG9zZTogQWlyIE1hbmFnZW1lbnQgR2F0ZXdheQotIG5hbWU6IGV0aDIKICBpcDogMTkyLjE2OC4yMDAuMQogIG5ldG1hc2s6IDI0CiAgbmV0d29yazogMTkyLjE2OC4yMDAuMC8yNAogIHB1cnBvc2U6IE9PQiBNZ210IFN1Ym5ldCAxIEdhdGV3YXkK' | base64 -d > output/<arch>/<site>/inventory/host_vars/oob-server-01.yml

# Verify — both should print "---$" with no leading whitespace
head -1 output/<arch>/<site>/inventory/host_vars/dhcp-oob.yml | cat -A
head -1 output/<arch>/<site>/inventory/host_vars/oob-server-01.yml | cat -A
```

**What each base64 blob decodes to** (the reference content for the
**default** subnets — `192.168.200.0/24` OOB, `172.20.0.0/24` air-mgmt):

```yaml
# dhcp-oob.yml
---
ansible_host: 127.0.0.1        # always 127.0.0.1 — we run Ansible on this host
ansible_connection: local      # skip SSH entirely
hostname: dhcp-oob
ansible_user: ubuntu
```

```yaml
# oob-server-01.yml
---
ansible_host: 172.20.0.1       # oob-server-01's eth1 (Air-mgmt gateway)
hostname: oob-server-01
ansible_user: ubuntu
oob_server_interfaces:
- name: eth1
  ip: 172.20.0.1               # Air-mgmt gateway — almost always 172.20.0.1
  netmask: 24
  network: 172.20.0.0/24
  purpose: Air Management Gateway
- name: eth2
  ip: 192.168.200.1            # OOB subnet gateway — change if you customized
  netmask: 24                  # the OOB subnet in Excel
  network: 192.168.200.0/24    # OOB subnet itself — change if customized
  purpose: OOB Mgmt Subnet 1 Gateway
```

#### If you customized subnets in Excel

The base64 blobs above assume the **default** subnets. If your Excel
changes the OOB subnet (Settings tab, `mgmt_subnet_1` field) or adds
additional mgmt subnets, the `eth2` entry in `oob-server-01.yml` must
match. To find the correct values, inspect what the parser generated
*before* you overwrite it:

```bash
# What subnets did the parser think we have?
grep -A 20 "^mgmt_subnets\|^ztp_interfaces" \
  output/<arch>/<site>/inventory/group_vars/all/main.yml

# What did the parser originally put in oob-server-01.yml?
# (still has `oob_server_interfaces` even though ansible_host is wrong)
cat output/<arch>/<site>/inventory/host_vars/oob-server-01.yml
```

Then hand-edit `oob-server-01.yml` instead of base64-pasting. Keep the
structure exactly as shown above, just swap IPs / networks / netmasks
to match your deployment. Rules of thumb:

- `eth1` is **always** `172.20.0.1/24` (Air's internal management
  network; not user-configurable — determined by Air's topology template)
- `eth2` (and `eth3`, `eth4`, ... if you have multiple OOB subnets) must
  match the `mgmt_subnets` list from `group_vars/all/main.yml`
- The `ansible_host` at the top should match **eth1** (172.20.0.1) —
  that's the IP dhcp-oob uses to reach oob-server-01 over the air-mgmt
  network
- `ansible_user` is always `ubuntu` for Air; on physical hardware it
  matches whatever the host OS uses

For `dhcp-oob.yml`, the content never changes regardless of subnets —
we always connect locally (127.0.0.1 via `ansible_connection: local`).

> If you re-run `make generate`, these host_vars files will be overwritten
> with the external hostnames again — re-run the `echo | base64 -d`
> commands (or re-do your hand-edits) any time you regenerate.

### 3.4.2 Install and trust your SSH key for Ansible

Ansible on dhcp-oob will SSH to `oob-server-01` (and later to each server).
Give it a key so it isn't prompted for passwords:

```bash
# Create a key if you don't have one
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519

# Push it to oob-server-01 (password: nvidia)
ssh-copy-id -o StrictHostKeyChecking=no ubuntu@172.20.0.1

# Smoke test — should print "oob-server-01" without prompting for a password
ssh -o StrictHostKeyChecking=no ubuntu@172.20.0.1 hostname
```

### 3.5 Configure ZTP Server (on dhcp-oob itself)

This configures dnsmasq (DHCP) and nginx (config file hosting) on the machine
you're currently on:

```bash
# Air VMs have passwordless sudo — press Enter at the become password prompt
make ztp-setup
```

> **Note**: When Ansible asks for the "BECOME password", just press **Enter**
> (Air Ubuntu VMs have NOPASSWD sudo). Alternatively, skip the prompt:
> ```bash
> ansible-playbook playbooks/setup-ztp-server.yml \
>   -i output/<arch>/<site>/inventory/hosts \
>   -e "config_output_dir=../output/<arch>/<site>/configs" \
>   -e "ansible_become_password="
> ```

### 3.6 Trigger ZTP on Switches

Switches need to be told to provision. Use the Air GUI console for each switch:

1. Click on the switch (e.g., `core-01`) → **Console**
2. Log in with `cumulus` / `Cumu1usLinux!`  (note: digit `1`, not letter `l`)
3. Run: `sudo ztp -r`

Repeat for all switches: `core-01`, `core-02`, `oob-switch-01`, `oob-switch-02`
(and `oob-switch-03` if applicable).

Alternatively, power-cycle each switch via the Air GUI (**Power Off** → **Power On**).
ZTP runs automatically on boot.

> **Be patient.** Allow **15–20 minutes** for all switches to download configs,
> apply them, and reboot.

### 3.7 Deploy Server Configurations

Once switches have finished ZTP, configure the servers (hostname, netplan, LLDP):

```bash
# Direct SSH from dhcp-oob — no tunneling needed
make deploy-servers
```

> Press **Enter** at the become password prompt (same as above).

### 3.8 Validate

```bash
# Full validation suite
make validate-all

# Optional: server-to-server ping matrix
make validate-ping-matrix
```

---

## Troubleshooting

### Node Instruction shows COMPLETE but the node has no config

Most common failure mode. Air reports "1 command will be run → State COMPLETE"
but the node has no static IPs, no hostname change, etc. Air doesn't surface
script errors — a failed script still shows COMPLETE.

**Diagnose**:

```bash
# On the affected node (via Air console), check cloud-init's log:
sudo tail -100 /var/log/cloud-init-output.log
sudo tail -100 /var/log/cloud-init.log

# Look for: "error", the first few bytes of our script's first echo, or nothing
# at all from our script (means it never ran).

# Confirm whether expected files exist:
ls /etc/netplan/                   # expect 01-ztp-interfaces.yaml or 01-oob-config.yaml
ip -br a                           # expect eth1/eth2 to have the IPs the script set
hostname                           # expect the script's hostname
```

**Common causes**:

1. **Type wasn't set to Shell** — Air defaulted to `ansible` or `cloud-init`,
   so the bash script was treated as something else and silently discarded.
   Edit the instruction and set **Type: Shell**.
2. **Wait for network was left checked** — Air waited for network that never
   came up (chicken-and-egg), timed out, marked COMPLETE, never ran the script.
   Uncheck it.
3. **Heredoc in the script** — our generator uses base64 encoding specifically
   because heredocs don't survive Air's shell executor. If you hand-edited the
   script and re-introduced a `cat > file << 'EOF'` block, regenerate with
   `make generate`.

**Recover**: fix the instruction settings (Type, Wait for network), then either
restart the sim or SSH into the node and run the script manually as root:

```bash
sudo bash <<'EOF'
# paste the full script contents here
EOF
```

### dhcp-oob can't reach the internet

The internet path is: dhcp-oob → oob-server-01 (NAT masquerade) → eth0 → outbound.
Check that oob-server-01's Node Instruction ran successfully:

```bash
# From dhcp-oob, check if oob-server-01 is reachable
ping -c 3 172.20.0.1      # air-mgmt gateway
ping -c 3 192.168.200.1   # OOB gateway

# If gateways respond but no internet, check NAT on oob-server-01
ssh ubuntu@192.168.200.1 "sudo iptables -t nat -L POSTROUTING -n"
```

### Switches don't get DHCP leases

Check dnsmasq is running on dhcp-oob:

```bash
sudo systemctl status dnsmasq
sudo cat /var/lib/misc/dnsmasq.leases
sudo journalctl -u dnsmasq -f   # watch for DHCP requests
```

### Servers unreachable from dhcp-oob

Servers should be on the OOB network (192.168.200.x). Check:

```bash
# Verify dhcp-oob is on the right network
ip addr show eth2

# Check if servers are up and have IPs
ping 192.168.200.101   # first server's expected IP
```

If servers have no management IP, they need ZTP/DHCP on the OOB network. Check
that oob-server-01 is routing between subnets.

### Ansible asks for SSH password

Air VMs use `ubuntu` / `nvidia` by default. You can set this in the inventory
secrets file:

```bash
cat output/<arch>/<site>/inventory/group_vars/all/secrets.yml
# Should contain: server_ansible_password: "nvidia"
```

---

## Quick Reference

```bash
# === Phase 1: Local machine ===
make import EXCEL=/path/to/config.xlsx
make generate    # produces topology + node instructions

# === Phase 2: Air GUI ===
# Upload topology, paste 3 Node Instructions, start simulation

# === Phase 3: On dhcp-oob ===
git clone <repo-url> era-automation && cd era-automation

# Install Python 3.12 (Ubuntu 22.04 ships 3.10, Ansible 13+ needs 3.11+)
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update && sudo apt-get install -y python3.12 python3.12-venv

python3.12 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt

make import EXCEL=config.xlsx
make generate

# REQUIRED: override dhcp-oob + oob-server-01 host_vars for internal addressing
# (replace <arch>/<site> with your values, e.g. 2-8-5-200/default)
echo 'LS0tCmFuc2libGVfaG9zdDogMTI3LjAuMC4xCmFuc2libGVfY29ubmVjdGlvbjogbG9jYWwKaG9zdG5hbWU6IGRoY3Atb29iCmFuc2libGVfdXNlcjogdWJ1bnR1Cg==' | base64 -d > output/<arch>/<site>/inventory/host_vars/dhcp-oob.yml
echo 'LS0tCmFuc2libGVfaG9zdDogMTcyLjIwLjAuMQpob3N0bmFtZTogb29iLXNlcnZlci0wMQphbnNpYmxlX3VzZXI6IHVidW50dQpvb2Jfc2VydmVyX2ludGVyZmFjZXM6Ci0gbmFtZTogZXRoMQogIGlwOiAxNzIuMjAuMC4xCiAgbmV0bWFzazogMjQKICBuZXR3b3JrOiAxNzIuMjAuMC4wLzI0CiAgcHVycG9zZTogQWlyIE1hbmFnZW1lbnQgR2F0ZXdheQotIG5hbWU6IGV0aDIKICBpcDogMTkyLjE2OC4yMDAuMQogIG5ldG1hc2s6IDI0CiAgbmV0d29yazogMTkyLjE2OC4yMDAuMC8yNAogIHB1cnBvc2U6IE9PQiBNZ210IFN1Ym5ldCAxIEdhdGV3YXkK' | base64 -d > output/<arch>/<site>/inventory/host_vars/oob-server-01.yml

# Push SSH key to oob-server-01 (password: nvidia)
[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519
ssh-copy-id -o StrictHostKeyChecking=no ubuntu@172.20.0.1

make ztp-setup              # DHCP + nginx on this host
# Trigger ZTP on switches via Air console: sudo ztp -r
# Wait 15-20 minutes for switches to configure
make deploy-servers         # direct SSH to all servers
make validate-all           # full validation
```
