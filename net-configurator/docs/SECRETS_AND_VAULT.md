<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Secrets Management and Ansible Vault

This project uses two separate secret stores, each vault-encryptable:

| Store | Path | Contents | Scope |
|-------|------|----------|-------|
| **Shared Air vault** | `.era-secrets/air-secrets.yml` (repo-local, gitignored) | NGC API key, Air username, SSH key path | Per-checkout, shared across every arch/site in the repo |
| **Per-deployment secrets** | `output/<arch>/<site>/inventory/group_vars/all/secrets.yml` | Switch, server, sudo, LDAP passwords | Per-deployment — can legitimately differ per customer |

Only Ansible playbooks consume the per-deployment `secrets.yml`. Only the Air Python scripts consume the shared Air vault.

## Shared Air Vault

### Create it (one-time per checkout)

```bash
make air-setup
```

The wizard:

1. Verifies `ansible-vault` is installed.
2. Detects any existing vault and lets you update fields without re-entering unchanged ones.
3. Prompts for:
   - **NGC API key** — hint points you at <https://org.ngc.nvidia.com/account/api-keys>. Confirm the top-right account selector is correct, click **Generate Personal Key**, and copy the value (starts with `nvapi-`).
   - **Air username** — leave blank for NGC Air 2.0; email for legacy Air.
   - **SSH key path** — auto-detects `~/.ssh/id_ed25519`, `id_rsa`, `id_ecdsa`; offers to generate a new ed25519 key if none exist.
4. Asks whether to save the vault password to `.era-secrets/vault-pass` (mode 0600) or prompt every run.
5. Encrypts the YAML and writes it to `.era-secrets/air-secrets.yml` (mode 0600).

### Storage location

The vault lives inside the repo at `.era-secrets/` (gitignored). Keeping it repo-local means:

- Users working in restricted environments (no write access outside the project directory) can still use the wizard.
- Backing up or transferring a checkout to another machine carries the vault with it.
- Multiple checkouts on the same machine each get their own vault — good isolation if you want to separate work and test credentials.

If you have several checkouts and want them to share a vault, symlink `.era-secrets/` to a single source directory.

### Precedence for Air credentials

1. Shell environment variables — `AIR_API_KEY`, `AIR_USERNAME`, `AIR_SSH_KEY_PATH`, `AIR_BASE_URL`. Highest priority; use for CI or one-off overrides.
2. Shared vault — the everyday default, populated by `make air-setup`.

The Air URL (`air_url` in the vault, overridable via `AIR_BASE_URL`) is stored in
the shared vault alongside the credentials, selected during `make air-setup`. The
per-deployment Excel and inventory do not carry Air credentials or URLs — one
checkout, one Air instance.

### Edit, view, or rotate

```bash
# Edit in-place (decrypts into editor, re-encrypts on save)
ansible-vault edit .era-secrets/air-secrets.yml

# View contents
ansible-vault view .era-secrets/air-secrets.yml

# Change vault password
ansible-vault rekey .era-secrets/air-secrets.yml
```

Or just re-run `make air-setup` — it detects the existing vault and offers per-field updates.

### Vault password file (optional)

If you opt to save the vault password, it lives at `.era-secrets/vault-pass` with mode 0600 (gitignored). The loader auto-points `ANSIBLE_VAULT_PASSWORD_FILE` at this file when it exists, so no further setup is needed.

If `ANSIBLE_VAULT_PASSWORD_FILE` is already set in your environment, the loader respects it and skips the saved file.

## Per-Deployment Secrets (`secrets.yml`)

Used by Ansible playbooks for switch/server/LDAP passwords. Generated into each deployment's inventory.

### Location

```
output/<arch>/<site>/inventory/
└── group_vars/
    └── all/
        ├── main.yml      # Non-sensitive deployment config (VLANs, BGP, NTP, etc.)
        └── secrets.yml   # ALL non-Air passwords (can be vault-encrypted)
```

