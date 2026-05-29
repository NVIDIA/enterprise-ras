<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# ERA Switch Automation using NVIDIA NVUE

Ansible automation for ERA (Enterprise Reference Architecture) network switch configuration. Fill out an Excel spreadsheet describing your deployment, and this tool generates Ansible inventory, NVUE switch configs, and an NVIDIA Air topology -- then deploys everything via Zero Touch Provisioning (ZTP).

## Terms used in this guide

| Term | What it means |
|---|---|
| **ERA** | NVIDIA's Enterprise Reference Architecture — the set of network topologies this tool configures (2-4-3-200, 2-8-5-200, 2-8-9-400, 2-8-9-800). |
| **NVUE** | NVIDIA User Experience CLI — the config language for Cumulus Linux switches (`nv set ...`). This tool generates `.sh` scripts of NVUE commands. |
| **Cumulus Linux** | The switch OS running on NVIDIA Spectrum hardware. NVUE is its management interface. |
| **ZTP** | Zero Touch Provisioning — the switch boots, DHCP hands it a provisioning script, the script applies the NVUE config, done. No console access required. |
| **NGC** | [NVIDIA GPU Cloud](https://ngc.nvidia.com) — NVIDIA's cloud service portal. You'll need an NGC account and API key to use NVIDIA Air. |
| **NVIDIA Air** | A cloud-hosted network simulator. Runs your generated topology as virtual Cumulus switches so you can validate configs before touching physical hardware. Optional — you can skip Air and deploy straight to physical gear. |
| **OOB** | Out-of-band — the dedicated management network that configures switches separately from the data plane. The current architecture routes it as an **L3 OOB** network (its own VRF with external connectivity, NAT, and eBGP); older deployments used a flat L2 OOB subnet. This tool builds the OOB network + switches in every deployment. |
| **`utility`** | The L3 OOB jumpbox that Ansible connects through. Also hosts the status page and is the OOB-side DHCP relay target. In Air it's a virtual node; on physical hardware it's the customer's management server. (Supersedes the legacy L2 `oob-server-01`.) |
| **`external-dhcp`** | The node that runs the ZTP DHCP + web server — switches fetch their bootstrap script from here. Also the inter-VRF EXIT relay target. (Supersedes the legacy L2 `dhcp-oob`.) |
| **`external-conn`** | The NAT host (`172.20.0.1`) that routes OOB traffic outbound — provides internet access and the eBGP control plane into the OOB VRF. |
| **`cust-net-edge-01` / `-02`** | Simulated customer-edge switches that bridge the management network and run the EXIT-VRF eBGP underlay (`-02` is the HA NAT return path). |
| **`oob-server-01` / `dhcp-oob`** | Legacy L2 OOB jump host and DHCP/ZTP node. Still referenced in some sections of this guide; their L3 OOB equivalents are `utility` and `external-dhcp`. |
| **Site** | A named deployment within an architecture (e.g., `customer-a`, `lab`, `default`). Lets you run multiple isolated deployments from one checkout. |

## Supported Architectures

Architecture names follow the pattern `{CPUs}-{GPUs}-{NICs}-{B}` per compute
node, where **B = average per-GPU bandwidth on the East/West (compute)
network, in Gbps**. This remains the right measure even on future
systems that decouple North/South and East/West link speeds.

| Architecture | CPUs | GPUs | Network Adapters | Per-GPU E/W bandwidth | Fabric |
|---|---|---|---|---|---|
| `2-4-3-200`* | 2 | 4 | 3 | 200 Gbps | Converged (core) |
| `2-8-5-200`* | 2 | 8 | 5 | 200 Gbps | Converged (core) |
| `2-8-9-400` | 2 | 8 | 9 | 400 Gbps | Converged (core) |
| `2-8-9-800` | 2 | 8 | 9 | 800 Gbps | **Dual-plane** (CSL + GSL) |

\* In archs where the E/W NIC:GPU ratio is 1:2 (`2-4-3-200`, `2-8-5-200`),
   strict per-GPU arithmetic gives 100 Gbps; the label `200` follows the
   per-NIC link speed convention — a documented exception, not a bug.

### Converged vs dual-plane fabric

- **Converged (`core-*` switches):** one switch tier handles CPU/in-band,
  storage, support, OOB, *and* GPU east-west traffic on the same fabric.
  Used by 2-4-3-200 / 2-8-5-200 / 2-8-9-400.
- **Dual-plane (`csl-*` + `gsl-plane1-*` + `gsl-plane2-*`):** CSL leaves
  carry CPU/in-band, storage, support, and OOB. The GPU fabric is split
  across two independent planes — `gsl-plane1-*` and `gsl-plane2-*` — each
  with its own underlay loopback subnet, EVPN scope, and BGP graph. Same
  VLAN ID (900) on both planes, but they're L3-isolated by design.
  Used by 2-8-9-800 (HGX B300).

See [`docs/ROLES.md`](docs/ROLES.md) for the full role taxonomy.

### Feature support matrix

| Feature | `2-4-3-200` | `2-8-5-200` | `2-8-9-400` | `2-8-9-800` |
|---|:---:|:---:|:---:|:---:|
| L3 OOB underlay + EVPN | ✅ | ✅ | ✅ | ✅ |
| Inter-VRF DHCP relay (OOB + EXIT) | ✅ | ✅ | ✅ | ✅ |
| Operator-configurable SSH login banners | ✅ | ✅ | ✅ | ✅ |
| LDAP authentication (auto-detected from Excel) | ✅ | ✅ | ✅ | ✅ |
| NVIDIA Air simulation | ✅ | ✅ | ✅ | ✅ |
| Status page (HTTP report dashboard) | ✅ | ✅ | ✅ | ✅ |
| STORAGE VRF as first-class | — | — | — | ✅ |
| Dual-plane GPU fabric | — | — | — | ✅ |
| Per-rail-per-plane GPU VLAN mode | — | — | — | ✅ |
| Single-tier SU scaling | 1 SU | 1 SU | 1 SU | 1–2 SU |

See [`docs/ARCH_SUPPORT_MATRIX.md`](docs/ARCH_SUPPORT_MATRIX.md) for the
detailed support matrix including known gaps and roadmap items.

## Features

- **One-command deployment**: `make deploy EXCEL=...` handles the full pipeline
- **Excel-driven workflow**: Fill out a spreadsheet, everything else is generated
- **Zero Touch Provisioning (ZTP)**: Switches auto-configure on first boot via DHCP
- **NVIDIA Air integration**: Automated simulation creation and SSH setup (optional — physical-only deployments work without it)
- **Multi-site support**: Deploy the same architecture to multiple sites
- **LDAP authentication**: Optional centralized user management (auto-detected from Excel)
- **Inter-VRF DHCP relay**: VLAN clients in any VRF can lease from servers in OOB or EXIT (per the ERA Architecture Principals deck)
- **Ansible Vault**: Encrypt secrets at rest

## Known Limitations

- **Replace placeholder passwords before deploying to real hardware.** The
  shipped `secrets.yml` files use documented placeholders (`Cumu1usLinux!`,
  `nvidia`, etc.) that are safe for NVIDIA Air simulations only. See
  [`SECURITY.md`](SECURITY.md) for the rotation checklist.
- **SSH host-key checking is disabled** in `ansible.cfg` for lab/Air use.
  If you're running this against production hardware on an untrusted
  network, re-enable `host_key_checking` and populate `known_hosts` first.
  See [Security Considerations](#security-considerations) below.
- **Don't run this tool on a multi-user host** (bastion, shared jump box,
  CI runner with other tenants) until the `sshpass` refactor ships.
  Several validation playbooks (`validate-ping-matrix`, `validate-config`,
  `restart-ldap-switches`, and the Air `ProxyCommand`) pass passwords
  to `sshpass` via CLI arguments, which makes them visible in
  `ps auxww` to any other local user during those steps. The long-term
  fix is SSH key-based auth end-to-end.
- **If a deploy fails mid-flight**, see [`docs/MANUAL_FALLBACK_GUIDE.md`](docs/MANUAL_FALLBACK_GUIDE.md)
  for the manual Air-deployment path (uses Node Instructions + Ansible
  from `dhcp-oob`).
- **Test coverage is uneven.** Parser/template/topology have unit tests;
  the Air API client and several utility scripts do not yet. Bugs in
  those paths will surface as runtime errors rather than test failures.

---

## Installation

**Prerequisites:** Python 3.12+, Git, Make, SSH key pair for Air access (only if using NVIDIA Air), NGC account (only if using NVIDIA Air)

> **macOS users:** After creating your venv, run `pip install certifi` before any other commands to avoid SSL certificate errors when connecting to NVIDIA Air.

### Option A: Download a release archive

Download the latest `nc-v<version>.zip` from the
[GitHub Releases page](https://github.com/NVIDIA/enterprise-ras/releases).

```bash
unzip nc-v<version>.zip
cd net-configurator/

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Option B: Clone the repo

```bash
git clone https://github.com/NVIDIA/enterprise-ras.git
cd enterprise-ras/net-configurator

python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# On Windows, run inside WSL — native Windows is not supported as a controller

pip install -r requirements.txt

# Verify
ansible --version    # should show 2.20+
make help            # list available commands
```

> Re-run `source .venv/bin/activate` at the start of each terminal session.

> **macOS users:** Run `pip install certifi` after activating your venv to avoid SSL
> certificate errors when connecting to NVIDIA Air.

**Windows users:** Use WSL (Windows Subsystem for Linux) — Ansible does not support
Windows as a controller.

---

## Quick Start

The recommended path is a single command that validates your Excel, imports it, generates all configs, creates an NVIDIA Air simulation, and deploys via ZTP.

### Step 1 -- Fill out the Excel template

Copy the template for your architecture and fill it in:

**Ready-to-use sample files** (recommended — deploy directly without modifying defaults):

| Architecture | Sample File | Description |
|---|---|---|
| `2-4-3-200` | `input/sample-2-4-3-200.xlsx` | 2 CPU, 4 GPU, 3 NIC, 200G — converged |
| `2-8-5-200` | `input/sample-2-8-5-200.xlsx` | 2 CPU, 8 GPU, 5 NIC, 200G — converged |
| `2-8-9-400` | `input/sample-2-8-9-400.xlsx` | 2 CPU, 8 GPU, 9 NIC, 400G — converged |
| `2-8-9-800` | `input/sample-2-8-9-800.xlsx` | 2 CPU, 8 GPU, 9 NIC, 800G — dual-plane (CSL + GSL) |

These sample files have `site_name` set to `sample` so they import to their own
directory (`input/<arch>/sample/`) without overwriting the committed defaults.

To deploy a sample as-is:
```bash
make deploy EXCEL=input/sample-2-8-5-200.xlsx
```

To customize, copy a sample and edit:
```bash
cp input/sample-2-8-5-200.xlsx ~/my-deployment.xlsx
# Edit the Excel, then:
make deploy EXCEL=~/my-deployment.xlsx
```

**Reference templates** (the committed defaults — do not edit directly):

| Architecture | Template |
|---|---|
| `2-4-3-200` | `input/2-4-3-200/default/2-4-3-200.xlsx` |
| `2-8-5-200` | `input/2-8-5-200/default/2-8-5-200.xlsx` |
| `2-8-9-400` | `input/2-8-9-400/default/2-8-9-400.xlsx` |
| `2-8-9-800` | `input/2-8-9-800/default/2-8-9-800.xlsx` |

Each template is pre-configured with default values. Update the sheets for your deployment:

- **Settings** -- site name, management subnets, LDAP toggle, Air options
- **Nodes** -- hostnames, MAC addresses, management IPs
- **VLANs & Profiles** -- VLAN IDs, subnets, network profiles
- **Wire Map** -- every physical cable connection

See the [Excel Configuration Guide](docs/EXCEL_CONFIGURATION_GUIDE.md) for detailed field-by-field documentation.

### Step 2 -- Configure Air credentials (only if deploying to NVIDIA Air)

> **Skip this step if you are deploying to physical hardware only** — jump to
> Step 3 and use the `make switch-ztp-deploy` path instead of `make deploy`.
> You do not need an NGC account or Air credentials for physical-only
> deployments.

Run the onboarding wizard:

```bash
make air-setup
```

The wizard prompts for your NGC API key, which Air instance to use (public NGC Air at `https://air-ngc.nvidia.com` vs. internal air-inside), optional username, SSH key path, and a **vault password** you choose. The vault password encrypts the credentials file at rest (`era-secrets/air-secrets.yml`). If you choose to save it to `.era-secrets/vault-pass`, subsequent `make` commands use it automatically. If you skip saving it, you will be prompted for it each time. The `.era-secrets/` directory is gitignored. Every arch/site in this checkout reads from that single shared vault — no per-deployment credential setup needed.

For one-off overrides (e.g. CI), export `AIR_API_KEY` / `AIR_BASE_URL` as shell environment variables instead of running the wizard.

### Step 3 -- Deploy

Pick the path that matches your target:

**Deploying to NVIDIA Air (virtual simulation):**

```bash
# Fastest path (recommended for Air): configs are injected at boot via Air
# Node Instructions — no DHCP/HTTP ZTP wait. Switches + servers come up
# already configured (~2-3 min after the sim reaches LOADED).
make deploy EXCEL=/path/to/your-config.xlsx NOZTP=1

# Standard ZTP path: switches fetch their configs over DHCP/HTTP after boot
# (5-10 min per switch). Use this to exercise the real ZTP server flow.
make deploy EXCEL=/path/to/your-config.xlsx

# Switches only (run make deploy-servers-via-jump afterwards for servers)
make deploy-exclude-servers EXCEL=/path/to/your-config.xlsx
```

> **`NOZTP=1` is the quickest way to stand up an Air sim.** It skips the ZTP
> server setup (steps 7-8 below) and delivers configs as Node Instructions
> that apply via `era-apply.service` shortly after boot. Don't SSH in or run
> validation until that apply window passes (~2-3 min after LOADED), or a
> manual change can be overwritten by the deferred apply.

**Deploying to physical hardware only (no Air):**

> **Prerequisite:** Your OOB server (management host) must be running and reachable
> before you power on any switches. ZTP relies on the OOB server to hand out DHCP
> leases and serve config scripts. See [`docs/OOB_SERVER_SETUP.md`](docs/OOB_SERVER_SETUP.md)
> for setup instructions. **Do not power on switches until the OOB server is ready.**

```bash
# Validate + import the Excel
make validate-excel EXCEL=/path/to/your-config.xlsx
make import EXCEL=/path/to/your-config.xlsx

# Generate inventory, configs, and topology
make generate

# Deploy via ZTP to your physical fabric (requires a reachable ZTP server —
# see docs/OOB_SERVER_SETUP.md and docs/ZTP_MODES.md for preparing one)
make switch-ztp-deploy
```

Both Air commands run the same pipeline:

1. Validates the Excel file (structure, IPs, ports, duplicates)
2. Imports the Excel (copies to `input/<arch>/<site>/`, sets context)
3. Generates Ansible inventory, NVUE switch configs, and Air topology
4. Creates an NVIDIA Air simulation and configures SSH access
5. Configures the OOB server (gateway/routing)
6. Configures LDAP (if enabled in Excel)
7. Generates switch configs on the ZTP server
8. Sets up the ZTP server (dnsmasq + nginx)

`make deploy` also injects server configuration (hostname, netplan, lldp) as
Air Node Instructions in step 4, so servers are fully configured on first boot.
Use `make deploy-exclude-servers` if you want to skip server config and run
`make deploy-servers-via-jump` separately afterwards.

You will be prompted to confirm before deployment begins.

### Step 4 -- Wait for ZTP to complete

> **Be patient.** ZTP takes time — switches must boot, download their config, apply it,
> and reboot. This is normal and expected. Do not interrupt the process or re-run
> deployment commands while ZTP is in progress.

After `make deploy` finishes, the switches in the Air simulation will pick up their
configurations automatically. The timeline:

- **Switches**: 5–10 minutes per switch for ZTP to complete (boot → DHCP → download config → apply → reboot)
- **Servers** (when using `make deploy`): 3–5 minutes for Node Instructions to run (boot → hostname + netplan + lldp)
- **Full simulation**: Allow **15–20 minutes** for all nodes to be fully configured

Each switch goes through this sequence:

1. Boots and sends a DHCP request
2. Receives its IP address and the ZTP script URL
3. Downloads its NVUE config from the ZTP server (nginx)
4. Applies the config with `nv config apply`
5. Reboots with the final configuration

To check ZTP progress, SSH into a switch through the Air console and run:

```bash
cat /var/log/autoprovision    # ZTP log on the switch
```

> **Tip:** If a switch shows no ZTP log after 10 minutes, try triggering ZTP manually:
> `sudo ztp -r`

### Step 5 -- Validate

```bash
make validate-all
```

This runs four checks:
1. Topology validation (generated topology matches wiremap)
2. ZTP validation (switches received correct configs via ZTP server)
3. Config comparison (running switch config matches generated config)
4. Server validation (bonds, VLANs, connectivity, LLDP on all servers)

---

## Deployment Decision Matrix

Choose the right command based on where you are in the workflow:

| Command | Use When | What It Does |
|---------|----------|--------------|
| `make deploy EXCEL=... NOZTP=1` | **Fastest Air deploy** — want a configured sim quickly | Same all-in-one pipeline, but injects configs as Node Instructions at boot (no ZTP server, no DHCP wait) |
| `make deploy EXCEL=...` | Starting from scratch, deploying to **NVIDIA Air** | Validate + import + generate + Air sim + ZTP + server config (all-in-one; **Air only**) |
| `make deploy-exclude-servers EXCEL=...` | Air deploy without server config | Same as above but skips server Node Instructions |
| `make switch-ztp-deploy` | Deploying to **physical hardware** (or Air sim already exists) | OOB setup + LDAP + generate + ZTP server setup |
| `make air-full-deploy` | Excel already imported, need to (re)deploy to Air | Generate + create Air sim + ZTP deploy |
| `make generate` | Just want to create configs without deploying | Excel to inventory + configs + topology |

---

## Deployment Context

Every architecture-specific command needs to know which architecture and site to target. This is managed through a **context** -- a saved `architecture + site` pair stored in `.era-context`.

- **Set automatically** by `make import` or `make deploy` (reads from the Excel Settings tab)
- **Set manually** with `make use ARCH=2-8-5-200 SITE=customer-a`
- **Override anytime** by passing `ARCH=` and/or `SITE=` to any command
- **View** with `make show-context`
- **Clear** with `make clear-context`

Once context is set, all commands work without parameters:

```bash
make use ARCH=2-8-5-200 SITE=lab-west    # set context once
make generate                             # uses saved context
make air-deploy                           # uses saved context
make switch-ztp-deploy                    # uses saved context
make validate-all                         # uses saved context
```

If `SITE` is not specified, it defaults to `default`.

---

## Direct vs Via-Server Commands

Some commands have two variants -- **direct** and **via-server**:

| Direct | Via-Server | Difference |
|--------|------------|------------|
| `make deploy-servers` | `make deploy-servers-via-jump` | How server configs are pushed |
| `make validate-ztp-direct` | `make validate-ztp` | How ZTP is validated |
| `make restart-ldap-direct` | `make restart-ldap` | How LDAP is restarted |

- **Direct**: Your machine SSHs directly to the switches/servers. Use this when you have direct network access (e.g., lab environment on the same network).
- **Via-server**: Commands go through `oob-server-01` as an SSH jump host. Required for NVIDIA Air simulations, where your machine cannot reach switches directly.

`make validate-all` uses the via-server path automatically, since it is designed for post-deployment validation in Air.

---

## After ZTP Completes

Once `make deploy` or `make switch-ztp-deploy` finishes, the ZTP server is running and switches will auto-provision on their next boot. **Allow 15–20 minutes** for the full simulation to converge before running validation.

1. **Wait for ZTP** — switches need 5–10 minutes each. Resist the urge to re-run commands; let the process complete.
2. **Check progress** by SSHing to individual switches (via Air console) and inspecting the log:
   ```bash
   cat /var/log/autoprovision
   ```
3. **Validate the deployment** (run after all switches have rebooted):
   ```bash
   make validate-all
   ```
   This confirms topology correctness, ZTP success, config accuracy, and server network configuration.
4. **Run the ping matrix** (optional, confirms full server-to-server connectivity):
   ```bash
   make validate-ping-matrix
   ```
5. **View Air simulation details** (SSH connection info, node status):
   ```bash
   make air-list
   ```

If a switch did not provision correctly, you can re-trigger ZTP manually from the Air console:

```bash
sudo ztp -r
```

---

## Validation

### Customer-facing validation

```bash
make validate-all         # Runs all four checks below (via-server):
                          #   1. Topology vs wiremap
                          #   2. ZTP status on switches
                          #   3. Running config vs generated config
                          #   4. Server architecture (bonds, VLANs, connectivity)
```

### Individual validation commands

```bash
make validate-excel EXCEL=/path/to/file.xlsx   # Validate Excel before import
make validate-topology                          # Topology JSON matches wiremap
make validate-ztp-direct                        # ZTP success (direct SSH)
make validate-ztp                               # ZTP success (via oob-server-01)
make validate-config                            # Running config vs generated config
make validate-servers                           # Server config (bonds, VLANs, connectivity)
make validate-ping-matrix                       # Full server-to-server ping matrix (all VLANs)
make validate                                   # Ansible playbook syntax check
```

---

## Makefile Commands

### Context Management

```bash
make import EXCEL=my-config.xlsx          # Import filled Excel (sets context automatically)
make import EXCEL=my-config.xlsx SITE=lab # Import with site name override
make use ARCH=2-8-5-200                   # Set arch manually (SITE defaults to 'default')
make use ARCH=2-8-5-200 SITE=customer-a   # Set arch + custom site
make show-context                         # Show current arch/site
make clear-context                        # Remove saved context
```

### Full Deployment Workflows

```bash
make deploy EXCEL=/path/to/config.xlsx                   # Full pipeline: validate + import + generate + Air + ZTP + server config
make deploy-exclude-servers EXCEL=/path/to/config.xlsx   # Same but skips server config (run deploy-servers-via-jump afterwards)
make air-full-deploy                                     # Generate + create Air sim + ZTP deploy
make switch-ztp-deploy                    # OOB + LDAP + generate + ZTP server (Air sim must exist)
make switch-ztp-deploy LDAP=1             # Force LDAP even if not set in Excel
```

### Individual Steps

```bash
make generate                    # Generate configs + Air topology from imported Excel
make oob-setup                   # Configure OOB server (gateway/routing)
make ztp-setup                   # Setup ZTP server (dnsmasq + nginx)
make ztp-update                  # Regenerate configs and push to ZTP server
make deploy-servers              # Deploy server configs (direct SSH)
make deploy-servers-via-jump     # Deploy server configs (via oob-server-01, for Air)
make push-switch-configs         # Push and apply generated NVUE configs to switches
make restart-ldap                # Restart LDAP on switches (via OOB)
make restart-ldap-direct         # Restart LDAP on switches (direct SSH)
```

### NVIDIA Air

```bash
make air-full-deploy             # Full pipeline: generate + air-deploy + switch-ztp-deploy
make air-auth-test               # Test Air API credentials and connectivity
make air-ssh-check               # Check SSH key/password auth to jump hosts
make air-ssh-check FIX=1         # Auto-inject SSH key if auth fails
make air-deploy                  # Create Air simulation and configure SSH
make air-destroy                 # Destroy Air simulation and clean up
make air-list                    # List Air simulations with SSH info
make air-budget                  # Check Air resource budget
make air-connect                 # Set Air SSH connection details manually
make air-show                    # Show current Air connection settings
```

### Topology

```bash
make topology                    # Generate Air topology JSON only
make validate-topology           # Validate topology against wiremap
```

### Utilities

```bash
make list-archs              # Show available architectures
make list-sites              # List existing sites
make inventory               # Show Ansible inventory summary
make validate                # Validate Ansible playbook syntax
make validate-excel          # Validate Excel file structure, IPs, ports
make lint                    # Lint YAML and Python files
make status                  # Project status overview
make clean                   # Clean caches and temp files
```

### Help

```bash
make help                    # All available commands
make help-switch-ztp-deploy  # Detailed help for a specific command
make help-generate
make help-air                # Air deployment quick-reference
```

---

## Project Structure

```
era-automation/
├── input/
│   └── <arch>/
│       └── <site>/          # 'default' site committed; others gitignored
│           └── <arch>.xlsx  # Filled-out configuration template
├── output/
│   └── <arch>/
│       └── <site>/
│           ├── inventory/   # Ansible inventory (hosts, host_vars, group_vars)
│           ├── configs/     # Generated NVUE CLI scripts (.sh)
│           └── topology/    # Generated Air topology JSON
├── topology/                # Reference NVIDIA Air topology JSON files (per arch)
├── roles/
│   ├── core/                # Core switch role
│   ├── oob-switch/          # OOB switch role
│   ├── oob-server/          # OOB server setup (gateway/routing)
│   ├── ztp-server/          # ZTP server (dnsmasq + nginx)
│   └── ldap/                # LDAP configuration
├── playbooks/               # Ansible playbooks
├── scripts/
│   ├── import-excel.py      # Import filled Excel into input/<arch>/<site>/
│   ├── excel_parser.py      # Excel to Ansible inventory generator
│   ├── topology_generator.py # Excel Wire Map to Air topology JSON
│   ├── air-deploy.py        # Create Air simulation and configure SSH
│   ├── air-destroy.py       # Destroy Air simulation
│   ├── air-list.py          # List Air simulations
│   ├── air-budget-check.py  # Check Air resource budget
│   ├── air-auth-test.py     # Test Air API credentials
│   ├── air-ssh-check.py     # Check and fix SSH key access to jump hosts
│   ├── air-connect.py       # Interactive Air SSH connection setup
│   ├── airlib/              # Air API client library
│   └── validate_excel.py    # Excel validation (structure, IPs, ports, duplicates)
├── docs/                    # Documentation
├── Makefile                 # Primary interface -- run 'make help' for all commands
└── .era-context             # Saved deployment context (gitignored)
```

---

## Secrets Management

All passwords are stored in `output/<arch>/<site>/inventory/group_vars/all/secrets.yml`:

```yaml
switch_ansible_password: "Cumu1usLinux!"   # SSH to switches
server_ansible_password: "nvidia"          # SSH to servers
ansible_become_password: "nvidia"          # sudo (no --ask-become-pass needed)
switch_password: "Cumu1usLinux!"           # Password set on switches during ZTP
ldap_admin_password: "Ldap@123"            # LDAP bind password
```

The default values above are placeholders for development and Air simulations. For production deployments, change these passwords and encrypt the file with Ansible Vault.

### Encrypt with Ansible Vault (recommended for production)

```bash
# Encrypt
ansible-vault encrypt output/2-8-5-200/default/inventory/group_vars/all/secrets.yml

# Run commands with vault password
export ANSIBLE_VAULT_PASSWORD_FILE=~/.vault_pass
make switch-ztp-deploy
```

See [docs/SECRETS_AND_VAULT.md](docs/SECRETS_AND_VAULT.md) for full details.

---

## Documentation

### Getting Started
- **[Excel Configuration Guide](docs/EXCEL_CONFIGURATION_GUIDE.md)** -- How to fill out the Excel template (every field explained)
- **[Air Deployment Guide](docs/AIR_DEPLOYMENT_GUIDE.md)** -- Step-by-step NVIDIA Air deployment walkthrough

### ZTP and Deployment
- **[ZTP Setup](docs/MULTI_INTERFACE_ZTP.md)** -- Zero Touch Provisioning details
- **[ZTP Validation](docs/ZTP_VALIDATION.md)** -- Testing and troubleshooting ZTP
- **[OOB Server Setup](docs/OOB_SERVER_SETUP.md)** -- Gateway/routing for Air and lab environments
- **[ZTP Modes](docs/ZTP_MODES.md)** -- ZTP configuration options
- **[ZTP Interface Configuration](docs/ZTP_INTERFACE_CONFIGURATION.md)** -- dnsmasq interface setup for ZTP
- **[ZTP MAC Addresses](docs/ZTP_MAC_ADDRESSES.md)** -- MAC address handling for ZTP reservations

### Security and Configuration
- **[Secrets and Vault](docs/SECRETS_AND_VAULT.md)** -- Password management and encryption
- **[LDAP Setup](docs/LDAP_CONFIGURATION.md)** -- Optional centralized authentication
- **[DNS Setup](docs/DNSMASQ_INTERFACE_SETUP.md)** -- dnsmasq configuration
- **[Ansible Sudo Setup](docs/ANSIBLE_SUDO_SETUP.md)** -- Configuring passwordless sudo for Ansible

### Development
- **[Testing](docs/TESTING.md)** -- Unit tests and validation
- **[Scripts README](scripts/README.md)** -- Utility scripts reference
- **[NVUE Version Compatibility](docs/NVUE_VERSION_COMPAT.md)** -- NVUE syntax changes across Cumulus versions

---

## Security Considerations

### SSH Host Key Verification

SSH host key checking is **disabled by default** across this project. This is intentional for NVIDIA Air simulation and ZTP environments, where switches are frequently reprovisioned and their host keys change on every rebuild. Strict host key checking in these environments would cause constant connection failures and break automated workflows.

The settings that control this behavior:

- **`ansible.cfg`** -- `host_key_checking = False` (line 6) disables Ansible's built-in check, and `StrictHostKeyChecking=no` in `ssh_args` (line 26) disables the OpenSSH-level check. Both also suppress known_hosts warnings via `/dev/null`.
- **`scripts/airlib/ssh.py`** -- The `SSH_STRICT_OFF` constant passes the same `-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null` flags to SSH commands issued by the Air deployment scripts.

**For production deployments**, re-enable host key verification to protect against man-in-the-middle attacks:

1. In `ansible.cfg`, set `host_key_checking = True` and remove `-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null` from `ssh_args`
2. In `scripts/airlib/ssh.py`, update the `SSH_STRICT_OFF` constant to remove the flags (or set it to an empty string)
3. Pre-populate `~/.ssh/known_hosts` with the expected host keys for your switches before running any playbooks

These changes are not needed for Air simulations or lab environments where node identities are ephemeral.

---

## Troubleshooting

### Import and Generate Errors

**"Excel not found" or file path errors**
- Verify the path to your Excel file is correct and the file exists
- Use an absolute path if a relative path is not resolving

**"architecture key not found in Settings tab"**
- Open the Excel file and confirm the Settings sheet has an `architecture` field
- The value must be one of: `2-4-3-200`, `2-8-5-200`, `2-8-9-400`, `2-8-9-800`

**"SameFileError" during import**
This happens when your Excel file already lives at the exact destination
path `make import` wants to copy it to — typically because you edited
it in place at `input/<arch>/<site>/<arch>.xlsx`. Two options:
- **Skip import and go straight to generate:** `make use ARCH=<type> SITE=<site>` then `make generate` — the Excel is already where the parser expects it.
- **Copy the source elsewhere first:** `cp input/2-8-5-200/default/2-8-5-200.xlsx /tmp/my-config.xlsx && make import EXCEL=/tmp/my-config.xlsx`

**`make import` put my file in the wrong site**
`make import` reads the destination site from the Excel **`site_name`
cell in the Settings tab**, not from the directory path you placed
the file at. If you want your deployment to land at
`input/2-8-5-200/customer-acme/`, you must also set
`site_name: customer-acme` inside the Excel's Settings tab before
importing — otherwise the import will route to whatever the Excel's
`site_name` currently says (often `sample` or `default`).

**Ansible syntax errors during generate**
- Run `make validate-excel EXCEL=/path/to/file.xlsx` to check for invalid data
- Review the error message -- it usually points to a specific variable or sheet
- Common causes: empty required fields, invalid IP addresses, duplicate hostnames

### Applying Pre-built Configs Manually to Physical Switches

The `output/<arch>/default/configs/` directory contains ready-to-run NVUE CLI
scripts for each switch. To apply them without ZTP or Ansible:

> **Switch starting state:** Switches should be at factory defaults (or freshly
> reset via `nv config detach && nv config replace factory`). If a switch already
> has a partial config applied, run the factory reset first, then apply the script.

1. **Replace placeholder passwords first** — edit
   `output/<arch>/default/inventory/group_vars/all/secrets.yml` and replace
   all placeholder values (`Cumu1usLinux!`, `nvidia`, etc.) before touching
   real hardware.
2. **Apply the config** — two options:

   **Option A — SCP and run (SSH access required):**
   ```bash
   scp output/2-8-5-200/default/configs/core-01-config.sh admin@<switch-mgmt-ip>:~/
   ssh admin@<switch-mgmt-ip>
   chmod +x core-01-config.sh
   ./core-01-config.sh
   ```

   **Option B — Console and paste (no network access required):**
   Open a console session to the switch and paste the contents of
   `core-01-config.sh` directly into the NVUE CLI. The `nv set ...`
   commands can be pasted line by line or in bulk.
3. **Review and apply the staged config:**
   ```bash
   nv config diff    # review what will change
   nv config apply   # apply it
   ```
4. Repeat for each switch (`core-02`, `oob-switch-01`, etc.).

### ZTP Issues

**Switches not provisioning?**
```bash
# On the ZTP server (dhcp-oob):
sudo cat /var/lib/misc/dnsmasq.leases         # Check DHCP leases
sudo tail -f /var/log/nginx/ztp-access.log    # Check if switches are downloading configs

# On the switch (via Air console):
cat /var/log/autoprovision                    # ZTP log on the switch

# Automated check:
make validate-ztp                  # Validate via ZTP server
```

**Configuration errors?**
```bash
make validate                                 # Validate playbook syntax
cat output/<arch>/<site>/configs/core-01-config.sh  # Review generated config
```

**Network connectivity issues?**
```bash
# Verify MACs match between inventory and actual switch:
cat output/<arch>/<site>/inventory/host_vars/<switch>.yml
sudo cat /etc/dnsmasq.d/ztp.conf              # Check DHCP reservations on ZTP server
```

### Air Issues

**SSL certificate error on macOS (`CERTIFICATE_VERIFY_FAILED`)?**

Python on macOS does not use the system keychain by default. Install
the `certifi` certificate bundle inside your venv:

```bash
pip install certifi
```

Then retry the failed command.

**Air API authentication failing?**
```bash
make air-auth-test     # Test credentials and connectivity
```
- Verify your NGC API key (set via `make air-setup`) is correct and not expired — keys start with `nvapi-`
- Verify the Air instance URL is correct — re-run `make air-setup` and pick `[3] air_url` to update it

**Cannot SSH to Air nodes?**
```bash
make air-ssh-check         # Diagnose SSH key + password auth to jump hosts
make air-ssh-check FIX=1   # Auto-inject your SSH key if auth fails
make air-list              # Show SSH connection info for all nodes
make air-show              # Show current Air connection settings
```
- Ensure your SSH key path (set via `make air-setup`) matches the key registered in NGC
- If using a passphrase-protected key, load it into the agent: `eval $(ssh-agent) && ssh-add ~/.ssh/id_ed25519`
- If using an NGC Service API key (not personal), run `make air-ssh-check FIX=1` to inject your key

**Automated Air deploy failing mid-pipeline?** Fall back to the manual
procedure: [`docs/MANUAL_FALLBACK_GUIDE.md`](docs/MANUAL_FALLBACK_GUIDE.md).
You upload the topology through the Air web UI, SSH into `dhcp-oob`, and
run the Ansible roles by hand from there. Slower, but every step is
inspectable.

### LDAP Issues

```bash
make restart-ldap                             # Restart LDAP on switches (via OOB)
ldapsearch -x -H ldap://<server-ip>          # Test LDAP server directly
```

### Validation Failures

After deploying, `make validate-all` runs the full validation suite:
topology, ZTP, running-config comparison, and server checks. When a
stage fails, run the individual targets to narrow it down:

```bash
make validate-topology     # Air topology vs. wiremap
make validate-config       # Running switch config vs. generated config
make validate-servers      # Server bonds, VLANs, connectivity
make validate-ping-matrix  # Full server-to-server ping matrix across VLANs
```

- **`validate-config` reports diffs:** the switch is running a config
  that differs from the freshly generated one. Re-push with
  `make push-switch-configs`, or for a ZTP deployment re-run
  `make ztp-update` then reboot the affected switch. Cosmetic ordering
  differences (NVUE re-orders some stanzas on apply) are normalized by
  the comparison and should not be reported — if you see them, confirm
  you regenerated configs after the last Excel change.
- **`validate-servers` shows missing bonds or VLANs:** the server-side
  config did not land. Re-run `make deploy-servers` (direct SSH) or
  `make deploy-servers-via-jump` (Air, via the OOB jump host).
- **`validate-ping-matrix` flags failures:** confirm the VRF routing
  rules. INBAND members (compute/support/storage) can cross-ping; the
  GPU/East-West network is intentionally isolated, and OOB never leaks
  into INBAND — failures across those boundaries are *expected*. On the
  dual-plane `2-8-9-800` architecture, GPU↔GPU pings *across* planes
  are also expected to fail, since each plane is a separate fabric.
- **`validate-topology` fails:** the generated topology references a
  port or node the wiremap does not define. Regenerate with
  `make generate` and confirm the Wire Map sheet matches your node list.
