#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Pre-flight check: can the switch passwords in secrets.yml actually be applied?

ERA policy (ADR-0078): a switch password must satisfy the Cumulus Linux
*password security* rule set -- at least 8 characters, one lowercase, one
uppercase, one digit, one special character, and not the username -- whether
or not the target switch has ``nv set system security password-hardening``
enabled (it is off by default on 5.18; this repo neither enables nor disables
it). A value that fails it on a hardened switch is refused by ``nv set system
aaa user cumulus password ...`` at ZTP time and by ``chpasswd`` afterwards, so
the switch stays on the factory password and every later step
(push-switch-configs, validate-*) cannot log in. Placeholders such as
``CHANGE_ME`` fail it too. ``--policy placeholder`` (env
``SECRETS_PASSWORD_POLICY=placeholder``) relaxes the check to placeholder /
empty / equals-username only for sites that knowingly run unhardened switches.

The documented ``Cumu1usLinux!`` default is allowed for switch passwords;
status-page checks keep a separate denylist.

The development placeholders (``CHANGE_ME``, ...)
are refused for every generate/deploy target, NVIDIA Air included (ADR-0091).
``ERA_DEV_ALLOW_PLACEHOLDER_SECRETS=1`` is the only way past that: it is a
development-only opt-in, never on by default, warns on every use and, with
``--arch``, records itself in ``output/<arch>/<site>/DEV-PLACEHOLDER-SECRETS.txt``.
It waives the placeholder rule for switch passwords only; every other rule
still applies.

When the site's workbook or its generated inventory has the status page
enabled (``status_page_enabled``) the
status page must have its own ``status_page_password``: set, not a
placeholder, not a switch password. The opt-in does not waive that -- the
page is served over plain HTTP and Air forwards it publicly.

Values are checked as Ansible would apply them: a ``{{ other_key }}`` alias to
another key in the same file is followed; a ``!vault`` scalar or any other
Jinja expression (``lookup(...)``, filters, ...) cannot be inspected here and
is reported as *not checked*, never as viable.

This script runs before ``make generate`` and before the deploy targets so the
failure surfaces at the desk, not on the switch. Server-side passwords
(``server_ansible_password``, ``ansible_become_password``) are plain Ubuntu
credentials with no such policy and are deliberately NOT gated -- the shipped
default is fine there.

Password *values* are never printed; only the key name and which rule failed.

Usage:
    python3 scripts/check_secrets.py --arch 2-8-9-800 [--site default]
    python3 scripts/check_secrets.py --file path/to/secrets.yml

Exit status: 0 = viable, 1 = at least one switch password cannot be applied,
0 with a note when the file is vault-encrypted (cannot inspect; Ansible will
decrypt it at run time).
"""

import argparse
import os
import re
import sys
from pathlib import Path

import openpyxl
import yaml


class VaultedValue:
    """Placeholder for a ``!vault`` scalar: present, encrypted, not inspectable."""

    def __repr__(self):
        return "<!vault>"


class _SecretsLoader(yaml.SafeLoader):
    """SafeLoader that accepts Ansible's ``!vault`` tag (per-variable encryption)."""


_SecretsLoader.add_constructor("!vault", lambda loader, node: VaultedValue())
_SecretsLoader.add_constructor("!vault-encrypted", lambda loader, node: VaultedValue())

# `{{ some_key }}` and nothing else — an alias to another key in the same file.
# Whitespace is allowed only inside the braces: literal text around the
# expression (even a trailing space or newline) becomes part of the password
# Ansible applies, so such values are templates we do not evaluate.
_ALIAS_RE = re.compile(r"\A\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}\Z")
_TEMPLATE_RE = re.compile(r"\{\{|\{%|\{#")
_MAX_ALIAS_DEPTH = 8

POLICIES = ("hardening", "placeholder")
POLICY_ENV = "SECRETS_PASSWORD_POLICY"

DEV_OPT_IN_ENV = "ERA_DEV_ALLOW_PLACEHOLDER_SECRETS"
DEV_OPT_IN_RECORD = "DEV-PLACEHOLDER-SECRETS.txt"

