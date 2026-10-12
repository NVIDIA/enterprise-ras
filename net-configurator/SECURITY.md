<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Security Policy

## Reporting a Vulnerability

**Do not open a public GitHub issue for a security report.** The scope below
includes flaws in generated switch configurations and in credential handling;
a public report discloses those against live network fabric before a fix
exists. Please use one of the coordinated-disclosure channels instead:

1. **NVIDIA PSIRT** — email **psirt@nvidia.com**, or use the reporting form at
   <https://www.nvidia.com/en-us/security/>. This is the preferred route and
   the one to use if you are unsure.
2. **GitHub private vulnerability reporting** — the *Security* tab →
   *Report a vulnerability*, which opens a private advisory visible only to
   the maintainers.

In your report, please include the affected file(s), a minimal reproduction,
the impact you've observed, and the release or commit you tested against.
We will acknowledge your report and coordinate disclosure timing with you.

Non-security bugs, questions, and feature requests are welcome as ordinary
public GitHub issues.

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
2. **`restart-ldap-switches`** and **`push-switch-configs`** hand the password to
   the task through Ansible's `environment:` / the task text, which Ansible's
   own `/bin/sh -c` wrapper carries in its argv (visible on the **jump host**).

The validation playbooks (`validate-ztp`, `validate-servers`, `validate-config`,
`validate-switch-health`, `validate-oob-bgp`, `validate-ping-matrix`) and their
probe scripts no longer do this: the password reaches the task on **stdin**,
the task exports it as `SSHPASS` for `sshpass -e`, and a remote `sudo` reads
it on stdin — never a positional argument, never shell text (ADR-0090). The
Air SSH helpers (`scripts/airlib/ssh.py`, used by `air-deploy` /
`air-ssh-check`) also use `sshpass -e`.
On a multi-tenant host (shared bastion, CI runner with other tenants, jump box
with other user accounts) the exposures in (1) and (2) above are still visible to
any local user during the task.

**Mitigation:** run this tool from a single-user host (your laptop,
a dedicated controller VM). If you must run on shared infrastructure,
ensure no other users have local shell access during
`make restart-ldap` / `make push-switch-configs` / Air deployments.

The LDAP server provisioning role (`roles/ldap/tasks/main.yml`) no longer
exposes its bind/user passwords on the command line — `slappasswd` and
`ldapadd` now read the secret from a mode-`0600` file (`-T` / `-y`) or the
process environment, so the remaining `ps auxww` exposure is limited to the
`sshpass`-based playbooks listed above.

### Air API key only travels over HTTPS; SSH helpers do not forward your agent

Every Air API call carries the NGC API key as a bearer token. `make air-setup`
accepts only `https://` Air URLs, and every Air script refuses to start when
the URL from the vault or `AIR_BASE_URL` is not `https://`. The SSH commands
built by `scripts/airlib/ssh.py` (including the one `air-deploy` prints for
reaching a sim) do not use agent forwarding (`-A`); add it yourself only for a
host you trust, since anyone with root on that host can use your forwarded
keys while the session is open.

### Rendered switch configs are not left on the switch

A rendered `<host>-config.sh` holds the LDAP bind password when LDAP is on.
`make push-switch-configs` copies it to a private `mktemp` file (mode `0600`,
random name) and deletes it after it has run, whether or not it succeeded.
ZTP (`ztp.sh`) downloads it the same way and deletes it once it has been
sourced; `/tmp/config-load.log` and `/tmp/config-apply.log` are written mode
`0600`. The ZTP server's `/opt/ztp/manual-ztp.sh` helper reads the switch
password from `SSHPASS` or a no-echo prompt and passes it with `sshpass -e`,
never on the command line.

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
include documented defaults. `Cumu1usLinux!` is allowed for switch passwords
by `make secrets`, `make generate` and deploy checks, without an override on
Air or physical targets. This is a tool policy, not a statement that a
published password is private. Other placeholders such as `CHANGE_ME` remain
rejected; the development-only opt-in applies to those remaining placeholders
(see `docs/SECRETS_AND_VAULT.md`). The enabled status page still rejects the
published default and needs a dedicated password.

1. Use unique passwords for production. `make secrets ARCH=<arch> [SITE=<site>]`
   checks switch passwords and prompts for LDAP when the workbook or inventory
   enables it. Disabled LDAP skips both LDAP passwords; unknown deployment
   state still checks them. Only shared templates offer a default-no LDAP choice.
2. Encrypt the file with `ansible-vault encrypt` before committing (the
   wizard offers this step), or keep it outside version control entirely.
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

- [ ] Reviewed passwords for the services this deployment enables and chose
      unique values for production. `Cumu1usLinux!` is allowed for switches;
      unused LDAP credentials can be left unchanged.
- [ ] Ran `make secrets ARCH=<arch> [SITE=<site>]` and addressed any rejected
      values for active services. Status-page credentials must be dedicated.
- [ ] Ran `ansible-vault encrypt output/<arch>/<site>/inventory/group_vars/all/secrets.yml`
      (or kept the file outside version control).
- [ ] Rotated NGC API key within the last 90 days (`make air-setup`, select `[2] api_key`).
- [ ] Confirmed the deployment host is not shared with untrusted local users — the Air `ProxyCommand` (`sshpass -p`) and `restart-ldap-switches` / `push-switch-configs` (Ansible's `/bin/sh -c` wrapper) still put passwords in process arguments, which are visible in `ps auxww` (see [Known Operational Risks](#known-operational-risks)).

### On compromise

If you believe any credential has been exposed:

1. Rotate the affected credential at its source (NGC portal, LDAP, IPMI/BMC, etc.).
2. Re-run `make air-setup` and/or re-encrypt `secrets.yml`.
3. Redeploy affected switches — ZTP will pull the new password and apply it on next boot.

## Supported Versions

Security fixes are applied to `main` and to the most recent tagged
release. Older releases are not patched — please upgrade.
