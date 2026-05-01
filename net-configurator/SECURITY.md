<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Security Policy

## Reporting a Vulnerability

Open a GitHub issue and include **SECURITY** in the title. Describe the
affected file(s), a minimal reproduction, and the impact you've observed.

## Scope

In scope:

- This repository's Python scripts, Ansible playbooks/roles, Jinja2
  templates, and Makefile
- Generated switch configurations that expose an exploitable flaw
  (e.g. template injection, weak defaults)
- Credential handling in the shared vault (`.era-secrets/air-secrets.yml`)

Out of scope:

- Vulnerabilities in upstream dependencies (Ansible, openpyxl, httpx,
  Cumulus Linux, NVIDIA Air itself) — please report those to the
  respective projects
- Issues in sample / placeholder credentials committed for local
  testing (`Cumu1usLinux!`, `nvidia`, `CHANGE_ME`) — these are
  documented placeholders, not secrets
- Social-engineering or physical-access scenarios

## Known Operational Risks

### Do not run on a multi-user host (until `sshpass` is retired)

Several validation playbooks — `playbooks/validate-ping-matrix.yml`,
`playbooks/validate-config.yml`, `playbooks/restart-ldap-switches.yml`,
and the Air `ProxyCommand` in `playbooks/vars/air_proxy.yml` — pass
switch / server passwords to `sshpass` via CLI arguments. On a
multi-tenant host (shared bastion, CI runner with other tenants, jump
box with other user accounts) those passwords are visible in
`ps auxww` to any local user while the task is running.

**Mitigation:** run this tool from a single-user host (your laptop,
a dedicated controller VM). If you must run on shared infrastructure,
ensure no other users have local shell access during
`make validate-*` / `make restart-ldap` / Air deployments.

## Credential Handling

This project generates Ansible inventories that contain switch, server,
and LDAP passwords. The defaults shipped in `output/<arch>/<site>/inventory/group_vars/all/secrets.yml`
are documented placeholders (e.g. `Cumu1usLinux!`) intended for
development and NVIDIA Air simulations. **For any real deployment you
MUST:**

1. Replace every password in `output/<arch>/<site>/inventory/group_vars/all/secrets.yml`
   before running `make deploy` / `make switch-ztp-deploy`.
2. Encrypt the file with `ansible-vault encrypt` before committing, or
   keep it outside version control entirely.
3. Rotate passwords on personnel change and on any suspected
   compromise. NGC API keys should be rotated at least every 90 days
   — re-run `make air-setup` to update the shared vault.

The Air credentials vault (`.era-secrets/air-secrets.yml`) is
gitignored and is created mode `0600` inside a mode `0700` directory.
If your vault password file (`.era-secrets/vault-pass`) is ever
exposed, rotate your NGC API key immediately and re-run
`make air-setup`.

### Pre-deployment credential checklist

Before `make deploy` or `make switch-ztp-deploy` against real hardware:

- [ ] Opened `output/<arch>/<site>/inventory/group_vars/all/secrets.yml` and replaced **every** placeholder password (`switch_ansible_password`, `server_ansible_password`, `ansible_become_password`, `switch_password`, `ldap_admin_password`, `ldap_user_default_password`, `status_page_password`).
- [ ] Ran `ansible-vault encrypt output/<arch>/<site>/inventory/group_vars/all/secrets.yml` (or kept the file outside version control).
- [ ] Verified none of the placeholders (`Cumu1usLinux!`, `nvidia`, `CHANGE_ME`, `Ldap@123`) appear in the encrypted file:
      `ansible-vault view output/<arch>/<site>/inventory/group_vars/all/secrets.yml | grep -E "Cumu1usLinux!|nvidia|CHANGE_ME|Ldap@123"` should return nothing.
- [ ] Rotated NGC API key within the last 90 days (`make air-setup`, select `[2] api_key`).
- [ ] Confirmed the deployment host is not shared with untrusted local users — some playbook tasks pass passwords to `sshpass` via CLI args, which are visible in `ps auxww`.

### On compromise

If you believe any credential has been exposed:

1. Rotate the affected credential at its source (NGC portal, LDAP, IPMI/BMC, etc.).
2. Re-run `make air-setup` and/or re-encrypt `secrets.yml`.
3. Redeploy affected switches — ZTP will pull the new password and apply it on next boot.

## Supported Versions

Security fixes are applied to `main` and to the most recent tagged
release. Older releases are not patched — please upgrade.