Source template: `inventories/secrets.yml.example` → shared `inventories/secrets.yml` (one file for every arch; there are no per-arch source secrets files). The per-site copy `make import` writes is `output/<arch>/<site>/inventory/group_vars/all/secrets.yml`.

### `make secrets` — create, edit and vault-encrypt `secrets.yml`

The wizard is the supported way to fill in `secrets.yml`; hand-editing (below)
still works. It has two modes, mirroring the seed structure:

```bash
make secrets                              # shared template inventories/secrets.yml
make secrets ARCH=2-8-5-200               # output/2-8-5-200/default/inventory/group_vars/all/secrets.yml
make secrets ARCH=2-8-5-200 SITE=cust-a   # output/2-8-5-200/cust-a/inventory/group_vars/all/secrets.yml
```

- **No `ARCH`** edits the shared template `inventories/secrets.yml` (created
  from `secrets.yml.example` if absent). `make generate` copies this file into
  every arch/site the first time it generates one, so this sets the org-wide
  default going forward. Existing `output/<arch>/<site>` copies are not touched.
  `ARCH` is intentionally optional here, unlike other per-deployment targets,
  and only an `ARCH=` given on the command line selects a deployment —
  `.era-context` is ignored so a bare `make secrets` always means the template.
- **With `ARCH` (and optional `SITE`, default `default`)** edits that
  deployment's copy, creating the directories and seeding from the shared
  template if `make generate` has not run yet. `SITE` too is taken only from
  the command line (never from `.era-context`), so `make secrets ARCH=x`
  always means `x/default`. If the shared template is itself vault-encrypted
  it is decrypted in memory (same vault-password chain as below) before it
  seeds the new file. `ARCH`/`SITE` must be plain directory names — `..`,
  `a/b` and dot-prefixed values are refused so the file can never land
  outside `output/<arch>/<site>/`.

When LDAP is disabled in the generated inventory, both LDAP password prompts
are skipped and existing values are preserved. Deployment mode checks the
workbook Deployment sheet and generated inventory; either source enabling
LDAP requires the prompts. Unknown deployment state still checks LDAP.
Only shared templates offer `Configure LDAP passwords now? [y/N]`, where Enter
skips them. This does not change whether LDAP is enabled in a deployment.

For each active key in the Fields table below the wizard shows whether the value is set,
unset, a placeholder, `!vault` or a Jinja template — never the value itself —
and asks for a new one (Enter keeps the current value, except a missing or
rejected switch password, which must be set). Switch-side passwords
(`switch_password`, `switch_ansible_password`, and `ldap_user_default_password`
when the workbook or inventory enables LDAP, deployment state is unknown,
or you choose to configure LDAP in the shared template) are checked **at prompt time** with the same rules
`make generate` and the deploy targets enforce (`scripts/check_secrets.py`) and re-prompted on
failure. `SECRETS_PASSWORD_POLICY=placeholder` relaxes the rule the same way it
does for the gate.

At the end the wizard offers to `ansible-vault encrypt` the file (default yes).
The vault password is looked up from `ANSIBLE_VAULT_PASSWORD_FILE`, else
`.era-secrets/vault-pass` — but a found password is **offered, never assumed**:
the wizard says where it came from (and, for `.era-secrets/vault-pass`, that it
is the password `make air-setup` uses for the shared Air vault) and asks
`Use the vault password from vault-pass? [Y/n]`. Answer `n` to type a different
one. A typed password is then offered for saving to `.era-secrets/vault-pass`;
if that file already holds a different password the default flips to `n` and
the wizard warns that replacing it means the Air vault (and anything else
encrypted with the old password) must be `ansible-vault rekey`ed before the
saved file opens them again. Files are written mode `0600`. If you accept
encryption but `ansible-vault` is not installed the wizard exits 2 with nothing
written — plaintext is only ever written when you explicitly answer `n`.

