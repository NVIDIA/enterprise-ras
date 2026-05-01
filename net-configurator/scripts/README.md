<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Scripts Directory

Utility scripts for ERA switch automation.

---

## excel_parser.py

Generates Ansible inventory from an Excel configuration template.

### Usage

```bash
# Via Makefile (recommended)
make generate ARCH=2-8-9-400

# Direct execution
python3 scripts/excel_parser.py --arch 2-8-9-400 --site default
```

### What It Does

- Reads the Excel file from `input/<arch>/<site>/<arch>.xlsx`
- Parses Settings, Nodes, VLANs & Profiles, and Wire Map tabs
- Generates `hosts` file with group structure
- Generates `host_vars/` for each switch and server
- Generates `group_vars/` merging source inventory settings with Excel data
- Assigns management IPs based on Wire Map OOB switch mappings

### Output

```
output/<arch>/<site>/inventory/
├── hosts
├── host_vars/*.yml
└── group_vars/
    ├── all/main.yml
    ├── all/secrets.yml
    ├── core.yml, oob.yml, servers.yml, switches.yml
```

---

## topology_generator.py

Generates NVIDIA Air topology JSON from the Excel Wire Map.

### Usage

```bash
# Via Makefile (recommended)
make topology ARCH=2-8-9-400
make validate-topology ARCH=2-8-9-400

# Direct execution
python3 scripts/topology_generator.py generate --arch 2-8-9-400 --site default
python3 scripts/topology_generator.py validate --arch 2-8-9-400 --site default
```

### What It Does

- Reads Wire Map from Excel (Air connections, data-plane links, management links)
- Creates nodes with correct OS images and hardware models
- Builds link topology between switches and servers
- Applies grid-based layout for clean visualization in Air
- Handles outbound internet links, disabled ports, duplicate dedup

### Output

```
output/<arch>/<site>/topology/<arch>-topology.json
```

---

## generate-node-instructions.py

Generates three pasteable Node Instruction bash scripts for manual Air
deployments (see `docs/MANUAL_FALLBACK_GUIDE.md`). Runs as step 4 of
`make generate` — there is no separate make target.

### Usage

```bash
# Part of the generate pipeline (recommended)
make generate ARCH=2-8-9-400

# Direct execution
python3 scripts/generate-node-instructions.py --arch 2-8-9-400 --site default
```

### What It Does

- Reads the generated inventory (`group_vars/all/main.yml`,
  `host_vars/oob-server-01.yml`) and topology JSON
- Emits three bash scripts that configure `air-oob-switch` (NVUE VLAN
  bridge), `oob-server-01` (IP forwarding + static IPs + NAT masquerade),
  and `dhcp-oob` (static IPs + apt prerequisites)
- File writes use **base64-encoded single-line commands** — heredocs are
  unreliable through Air's shell executor, so netplan/sysctl content is
  encoded inline
- Netplan always includes `eth0` as DHCP so `netplan apply` doesn't tear
  down Air's management interface

### Output

```
output/<arch>/<site>/topology/node-instructions/
├── air-oob-switch.sh
├── oob-server-01.sh
└── dhcp-oob.sh
```

Paste each file's contents into the Air GUI as a Node Instruction
(Type: **Shell**, Wait for network: **unchecked**) **before** starting
the simulation.

---

## import-excel.py

Imports a filled-out Excel template into the project.

### Usage

```bash
make import EXCEL=/path/to/your-config.xlsx
```

### What It Does

- Reads `architecture` and `site_name` from the Excel Settings tab
- Copies the file to `input/<arch>/<site>/<arch>.xlsx`
- Writes `.era-context` so subsequent `make` commands work without parameters

---

## utils.py

Shared utility functions used by both `excel_parser.py` and `topology_generator.py`.

### Functions

- `generate_mac(node, interface)` — deterministic MAC address generation (MD5-based)
- `classify_node(name)` — fine-grained role classification (core, oob, edge, compute, storage, support, k8s, bcme, infra, unknown)
- `is_switch(name)` — check if a node is a switch
- `is_valid_hostname(name)` — RFC1123 hostname validation

---

## Air API Scripts (`airlib/` + `air-*.py`)

Automate NVIDIA Air simulation lifecycle via REST API.

### Scripts

| Script | Makefile Target | Purpose |
|--------|----------------|---------|
| `air-setup.py` | `make air-setup` | **One-time onboarding wizard** — creates encrypted shared Air credentials vault |
| `air-deploy.py` | `make air-deploy` | Create simulation, configure SSH, start |
| `air-destroy.py` | `make air-destroy` | Teardown simulation + cleanup |
| `air-auth-test.py` | `make air-auth-test` | Verify API credentials |
| `air-list.py` | `make air-list` | List simulations |
| `air-budget-check.py` | `make air-budget` | Check resource budget |
| `air-connect.py` | `make air-connect` | Manual SSH config (fallback) |

