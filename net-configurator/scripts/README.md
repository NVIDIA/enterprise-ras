<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Scripts Directory

Utility scripts for ERA switch automation. These are the scripts used to fill
out an Excel, generate inventory/configs/topology, and deploy — you normally
invoke them through `make`, but the direct invocations are documented here too.

Only the operator-facing entry points are listed below. Other files in this
directory are shared library modules imported by those scripts (for example
`asn_allocation.py`, `loopback_allocation.py`, `oob_reserved.py`) or internal
helpers prefixed with `_`; neither is meant to be run directly.

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
- Parses the intake-form sheets (`Deployment`, `Switch Data`, `Host Data`, `Network Data`, `Wiremap`; ADR-0064)
- Generates `hosts` file with group structure
- Generates `host_vars/` for each switch and server
- Generates `group_vars/` merging source inventory settings with Excel data
- Assigns management IPs based on Wiremap OOB switch mappings

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

Generates NVIDIA Air topology JSON from the Excel Wiremap.

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

- Reads the Wiremap from Excel (Air connections, data-plane links, management links)
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

Generates pasteable Node Instruction bash scripts for manual Air deployments
(see `docs/MANUAL_FALLBACK_GUIDE.md`). Runs as a step of `make generate` — there
is no separate make target.

### Usage

```bash
# Part of the generate pipeline (recommended)
make generate ARCH=2-8-9-400

# Direct execution
python3 scripts/generate-node-instructions.py --arch 2-8-9-400 --site default
```

### What It Does

- Reads the generated inventory and topology JSON
- Emits bash scripts that configure the OOB/management nodes (VLAN bridge, IP
  forwarding + static IPs + NAT, DHCP prerequisites)
- File writes use **base64-encoded single-line commands** — heredocs are
  unreliable through Air's shell executor, so netplan/sysctl content is
  encoded inline
- Netplan always includes `eth0` so `netplan apply` doesn't tear down Air's
  management interface

### Output

```
output/<arch>/<site>/topology/node-instructions/
```

Paste each file's contents into the Air GUI as a Node Instruction
(Type: **Shell**, Wait for network: **unchecked**) **before** starting
the simulation.

---

## prune_stale_artifacts.py

Last step of `make generate`. Removes per-node artefacts left behind when a
node was renamed or disabled in the workbook and the site was regenerated —
without touching anything the generator did not write.

### Usage

```bash
# Part of the generate pipeline
make generate ARCH=2-8-9-400 SITE=default

# Preview (no start marker present, so adopt-all is needed to evaluate a site)
python3 scripts/prune_stale_artifacts.py --arch 2-8-9-400 --site default --dry-run --adopt-all

# What `make generate` runs: marker before the generators, prune after them
python3 scripts/prune_stale_artifacts.py --arch 2-8-9-400 --site default --mark-start
python3 scripts/prune_stale_artifacts.py --arch 2-8-9-400 --site default
```

### What It Does