Re-running on an **already vault-encrypted** file is safe: the wizard asks
which vault password to decrypt with (same offer as above; a typed password is
only offered for saving after it has actually decrypted the file), prompts for
the fields, then asks `Encrypt with the same vault password…? [Y/n]`. Answer
`n` to **change the vault password** (rekey) — the file is re-encrypted with
the new one and you are offered to save it. Plaintext only ever touches a `0600`
temp file that is replaced atomically once encryption succeeds; if decryption
fails (wrong password) the file is left untouched and the wizard exits 1 with
a pointer to `ansible-vault edit`. A per-variable `!vault` value that you keep
is left exactly as it was; one you replace is removed together with its
ciphertext block. A root mapping that is uniformly indented keeps its
indentation and its unrelated keys. Before anything is written the wizard
re-parses the edited text and checks every new value reads back — if that
fails, nothing is written.

Make variables are case-sensitive: `make secrets arch=…` (or `site=…`) is
rejected with an error instead of silently editing the shared template.

### Fields

| Variable | Purpose |
|----------|---------|
| `switch_ansible_password` | SSH password for switches (cumulus user) |
| `switch_bootstrap_password` | Factory / expired first-login password. Used only by `push-switch-configs` when `switch_ansible_password` cannot log in yet. Default `cumulus` if omitted. |
| `server_ansible_password` | SSH password for servers (ubuntu user) |
| `ansible_become_password` | Sudo password. `make deploy-servers`, `deploy-servers-via-jump`, `ztp-setup`, `oob-setup` and `restart-ldap-direct` always pass `--ask-become-pass`, so they still prompt. |
| `switch_password` | Password configured on switches during ZTP |
| `ldap_admin_password` | LDAP bind/admin password |
| `ldap_user_default_password` | Default password for LDAP users |
| `status_page_username` / `status_page_password` | Basic auth for the ZTP status page **and the validation-report page** (`/reports/`), only if `status_page_enabled=Yes` (off by default). Shipped as `era` / `CHANGE_ME`; with the page enabled a placeholder, empty value or a reused switch password is **refused** (see below). There is no fallback to any other secret. |

### Switch passwords must pass the ERA switch-password policy

The ERA policy for switch passwords is the Cumulus Linux *password security*
rule set: at least 8 characters, a lowercase letter, an uppercase letter, a
digit and a special character, and not the switch username (`switch_user`,
default `cumulus`). It is enforced whether or not your switches have
`nv set system security password-hardening` enabled (off by default on
Cumulus 5.18; this tool does not turn it on or off) so that the same
`secrets.yml` works on a hardened switch too. ZTP applies `switch_password`
and `push-switch-configs` rotates to `switch_ansible_password`; on a hardened
switch a value that fails the rules is refused, the switch keeps the factory
password and every later step logs in with the wrong one.

`make generate` (Step 0b) and the switch deploy / ZTP targets
(`push-switch-configs`, `air-deploy*`, `switch-ztp-deploy`, `ztp-setup`,
`ztp-update`) therefore run `scripts/check_secrets.py` first and **stop** when
`switch_password` or `switch_ansible_password` would be refused — including
the untouched `CHANGE_ME` placeholder from `secrets.yml.example` — or when
`switch_ansible_password` is missing altogether (the switch inventory
references it with no default). The message names the key and the rule(s) it fails,
never the value.

- The shipped `Cumu1usLinux!` is allowed by `make secrets` and the switch
  preflight checks on Air and physical hardware, without an override. Enter
  keeps it when already set. Use a unique password for production.
  Other placeholders such as `CHANGE_ME` remain rejected.
  For development and CI that explicitly need those placeholders, set
  `ERA_DEV_ALLOW_PLACEHOLDER_SECRETS=1` (exactly `1`; off by default). It waives
  **only** the placeholder rule on the switch keys, prints a warning on every
  run, and writes `output/<arch>/<site>/DEV-PLACEHOLDER-SECRETS.txt` naming the
  waived keys (never the values). The file is removed on the next run without
  the opt-in. Never set it for a real deployment.