STATUS_PAGE_PASSWORD_KEY = "status_page_password"  # pragma: allowlist secret
STATUS_PAGE_USER = "era"

# Keys whose value ends up as the password of the Cumulus `cumulus` user.
#   switch_password         -> set on the switch by roles/ztp-server/templates/ztp.sh.j2
#   switch_ansible_password -> target password push-switch-configs rotates to, and
#                              the SSH credential every validate-* playbook uses
SWITCH_PASSWORD_KEYS = ("switch_password", "switch_ansible_password")

# Keys the inventory references with no `| default()`: group_vars/switches.yml
# sets `ansible_password: "{{ switch_ansible_password }}"`, so a secrets file
# that omits it breaks every switch login. switch_password falls back to the
# ztp.sh.j2 default and may be omitted.
REQUIRED_KEYS = ("switch_ansible_password",)

# Keys that are explicitly NOT gated: plain-Ubuntu credentials with no
# complexity policy, and the factory password the switch ships with.
UNGATED_KEYS = ("server_ansible_password", "ansible_become_password",
                "switch_bootstrap_password")

SWITCH_USER = "cumulus"

# Cumulus Linux password-security rule set (the ERA policy, ADR-0078 D2).
# Checked against the Cumulus Linux docs of this release (ADR-0078, "Release
# verification"). A model pinned to a newer release fails
# data-models/tests/test_password_policy_verified_release.py until the rules
# below are re-checked against that release's docs and this is moved up.
POLICY_VERIFIED_RELEASE = "5.18.3"
MIN_LEN = 8
# Documented special set: ` ~ ! @ # $ % ^ & * ( ) - _ + = | [ { } ] ; : ' , < . > / ? and white space
_SPECIAL_RE = re.compile(r"[`~!@#$%^&*()\-_+=|\[\]{};:',<.>/?\s]")

# Compared lower-cased. Includes the development defaults the repo ships in
# inventories/secrets.yml.example and the old status-page fallback sentinel.
# Cumu1usLinux! is an allowed switch password; status-page checks stay separate.
PLACEHOLDERS = frozenset({
    "change_me", "changeme", "change-me", "replace_me", "replaceme",
    "password", "passw0rd", "todo", "fixme", "xxx", "secret",
    "era-status-change_me",
})
STATUS_PAGE_PLACEHOLDERS = PLACEHOLDERS | {"cumu1uslinux!"}
PLACEHOLDER_PROBLEM = "is a placeholder value (edit secrets.yml)"

VAULT_MARKER = "$ANSIBLE_VAULT"


def password_problems(value, username=SWITCH_USER, policy="hardening"):
    """Return the list of policy rules a switch password fails (empty = viable).

    ``policy="placeholder"`` checks only set / non-empty / not-a-placeholder /
    not-the-username. Never include the value itself in the returned strings.
    """
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}; expected one of {POLICIES}")
    if value is None:
        return ["is not set"]
    if not isinstance(value, str):
        value = str(value)
    if not value.strip():
        return ["is empty"]
    problems = []
    if value.strip().lower() in PLACEHOLDERS:
        problems.append(PLACEHOLDER_PROBLEM)
    if value.lower() == username.lower():
        problems.append(f"equals the username '{username}'")
    if policy == "placeholder":
        return problems
    if len(value) < MIN_LEN:
        problems.append(f"is shorter than {MIN_LEN} characters")
    if not re.search(r"[a-z]", value):
        problems.append("has no lowercase letter")
    if not re.search(r"[A-Z]", value):
        problems.append("has no uppercase letter")
    if not re.search(r"[0-9]", value):
        problems.append("has no digit")
    if not _SPECIAL_RE.search(value):
        problems.append("has no special character")
    return problems


