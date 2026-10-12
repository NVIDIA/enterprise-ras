<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# ZTP Validation

This document describes how to validate that ZTP configuration was successfully applied to switches.

## Overview

ZTP validation verifies that switches have been properly configured via ZTP. There are **two** playbooks for two network-access scenarios:

- **`validate-ztp`** (canonical, recommended) — runs on the inventory jump host (the `[jump]` group: `dhcp-oob` in L2 OOB mode, `utility` in L3 OOB mode) and uses sshpass to reach each switch. Works from your laptop (Ansible connects to the jump host, which connects to switches) or from the jump host itself (e.g. inside an Air simulation). No requirement that the control host can reach switches directly.
- **`validate-ztp-direct`** — Ansible connects directly from the control host to each switch's `ansible_host`. Use this on-prem when your workstation is on the management network, or in an Air laptop flow where `ansible_host` points to Air's external SSH jump. It is the validation path for a physical (`deploy_in_air = No`) site, which has no Air jump host.

`validate-ztp-direct` passes a switch only when the SSH command succeeded, the
switch reports the inventory hostname, **and** NVUE's applied hostname matches
it (the generated config was applied). A reachable switch that still has a
factory or wrong configuration fails. The make target exits with the
playbook's own status, so a failed run fails the target even though its output
is filtered, and a successful run with no output passes.

### One-Command Validation

To run all validations at once:

```bash
make validate-all ARCH=<type>
```

This runs **five phases** in sequence:

1. **Topology validation** (`make validate-topology`) -- Compares the generated Air topology JSON against the Excel Wiremap to ensure all connections, interfaces, and node definitions match.
2. **Config comparison** (`make validate-config`) -- Compares the running NVUE configuration on each switch against the generated config scripts to detect drift or missing commands.
3. **ZTP validation** (`make validate-ztp`) -- Connects to each switch (via the jump host) and verifies SSH access, hostname, Cumulus version, NVUE config, BGP/EVPN status, and interface state.
4. **Switch operational health** (`make validate-switch-health`) -- Clean config apply + BGP sessions Established + EVPN ES/VNI + interface state, in a single per-switch SSH session.
5. **Server validation** (`make validate-servers`) -- Checks server network config (bonds, VLANs, LLDP, gateway/internet connectivity) and cross-pings between server roles. Auto-reported **N/A** on switches-only sims.

Reports from each check are saved to `output/<arch>/<site>/reports/`. If `status_page_enabled=Yes` is set in the Excel Deployment sheet, the reports are also uploaded to the status page.

To access the status page when enabled, open a browser to the HTTP service URL (shown in `make air-list` output). The page uses basic auth -- default credentials are username `era` and the `status_page_password` from `secrets.yml` (default `CHANGE_ME` — set a real value; it does **not** fall back to `switch_password`).

### All validation commands

| Command | What it checks |
|---------|----------------|
| `make validate-all` | Runs the five phases above in order (via the jump host). |
| `make validate-excel EXCEL=<file>` | Pre-import Excel checks: structure, IPs, ports, duplicates, single-tier SU cap, mgmt-IP collisions, OOB-uplink port rules. |
| `make validate-topology` | Generated Air topology JSON matches the Excel Wiremap. |
| `make validate-config` | Running switch config vs the generated config (drift). |
| `make validate-ztp` | ZTP success on switches via the jump host (SSH/hostname/version/NVUE/BGP/EVPN/interfaces). |
| `make validate-ztp-direct` | Same as `validate-ztp` but Ansible connects directly to each switch (on-prem / same-network use). |
| `make validate-switch-health` | Tier-1 operational health: clean apply + BGP Established + EVPN ES/VNI + interface state. STORAGE-VRF external-eBGP down peers are a non-gating WARN (see `make fix-ext-storage`). |
| `make validate-oob-bgp` | Gating OOB↔CSL BGP check — asserts every OOB-switch BGP neighbor is Established (L3 OOB only; N/A otherwise). Runs as part of `validate-ztp`. |
| `make validate-servers` | Server config: bonds, VLANs, LLDP, gateway/internet connectivity, cross-role pings. |
| `make validate-ping-matrix` | Full server-to-server ping matrix across all VLANs. Fail-closed: exits non-zero if any server returned no results (`FETCHFAIL`/`NODATA` in the report) or any ping result is unexpected. Collection from the jump runs in batches of `collect_batch_size` (32) concurrent SSH sessions; override with `-e`. |

The individual commands below are available for targeted troubleshooting.

## Quick Start

In most cases, just use:

```bash
make validate-ztp ARCH=<type>
```