### Library (`airlib/`)

| Module | Purpose |
|--------|---------|
| `api.py` | All Air REST API calls |
| `auth.py` | NGC + legacy authentication |
| `env.py` | Credential loading (shared Air vault + env vars) |
| `models.py` | Typed dataclasses (Simulation, SSHService, etc.) |
| `ssh.py` | SSH key utilities |
| `errors.py` | Exception hierarchy |
| `budget.py` | Budget formatting helpers |

### Usage

```bash
# One-time setup (per machine)
make air-setup                        # Wizard: NGC API key + SSH key → vault-encrypted

# Automated workflow
make air-auth-test ARCH=2-8-5-200     # Verify credentials
make air-deploy ARCH=2-8-5-200        # Create + start simulation
make air-full-deploy ARCH=2-8-5-200   # Generate + deploy + ZTP in one

# Manual fallback
make air-connect ARCH=2-8-5-200       # Enter SSH details interactively
make air-show ARCH=2-8-5-200          # Show current settings
```

Credentials live in `.era-secrets/air-secrets.yml` at the repo root (vault-encrypted, gitignored). Override per-run with `AIR_API_KEY` / `AIR_BASE_URL` / `AIR_SSH_KEY_PATH` environment variables.

---

## compare_excel_inventory_and_configs.py

Compares generated switch configs against source-of-truth reference configs.

### Usage

```bash
python3 scripts/compare_excel_inventory_and_configs.py [--no-generate] [--enterprise-ras PATH]
```

### What It Does

- Runs the full generation pipeline (Excel → inventory → configs)
- Normalizes NVUE commands (range expansion, port sorting)
- Diffs generated configs against `enterprise-ras` reference configs
- Reports missing, extra, and different lines per switch

---

## validate_excel.py

Validates an ERA Excel configuration file before import or generate.

### Usage

```bash
# Via Makefile (recommended)
make validate-excel EXCEL=/path/to/config.xlsx
make validate-excel ARCH=2-8-5-200

# Direct execution
python3 scripts/validate_excel.py input/2-8-5-200/default/2-8-5-200.xlsx
```

### What It Does

- Checks required sheets exist (Settings, Nodes, VLANs & Profiles, Wire Map)
- Validates Settings keys, IP/CIDR formats, MAC addresses, integer fields
- Checks Nodes for duplicate function names, duplicate management IPs, missing core switches
- Checks VLANs for valid IDs, duplicate names, overlapping subnets
- Detects duplicate switch port assignments in Wire Map (two systems on same port)
- Cross-validates: gateway within subnet, node IPs within mgmt_subnets, VLAN gateway within VLAN subnet

---

## normalize_nvue.py

Normalizes NVUE CLI config output for comparison (expands port ranges, sorts tokens).

### Usage

```bash
cat config.sh | python3 scripts/normalize_nvue.py
nv config show -o commands | python3 scripts/normalize_nvue.py
```

Used by `playbooks/validate-config.yml` to compare running config against generated config.

---

## validate_requirements.py

Validates generated configurations against architecture requirements extracted from PDFs.

### Usage

```bash
make validate-requirements ARCH=2-8-5-200
```

---

## extract_requirements.py

Extracts configuration requirements from architecture reference PDFs into draft YAML files for review.

### Usage

```bash
make extract-requirements
```

---

## create_test_site.py

Creates modified Excel copies for site validation testing. Remaps all IPs to a test range and sets a unique site name.

### Usage

```bash
python3 scripts/create_test_site.py
```

Creates test Excel files in `/tmp/` for all 3 architectures with remapped IPs (`192.168.x.y` → `10.100.x.y`, `172.16.x.y` → `10.200.x.y`).

---

## Shell Scripts

| Script | Purpose |
|--------|---------|
| `verify-ztp-server.sh` | Validate ZTP server health (nginx, dnsmasq, configs) |
| `debug-dnsmasq.sh` | Check dnsmasq configuration and logs |
| `debug-ztp-hostname.sh` | Test hostname detection from DHCP |
| `detect-interface.sh` | Identify network interfaces |
| `fix-dns.sh` | Repair DNS configuration issues |

---

## Configuration Workflow

```bash
# 1. Validate the Excel file
make validate-excel EXCEL=my-config.xlsx

# 2. Import filled Excel (sets context automatically)
make import EXCEL=my-config.xlsx

# 3. Generate everything (inventory + configs + topology)
make generate

# 4. Deploy
make switch-ztp-deploy
```

---

## Related Documentation

- [Air Deployment Guide](../docs/AIR_DEPLOYMENT_GUIDE.md)
- [ZTP Validation](../docs/ZTP_VALIDATION.md)
- [Main README](../README.md)