def resolve_value(secrets, key):
    """Return (value, reason) for ``secrets[key]`` as Ansible would apply it.

    Follows ``{{ other_key }}`` aliases within the mapping. ``reason`` is None
    when ``value`` is a checkable plaintext scalar; otherwise it says why the
    value cannot be checked here (vaulted, templated, alias loop / dangling).
    """
    seen = []
    value = secrets[key]
    while True:
        if isinstance(value, VaultedValue):
            return None, "is !vault-encrypted (Ansible decrypts it at run time)"
        if not isinstance(value, str):
            return value, None
        alias = _ALIAS_RE.match(value)
        if alias is None:
            if _TEMPLATE_RE.search(value):
                return None, ("is a Jinja template that cannot be evaluated "
                              "here (lookup/filter/comment/literal text) "
                              "— not checked")
            return value, None
        target = alias.group(1)
        if target in seen or len(seen) >= _MAX_ALIAS_DEPTH:
            return None, f"is an alias loop via '{target}'"
        if target not in secrets:
            return None, f"aliases '{target}', which is not set in this file"
        seen.append(target)
        value = secrets[target]


def classify_switch_passwords(secrets, policy="hardening", waived=None):
    """Check every Cumulus-facing key in a secrets mapping.

    Returns ``(findings, unchecked)``: findings are human-readable failures
    (key + failed rules) and mean fail closed; unchecked are keys whose value
    is present but cannot be inspected here (``!vault`` scalar, Jinja lookup)
    and are reported, never asserted viable. A missing key is a finding only
    when the inventory references it without a default (REQUIRED_KEYS);
    otherwise the template fallback applies and the key is skipped.

    When ``waived`` is a list (the development opt-in is on), a key whose only
    problem is the placeholder rule is appended there instead of to findings.
    """
    findings, unchecked = [], []
    username = SWITCH_USER
    if "switch_user" in secrets:
        resolved, reason = resolve_value(secrets, "switch_user")
        if reason is None and resolved:
            username = str(resolved)
    for key in SWITCH_PASSWORD_KEYS:
        if key not in secrets:
            if key in REQUIRED_KEYS:
                findings.append(f"{key} is not set (no template default; "
                                "group_vars/switches.yml requires it)")
            continue
        value, reason = resolve_value(secrets, key)
        if reason is not None:
            if reason.startswith(("is an alias loop", "aliases ")):
                findings.append(f"{key} {reason}")
            else:
                unchecked.append(f"{key} {reason}")
            continue
        problems = password_problems(value, username=username, policy=policy)
        if waived is not None and problems == [PLACEHOLDER_PROBLEM]:
            waived.append(key)
        elif problems:
            findings.append(f"{key} {'; '.join(problems)}")
    return findings, unchecked


def dev_opt_in_enabled(environ=None):
    """True only for an explicit ``ERA_DEV_ALLOW_PLACEHOLDER_SECRETS=1``."""
    environ = os.environ if environ is None else environ
    return environ.get(DEV_OPT_IN_ENV, "").strip() == "1"


def check_status_page_password(secrets):
    """Return (findings, unchecked) for an ENABLED status page.

    Not waivable by the development opt-in. There is no fallback: the role and
    playbook refuse to build .htpasswd without a real ``status_page_password``.
    """
    key = STATUS_PAGE_PASSWORD_KEY
    if key not in secrets:
        return [f"{key} is not set (status_page_enabled is Yes; the status page "
                "needs its own password)"], []
    value, reason = resolve_value(secrets, key)
    if reason is not None:
        if reason.startswith(("is an alias loop", "aliases ")):
            return [f"{key} {reason}"], []
        return [], [f"{key} {reason}"]
    username = STATUS_PAGE_USER
    if "status_page_username" in secrets:
        resolved, why = resolve_value(secrets, "status_page_username")
        if why is None and resolved:
            username = str(resolved)
    problems = password_problems(value, username=username, policy="placeholder")
    if (str(value).strip().lower() in STATUS_PAGE_PLACEHOLDERS
            and PLACEHOLDER_PROBLEM not in problems):
        problems.append(PLACEHOLDER_PROBLEM)
    if any(ch in str(value) for ch in "\r\n\x00"):
        problems.append("contains a line break or NUL (htpasswd would hash only the first line)")
    for other in SWITCH_PASSWORD_KEYS:
        if other in secrets and not problems:
            other_value, why = resolve_value(secrets, other)
            if why is None and other_value is not None and str(other_value) == str(value):
                problems.append(f"reuses {other} (the page is plain HTTP)")
    if problems:
        return [f"{key} {'; '.join(problems)}"], []
    return [], []