This works both from a laptop (Ansible tunnels to the `[jump]` host — `utility` in L3 OOB, `dhcp-oob` in legacy L2) and from the jump host itself (inside an Air sim).

Use the direct variant only when running on-prem with laptop → switch reachability:

```bash
make validate-ztp-direct ARCH=<type>
```

## What Gets Validated

The validation playbook checks the following for each switch:

### All Switches
- **SSH Connectivity**: Verifies that the switch is reachable via SSH
- **Hostname**: Confirms the hostname matches the inventory
- **Cumulus Linux Version**: Reports the installed version
- **NVUE Config**: Verifies startup.yaml exists and is applied
- **Bridge Configuration**: Checks bridge domain configuration
- **Interface Status**: Reports number of interfaces that are up

### Core Switches Only
- **BGP Status**: Verifies BGP is enabled
- **BGP Neighbors**: Reports number of BGP neighbors configured
- **EVPN Status**: Verifies EVPN is enabled

## Validation Playbooks

Two playbooks back this system:

- **`playbooks/validate-ztp.yml`** — `hosts: jump`. Pulls running state from each switch via sshpass and reports from the bastion. Invoked by `make validate-ztp`.
- **`playbooks/validate-ztp-direct.yml`** — `hosts: core oob`. Connects Ansible directly to each switch's `ansible_host`. Invoked by `make validate-ztp-direct`.

Both:

1. Connect to each switch, run validation checks appropriate for the switch type
2. Display detailed per-switch results and a final summary
3. Exit non-zero if any validation fails

## Manual Usage

```bash
# Canonical — works from laptop (tunnels via the [jump] host) or from the jump host itself
ansible-playbook -i output/<arch>/<site>/inventory/hosts playbooks/validate-ztp.yml

# Direct — on-prem / requires workstation→switch reachability
ansible-playbook -i output/<arch>/<site>/inventory/hosts playbooks/validate-ztp-direct.yml

# Limit scope (works with either playbook)
ansible-playbook -i output/<arch>/<site>/inventory/hosts playbooks/validate-ztp-direct.yml --limit oob
ansible-playbook -i output/<arch>/<site>/inventory/hosts playbooks/validate-ztp-direct.yml --limit core
ansible-playbook -i output/<arch>/<site>/inventory/hosts playbooks/validate-ztp-direct.yml --limit oob-switch-01

# Verbose
ansible-playbook -i output/<arch>/<site>/inventory/hosts playbooks/validate-ztp.yml -v
```

## Output Example

```
==========================================
Switch: oob-switch-01 (192.168.1.11)
==========================================
✓ SSH Reachable:           True
✓ Hostname Matches:        True (oob-switch-01)
✓ Cumulus Version:         5.18.0
✓ NVUE Config Exists:      True
✓ NVUE Config Applied:     True
✓ Bridge Domains:          1
✓ Interfaces Up:           12

==========================================
Switch: core-01 (192.168.200.201)
==========================================
✓ SSH Reachable:           True
✓ Hostname Matches:        True (core-01)
✓ Cumulus Version:         5.18.0
✓ NVUE Config Exists:      True
✓ NVUE Config Applied:     True
✓ BGP Enabled:             True
✓ BGP Neighbors:           2
✓ EVPN Enabled:            True
✓ Bridge Domains:          1
✓ Interfaces Up:           45

==========================================
VALIDATION SUMMARY
==========================================
Total Switches:            5
Successful:                5
Failed:                    0
==========================================
```

## Adding Custom Validations

To add additional validations, edit `playbooks/validate-ztp-direct.yml` and add new tasks. For example:

```yaml
- name: Check custom application is running
  shell: systemctl is-active my-custom-app
  register: app_status
  delegate_to: "{{ validation_delegate }}"
  ignore_errors: true
  when: 
    - ssh_check is succeeded
    - "'custom-group' in group_names"

- name: Update validation results with custom check
  set_fact:
    validation_result:
      # ... existing checks ...
      custom_app_running: "{{ app_status.stdout == 'active' }}"
```

Then update the display task to show your custom validation:

```yaml
- name: Display detailed results
  debug:
    msg: |
      ...
      ✓ Custom App Running:      {{ validation_result.custom_app_running }}
```

## Troubleshooting

### SSH Connection Failures

If SSH connections fail:

1. Verify SSH keys are properly deployed on the ZTP server (the `[dhcp]` group: `external-dhcp` in L3 OOB, `dhcp-oob` in legacy L2):
   ```bash
   ansible dhcp -i output/<arch>/<site>/inventory/hosts -m shell -a "cat /var/www/ztp/authorized_keys"
   ```