- **Status page.** When `status_page_enabled` is `Yes` in the generated
  inventory, `status_page_password` must be set, not a placeholder, not the
  username and not equal to `switch_password` / `switch_ansible_password`. This
  is checked on Air and physical alike and is **not** waived by the development
  opt-in; the ZTP-server role and `setup-status-page.yml` assert the same rule
  before writing `.htpasswd`, and hand the password to `htpasswd` on stdin.
  The username comparison is case-insensitive and also runs in those asserts, so a
  vault-encrypted `secrets.yml` (skipped by the preflight) is still checked at deploy.
  With the page off, nginx does not serve the dashboard or `/reports/` at all.
- Server-side passwords (`server_ansible_password`, `ansible_become_password`),
  `switch_bootstrap_password` and the LDAP keys are **not** checked; their
  defaults are fine to run with.
- A vault-encrypted `secrets.yml` is skipped with a note (the check has no
  vault password and will not ask for one). A single `!vault` value is
  accepted: on an unchecked key it is ignored; on a switch key it is reported
  as *not checked*.
- `switch_password: "{{ switch_ansible_password }}"` (exactly that — no text
  outside the braces) is followed and the target checked. Any other Jinja
  construct (`lookup('env', …)`, filters, `{# comments #}`, text around an
  expression) is reported as *not checked* — the gate never calls such a
  value viable and never guesses at what Ansible would render.
- Check a file by hand: `python3 scripts/check_secrets.py --arch 2-8-5-200`
  or `--file path/to/secrets.yml`.
- If your switches knowingly run without password hardening and you want a
  simpler password, `SECRETS_PASSWORD_POLICY=placeholder` (make variable or
  environment) relaxes the check to *set, non-empty, not a placeholder such as
  `CHANGE_ME`, not the username*. `GENERATE_SKIP_VALIDATE=1` (on
  `make generate`) or `DEPLOY_SKIP_VALIDATE=1` (on the deploy targets)
  bypasses the check entirely (not recommended).

### Plain text (development/testing)

The generated file works as-is for dev — the parser copies source defaults. Edit the generated copy for real credentials:

```bash
make secrets ARCH=2-8-5-200            # or by hand:
nano output/2-8-5-200/default/inventory/group_vars/all/secrets.yml
```

### Encrypt with Ansible Vault (production)

`make secrets ARCH=…` offers this step at the end; by hand:

```bash
ansible-vault encrypt output/2-8-5-200/default/inventory/group_vars/all/secrets.yml
```

Every `make` target that runs `ansible-playbook` goes through
`scripts/ansible-playbook.sh`. When no explicit source is set, the wrapper
discovers `.era-secrets/vault-pass` automatically (mode 0600, gitignored).
Vault-password discovery order is:

1. an explicit source: `ANSIBLE_VAULT_PASSWORD_FILE`,
   `ANSIBLE_VAULT_IDENTITY_LIST`, `--vault-id`, `--vault-password-file`, or
   `--ask-vault-pass` on the command line or in `ANSIBLE_ARGS`, or
   `vault_password_file` / `vault_identity_list` in the effective
   `ansible.cfg`;
2. `.era-secrets/vault-pass`;
3. no source, leaving Ansible's normal default behavior.

Explicit sources are never overridden. For `generate` and any other target
that runs the Python readers, provide a file-based source:

```bash
ANSIBLE_VAULT_PASSWORD_FILE=/path/to/pw make generate ARCH=2-8-5-200
```

Interactive `--ask-vault-pass` (on the CLI or in `ANSIBLE_ARGS`) is honored by
the Ansible stage only. It is supported for playbook-only targets such as
`push-switch-configs`, `switch-ztp-deploy`, `ztp-setup`, `ztp-update`,
`validate-*`, and `restart-ldap*`; `generate`, `deploy`, and `air-*` targets
also run Python readers and require `make secrets`, `.era-secrets/vault-pass`,
`ANSIBLE_VAULT_PASSWORD_FILE`, `ANSIBLE_VAULT_IDENTITY_LIST`, or
`ansible.cfg`. The prompted password is never written anywhere.