def _unsafe_scalar(loader, node):
    return loader.construct_scalar(node)


class _InventoryLoader(yaml.SafeLoader):
    """Reads generated group_vars; workbook text there may be tagged ``!unsafe``."""


_InventoryLoader.add_constructor("!unsafe", _unsafe_scalar)


def _is_on(value):
    return str(value).strip().lower() in ("true", "yes", "1")


def _inventory_status_page(project_root, arch, site):
    main = project_root / "output" / arch / site / "inventory" / "group_vars" / "all" / "main.yml"
    if not main.exists():
        return None
    try:
        data = yaml.load(main.read_text(encoding="utf-8"), Loader=_InventoryLoader) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return _is_on(data.get("status_page_enabled", False))


def _workbook_status_page(project_root, arch, site):
    path = project_root / "input" / arch / site / f"{arch}.xlsx"
    if not path.exists():
        return None
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 — unreadable workbooks are validate_excel's to report
        return None
    try:
        if "Deployment" not in wb.sheetnames:
            return None
        for row in wb["Deployment"].iter_rows(values_only=True):
            if row and len(row) > 1 and str(row[0] or "").strip() == "status_page_enabled":
                return _is_on(row[1] if row[1] is not None else "No")
        return False
    finally:
        wb.close()


def status_page_enabled(project_root, arch, site):
    """Whether the site enables the status page, or None if nothing says.

    Both the workbook (the next ``generate`` builds from it) and the generated
    inventory (what a deploy uses) are read; either one enabling it counts."""
    found = [v for v in (_workbook_status_page(project_root, arch, site),
                         _inventory_status_page(project_root, arch, site)) if v is not None]
    return any(found) if found else None


def check_switch_passwords(secrets, policy="hardening"):
    """Findings only (see classify_switch_passwords)."""
    return classify_switch_passwords(secrets, policy=policy)[0]


