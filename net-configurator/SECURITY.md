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

Password authentication still exposes secrets in the OS **process table**
(`ps auxww`) in two places while a task runs:

1. **Air `ProxyCommand`** (`playbooks/vars/air_proxy.yml`) passes the jump-host
   password via `sshpass -p '<pw>'` — visible to any local user on the **control
   node**.
2. **Validation probes** (`scripts/switch_health_probe.sh` and the per-switch/
   server fan-out in `validate-*`/`restart-ldap-switches`) pass a password as a
   **positional argument** — to the local probe invocation (visible on the
   **jump host**) and, for the switch-health sudo password, into a remote
   `bash -s -- '<pw>'` session (visible in `ps` on the **target switch**).

The SSH-auth password itself is now passed via the `SSHPASS` **environment
variable** (`sshpass -e`), not `-p`, in `validate-config` / `validate-ping-matrix`
/ `restart-ldap-switches` **and in the Air SSH helpers** (`scripts/airlib/ssh.py`,
used by `air-deploy` / `air-ssh-check`) — a prior `-p` argv exposure that has
since been fixed.
On a multi-tenant host (shared bastion, CI runner with other tenants, jump box
with other user accounts) the exposures in (1) and (2) above are still visible to
any local user during the task.

**Mitigation:** run this tool from a single-user host (your laptop,
a dedicated controller VM). If you must run on shared infrastructure,
ensure no other users have local shell access during
`make validate-*` / `make restart-ldap` / Air deployments.

The LDAP server provisioning role (`roles/ldap/tasks/main.yml`) no longer
exposes its bind/user passwords on the command line — `slappasswd` and
`ldapadd` now read the secret from a mode-`0600` file (`-T` / `-y`) or the
process environment, so the remaining `ps auxww` exposure is limited to the
`sshpass`-based playbooks listed above.

### Air bootstrap disables SSH host-key checking (accepted risk)

The password-auth SSH helpers in `scripts/airlib/ssh.py` (used by
`air-ssh-check` / `air-deploy` to verify access and inject the operator's key on
freshly-created Air jump hosts) run with `StrictHostKeyChecking=no` and
`UserKnownHostsFile=/dev/null`. This is inherent to the bootstrap: an Air sim's
hosts are ephemeral and have no pre-known host key on first contact, so a
network-position attacker who can impersonate the jump host during that brief
window could capture the server password. The password is now passed via
`SSHPASS` (above), and the window is the initial key-injection only; afterward
all access is key-based.

**Mitigation:** run `air-ssh-check`/`air-deploy` from a trusted network path to
the Air endpoint. This is **accepted risk** for the bootstrap flow; pinning a
TOFU host key would require an Air-API-provided fingerprint that the platform
does not expose.

### The OOB management network is the trust boundary

ERA provisions and manages switches over a dedicated Out-of-Band (OOB)
management network. Two of the protocols on that network are
unauthenticated/unencrypted by design (see the two risks below). The
security model assumes the **OOB network is physically or logically
isolated and carries no untrusted hosts.** An attacker with a foothold
on the OOB segment — able to ARP-spoof, run a rogue DHCP server, or
sniff traffic — can exploit both of the following. Treat OOB isolation
as a hard requirement, not a convenience.

### Zero-Touch Provisioning fetches and executes configuration over unauthenticated HTTP

During ZTP, a factory-fresh switch receives a provisioning URL via DHCP
option 239 and then downloads `ztp.sh`, its NVUE config script, its
`authorized_keys`, and its topology file over plain **HTTP**
(`roles/ztp-server/templates/ztp.sh.j2`). The config script is executed
as root. There is no transport encryption and no integrity check.

This is inherent to ZTP: a blank switch has no pre-installed trust
anchor before provisioning runs, so HTTPS would fall back to
`--no-check-certificate` (no real gain), and a checksum manifest served
over the same channel is rewritable by an active MITM. Genuine
integrity would require image-signed configs with a key baked into the
switch OS image — outside this project's control.

**Mitigations:**

- Run ZTP only on an isolated OOB provisioning segment with no untrusted
  hosts present during bring-up.
- The nginx ZTP vhost restricts the secret-bearing locations (`/scripts/`,
  `/configs/`, `/authorized_keys`) to the OOB provisioning subnet(s) with an
  `allow`/`deny all` rule and disables directory listing, so a host outside
  the OOB segment can neither enumerate nor fetch them. The allowed CIDRs
  default to `192.168.200.0/24` + `192.168.210.0/24`; override the
  `ztp_allow_subnets` group var if your provisioning network differs (a
  mismatch will block ZTP delivery).
- For environments where even that is unacceptable, use the **non-ZTP
  delivery path** (`make air-deploy NOZTP=1`, or pre-staged Node
  Instructions): configurations are placed on the switch at first boot
  without any HTTP fetch, eliminating this vector entirely.

### LDAP (optional feature) — accepted residual risks

LDAP is **opt-in and off by default** — it is provisioned only when the
Excel workbook sets `ldap_enabled: Yes` (or `LDAP=1` is passed explicitly).
Deployments that do not enable LDAP are unaffected by everything in this
section. Because LDAP is optional and the residual risks all require either
the OOB network as a trust boundary or a prior local-shell compromise of the
LDAP/jump host, the project **accepts and documents** the following rather
than shipping TLS-certificate infrastructure for an optional feature. The
two argv/file-permission risks in this class were already fixed (see below).

When you do enable LDAP, deploy it **only on an isolated, trusted OOB
management network** and treat the LDAP bind credential as exposed to anyone
with OOB-network access or a local shell on the LDAP host.

- **Switch↔LDAP binds are not encrypted.** The generated switch config
  (`roles/core/templates/core_nvue_cli.j2` and the OOB/GSL equivalents) binds
  with `nv set system aaa ldap ...` and **no TLS directive**, so the bind DN,
  bind secret, and user-auth traffic cross the OOB network in cleartext. NVUE
  supports LDAPS/STARTTLS, but enabling it requires a server certificate for
  the LDAP host **and** CA distribution to every switch — infrastructure this
  project does not provide. *Accepted; mitigated by the isolated-OOB
  requirement above.*
- **LDAP password hashes use `{SSHA}`** (salted SHA-1). `slappasswd` in
  `roles/ldap/tasks/main.yml` runs without `-h`, so OpenLDAP's default
  `{SSHA}` scheme hashes `olcRootPW`, the `cn=admin` bind DN, and every
  provisioned user. `{SSHA}` is cheap to brute-force offline, so an attacker
  who already has read access to the slapd database (a prior compromise of the
  LDAP host) could recover passwords. *Accepted; the precondition is filesystem
  read on the LDAP host.*
- **debconf preseed interpolates the admin password into a shell `echo`.**
  The slapd preseed task pipes `echo "slapd … {{ ldap.admin_password }}"` to
  `debconf-set-selections` (with `no_log: true`); backticks/`$()` in the
  operator-set admin password would expand. The value is operator-controlled
  (not OEM-Excel-supplied), so this is low-risk. *Accepted.*

**Already fixed (not accepted risk):** LDAP passwords are no longer passed on
the command line — `slappasswd`/`ldapadd` read the secret from a mode-`0600`
file via `-T`/`-y`, and the generated LDIF files are `mode: '0600'`
and removed after use.

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
