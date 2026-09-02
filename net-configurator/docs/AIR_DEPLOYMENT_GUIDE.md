<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# NVIDIA Air Deployment Guide

Step-by-step instructions for deploying ERA switch configurations in NVIDIA Air simulations.

## Prerequisites

- This repository cloned to your local machine
- Ansible installed locally (`pip install ansible`)
- Python 3 with openpyxl, httpx, rich (`pip install openpyxl httpx rich`)
- An SSH key pair (see Step 3 below)

---

## Getting Started

### Fastest Path

The Excel template contains no Air credentials or URLs — everything Air-specific
lives in the shared vault. You configure it once per checkout:

1. Run the one-time wizard: `make air-setup` — it prompts for your NGC API key,
   which Air instance to use (public `dsx-air` vs. internal `inside.dsx-air`), and your
   SSH key path, then vault-encrypts everything to `.era-secrets/air-secrets.yml`
   (inside this repo, gitignored)
2. Run:

```bash
# Standard deployment (switches + servers, servers auto-configured on boot)
make deploy EXCEL=/path/to/your-config.xlsx

# Or: switches only (server VMs still in sim, configured separately afterwards)
make deploy-exclude-servers EXCEL=/path/to/your-config.xlsx

# Or: switches-ONLY / no-ZTP (server VMs omitted entirely — smaller/cheaper sim)
make deploy-switches-only EXCEL=/path/to/your-config.xlsx
```

`make deploy` runs the full pipeline — switches are configured via ZTP, and server
configuration (hostname, netplan, lldp) is injected as Air Node Instructions so
servers are fully configured on first boot. No separate server deployment step needed.

`make deploy-exclude-servers` skips the server Node Instructions (the server VMs
are still created). Run `make deploy-servers-via-jump` afterwards to configure them.

### Switches-only / no-ZTP deployments

`make deploy-switches-only EXCEL=<file>` (or, ARCH/SITE-driven,
`make air-deploy-switches-only ARCH=<a> SITE=<s>` once the site's Excel is
imported) builds a **switches-only** sim: the server VMs are dropped entirely, so
the sim is far smaller and cheaper — the budget-friendly way to validate a large
switch fabric. The **full switch configuration still applies**; each server-facing
port is kept as an `unconnected` topology stub so the NVUE apply never rolls back
(Air rolls back the *whole* apply if a config references a missing port).

What it proves vs. omits, and how to validate:

- **Validate with** `make validate-all` — the **Servers** phase is auto-reported
  `➖ N/A (switches-only)`; Topology, Config, ZTP, and **Switch Health**
  (clean apply + BGP Established + EVPN ES/VNI) still run.
- Or run the targeted fabric-health layer alone: `make validate-switch-health`.
- Server-edge data-plane (EVPN-MH bonds, server NIC/netplan) is **not** exercised
  — that needs a full sim (`make deploy`) or bare metal.

```bash
make deploy-switches-only EXCEL=/path/to/your-config.xlsx
make validate-all SKIP_UPLOAD=1          # Servers => N/A; everything else runs
```

The detailed steps below are for understanding the process or troubleshooting.

### Step 1: Create an NGC Account

NVIDIA Air uses NGC (NVIDIA GPU Cloud) for authentication.

