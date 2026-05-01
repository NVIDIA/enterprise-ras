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

Source template: `inventories/secrets.yml.example`. Source per-arch defaults: `inventories/<arch>/group_vars/all/secrets.yml`.

### Fields

| Variable | Purpose |
|----------|---------|
| `switch_ansible_password` | SSH password for switches (cumulus user) |
| `server_ansible_password` | SSH password for servers (ubuntu user) |
| `ansible_become_password` | Sudo password (eliminates `--ask-become-pass`) |
| `switch_password` | Password configured on switches during ZTP |
| `ldap_admin_password` | LDAP bind/admin password |
| `ldap_user_default_password` | Default password for LDAP users |
| `status_page_username` / `status_page_password` | ZTP status page basic auth (only if `status_page_enabled=Yes`) |

### Plain text (development/testing)

The generated file works as-is for dev — the parser copies source defaults. Edit the generated copy for real credentials:

```bash
nano output/2-8-5-200/default/inventory/group_vars/all/secrets.yml
```

### Encrypt with Ansible Vault (production)

```bash
ansible-vault encrypt output/2-8-5-200/default/inventory/group_vars/all/secrets.yml
```

Provide the password to playbooks via one of:

```bash
# Option A: password file (works seamlessly with make targets)
export ANSIBLE_VAULT_PASSWORD_FILE=~/.vault_pass
make generate ARCH=2-8-5-200

# Option B: prompt
ansible-playbook ... --ask-vault-pass
```

You can reuse the same password file for both the shared Air vault and the per-deployment secrets — just point `ANSIBLE_VAULT_PASSWORD_FILE` at `.era-secrets/vault-pass` (or any other file).

### Edit encrypted files

```bash
ansible-vault edit output/.../secrets.yml
ansible-vault view output/.../secrets.yml
ansible-vault rekey output/.../secrets.yml
ansible-vault decrypt output/.../secrets.yml
```

## Best Practices

1. **Don't commit unencrypted secrets.** `output/` is gitignored except for `default/` per the project's `.gitignore`; verify before committing.
2. **Use unique switch/LDAP passwords per customer deployment.** That's why per-deployment secrets are per-arch/site.
3. **One shared Air vault per user.** Your NGC API key is yours — it doesn't belong in a per-customer deployment file.
4. **Rotate credentials** on the usual cadence; `make air-setup` + `ansible-vault rekey` cover Air and per-deployment separately.
5. **Back up your vault password** in a password manager. Losing it means re-running `make air-setup` and regenerating NGC API keys.

## Troubleshooting

### "Failed to decrypt .era-secrets/air-secrets.yml"

The loader couldn't decrypt the shared vault. Either:

- `.era-secrets/vault-pass` is missing or has the wrong password — re-run `make air-setup` to reset, or set `ANSIBLE_VAULT_PASSWORD_FILE` explicitly.
- `ansible-vault` isn't installed — `pip install ansible-core`.

### "Missing required Air configuration: api_key"

No shared vault and no `AIR_API_KEY` in the environment. Run `make air-setup`.

### "input is not vault encrypted data"

The file isn't vault-encrypted. Either encrypt it, or (for dev) leave it plain — the loader tolerates both formats for the shared Air vault.
