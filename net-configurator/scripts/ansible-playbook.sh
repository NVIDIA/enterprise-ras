#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail

TOOL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAVED_VAULT_PASS="$TOOL_ROOT/.era-secrets/vault-pass"
ansible_args=()
if [[ -n "${ANSIBLE_ARGS:-}" ]]; then
    read -r -a ansible_args <<< "$ANSIBLE_ARGS"
fi

has_vault_source_arg() {
    local arg
    for arg in "$@"; do
        case "$arg" in
            --vault-id|--vault-id=*|--vault-password-file|--vault-password-file=*|\
            --vault-pass-file*|--ask-vault-pass|--ask-vault-password|-J)
                return 0
                ;;
        esac
    done
    return 1
}

config_has_vault_source() {
    local config
    if [[ -n "${ANSIBLE_CONFIG:-}" && -f "$ANSIBLE_CONFIG" ]]; then
        config="$ANSIBLE_CONFIG"
    elif [[ -f "./ansible.cfg" ]]; then
        config="./ansible.cfg"
    elif [[ -f "$HOME/.ansible.cfg" ]]; then
        config="$HOME/.ansible.cfg"
    elif [[ -f "/etc/ansible/ansible.cfg" ]]; then
        config="/etc/ansible/ansible.cfg"
    else
        return 1
    fi
    grep -Eq '^[[:space:]]*vault_(password_file|identity_list)[[:space:]]*=' "$config"
}

inventory_paths() {
    local arg next
    while (($#)); do
        arg="$1"
        shift
        case "$arg" in
            -i|--inventory)
                if (($#)); then
                    next="$1"
                    shift
                    printf '%s\n' "$next"
                fi
                ;;
            -i=*|--inventory=*)
                printf '%s\n' "${arg#*=}"
                ;;
        esac
    done
}

preflight_encrypted_inventory() {
    local inventory path inventory_dir secrets
    while IFS= read -r inventory; do
        [[ -n "$inventory" ]] || continue
        path="$inventory"
        if [[ ! -d "$path" ]]; then
            inventory_dir="$(dirname "$path")"
        else
            inventory_dir="$path"
        fi
        secrets="$inventory_dir/group_vars/all/secrets.yml"
        if [[ -f "$secrets" ]] && [[ "$(head -n 1 "$secrets")" == '$ANSIBLE_VAULT'* ]]; then
            cat >&2 <<EOF
❌ $secrets is vault-encrypted but no vault password source was found.
   Provide one of:
     • make secrets            # re-run the wizard and save the vault password to .era-secrets/vault-pass
     • .era-secrets/vault-pass # save the vault password there (mode 0600, gitignored)
     • export ANSIBLE_VAULT_PASSWORD_FILE=/path/to/password-file
     • vault_password_file = /path in ansible.cfg
   (ANSIBLE_ARGS="--ask-vault-pass" works only for playbook-only targets such as make push-switch-configs / validate-*; make generate, make deploy and air-* targets also run Python readers that need a file-based source.)
   See docs/SECRETS_AND_VAULT.md.
EOF
            return 1
        fi
    done < <(inventory_paths "$@")
}

explicit_source=0
if [[ -n "${ANSIBLE_VAULT_PASSWORD_FILE:-}" ||
      -n "${DEFAULT_VAULT_PASSWORD_FILE:-}" ||
      "${ANSIBLE_VAULT_IDENTITY_LIST+x}" == x ]] ||
    has_vault_source_arg "$@" ||
    has_vault_source_arg "${ansible_args[@]}" ||
    config_has_vault_source; then
    explicit_source=1
fi

if ((explicit_source == 0)) && [[ -r "$SAVED_VAULT_PASS" ]]; then
    export ANSIBLE_VAULT_PASSWORD_FILE="$SAVED_VAULT_PASS"
fi

if ((explicit_source == 0)) && [[ ! -r "$SAVED_VAULT_PASS" ]]; then
    preflight_encrypted_inventory "$@"
fi

exec ansible-playbook "$@" "${ansible_args[@]+"${ansible_args[@]}"}"