1. Go to [ngc.nvidia.com](https://ngc.nvidia.com/signin)
2. Sign up with a **business email address** (personal email like gmail.com will not work)
3. Follow the prompts to create your NVIDIA Cloud Account (NCA) and join or create an organization

### Step 2: Get Air Access

1. Go to [org.ngc.nvidia.com/users](https://org.ngc.nvidia.com/users)
2. Select your user and click **Edit membership**
3. Set the role context to **Organization**
4. Assign one of these roles:
   - **Air User** — standard access (recommended)
   - **Air Org Admin** — full administrative access
5. Verify access by logging in to [dsx-air.nvidia.com](https://dsx-air.nvidia.com)
   - Enter your business email, select your NGC organization
   - You should see the Air dashboard

> **Note**: Organization owners get an automatic trial: 60 concurrent vCPUs, 60 GiB memory, 10,000 compute hours for one year.

### Step 3: Create an SSH Key Pair (if you don't have one)

The Air deploy script distributes your SSH public key to all nodes in the simulation, enabling passwordless access.

```bash
# Generate an ed25519 key (recommended)
ssh-keygen -t ed25519 -C "your-email@company.com"

# Or check if you already have one
ls ~/.ssh/id_ed25519.pub
```

### Step 4: Register Your SSH Key in Air

1. Log in to [dsx-air.nvidia.com](https://dsx-air.nvidia.com)
2. Click your **username** in the top right corner
3. Select **Settings**
4. Under **SSH Keys**, click **Add**
5. Paste the contents of your public key file (`~/.ssh/id_ed25519.pub`)
6. Give it a descriptive name (e.g., `my-workstation`) and save

> **Why?** Air uses this key to allow SSH access to `oob-mgmt-server` (the platform jump host). The ERA deploy script also embeds this key into all simulation nodes via ZTP and cloud-init.

### Step 5: Generate an NGC API Key

1. Go to [org.ngc.nvidia.com/account/api-keys](https://org.ngc.nvidia.com/account/api-keys)
2. **Check the account selector in the top-right corner** and make sure you're on the correct NGC account before generating the key
3. Click **Generate Personal Key**
   - (For shared/CI use, choose **Generate Service Key** instead)
4. Fill in:
   - **Key Name**: a descriptive name (e.g., `net-configurator`)
   - **Services Included**: select **NVIDIA Air** from the list
   - **Expiration**: set as appropriate for your use case
5. Click **Generate**
6. **Copy the key immediately** — NGC will not show it again after you leave this page. The value starts with `nvapi-`.

> **Personal Key vs Service Key**: Personal keys are tied to your user account. Service keys are tied to the NGC organization and are better for automation or shared use. Either works with ERA, but most users should choose Personal Key.

### Step 6: Add Air Credentials

Air credentials and the Air instance URL live in a **shared vault** at
`.era-secrets/air-secrets.yml` inside this repo (vault-encrypted, gitignored).
Every arch/site in this checkout reads from that single file.

Loader precedence (first match wins):

| Priority | Source | When to use |
|----------|--------|-------------|
| 1 | Environment variables (`AIR_API_KEY`, `AIR_BASE_URL`, `AIR_USERNAME`, `AIR_SSH_KEY_PATH`) | CI/CD pipelines, one-off overrides |
| 2 | Shared vault (`.era-secrets/air-secrets.yml`) | Everyday use — set once via `make air-setup` |

Run the wizard:

```bash
make air-setup
```

It prompts for:
- **NGC API key** (pasted once, masked on re-entry)
- **Air instance** — `[1]` Public Air (`https://dsx-air.nvidia.com`),
  `[2]` Internal (`https://inside.dsx-air.nvidia.com`, reachable only from
  inside NVIDIA — external users want `[1]`), or
  `[3]` a custom URL. Use the web UI URL you see in your browser; the automation
  maps it to the correct API host automatically (e.g., `dsx-air.nvidia.com` →
  `api.dsx-air.nvidia.com`).
- **Username** — leave blank for NGC Air 2.0 (bearer token); fill for legacy Air
- **SSH key path** — auto-detects `~/.ssh/id_ed25519`, `id_rsa`, `id_ecdsa`, or
  offers to generate a new ed25519 key

Re-run the wizard any time to update one or more fields; existing values are
preserved for fields you don't change.

**Clearing an optional field.** The optional fields — **Username** and **NGC
org** — can be emptied again once set. Press Enter at the prompt and confirm:

```
  NGC org (blank = clear) [myorg]:
  ⚠️  Clear the existing NGC org "myorg"?  [y/N]
  > y
```

The confirmation defaults to **No**, so Enter-ing straight through a re-run
never discards a working setting. This matters for **NGC org**: a stale value is
sent as the `nv-ngc-org` header on every Air API call, and a gateway that does
not expect it answers **403 Forbidden** on operations like listing simulations
or checking the resource budget. If you hit unexplained 403s, clear the org and
retry — most gateways (including inside.dsx-air) accept bearer-only requests.

### Step 7: Verify Credentials

You can test credentials immediately — even before importing an Excel file:

```bash
make air-auth-test ARCH=2-8-5-200
```

This tests API connectivity, authentication, and budget, and prints the fingerprint of your local SSH key so you can confirm it matches the key registered in Air (Settings → SSH Keys). Note it does *not* verify registration for you — that check is manual. The `ARCH` parameter is used to load the Air URL from the per-deployment inventory; credentials themselves come from the shared vault, so this works even before any inventory exists.

### Step 8: Import Your Excel File

```bash
make import EXCEL=/path/to/your-config.xlsx
```

The import script reads `architecture` and `site_name` from the Settings tab, then copies the file to `input/<arch>/<site>/<arch>.xlsx` and sets `.era-context` so subsequent commands work without parameters.

> **Note**: If `site_name` is set in the Excel (e.g., `acme-lab`), the file goes to `input/<arch>/acme-lab/`. If `site_name` is empty, it defaults to `default`. You can override with `make import EXCEL=... SITE=my-name`.

### Step 9: Generate Configs and Topology

```bash
make generate
```

This runs five steps:
1. Excel → Ansible inventory (`output/<arch>/<site>/inventory/`)
2. Inventory → NVUE CLI switch config scripts (`output/<arch>/<site>/configs/`)
3. Excel Wire Map → Air topology JSON (`output/<arch>/<site>/topology/`)
4. Node Instruction scripts for the manual-fallback / NOZTP path (`output/<arch>/<site>/topology/node-instructions/`)
5. Cross-check that netplan and topology eth-numbering agree

### Step 10: Deploy to Air

**One-command option (preferred):** If you started from `make import`, you can run the
entire pipeline -- generate, Air deploy, and ZTP -- in a single command:

```bash
make deploy EXCEL=/path/to/your-config.xlsx
```

**Or step by step:**

```bash
# Create the Air simulation and configure SSH access
make air-deploy

# Verify SSH access to jump hosts (recommended before ZTP)
make air-ssh-check

# Push switch configs via ZTP
make switch-ztp-deploy
```

**Or the full pipeline without re-importing:**

```bash
make air-full-deploy
```

`make air-deploy` will:
1. Import the topology JSON into Air and create a simulation
2. Install your SSH key on all nodes (ZTP for Cumulus switches, cloud-init for Ubuntu servers)
3. Start the simulation and wait for it to boot (~2-10 minutes)
4. Create SSH services on the jump hosts
5. Auto-update `host_vars` with the worker hostname and SSH ports

> **OOB mode & jump host — L3 is the default.** In the default **L3** OOB mode
> the management nodes are `utility` (the Ansible `[jump]` host) + `external-conn`
> + `external-dhcp`. Some steps below still reference the older **L2** node names
> `oob-server-01` / `dhcp-oob` — those apply only when `oob_uplink_mode=l2`; in
> the default L3 mode read `oob-server-01` → **`utility`** and `dhcp-oob` →
> **`external-dhcp`**.

> **Note**: After `make import` sets `.era-context`, you don't need to pass `ARCH=` to every command.

### Troubleshooting SSH Access

If `make switch-ztp-deploy` fails with SSH errors, or if you're using an NGC **Service API key** (rather than a personal key), run:

```bash
# Diagnose SSH access (checks key auth + password auth)
make air-ssh-check

# Auto-fix: inject your SSH key into jump hosts via password auth
make air-ssh-check FIX=1
```

The check verifies:
- SSH key path is configured and the key file exists
- Key is loaded in ssh-agent (required for passphrase-protected keys)
- SSH key auth works against the jump host (`utility` in L3 mode; `oob-server-01` / `dhcp-oob` in legacy L2)
- Password auth works (Ansible fallback via `ansible_password`)
- **`sshpass` is installed on the jump host itself** — Ansible hops
  jump-host → switch, and that second hop needs its own `sshpass`. Air's
  image does not ship one. `FIX=1` installs it.

**Reading a failure**: the check now names the failing host and prints the
underlying `ssh` exit code and stderr. A credential problem is only reported
as one when `sshpass` actually returned exit 5 — a dropped connection (exit
255) is reported as a connection fault on that host, not as a bad password.

**Passphrase-protected keys**: If your SSH key has a passphrase, load it into the agent first:

```bash
eval $(ssh-agent) && ssh-add ~/.ssh/id_ed25519
```

### Step 11: Manage Your Simulation

```bash
make air-list              # List simulations with SSH info
make air-budget            # Check resource budget
make air-ssh-check         # Check SSH key/password auth to jump hosts
make air-ssh-check FIX=1   # Auto-inject SSH key if auth fails
make air-destroy           # Teardown + cleanup
```

---

## Quick Reference Table

| Step | What | Where |
|------|------|-------|
| 1 | NGC account | [ngc.nvidia.com](https://ngc.nvidia.com/signin) (business email) |
| 2 | Air role | [org.ngc.nvidia.com/users](https://org.ngc.nvidia.com/users) → assign "Air User" |
| 3 | SSH key pair | `ssh-keygen -t ed25519` (if needed) |
| 4 | Register SSH key in Air | [dsx-air.nvidia.com](https://dsx-air.nvidia.com) → Settings → SSH Keys |
| 5 | NGC API key | [org.ngc.nvidia.com/account/api-keys](https://org.ngc.nvidia.com/account/api-keys) → confirm account in top-right → **Generate Personal Key** (value starts with `nvapi-`) |
| 6 | Air instance picked | `make air-setup` prompt → stored in shared vault |
| 7 | Credentials | `make air-setup` → wizard vaults your NGC API key |
| 8 | Verify | `make air-auth-test ARCH=...` (works before import/generate) |
| 9 | Import | `make import EXCEL=...` (reads arch + site from Excel) |
| 10 | Generate | `make generate` (uses .era-context from import) |
| 11 | Deploy | `make air-deploy` then `make air-ssh-check` then `make switch-ztp-deploy` |
| 12 | Manage | `make air-list`, `make air-ssh-check`, `make air-destroy` |

---

## Manual Workflow (Fallback)

If you prefer not to use the API, or if the automated workflow encounters issues, follow these manual steps.

> **Alternative: Run Ansible from inside the simulation.** For a procedure that
> avoids SSH tunneling entirely — by cloning the repo on `dhcp-oob` and running
> Ansible directly on the OOB network — see [MANUAL_FALLBACK_GUIDE.md](MANUAL_FALLBACK_GUIDE.md).
> `make generate` produces pasteable Node Instruction scripts for the three
> infrastructure nodes, then you run `make ztp-setup` and `make deploy-servers`
> from `dhcp-oob` with direct connectivity to all hosts.

### Step 1: Prepare Your Configuration

### 1.1 Get the Template

Every architecture ships a committed default template and ready-to-use samples
in the repo. Use whichever matches your target:

| Purpose | Path |
|---|---|
| Default template (per arch) | `input/{ARCH}/default/{ARCH}.xlsx` |
| Ready-to-use sample (default scale) | `input/sample-{ARCH}.xlsx` |
| Ready-to-use sample (largescale) | `input/largescale-{ARCH}.xlsx` |

Replace `{ARCH}` with one of: `2-4-3-200`, `2-4-5-400`, `2-8-5-200`,
`2-8-9-400`, `2-4-5-800`, `2-8-9-800`, `2-8-9-400-SP`. (When you import to a named site,
the working copy lands at `input/{ARCH}/{SITE}/{ARCH}.xlsx`.)

### 1.2 Fill Out the Excel

Key tabs:

| Tab | What to fill in |
|---|---|
| **Settings** | `site_name`, BGP ASN, management subnets, LDAP on/off |
| **VLANs & Profiles** | VLAN IDs, names, port profiles, port speeds |
| **Wire Map** | Server-to-switch cabling (per node) |

### 1.3 Import the Excel

```bash
make import EXCEL=/path/to/your-config.xlsx
```

This reads `architecture` and `site_name` from the Settings tab, creates `input/<arch>/<site>/`, copies the file there, and writes `.era-context` so all subsequent `make` commands work without parameters.

> **Tip**: You can also drop the file directly in `input/` as a staging area — it's gitignored at that level.

---

## Step 2: Create Air Simulation (Manual)

> **Note**: If you used `make air-deploy`, skip to Step 5. The deploy script handles Steps 2-4 automatically.

### 2.1 Access NVIDIA Air

Go to [dsx-air.nvidia.com](https://dsx-air.nvidia.com) and log in.

### 2.2 Create New Simulation

1. Click **Create Simulation** → **Upload Topology**
2. Choose the topology file for your architecture:

| Architecture | Topology File |
|---|---|
| `2-4-3-200` | `output/2-4-3-200/<site>/topology/2-4-3-200-topology.json` |
| `2-8-5-200` | `output/2-8-5-200/<site>/topology/2-8-5-200-topology.json` |
| `2-4-5-400` | `output/2-4-5-400/<site>/topology/2-4-5-400-topology.json` |
| `2-8-9-400` | `output/2-8-9-400/<site>/topology/2-8-9-400-topology.json` |
| `2-8-9-800` | `output/2-8-9-800/<site>/topology/2-8-9-800-topology.json` |

> **Note**: Topology files are auto-generated by `make generate`.

3. Give your simulation a name (e.g., `ERA-285-Acme-Lab`)
4. Click **Create**

### 2.3 Wait for Simulation to Start

All nodes will show as **Running** when ready (typically 2–3 minutes).

---

## Step 3: Add SSH Services

To run Ansible from your local machine you need SSH access to the two management servers. In Air, for each server:

### 3.1 oob-server-01

1. Click **oob-server-01** in the simulation
2. Go to the **Services** tab → **Add Service**
3. Service Type: **SSH**, Internal Port: **22**
4. Note the external hostname and port (e.g., `<air-host>:26788`)

### 3.2 dhcp-oob

1. Click **dhcp-oob** in the simulation
2. Go to the **Services** tab → **Add Service**
3. Service Type: **SSH**, Internal Port: **22**
4. Note the external hostname and port (e.g., `<air-host>:18252`)

### 3.3 Verify SSH Access

```bash
ssh -p 26788 ubuntu@<air-host>   # oob-server-01
ssh -p 18252 ubuntu@<air-host>   # dhcp-oob
```

Default credentials: `ubuntu` / `nvidia`

---

## Step 4: Update Inventory

### 4.1 Configure oob-server-01

```bash
nano output/<arch>/<site>/inventory/host_vars/oob-server-01.yml
```

Update with your Air service details:

```yaml
ansible_host: <air-host>
ansible_port: 26788
ansible_user: ubuntu
ansible_password: "{{ server_ansible_password }}"
```

### 4.2 Configure dhcp-oob

```bash
nano output/<arch>/<site>/inventory/host_vars/dhcp-oob.yml
```

```yaml
ansible_host: <air-host>
ansible_port: 18252
ansible_user: ubuntu
ansible_password: "{{ server_ansible_password }}"
```

### 4.3 Verify Secrets

Check `output/<arch>/<site>/inventory/group_vars/all/secrets.yml`:

```yaml
server_ansible_password: "nvidia"     # Default Air password
ansible_become_password: "nvidia"
switch_ansible_password: "Cumu1usLinux!"
switch_password: "Cumu1usLinux!"
```

Update any passwords that differ from your environment.

---

## Step 5: Run Deployment

### Option A: One Command (Recommended)

```bash
make switch-ztp-deploy
# With LDAP:
make switch-ztp-deploy LDAP=1
```

This runs in sequence:
1. Configures `oob-server-01` as the gateway/router for OOB networks
2. *(optional)* Sets up LDAP server
3. Parses Excel → generates Ansible inventory under `output/<arch>/<site>/inventory/`
4. Generates NVUE CLI switch config scripts + Air topology
5. Configures `dhcp-oob` with dnsmasq (DHCP) + nginx (serves config files)

### Option B: Step by Step

```bash
make oob-setup        # Configure OOB server as gateway
make generate         # Generate switch configs + Air topology
make ztp-setup        # Setup ZTP server (DHCP + nginx)
```

### Option C: Deploy Server Configurations (Nodes, Storage, Support)

In Air, servers are on internal networks not directly reachable from your machine. Use the `via-server` variant which SSH-tunnels through the OOB jump host
(`utility` in L3 OOB, `oob-server-01` in legacy L2):

```bash
make deploy-servers-via-jump    # SSH through the OOB jump host
```

This requires `sshpass` on your local machine (`sudo apt install sshpass`).

> **Direct mode**: If running Ansible from inside the simulation, or if servers are directly reachable, use `make deploy-servers` instead.

---

## Step 6: Trigger ZTP on Switches

Each switch needs to be told to provision itself.

### Via Air Console

For each switch (`core-01`, `core-02`, `oob-switch-01`, etc.):

1. Click the switch in Air → **Console**
2. Run:

```bash
sudo ztp -r
```

### Via SSH (if accessible from dhcp-oob)

```bash
ssh cumulus@core-01 "sudo ztp -r"
ssh cumulus@core-02 "sudo ztp -r"
```

### Via Power Cycle

In Air: click the switch → **Power Off** → wait a few seconds → **Power On**. The switch will run ZTP automatically on boot.

---

## Step 7: Verify Deployment

> **Be patient.** After triggering ZTP, allow **up to 30 minutes** for all switches to
> download configs, apply them, and reboot. Cores are the long pole — measured in CI as
> still converging at the 10-minute mark on healthy runs — because a core applies
> roughly 1900 config lines against an OOB switch's ~280. Do not re-trigger ZTP or
> re-run deployment commands while this is in progress. You can monitor progress via
> the Air console (`cat /var/log/autoprovision` on each switch).
>
> With `NOZTP=1` this does not apply: config is pre-injected and applied on first
> boot, and switches are reachable in roughly **90 seconds**.

### Run Automated Validation (after ZTP completes)

```bash
make validate-all        # Full validation: topology + ZTP + config + servers
make validate-ping-matrix  # Optional: full server-to-server connectivity test
```

### Manual Checks

On `dhcp-oob`:

```bash
# Verify switches got DHCP leases
sudo cat /var/lib/misc/dnsmasq.leases

# Check which configs were downloaded
sudo tail -f /var/log/nginx/ztp-access.log
```

On each switch:

```bash
nv config show          # View applied configuration
nv show system hostname # Confirm hostname
nv show interface       # Check interface status
```

---

## GUI-Only Deployment (No ZTP)

If you want to test switch configs in Air without setting up the full ZTP infrastructure —
for example, a quick demo or config review — you can inject configs directly as
**Node Instructions** via the Air web GUI.

### When to Use This

- Quick config testing or demos
- You don't need server/infrastructure setup (DHCP, LDAP, OOB routing)
- You just want switches to boot with the correct NVUE configuration

### Prerequisites

Generate the topology and config files locally:

```bash
make generate ARCH=2-8-5-200
```

This produces:

| Output | Path |
|---|---|
| Topology JSON | `output/<arch>/<site>/topology/<arch>-topology.json` |
| Switch configs | `output/<arch>/<site>/configs/<switch>-config.sh` |

### Step 1: Upload Topology

1. Go to [dsx-air.nvidia.com](https://dsx-air.nvidia.com) and log in
2. Click **Create Simulation** → **Upload Topology**
3. Upload the topology JSON from `output/<arch>/<site>/topology/`
4. Name your simulation (e.g., `ERA-285-demo`)
5. Click **Create** — do **NOT** start the simulation yet

### Step 2: Add Node Instructions

**Before starting the simulation**, add a Node Instruction for each switch:

1. Click on a switch node (e.g., `core-01`)
2. Go to **Node Instructions** → **Add Instruction**
3. Open the matching config file from `output/<arch>/<site>/configs/` (e.g., `core-01-config.sh`)
4. Paste the full contents, then **append these two lines at the end**:

```bash
nv config apply -y
nv config save
```

> **Why?** The config scripts contain `nv set` commands but do not apply them — the ZTP
> pipeline normally handles that. When using Node Instructions, you must apply explicitly.

Repeat for each switch:

| Config File | Node |
|---|---|
| `core-01-config.sh` | core-01 |
| `core-02-config.sh` | core-02 |
| `oob-switch-01-config.sh` | oob-switch-01 |
| `oob-switch-02-config.sh` | oob-switch-02 |
| `oob-switch-03-config.sh` | oob-switch-03 (if applicable) |

> **Mapping is 1:1 by filename** — paste each `<name>-config.sh` into the node named
> `<name>`. The rows above are the collapsed-core archs (`2-4-3-200`, `2-8-5-200`,
> `2-8-9-400`). The dual-plane **`2-8-9-800`** has no `core` switches; instead match
> `csl-01`, `csl-02`, `gsl-plane1-01`, `gsl-plane1-02`, `gsl-plane2-01`,
> `gsl-plane2-02` (plus its two `oob-switch-*`). Just match each generated config
> file to the like-named node — `ls output/<arch>/<site>/configs/` lists them all.

### Step 3: Start Simulation

Click **Start**. Nodes will boot, and the Node Instructions will execute automatically.
Allow 3–5 minutes for switches to boot and apply configurations.

### Step 4: Verify

Open the console for any switch and check:

```bash
nv config show          # Should show your NVUE configuration
nv show interface       # Check interface status
nv show router bgp      # Check BGP sessions
```

### Limitations

- **Switches only** — servers, DHCP, LDAP, and OOB routing are NOT configured.
  Nodes like `oob-server-01` and `dhcp-oob` will boot with default settings.
- **No ZTP server** — if a switch is reset, it won't auto-reprovision.
  You would need to re-apply the Node Instruction or re-create the simulation.
- **No server networking** — compute, storage, and support nodes won't have
  bonding, netplan, or data-plane IP configs.
- **Manual per-switch** — you must paste each config individually. For many
  switches this is tedious; use the automated pipeline (`make deploy`) instead.

For a complete deployment including infrastructure, use the
[automated workflow](#getting-started) or the
[manual workflow with ZTP](#manual-workflow-fallback).

---

## Understanding the Air Topology — Virtual vs. Physical Nodes

When you look at an ERA simulation in NVIDIA Air, you will see nodes that do **not**
correspond to hardware you need to purchase. These are virtual infrastructure nodes
that exist only in the simulation to represent OOB management services that are
outside the scope of the ERA reference architecture.

### Virtual Nodes (simulation only)

| Node | What It Represents | Why It Exists |
|---|---|---|
| **air-oob-switch** | The customer's existing OOB management infrastructure (top-of-rack switches, management LAN, etc.) | ERA does not specify what OOB infrastructure the customer uses — it could be an existing campus network, a separate management switch stack, or a direct connection. In Air, we need *something* to provide L2 connectivity between OOB switches, the ZTP server, and switch management ports. `air-oob-switch` fills that role as a simple VLAN-aware bridge. **It is not a device you buy.** |
| **dhcp-oob** | A DHCP/ZTP server that provisions switches on first boot | Runs dnsmasq (DHCP) and nginx (config file hosting). In production, this could be any server or VM on the customer's OOB network. In Air, it is auto-created as an Ubuntu node. |
| **oob-server-01** (legacy L2; `utility` in L3 OOB) | The management gateway / jump host for the OOB network | Provides routing between OOB subnets, acts as the SSH entry point into the simulation, and hosts the ZTP status page. In production, this is typically an existing management server. |

### What `air-oob-switch` actually does

In the simulation, `air-oob-switch` is configured (via Node Instructions) as a VLAN-aware
bridge that:

- Connects all switch **eth0** management ports on an untagged air-mgmt network
- Provides per-`mgmt_subnet` VLANs for OOB switch uplinks
- Connects `oob-server-01` and `dhcp-oob` to each management subnet

This mirrors what a customer's existing OOB infrastructure would provide in a physical
deployment — L2 reachability between management ports, DHCP servers, and gateways.

### Physical nodes (actual hardware)

Everything else in the topology represents real hardware defined in the ERA reference
architecture:

| Node Pattern | Hardware |
|---|---|
| `core-01`, `core-02` | NVIDIA SN5610 spine/leaf switches |
| `oob-switch-01`, `-02`, `-03` | NVIDIA SN2201 OOB management switches |
| `su-XX-node-YY` | Compute servers (GPU nodes) |
| `storage-XX` | Storage servers |
| `support-XX` | Support/infrastructure servers |

These are the devices specified by the ERA deployment guide and represent actual
equipment to be purchased and racked.

---

## Quick Reference

```bash
# One-time setup
make import EXCEL=my-config.xlsx          # Import filled Excel

# Full pipeline from Excel (recommended)
make deploy EXCEL=my-config.xlsx                            # Switches + servers configured on boot
make deploy-exclude-servers EXCEL=my-config.xlsx            # Switches only (run deploy-servers-via-jump afterwards)

# Or automated from ARCH (after import)
make air-auth-test ARCH=2-8-5-200         # Verify Air credentials
make air-full-deploy ARCH=2-8-5-200       # Generate + deploy + ZTP

# Or step by step
make generate ARCH=2-8-5-200              # Generate configs + topology
make air-deploy ARCH=2-8-5-200            # Create Air sim + configure SSH
make air-ssh-check ARCH=2-8-5-200         # Verify SSH access to jump hosts
make switch-ztp-deploy ARCH=2-8-5-200     # Push configs to switches

# Deploy servers separately (if using deploy-exclude-servers)
make deploy-servers-via-jump ARCH=2-8-5-200   # Air (via jump host)
make deploy-servers ARCH=2-8-5-200              # Direct SSH (physical)

# Manual workflow (fallback) — run from local machine
make air-connect ARCH=2-8-5-200           # Enter Air SSH details manually
make switch-ztp-deploy ARCH=2-8-5-200

# Manual workflow (fallback) — run from inside simulation
# See docs/MANUAL_FALLBACK_GUIDE.md for full procedure
# make generate already produces node-instructions/ in the topology folder

# Management
make air-list ARCH=2-8-5-200              # List simulations
make air-budget ARCH=2-8-5-200            # Check resource budget
make air-ssh-check ARCH=2-8-5-200         # Check SSH access to jump hosts
make air-ssh-check ARCH=2-8-5-200 FIX=1   # Auto-inject SSH key if needed
make air-destroy ARCH=2-8-5-200           # Teardown

# Trigger ZTP on switches (Air console)
sudo ztp -r

# Validate
make validate-ztp ARCH=2-8-5-200
```

### Default Credentials

| Server | Username | Password |
|---|---|---|
| oob-server-01 | ubuntu | nvidia |
| dhcp-oob | ubuntu | nvidia |
| Switches | cumulus | Cumu1usLinux! |

### Air Service URL Format

```
ssh -p <port> ubuntu@<air-host>
```

---

## Alternative: Run Ansible from Within Air

If you prefer to run Ansible directly on a node inside the simulation:

### 1. Open Console on oob-server-01

Click **oob-server-01** in Air → **Console**

### 2. Clone Repository

```bash
# Public release lives in the net-configurator/ subdirectory of the NVIDIA enterprise-ras repo
git clone https://github.com/NVIDIA/enterprise-ras.git
cd enterprise-ras/net-configurator
```

> If you deployed from a source tarball instead of a clone, `scp` your existing
> local checkout to the node rather than cloning.

### 3. Install Dependencies

```bash
sudo apt update
sudo apt install -y ansible python3-pip
pip3 install openpyxl jinja2
```

### 4. Run Deployment

No host_vars changes needed — Ansible connects locally:

```bash
make switch-ztp-deploy
```

---

## Troubleshooting

### Cannot Connect to Air Services

**Symptom**: SSH connection refused or timeout

**Solutions**:
1. Verify simulation is running (green status in Air)
2. Check that SSH services are created and show an external port
3. Try refreshing the Air page
4. Restart the simulation if needed

### Ansible Connection Failures

**Symptom**: `ansible-playbook` fails to connect

**Debug**:
```bash
# Test SSH directly
ssh -p <port> ubuntu@<air-host>

# Test Ansible ping
ansible oob-server -i output/<arch>/<site>/inventory/hosts -m ping -vvv
```

**Common fixes**:
- Verify `ansible_host` and `ansible_port` in host_vars
- Check password in `secrets.yml`
- Ensure SSH services are added in Air

### ZTP Not Working

**Symptom**: Switches don't auto-configure after boot

**Debug on switch**:
```bash
cat /var/log/autoprovision        # ZTP log
ping 192.168.200.252              # Test connectivity to ZTP server
sudo dhclient -v eth0             # Test DHCP
```

**Debug on ZTP server (dhcp-oob)**:
```bash
sudo systemctl status dnsmasq
sudo cat /etc/dnsmasq.d/ztp.conf
sudo systemctl status nginx
sudo cat /var/log/nginx/error.log
```

### Server Deployment Fails (Timeout / Password Prompt)

**Symptom**: `make deploy-servers` times out or prompts for `ubuntu@<air-host>'s password`

**Cause**: Servers are on Air internal networks (192.168.x.x) not reachable from your machine. The SSH proxy through the OOB jump host (`utility` in L3 OOB, `oob-server-01` in legacy L2) is needed.

**Fix**:
```bash
# Use the via-server variant (requires sshpass)
sudo apt install sshpass
make deploy-servers-via-jump
```

If you still get password prompts, verify `oob-server-01.yml` has the correct Air SSH service details and `secrets.yml` has the correct `server_ansible_password`.

### Config Files Not Downloaded

**Symptom**: Switch contacts ZTP server but config is not applied

**Check**:
```bash
# On dhcp-oob — verify configs were deployed
ls -la /var/www/html/ztp/configs/

# Test download manually
curl http://localhost/ztp/configs/core-01-config.sh
```

---

## See Also

- [OOB Server Setup](OOB_SERVER_SETUP.md) — Gateway configuration details
- [ZTP Setup Guide](MULTI_INTERFACE_ZTP.md) — ZTP server details
- [Secrets & Vault](SECRETS_AND_VAULT.md) — Password management
- [ZTP Validation](ZTP_VALIDATION.md) — Testing and troubleshooting
