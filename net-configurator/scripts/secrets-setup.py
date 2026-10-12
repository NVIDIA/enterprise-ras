#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Interactive wizard for the per-deployment ``secrets.yml`` (``make secrets``).

Two modes, mirroring how the file is seeded (excel_parser copies the shared
template into every arch/site the first time it generates):

* ``make secrets``                  -> ``inventories/secrets.yml`` (the shared
  template; created from ``inventories/secrets.yml.example`` when absent).
* ``make secrets ARCH=… [SITE=…]``  -> ``output/<arch>/<site>/inventory/
  group_vars/all/secrets.yml`` (one deployment; directories are created if
  ``make generate`` has not run yet).

The wizard prompts for active keys in docs/SECRETS_AND_VAULT.md's field table,
keeps values the operator does not change, and checks the switch-side keys
(``switch_password``, ``switch_ansible_password`` and, when LDAP is enabled or
selected by the operator, ``ldap_user_default_password``) against the ERA
switch-password policy from ``scripts/check_secrets.py`` *at prompt time* -- a rejected value
is re-prompted instead of failing later at generate/deploy. On completion it
offers to ``ansible-vault encrypt`` the file, using the same vault-password
precedence as the Air scripts (``ANSIBLE_VAULT_PASSWORD_FILE``, then
``.era-secrets/vault-pass``, then a prompt). An already-encrypted file is
decrypted in memory with that password, edited, and re-encrypted.

Password values are never printed; existing values are shown as set/unset.

Usage:
    python3 scripts/secrets-setup.py                         # shared template
    python3 scripts/secrets-setup.py --arch 2-8-5-200 [--site default]
    python3 scripts/secrets-setup.py ... --policy placeholder