2. Verify switches have pulled the ZTP configuration:
   ```bash
   ansible dhcp -i output/<arch>/<site>/inventory/hosts -m shell -a "tail -20 /var/log/nginx/access.log"
   ```

3. Test SSH manually:
   ```bash
   ssh cumulus@<switch-ip> hostname
   ```

4. Re-run ZTP setup to redeploy SSH keys:
   ```bash
   make ztp-setup ARCH=<type>
   ```

### Hostname Mismatches

If hostnames don't match:

1. Check inventory file (`output/<arch>/<site>/inventory/hosts`) for correct hostnames
2. Verify the ZTP configuration was applied (check `/etc/nvue.d/startup.yaml` on switch)
3. Re-run ZTP on the affected switch

### `make validate-ztp` Can't Reach Switches from the Jump Host

`validate-ztp` runs on the `[jump]` group (`utility` in L3 OOB, `dhcp-oob` in legacy L2) and expects that host to sshpass into each switch at its `ansible_host` IP:

1. Verify the jump host is reachable from the control host:
   ```bash
   ansible jump -i output/<arch>/<site>/inventory/hosts -m ping
   ```

2. Check that the jump host can reach the switches:
   ```bash
   ansible jump -i output/<arch>/<site>/inventory/hosts -m shell -a "ping -c 1 192.168.200.2"
   ```

3. Verify SSH from the jump host to a switch (this is what sshpass uses; `sshpass` is installed by `make validate-ztp` on first run, so run that once — or `apt-get install sshpass` on the jump host — before this step on a fresh sim):
   ```bash
   ansible jump -i output/<arch>/<site>/inventory/hosts -m shell -a "sshpass -p '<password>' ssh -o StrictHostKeyChecking=no cumulus@192.168.200.2 hostname"
   ```

### NVUE Config Not Applied

If `nvue_config_applied` is False:

1. Check if the startup config exists on the switch:
   ```bash
   ansible <switch-name> -i output/<arch>/<site>/inventory/hosts -m shell -a "ls -l /etc/nvue.d/startup.yaml"
   ```

2. Check for NVUE errors:
   ```bash
   ansible <switch-name> -i output/<arch>/<site>/inventory/hosts -m shell -a "nv config show -o json"
   ```

3. Review ZTP logs on the switch:
   ```bash
   ansible <switch-name> -i output/<arch>/<site>/inventory/hosts -m shell -a "tail -50 /var/log/autoprovision"
   ```

## Integration with CI/CD

The validation playbook can be integrated into CI/CD pipelines:

```bash
# In your CI/CD script — pick the variant matching your runner's network access
ansible-playbook -i output/<arch>/<site>/inventory/hosts playbooks/validate-ztp.yml || exit 1
```

The playbook will return a non-zero exit code if any validation fails, causing the CI/CD pipeline to fail.

## Network Access Scenarios

### Scenario 1: Inside an Air simulation (from the jump host)
Use `make validate-ztp` — Ansible runs locally on the `[jump]` host (`utility` in L3 OOB, `dhcp-oob` in legacy L2) and sshpass-es to switches on the OOB network.

### Scenario 2: Laptop with Air deployment
Use `make validate-ztp` — Ansible tunnels through Air's external SSH to the jump host, which sshpass-es to switches. This is the default universal path.

### Scenario 3: On-prem lab with direct workstation→switch reachability
Use `make validate-ztp-direct` — skips the jump host entirely, SSHing straight from your workstation to each switch.

### Scenario 4: Mixed access
Edit the inventory to set `ansible_ssh_common_args` or use jump hosts for custom routing.

## Workflow Integration

Typical ZTP workflow with validation:

```bash
# 1. Import Excel and generate configurations
make import EXCEL=your-config.xlsx
make generate ARCH=<type>

# 3. Deploy ZTP server
make ztp-setup ARCH=<type>

# 4. Boot switches (wait for ZTP to complete)

# 5. Validate deployment
make validate-ztp ARCH=<type>
```

## Scheduled Validation

You can set up scheduled validation using cron:

```bash
# On the ZTP server (external-dhcp in L3 OOB, dhcp-oob in legacy L2), add to crontab:
0 */6 * * * cd /path/to/repo && ansible-playbook -i output/<arch>/<site>/inventory/hosts playbooks/validate-ztp.yml >> /var/log/ztp-validation.log 2>&1
```

This runs validation every 6 hours and logs the results.

## See Also

- [ZTP Setup Documentation](../README.md)
- [Ansible Documentation](https://docs.ansible.com/)
- [NVUE Documentation](https://docs.nvidia.com/networking-ethernet-software/cumulus-linux/System-Configuration/NVIDIA-User-Experience-NVUE/)