The Python readers (`generate-node-instructions.py`, `air-deploy.py`,
`fix-ext-storage-frr.py`, and `air-ssh-check.py`) use this precedence through
`scripts/secrets_loader.py`: `ANSIBLE_VAULT_PASSWORD_FILE` → native Ansible
sources (`ANSIBLE_VAULT_IDENTITY_LIST`, `DEFAULT_VAULT_PASSWORD_FILE`, or the
effective `ansible.cfg`) → `.era-secrets/vault-pass` → an actionable error.
CLI flags and `ANSIBLE_ARGS` are wrapper-only. They decrypt whole-file Vault
data in memory only. If an existing encrypted file cannot be decrypted or
parsed, they fail with an actionable error; they do not silently fall back to
the default switch password. A plaintext file may still omit
`switch_password`, in which case the documented development placeholder is
used.

### Edit encrypted files

`make secrets ARCH=…` re-runs cleanly on an encrypted file (see above); by hand:

```bash
ansible-vault edit output/.../secrets.yml
ansible-vault view output/.../secrets.yml
ansible-vault rekey output/.../secrets.yml
ansible-vault decrypt output/.../secrets.yml
```

## Best Practices

1. **Don't commit unencrypted secrets.** `output/` is gitignored except for `default/` per the project's `.gitignore`; verify before committing.
2. **Use unique switch/LDAP passwords per customer deployment.** That's why per-deployment secrets are per-arch/site — `make secrets ARCH=… SITE=…` edits exactly one copy.
3. **One shared Air vault per user.** Your NGC API key is yours — it doesn't belong in a per-customer deployment file.
4. **Rotate credentials** on the usual cadence; `make air-setup` + `ansible-vault rekey` cover Air and per-deployment separately.
5. **Back up your vault password** in a password manager. Losing it means re-running `make air-setup` and regenerating NGC API keys.

## Troubleshooting

### "Failed to decrypt .era-secrets/air-secrets.yml"

The loader couldn't decrypt the shared vault. Either:

- `.era-secrets/vault-pass` is missing or has the wrong password — re-run `make air-setup` to reset, or set `ANSIBLE_VAULT_PASSWORD_FILE` explicitly.
- `ansible-vault` isn't installed — run `make setup` (or `pip install -r requirements.txt` in your venv) to get the pinned `ansible-core`.

### "Missing required Air configuration: api_key"

No shared vault and no `AIR_API_KEY` in the environment. Run `make air-setup`.

### "input is not vault encrypted data"

The file isn't vault-encrypted. Either encrypt it, or (for dev) leave it plain — the loader tolerates both formats for the shared Air vault.

### "Attempting to decrypt but no vault secrets found"

An existing `secrets.yml` is whole-file Vault-encrypted, but no password source
was available. Save the password in `.era-secrets/vault-pass`, set
`ANSIBLE_VAULT_PASSWORD_FILE`, `ANSIBLE_VAULT_IDENTITY_LIST`, or an
`ansible.cfg` vault source. Interactive `--ask-vault-pass` is available only
to playbook-only targets such as `push-switch-configs`, `switch-ztp-deploy`,
`ztp-setup`, `ztp-update`, `validate-*`, and `restart-ldap*`; `generate`,
`deploy`, and `air-*` targets run Python readers and need a file-based source.
Make targets report this before invoking Ansible; Python readers report the
same actionable guidance.

### `AttributeError: 'str' object has no attribute 'get'`

This indicates that encrypted Vault ciphertext was parsed as a YAML scalar
instead of being decrypted first. Use the shared
`scripts/secrets_loader.py` path and provide a vault password source; do not
parse an encrypted `secrets.yml` with `yaml.safe_load()` directly.