def is_vault_encrypted(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.readline().startswith(VAULT_MARKER)


def resolve_secrets_file(project_root, arch, site):
    """The secrets.yml the deploy will actually read.

    The generated per-deployment copy wins when it exists (excel_parser copies
    the shared template there once and never overwrites it, so operator edits
    live in the copy). Otherwise fall back to the shared template the parser
    would copy from.
    """
    generated = project_root / "output" / arch / site / "inventory" / "group_vars" / "all" / "secrets.yml"
    if generated.exists():
        return generated
    shared = project_root / "inventories" / "secrets.yml"
    if shared.exists():
        return shared
    return project_root / "inventories" / "secrets.yml.example"


def check_secrets_file(path, policy="hardening", waived=None, status_page=False):
    """Return (findings, note). findings non-empty => fail closed.

    ``note`` is None when every switch password was inspected; otherwise it
    says what could not be inspected (whole-file vault, missing file, a
    ``!vault`` scalar or Jinja lookup on a switch key). ``waived`` collects
    keys let through by the development opt-in (see classify_switch_passwords).
    ``status_page=True`` also gates ``status_page_password``.
    """
    path = Path(path)
    if not path.exists():
        return [], f"no secrets file at {path} — templates will use built-in defaults"
    if is_vault_encrypted(path):
        return [], (f"{path} is vault-encrypted — skipping password check "
                    f"(Ansible decrypts it at run time)")
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.load(fh, Loader=_SecretsLoader) or {}
    except yaml.YAMLError as exc:
        # Never echo the parser message: a marked error quotes the offending
        # source line, which may be a password.
        where = ""
        if isinstance(exc, yaml.MarkedYAMLError) and exc.problem_mark is not None:
            mark = exc.problem_mark
            where = f" (line {mark.line + 1}, column {mark.column + 1})"
        return [f"{path} is not valid YAML{where}"], None
    if not isinstance(data, dict):
        return [f"{path} does not contain a mapping"], None
    findings, unchecked = classify_switch_passwords(data, policy=policy, waived=waived)
    if status_page:
        sp_findings, sp_unchecked = check_status_page_password(data)
        findings += sp_findings
        unchecked += sp_unchecked
    note = "; ".join(unchecked) + " — not checked here" if unchecked else None
    return findings, note


def record_dev_opt_in(project_root, arch, site, waived):
    """Write (or, when nothing was waived, remove) the opt-in record for a site."""
    site_dir = project_root / "output" / arch / site
    record = site_dir / DEV_OPT_IN_RECORD
    if not waived:
        if record.exists():
            record.unlink()
        return None
    site_dir.mkdir(parents=True, exist_ok=True)
    record.write_text(
        "DEVELOPMENT ONLY - NOT FOR A REAL DEPLOYMENT\n"
        f"This output was generated with {DEV_OPT_IN_ENV}=1: the switch password\n"
        "key(s) below still hold a shipped placeholder value (ADR-0091).\n"
        "Set real values in secrets.yml and re-run without the opt-in.\n\n"
        + "".join(f"  - {key}\n" for key in waived),
        encoding="utf-8")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check that switch passwords in secrets.yml pass Cumulus password hardening.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--arch", help="Architecture (resolves output/<arch>/<site>/inventory/.../secrets.yml)")
    group.add_argument("--file", help="Explicit secrets.yml to check")
    parser.add_argument("--site", default="default", help="Site name (default: default)")
    parser.add_argument("--policy", choices=POLICIES,
                        default=os.environ.get(POLICY_ENV, "hardening"),
                        help="hardening (default, ERA policy = Cumulus password-security rules) "
                             f"or placeholder (only reject CHANGE_ME/empty/username); env {POLICY_ENV}")

    parser.add_argument("--status-page-enabled", action="store_true",
                        help="also gate status_page_password (automatic with --arch "
                             "when the workbook or generated inventory enables the status page)")
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parent.parent
    path = Path(args.file) if args.file else resolve_secrets_file(project_root, args.arch, args.site)
    status_page = args.status_page_enabled or bool(
        args.arch and status_page_enabled(project_root, args.arch, args.site))
    opt_in = dev_opt_in_enabled()
    waived = [] if opt_in else None

    findings, note = check_secrets_file(path, policy=args.policy, waived=waived,
                                        status_page=status_page)
    if note:
        print(f"  ℹ️  {note}")
    if waived:
        print(f"  ⚠️  WARNING: {DEV_OPT_IN_ENV}=1 — development only. Placeholder value(s) "
              f"accepted for: {', '.join(waived)}.")
        print("     Never deploy real hardware with these; set real passwords in secrets.yml.")
    elif opt_in:
        print(f"  ⚠️  WARNING: {DEV_OPT_IN_ENV}=1 is set (development only); no placeholder was waived.")
    if args.arch:
        record = record_dev_opt_in(project_root, args.arch, args.site, waived)
        if record:
            print(f"     Recorded in {record}")
    if not findings:
        if not note:
            print(f"  ✓ Switch passwords in {path} pass the ERA switch-password policy ({args.policy})")
            if status_page:
                print("  ✓ status_page_password is set and not a placeholder")
        return 0
    print(f"❌ Switch password(s) in {path} fail the ERA switch-password policy ({args.policy}):")
    for f in findings:
        print(f"   - {f}")
    if args.policy == "hardening":
        print("   Policy (ADR-0078) = Cumulus password-security rules: >= 8 characters with")
        print("   lowercase, uppercase, a digit and a special character, and not the switch")
        print("   username. A hardened switch refuses such a password at ZTP time and every")
        print(f"   later login uses the wrong one. {POLICY_ENV}=placeholder relaxes to")
        print("   placeholder/empty/username only (unhardened switches).")
    if any(PLACEHOLDER_PROBLEM in f for f in findings if not f.startswith(STATUS_PAGE_PASSWORD_KEY)):
        print(f"   Development/Air sandbox only: {DEV_OPT_IN_ENV}=1 accepts the shipped")
        print("   placeholders with a warning (ADR-0091). Never use it for real hardware.")
    print("   Fix the key(s) above in secrets.yml (see docs/SECRETS_AND_VAULT.md) and re-run.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