- Records the per-node artefacts this run *wrote* — `inventory/host_vars/<node>.yml`,
  `configs/<node>-config.sh`, `topology/node-instructions/<node>.sh` modified
  after the `.generate-started` marker (or already listed) whose node is
  current — in `output/<arch>/<site>/generated-manifest.json`. A matching file
  that this run did not write (e.g. an operator's `configs/support-01-config.sh`)
  is never adopted, so it can never be pruned later. `--adopt-all` skips the
  marker check for the one-off adoption of a site generated before the manifest.
- "Current" = a host in `inventory/hosts`; for `node-instructions/` also a
  node of the Air topology JSON and, only while that topology is in L2
  OOB-uplink mode, the legacy-L2 `air-oob-switch` / `dhcp-oob` /
  `oob-server-01` scripts (switching the site to L3 prunes them)
- Deletes a file in one of those classes **only** if it is listed in the
  previous manifest *and* its node is no longer current
- Warns about (and keeps) files in those classes it did not record —
  operator-added files, or files generated before the manifest existed
- Never looks at `group_vars/all/secrets.yml`, `hosts`, `main.yml`, topology
  JSON or reports; host_vars of current hosts (including Air
  `ansible_host`/`ansible_port`/`ansible_user`) are never candidates

---

## import-excel.py

Imports a filled-out Excel template into the project.

### Usage

```bash
make import EXCEL=/path/to/your-config.xlsx
```

### What It Does

- Reads `architecture` and `site_name` from the Excel `Deployment` sheet
- Copies the file to `input/<arch>/<site>/<arch>.xlsx`
- Writes `.era-context` so subsequent `make` commands work without parameters

---

## utils.py

Shared utility functions used by both `excel_parser.py` and `topology_generator.py`.

### Functions

- `generate_mac(node, interface)` — deterministic MAC address generation (MD5-based)
- `classify_node(name)` — fine-grained role classification (core, oob, edge, compute, storage, support, infra, unknown)
- `is_switch(name)` — check if a node is a switch
- `is_valid_hostname(name)` — RFC1123 hostname validation

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

- Checks required intake sheets exist (`Wiremap`, `Deployment`, `Switch Data`, `Host Data`, `Network Data`); a workbook in the older `Settings`/`Nodes`/`VLANs & Profiles`/`Wire Map` layout is refused with a pointer to `make convert-workbook`
- Validates Deployment settings, IP/CIDR formats, MAC addresses, integer fields
- Checks Switch Data / Host Data for duplicate function names, duplicate management IPs, missing core switches
- Checks VLANs for valid IDs, duplicate names, overlapping subnets
- Detects duplicate switch port assignments in the Wiremap (two systems on same port)
- Cross-validates: gateway within subnet, node IPs within the resolved OOB VLAN subnet(s) (VRF `OOB` rows in Network Data + each OOB switch's Switch Data `OOB VLAN` column), VLAN gateway within VLAN subnet
- Flags deployments exceeding the architecture's single-tier max SU count
- Warns when an active server has more than one Display=Yes OOB row (Air's plain Ubuntu can't bond two OOB links — CRA rule)
- Warns once per SU when every GPU/CPU Wiremap row of that SU's compute nodes is `Display in Air = No` (Air-only; the sim would have no data-plane). Interactively it offers to flip those rows to `Yes` (workbook backed up to `archive/<date>/` first, then re-validated); `AIR_DISPLAY_FIX=yes|no` decides without a prompt; a non-TTY run only warns

---

## check_secrets.py

Checks that the Cumulus-facing passwords in `secrets.yml` pass the ERA
switch-password policy (ADR-0078: the Cumulus password-security rule set —
≥ 8 chars, lower/upper/digit/special, not the switch username — plus not a
placeholder such as `CHANGE_ME`) and that `switch_ansible_password` is
present. Run by `make generate` (Step 0b) and by every switch deploy / ZTP
target; exit 1 stops the target (`SECRETS_PASSWORD_POLICY=placeholder`
relaxes to placeholder/empty/username only; `GENERATE_SKIP_VALIDATE=1` /
`DEPLOY_SKIP_VALIDATE=1` bypass).

### Usage

```bash
python3 scripts/check_secrets.py --arch 2-8-5-200 [--site default]
python3 scripts/check_secrets.py --file path/to/secrets.yml
python3 scripts/check_secrets.py --file path/to/secrets.yml --policy placeholder
```

### What It Does

- Picks the file the deploy reads: `output/<arch>/<site>/inventory/group_vars/all/secrets.yml`, else `inventories/secrets.yml`, else the `.example`
- Gates only `switch_password` and `switch_ansible_password`; server-side, bootstrap, LDAP and status-page keys are left alone
- Follows a `{{ other_key }}` alias to the key it names; a `!vault` scalar or any other Jinja expression on a switch key is reported as *not checked* (exit 0), never as viable; a `!vault` scalar on an unchecked key is ignored
- Prints key name + failed rule(s), never a value
- Vault-encrypted or missing file: note, exit 0

---

## arch_scaling.py

Scaling tables for each ERA architecture, used by `validate_excel.py` for the
SU-cap and OOB switch-count checks.

- `ARCH_SCALING` / `get_tier(arch, su_count)` / `max_single_tier_su(arch)` —
  single-tier fan-out tiers (expected OOB switch count + notes). Not every
  arch has one: `ARCH_MULTI_TIER_ONLY` names the arches that are leaf-spine
  from SU=1 by design (`2-4-5-800`), with the reason.
- `OOB_SWITCHES_BY_SU[arch][su]` — expected OOB switch count at **every**
  supported SU, single- or multi-tier (covers the `largescale` workbooks).
- `expected_oob_switches(arch, su_count)` → `(count, note)` or `None`; tier
  first, then the per-SU table. When it is `None` the validator emits
  `No OOB fan-out data for <arch> at SU=<n>; the OOB switch-count check was
  skipped` rather than staying silent.
- `MAX_SUPPORTED_SU` / `max_supported_su(arch)`, `node_name_to_su(name)`.

---

## _valid_archs.py + valid_archs.yml

The supported-architecture registry. `valid_archs.yml` is **generated** from the
architecture models and committed; `_valid_archs.py` is the one reader
(`from _valid_archs import VALID_ARCHS`) used by `validate_excel.py`,
`import-excel.py`, `_era_context.py`, `_excel_context.py` and
`_check_ldap_enabled.py`. The Makefile reads the same file for its
`VALID_ARCHS`. Do not edit either by hand — `tests/test_arch_registry_is_consistent.py`
fails on a hand-edited registry or on a reintroduced literal list. Adding an
arch is a model change plus a regeneration, not a search-and-replace.

`python3 scripts/_valid_archs.py` prints one arch per line.

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
| `air-ssh-check.py` | `make air-ssh-check` | Check / fix SSH key access to jump hosts |
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

## Shell Scripts

| Script | Purpose |
|--------|---------|
| `debug-dnsmasq.sh` | Check dnsmasq configuration and logs |
| `detect-interface.sh` | Identify network interfaces |

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