"""

import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_secrets as cs  # noqa: E402

PROJECT_ROOT = SCRIPTS_DIR.parent
SHARED_VAULT_DIRNAME = ".era-secrets"
SHARED_VAULT_PASS_FILENAME = "vault-pass"
VAULT_PASS_ENV = "ANSIBLE_VAULT_PASSWORD_FILE"

# Field table (docs/SECRETS_AND_VAULT.md). gate: "switch" = always checked
# against the ERA policy, "ldap" = checked when LDAP is enabled or selected,
# None = never checked (server / factory / bind / basic-auth credentials).
FIELDS = (
    ("switch_ansible_password", "SSH password for switches (cumulus user)", "switch", True),
    ("switch_bootstrap_password", "factory / first-login password (default cumulus)", None, True),
    ("server_ansible_password", "SSH password for servers (ubuntu user)", None, True),
    ("ansible_become_password", "sudo password on servers", None, True),
    ("switch_password", "password ZTP sets on the switches", "switch", True),
    ("ldap_admin_password", "LDAP bind/admin password", None, True),
    ("ldap_user_default_password", "default password for LDAP users", "ldap", True),
    ("status_page_username", "ZTP status page basic-auth user", None, False),
    ("status_page_password", "ZTP status page basic-auth password", None, True),
)
FIELD_KEYS = tuple(f[0] for f in FIELDS)


# ---------- output helpers (same look as air-setup.py) ----------

def banner(text):
    print()
    print(f"━━━ {text} ━━━")
    print()


def ok(msg):
    print(f"  ✓ {msg}")


def warn(msg):
    print(f"  ⚠️  {msg}")


def err(msg):
    print(f"  ✗ {msg}", file=sys.stderr)


def describe(value, key=None):
    """Say whether a value is set without revealing it."""
    if value is None:
        return "(not set)"
    if isinstance(value, cs.VaultedValue):
        return "(set, !vault)"
    text = str(value)
    if not text.strip():
        return "(empty)"
    placeholders = cs.STATUS_PAGE_PLACEHOLDERS if key == "status_page_password" else cs.PLACEHOLDERS
    if text.strip().lower() in placeholders:
        return "(PLACEHOLDER — change before production)"
    if cs._TEMPLATE_RE.search(text):
        return "(set, Jinja template)"
    return "(set)"


# ---------- target resolution ----------

# One path component: no separators, no leading dot (so `.`/`..`/hidden dirs
# are out). Same shape scripts/_era_context.py accepts for SITE.
_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")


def check_component(name, value):
    """Raise ValueError unless ``value`` is a single safe path component."""
    if not _COMPONENT_RE.match(value or ""):
        raise ValueError(f"{name}={value!r} is not a single path component"
                         " (letters, digits, '.', '_', '-'; no separators, no leading '.')")


def target_path(project_root, arch, site):
    """(path, mode) for the file the wizard edits. mode is 'global' or 'deployment'.

    ``arch``/``site`` must each be one plain directory name; anything that could
    escape ``output/<arch>/<site>`` raises ValueError.
    """
    if arch:
        check_component("ARCH", arch)
        check_component("SITE", site)
        path = (project_root / "output" / arch / site / "inventory" / "group_vars"
                / "all" / "secrets.yml")
        base = (project_root / "output").resolve()
        if base not in path.resolve().parents:
            raise ValueError("ARCH/SITE resolve outside output/")
        return path, "deployment"
    return project_root / "inventories" / "secrets.yml", "global"


def seed_template(project_root):
    """Template a new file starts from: shared template, else the .example."""
    shared = project_root / "inventories" / "secrets.yml"
    if shared.exists():
        return shared
    return project_root / "inventories" / "secrets.yml.example"


def _ldap_bool(value):
    """Decode explicit booleans; malformed/missing settings remain unknown."""
    text = str(value).strip().lower()
    if text in ("true", "yes", "1"):
        return True
    if text in ("false", "no", "0"):
        return False
    return None


def _inventory_ldap(project_root, arch, site):
    main = project_root / "output" / arch / site / "inventory" / "group_vars" / "all" / "main.yml"
    try:
        data = yaml.load(main.read_text(encoding="utf-8"), Loader=cs._InventoryLoader)
    except (OSError, yaml.YAMLError):
        return None
    ldap = data.get("ldap") if isinstance(data, dict) else None
    return _ldap_bool(ldap.get("enabled")) if isinstance(ldap, dict) else None


def _workbook_ldap(project_root, arch, site):
    path = project_root / "input" / arch / site / f"{arch}.xlsx"
    try:
        wb = cs.openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 — validate-excel diagnoses unreadable input
        return None
    try:
        if "Deployment" not in wb.sheetnames:
            return None
        for row in wb["Deployment"].iter_rows(values_only=True):
            if row and len(row) > 1 and str(row[0] or "").strip() == "ldap_enabled":
                return _ldap_bool(row[1])
        return None
    finally:
        wb.close()


def ldap_enabled(project_root, arch, site):
    """Either workbook or generated inventory may enable LDAP; None if unknown."""
    if not arch:
        return None
    states = (_inventory_ldap(project_root, arch, site), _workbook_ldap(project_root, arch, site))
    if True in states:
        return True
    if any(state is False for state in states):
        return False
    return None


def gated_keys(ldap_state):
    """Keys checked against the ERA policy for this run."""
    keys = [k for k, _, gate, _ in FIELDS if gate == "switch"]
    if ldap_state is not False:
        keys += [k for k, _, gate, _ in FIELDS if gate == "ldap"]
    return tuple(keys)


# ---------- vault password precedence ----------

def vault_password_file(project_root, environ=None):
    """ANSIBLE_VAULT_PASSWORD_FILE, else .era-secrets/vault-pass, else None."""
    environ = os.environ if environ is None else environ
    env_path = environ.get(VAULT_PASS_ENV)
    if env_path:
        p = Path(env_path).expanduser()
        if p.exists():
            return p
    saved = project_root / SHARED_VAULT_DIRNAME / SHARED_VAULT_PASS_FILENAME
    if saved.exists():
        return saved
    return None


def _write_password_tempfile(password):
    fd, tmp_path = tempfile.mkstemp(prefix="era-vault-", suffix=".pass")
    os.close(fd)
    path = Path(tmp_path)
    path.chmod(0o600)
    path.write_text(password)
    return path


def save_vault_password(project_root, password):
    cfg_dir = project_root / SHARED_VAULT_DIRNAME
    cfg_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    cfg_dir.chmod(0o700)
    pass_path = cfg_dir / SHARED_VAULT_PASS_FILENAME
    fd = os.open(pass_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(password + "\n")
    pass_path.chmod(0o600)
    return pass_path


# ---------- ansible-vault I/O ----------

class VaultError(Exception):
    pass


def _vault_env():
    """Environment for ansible-vault: drop ANSIBLE_VAULT_PASSWORD_FILE.

    The password is always passed explicitly; leaving the variable set as well
    gives ansible-vault two 'default' vault-ids and encrypt refuses to run.
    """
    env = dict(os.environ)
    env.pop(VAULT_PASS_ENV, None)
    return env


def ensure_ansible_vault():
    if shutil.which("ansible-vault"):
        return True
    err("ansible-vault not found in PATH (pip install ansible-core).")
    return False


def decrypt_text(path, password):
    """Plaintext of a vault-encrypted file (``ansible-vault view``)."""
    pass_file = _write_password_tempfile(password)
    try:
        result = subprocess.run(
            ["ansible-vault", "view", str(path), "--vault-password-file", str(pass_file)],
            capture_output=True, text=True, timeout=60, env=_vault_env(),
        )
    finally:
        pass_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise VaultError("ansible-vault could not decrypt the file (wrong vault password?)")
    return result.stdout


def write_encrypted(path, text, password):
    """Write ``text`` to ``path`` vault-encrypted, mode 0600, atomically.

    Plaintext only ever touches a 0600 temp file next to the destination; the
    destination is replaced only after ``ansible-vault encrypt`` succeeds, so a
    failure leaves whatever was there before (plaintext or ciphertext) intact.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    pass_file = _write_password_tempfile(password)
    fd, plain_tmp = tempfile.mkstemp(prefix="secrets-plain-", suffix=".yml", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    plain_path = Path(plain_tmp)
    plain_path.chmod(0o600)
    fd, enc_tmp = tempfile.mkstemp(prefix="secrets-enc-", suffix=".yml", dir=path.parent)
    os.close(fd)
    enc_path = Path(enc_tmp)
    enc_path.unlink()  # `encrypt --output` refuses an existing file
    try:
        result = subprocess.run(
            ["ansible-vault", "encrypt", "--vault-password-file", str(pass_file),
             "--output", str(enc_path), str(plain_path)],
            capture_output=True, text=True, timeout=60, env=_vault_env(),
        )
        if result.returncode != 0:
            raise VaultError("ansible-vault encrypt failed; the existing file was left unchanged")
        enc_path.chmod(0o600)
        os.replace(enc_path, path)
    finally:
        pass_file.unlink(missing_ok=True)
        plain_path.unlink(missing_ok=True)
        enc_path.unlink(missing_ok=True)


# ---------- secrets file rendering ----------

_KEY_LINE = r"^(?P<indent>[ \t]*)(?P<key>{key})[ \t]*:.*$"


def _scalar(value):
    """Double-quoted YAML scalar for a password (so ``{{``, ``#``, ``:`` stay literal)."""
    return yaml.safe_dump(str(value), default_style='"').strip()


def render_secrets(text, values):
    """Return ``text`` with each ``key: …`` line set to ``values[key]``.

    Comments and unrelated keys are preserved; keys absent from ``text`` are
    appended. A ``!vault`` value that the operator kept is left untouched
    (its ciphertext block is not a single line we can rewrite).
    """
    lines = text.splitlines()
    done = set()
    out = []
    root_indent = None
    i = 0
    while i < len(lines):
        line = lines[i]
        hit = None
        for key, value in values.items():
            if key in done or value is None or isinstance(value, cs.VaultedValue):
                continue
            m = re.match(_KEY_LINE.format(key=re.escape(key)), line)
            if m:
                hit = (key, value, m.group("indent"))
                break
        if hit is None:
            out.append(line)
            i += 1
            continue
        key, value, indent = hit
        if root_indent is None:
            root_indent = indent
        out.append(f"{indent}{key}: {_scalar(value)}")
        done.add(key)
        i += 1
        # Drop the continuation of a multi-line value (a `!vault |` ciphertext
        # block, a folded/literal scalar): following lines indented deeper than
        # the key itself. A sibling key at the same indentation ends it.
        while i < len(lines):
            nxt = lines[i]
            if nxt.strip() == "":
                j = i + 1
                while j < len(lines) and lines[j].strip() == "":
                    j += 1
                if j < len(lines) and _deeper(lines[j], indent):
                    i = j
                    continue
                break
            if not _deeper(nxt, indent):
                break
            i += 1
    lines = out
    root_indent = root_indent or ""
    missing = [k for k in values if k not in done and values[k] is not None
               and not isinstance(values[k], cs.VaultedValue)]
    if missing:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{root_indent}# Added by `make secrets`")
        for key in missing:
            lines.append(f"{root_indent}{key}: {_scalar(values[key])}")
    return "\n".join(lines) + "\n"


def _deeper(line, indent):
    """True if ``line`` is indented strictly more than ``indent``."""
    lead = line[:len(line) - len(line.lstrip(" \t"))]
    return len(lead) > len(indent) and lead.startswith(indent)


def write_plain(path, text):
    """Atomically write ``text`` to ``path`` with mode 0600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="secrets-", suffix=".yml", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load_mapping(text):
    """Parse secrets YAML (accepting ``!vault`` scalars); {} for an empty file."""
    data = yaml.load(text, Loader=cs._SecretsLoader) or {}
    if not isinstance(data, dict):
        raise ValueError("secrets.yml does not contain a mapping")
    return data


# ---------- prompting ----------

def prompt_field(key, label, current, gate, policy, username, hidden,
                 ask=input, ask_secret=getpass.getpass):
    """Prompt until an acceptable value is entered. Returns the value to store.

    Enter keeps ``current`` when it is acceptable; a gated key whose current
    value fails the policy (e.g. an untouched ``CHANGE_ME``) cannot be kept.
    ``!vault`` and Jinja-templated current values are kept as-is when the
    operator presses Enter (they are not checkable here, per check_secrets).
    """
    read = ask_secret if hidden else ask
    # An unset, ungated key may stay unset (the inventory default applies,
    # e.g. switch_bootstrap_password -> cumulus); unset switch keys must be set.
    keepable = current is not None or not gate
    unverifiable = isinstance(current, cs.VaultedValue) or (
        isinstance(current, str) and cs._TEMPLATE_RE.search(current))
    if keepable and gate and not unverifiable:
        keepable = not cs.password_problems(current, username=username, policy=policy)
    print(f"  {key} — {label}")
    print(f"    current: {describe(current, key=key)}"
          + ("" if keepable or current is None else "  ← fails the ERA policy, must change"))
    while True:
        if not keepable:
            hint = "required"
        elif current is None:
            hint = "Enter = leave unset, inventory default applies"
        else:
            hint = "Enter = keep"
        raw = read(f"    new value ({hint}): ")
        if raw == "":
            if keepable:
                return current
            warn("A value is required here.")
            continue
        if hidden:
            again = ask_secret("    confirm:                    ")
            if again != raw:
                warn("Values do not match, try again.")
                continue
        if gate:
            problems = cs.password_problems(raw, username=username, policy=policy)
            if problems:
                warn(f"{key} {'; '.join(problems)} — rejected (ERA switch-password policy, "
                     f"{policy}); try again.")
                continue
        elif raw.strip().lower() in (cs.STATUS_PAGE_PLACEHOLDERS
                                    if key == "status_page_password" else cs.PLACEHOLDERS):
            warn(f"{key} looks like a placeholder — stored anyway (not a switch password).")
        return raw


def yes_no(question, default, ask=input):
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = ask(f"  {question} {suffix}: ").strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        warn("Answer y or n.")


def prompt_vault_password(ask_secret=getpass.getpass, confirm=True):
    while True:
        pw = ask_secret("  Vault password: ")
        if not pw:
            warn("Password cannot be empty.")
            continue
        if not confirm or ask_secret("  Confirm:        ") == pw:
            return pw
        warn("Passwords do not match, try again.")


SHARED_VAULT_PASS_REL = f"{SHARED_VAULT_DIRNAME}/{SHARED_VAULT_PASS_FILENAME}"
AIR_VAULT_REL = f"{SHARED_VAULT_DIRNAME}/air-secrets.yml"


def _describe_pass_file(project_root, pass_file, environ):
    """Human label for where a vault password came from, noting when it is the Air one."""
    shared = project_root / SHARED_VAULT_DIRNAME / SHARED_VAULT_PASS_FILENAME
    if pass_file == shared:
        return (f"{SHARED_VAULT_PASS_REL} — the password `make air-setup` uses for the shared"
                f" Air vault ({AIR_VAULT_REL})")
    return f"{pass_file} ({VAULT_PASS_ENV})"


def offer_save_vault_password(project_root, password, ask=input, default=True):
    """Offer to persist ``password`` to .era-secrets/vault-pass; warn when that replaces one."""
    shared = project_root / SHARED_VAULT_DIRNAME / SHARED_VAULT_PASS_FILENAME
    if shared.exists():
        if shared.read_text().strip() == password:
            return False
        warn(f"{SHARED_VAULT_PASS_REL} already holds a different password. Replacing it means"
             f" the Air vault ({AIR_VAULT_REL}) and any secrets.yml encrypted with the old"
             " password will no longer decrypt via that file until you `ansible-vault rekey` them.")
        question = f"Replace the saved password in {SHARED_VAULT_PASS_REL} with this one?"
        default = False
    else:
        question = (f"Save it to {SHARED_VAULT_PASS_REL} (mode 0600, gitignored) so the Air"
                    " vault and every secrets.yml share one password?")
    if yes_no(question, default=default, ask=ask):
        saved = save_vault_password(project_root, password)
        ok(f"saved vault password to {saved.relative_to(project_root)}")
        return True
    return False


def choose_vault_password(project_root, environ, ask=input, ask_secret=getpass.getpass,
                          confirm=True, offer_save=True):
    """Pick the vault password for this run — never silently reuse a saved one.

    A password found via ANSIBLE_VAULT_PASSWORD_FILE / .era-secrets/vault-pass is
    offered, not assumed; the operator may type a different one instead and is
    then offered to save it (replacing the shared file only on explicit consent).
    Returns ``(password, typed)``; with ``offer_save=False`` the caller offers the
    save itself once the typed password has proven to work.
    """
    pass_file = vault_password_file(project_root, environ)
    if pass_file is not None:
        print(f"  Found a vault password in {_describe_pass_file(project_root, pass_file, environ)}")
        if yes_no(f"Use the vault password from {pass_file.name}?", default=True, ask=ask):
            ok(f"using vault password from {pass_file}")
            return pass_file.read_text().strip(), False
        print("  Enter a different vault password:")
    else:
        print(f"  No vault password file found ({VAULT_PASS_ENV} / {SHARED_VAULT_PASS_REL}).")
    password = prompt_vault_password(ask_secret, confirm=confirm)
    if offer_save:
        offer_save_vault_password(project_root, password, ask=ask)
    return password, True


# ---------- wizard ----------

def run_wizard(project_root, arch, site, policy, ask=input, ask_secret=getpass.getpass,
               environ=None):
    environ = os.environ if environ is None else environ
    try:
        path, mode = target_path(project_root, arch, site)
    except ValueError as exc:
        err(str(exc))
        return 2
    ldap_state = ldap_enabled(project_root, arch, site)

    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Per-deployment secrets setup (secrets.yml)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    if mode == "global":
        print("  Mode:    shared template — the seed `make generate` copies into every")
        print("           arch/site on first run (pass ARCH=… to edit one deployment)")
    else:
        print(f"  Mode:    deployment {arch}/{site}")
    print(f"  File:    {path.relative_to(project_root)}")
    print(f"  Policy:  {policy}")
    print()

    # ---- existing file (or the seed it starts from) ----
    vault_password = None
    if path.exists():
        source = path
        banner("Existing secrets.yml detected")
    else:
        source = seed_template(project_root)
        banner("No secrets.yml yet")
        print(f"  Starting from {source.relative_to(project_root)}")
    source_encrypted = cs.is_vault_encrypted(source)
    what = "file" if source == path else str(source.relative_to(project_root))
    if source_encrypted:
        ok(f"{what} is vault-encrypted ($ANSIBLE_VAULT header)")
        if not ensure_ansible_vault():
            return 2
        print("  A vault password is needed to decrypt it for editing.")
        vault_password, typed = choose_vault_password(project_root, environ, ask=ask,
                                                      ask_secret=ask_secret, confirm=False,
                                                      offer_save=False)
        try:
            existing_text = decrypt_text(source, vault_password)
        except VaultError as exc:
            err(str(exc))
            print("  Fix the vault password source (ANSIBLE_VAULT_PASSWORD_FILE or"
                  " .era-secrets/vault-pass) or use `ansible-vault edit` directly.")
            return 1
        ok("decrypted in memory (nothing written yet)")
        if typed:
            offer_save_vault_password(project_root, vault_password, ask=ask)
    else:
        ok(f"{what} is plaintext")
        existing_text = source.read_text(encoding="utf-8")
    # Only an encrypted *destination* forces re-encryption; an encrypted seed
    # just means we already hold a vault password to offer for the new file.
    was_encrypted = source_encrypted and source == path

    try:
        existing = load_mapping(existing_text)
    except (yaml.YAMLError, ValueError):
        err(f"{source.relative_to(project_root)} is not valid YAML — fix it by hand first")
        return 1

    username = cs.SWITCH_USER
    if "switch_user" in existing:
        resolved, reason = cs.resolve_value(existing, "switch_user")
        if reason is None and resolved:
            username = str(resolved)

    # Only shared templates lack a deployment whose LDAP settings we can check.
    if mode == "global":
        ldap_state = yes_no("Configure LDAP passwords now?", default=False, ask=ask)
    elif ldap_state is None:
        print("  LDAP state unknown: checking LDAP passwords until deployment settings are available.")
    gated = gated_keys(ldap_state)
    print(f"  Password keys checked: {', '.join(gated)}")
    if ldap_state is False:
        print("  LDAP passwords skipped; existing values are preserved.")

    # ---- per-field prompts ----
    banner("Values (Enter keeps a value that passes; nothing is echoed)")
    new_values = {}
    for key, label, gate, hidden in FIELDS:
        if key in ("ldap_admin_password", "ldap_user_default_password") and ldap_state is False:
            continue
        gate_now = gate if key in gated else None
        new_values[key] = prompt_field(key, label, existing.get(key), gate_now, policy,
                                       username, hidden, ask=ask, ask_secret=ask_secret)
        print()
    if (isinstance(new_values["status_page_password"], str)
            and new_values["status_page_password"] == new_values.get("switch_password")):
        warn("status_page_password equals switch_password — the status page is plain HTTP;"
             " consider a different value.")

    # Final switch-password gate; LDAP user passwords were checked at their prompts.
    merged = dict(existing)
    merged.update({k: v for k, v in new_values.items() if v is not None})
    findings = cs.check_switch_passwords(merged, policy=policy)
    if findings:
        err("switch passwords still fail the ERA policy: " + "; ".join(findings))
        return 1

    # ---- write (encrypted unless declined; an encrypted file never goes back to plaintext) ----
    banner("Writing")
    text = render_secrets(existing_text, new_values)
    try:
        rendered = load_mapping(text)
    except (yaml.YAMLError, ValueError):
        err("internal error: the edited secrets.yml would not be valid YAML — nothing written")
        return 1
    for key, value in new_values.items():
        if isinstance(value, str) and rendered.get(key) != value:
            err(f"internal error: {key} did not round-trip through the edited file — nothing written")
            return 1
    if was_encrypted:
        encrypt = True
        print("  File was vault-encrypted — it will be re-encrypted (never written back as plaintext).")
    else:
        encrypt = yes_no("Encrypt secrets.yml with ansible-vault now?", default=True, ask=ask)
        if encrypt and not ensure_ansible_vault():
            err("encryption was requested but cannot be performed — nothing written.")
            print("  Install ansible-core, or re-run and answer 'n' to write plaintext deliberately.")
            return 2
    if encrypt:
        if vault_password is not None:
            same = yes_no(f"Encrypt with the same vault password that decrypted {what}?"
                          " (n = choose a new vault password)", default=True, ask=ask)
            if not same:
                print("  Enter the new vault password:")
                vault_password = prompt_vault_password(ask_secret, confirm=True)
                if was_encrypted:
                    ok("rekeying: the file will only decrypt with the new password from now on")
                offer_save_vault_password(project_root, vault_password, ask=ask)
        else:
            vault_password, _ = choose_vault_password(project_root, environ, ask=ask,
                                                      ask_secret=ask_secret, confirm=True)
        try:
            write_encrypted(path, text, vault_password)
        except VaultError as exc:
            err(str(exc))
            return 1
        ok(f"wrote {path.relative_to(project_root)} (vault-encrypted, mode 0600)")
    else:
        write_plain(path, text)
        ok(f"wrote {path.relative_to(project_root)} (plaintext, mode 0600)")
        warn("encrypt before committing: "
             f"ansible-vault encrypt {path.relative_to(project_root)}")

    print()
    if mode == "global":
        ok("done. New arch/site generations will seed from this template; existing"
           " output/<arch>/<site> copies are unchanged (edit them with make secrets ARCH=…).")
    else:
        ok(f"done. `make generate ARCH={arch} SITE={site}` and the deploy targets will use it.")
    print()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Create / edit / vault-encrypt secrets.yml (global template or one deployment).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--arch", help="edit output/<arch>/<site>/... instead of the shared template")
    parser.add_argument("--site", default="default", help="site name (default: default)")
    parser.add_argument("--policy", choices=cs.POLICIES,
                        default=os.environ.get(cs.POLICY_ENV, "hardening"),
                        help=f"ERA switch-password policy (env {cs.POLICY_ENV})")
    args = parser.parse_args(argv)
    if args.site != "default" and not args.arch:
        parser.error("--site only applies together with --arch")
    try:
        return run_wizard(PROJECT_ROOT, args.arch, args.site, args.policy)
    except (KeyboardInterrupt, EOFError):
        print()
        print("  Aborted — nothing written.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
