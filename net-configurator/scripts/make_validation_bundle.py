#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Package a deployment's generated artifacts into a validation bundle an OEM
can send for endorsement (ERA-37).

    python3 scripts/make_validation_bundle.py --arch 2-8-9-800 [--site default]
    make validation-bundle ARCH=2-8-9-800

Contents: the rendered switch configs, the generated inventory, the topology,
any reports, and the source Excel — plus a MANIFEST.txt with per-file SHA-256
so a reviewer can verify nothing was altered in transit.

**The bundle is built to be safe to email.** `output/` holds a *plaintext*
`group_vars/all/secrets.yml`, and an LDAP-enabled deployment renders its LDAP
secret into the switch config scripts. Three layers keep those out:

  1. `secrets.yml` is never staged.
  2. Every literal value from `secrets.yml` is redacted wherever else it appears
     (value-based, so it does not depend on guessing the syntax).
  3. A pattern guard scans the staged tree; any credential-shaped survivor
     aborts the build with a non-zero exit and no archive written.

Layer 3 is the important one: it means a future template change cannot silently
reintroduce a leak, because the bundle simply refuses to build.
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Staged from output/<arch>/<site>/. Missing directories are skipped with a note
# rather than failing — a switches-only run has no reports, which is fine.
BUNDLE_DIRS = ("configs", "inventory", "topology", "reports")

# Never staged, matched against the path relative to the site directory.
EXCLUDE_RELPATHS = ("inventory/group_vars/all/secrets.yml",)

# Text extensions worth rewriting/scanning. Binary artifacts (.xlsx) are staged
# as-is; the Excel is operator input and carries no generated credentials.
TEXT_SUFFIXES = {".sh", ".yml", ".yaml", ".json", ".txt", ".cfg", ".conf", ".ini", ""}

REDACTED = "<REDACTED-FOR-VALIDATION-BUNDLE>"

# Backstop patterns for the final guard. Deliberately broader than the redaction
# rules: this is the net that catches something the value-based pass missed.
# Each entry is (label, compiled regex). A match is a hard failure.
GUARD_PATTERNS = [
    ("nvue aaa secret", re.compile(r"nv set .*\b(secret|password)\s+(?!<REDACTED)\S+")),
    ("ansible vault body", re.compile(r"^\$ANSIBLE_VAULT;", re.M)),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("ngc api key", re.compile(r"\bnvapi-[A-Za-z0-9_\-]{8,}")),
]

# A Jinja reference like "{{ switch_ansible_password }}" is not a secret — the
# generated inventory is full of them by design.
JINJA_REF = re.compile(r"\{\{[^}]*\}\}")

# Documented placeholders (CLAUDE.md: "Only default/placeholder passwords in
# version control"). These carry no secret, and redacting them actively damages
# the bundle: the shipped defaults set status_page_password to CHANGE_ME, which
# also appears as `ansible_host: CHANGE_ME` in the Air vnode host_vars — so a
# naive value-based pass blanks a hostname field the reviewer needs.
PLACEHOLDER_VALUES = {
    "change_me", "changeme", "change-me", "tbd", "todo", "none", "null",
    "example", "placeholder", "unset", "n/a",
    # Documented shipped defaults (CLAUDE.md / SECURITY.md). They are public in
    # the repo, so redacting one protects nothing — and each is a common word
    # that appears in legitimate content, where redaction does real damage:
    #   nvidia  -> `ansible_host: air-worker-example.air-inside.nvidia.com`
    #              `status_page_url: http://...air-inside.nvidia.com:14357`
    #   cumulus -> `nv set system aaa user cumulus ...` in every switch config
    # Observed on a real site (2-8-9-800/evpnval): server_ansible_password and
    # ansible_become_password were both `nvidia`, matching 8 files each.
    "nvidia", "cumulus", "ubuntu", "admin", "root",
}

# Values that are already masked — by Cumulus itself, or by a previous pass.
# A running-config dump renders an unset/hidden password as `'*'`, which is the
# absence of a secret, not one. Without this the guard fires on every collected
# `reports/raw/config-*.txt`, which is exactly the artifact an endorsement
# bundle exists to carry.
MASKED_VALUES = {"'*'", '"*"', "*", "''", '""', "!", "!!", "x", "xxx", "<hidden>"}

# A real secret that is also a common word (e.g. "nvidia") would redact half the
# tree, including SPDX headers. We still redact — under-redaction is a security
# bug, over-redaction is only a usability one — but say so loudly, because the
# right fix is to change the password, not to weaken the scrub.
WIDE_MATCH_WARN_FILES = 5

# Minimum length for value-based redaction. Below this a value matches too much
# to be redacted safely, and is too weak to be a real credential anyway.
MIN_SECRET_LEN = 6


def _print(msg=""):
    print(msg, flush=True)


def site_dir(arch: str, site: str) -> Path:
    return REPO / "output" / arch / site


def source_excel(arch: str, site: str) -> Path | None:
    p = REPO / "input" / arch / site / f"{arch}.xlsx"
    return p if p.exists() else None


def load_secret_values(arch: str, site: str) -> list[str]:
    """Literal secret values to redact, read from the site's secrets.yml.

    Returns the values only — never logged, only used for replacement. Skipped:
    templated values, anything shorter than MIN_SECRET_LEN, and documented
    placeholders (which are not secrets and whose redaction corrupts real
    fields — see PLACEHOLDER_VALUES).
    """
    path = site_dir(arch, site) / "inventory" / "group_vars" / "all" / "secrets.yml"
    if not path.exists():
        return []
    values = []
    for line in path.read_text().splitlines():
        m = re.match(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*:\s*(.+?)\s*$", line)
        if not m:
            continue
        val = m.group(1).strip().strip('"').strip("'")
        if not val or JINJA_REF.search(val):
            continue
        if val.strip().lower() in PLACEHOLDER_VALUES:
            continue
        if len(val) < MIN_SECRET_LEN:
            continue
        values.append(val)
    # Longest first, so a value that contains another is redacted whole.
    return sorted(set(values), key=len, reverse=True)


def is_texty(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    try:
        path.read_text()
        return True
    except (UnicodeDecodeError, OSError):
        return False


def stage(arch: str, site: str, staging: Path) -> tuple[int, int]:
    """Copy the bundle contents into `staging`, redacting as we go.

    Returns (files_staged, files_redacted)."""
    src_site = site_dir(arch, site)
    secrets = load_secret_values(arch, site)
    staged = redacted = 0
    per_value_hits = {v: 0 for v in secrets}

    for sub in BUNDLE_DIRS:
        src = src_site / sub
        if not src.is_dir():
            _print(f"    - {sub}/ not present, skipping")
            continue
        for f in sorted(src.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(src_site)
            if str(rel) in EXCLUDE_RELPATHS:
                _print(f"    ! excluded {rel} (plaintext credentials)")
                continue
            dst = staging / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if secrets and is_texty(f):
                text = f.read_text()
                original = text
                for val in secrets:
                    if val in text:
                        per_value_hits[val] += 1
                        text = text.replace(val, REDACTED)
                if text != original:
                    redacted += 1
                dst.write_text(text)
            else:
                shutil.copy2(f, dst)
            staged += 1

    xlsx = source_excel(arch, site)
    if xlsx:
        shutil.copy2(xlsx, staging / xlsx.name)
        staged += 1
    else:
        _print(f"    - no source Excel at input/{arch}/{site}/{arch}.xlsx, skipping")

    # A credential that reads like a common word redacts far more than intended.
    # Warn without naming the value, so the operator can fix the password rather
    # than discover a mangled bundle downstream.
    for val, hits in per_value_hits.items():
        if hits >= WIDE_MATCH_WARN_FILES:
            _print(f"    ⚠️  a secrets.yml value matched {hits} files — it is "
                   f"probably a common word, so this bundle is likely "
                   f"over-redacted. Change that password rather than relaxing "
                   f"the scrub.")

    return staged, redacted


def guard(staging: Path) -> list[str]:
    """Scan the staged tree; return human-readable findings (empty = clean)."""
    findings = []
    for f in sorted(staging.rglob("*")):
        if not f.is_file() or not is_texty(f):
            continue
        text = f.read_text()
        for label, pat in GUARD_PATTERNS:
            for m in pat.finditer(text):
                snippet = m.group(0)
                if JINJA_REF.search(snippet) or REDACTED in snippet:
                    continue
                # Already-masked values are the absence of a secret.
                if snippet.rsplit(None, 1)[-1] in MASKED_VALUES:
                    continue
                line_no = text[: m.start()].count("\n") + 1
                findings.append(
                    f"{f.relative_to(staging)}:{line_no}: {label}")
    return findings


def git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def write_manifest(staging: Path, arch: str, site: str, stamp: str) -> None:
    lines = [
        "ERA Validation Bundle",
        "=" * 60,
        f"Architecture : {arch}",
        f"Site         : {site}",
        f"Generated    : {stamp}",
        f"Tool commit  : {git_sha()}",
        "",
        "Credential handling: `inventory/group_vars/all/secrets.yml` is omitted,",
        "and any secret value it contained is redacted wherever else it appeared.",
        "This bundle was scanned for credential patterns before packaging; the",
        "build fails rather than shipping a match.",
        "",
        "SHA-256 of every included file:",
        "-" * 60,
    ]
    for f in sorted(staging.rglob("*")):
        if f.is_file():
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            lines.append(f"{digest}  {f.relative_to(staging)}")
    (staging / "MANIFEST.txt").write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arch", required=True)
    ap.add_argument("--site", default="default")
    ap.add_argument("--out", help="output .zip path (default: output/<arch>/<site>/)")
    args = ap.parse_args()

    src_site = site_dir(args.arch, args.site)
    if not src_site.is_dir():
        _print(f"❌ No generated output at {src_site.relative_to(REPO)}")
        _print(f"   Run: make generate ARCH={args.arch} SITE={args.site}")
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fname = f"validation-bundle-{args.arch}-{args.site}-" \
            f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.zip"
    out_zip = Path(args.out) if args.out else src_site / fname

    _print("=" * 60)
    _print(f"  Validation bundle — {args.arch} / {args.site}")
    _print("=" * 60)

    staging = src_site / ".bundle-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        _print("  Staging contents...")
        staged, redacted = stage(args.arch, args.site, staging)
        _print(f"    ✓ {staged} file(s) staged, {redacted} redacted")

        _print("  Scanning for credentials...")
        findings = guard(staging)
        if findings:
            _print("")
            _print("❌ Credential-shaped content survived redaction — refusing to")
            _print("   write a bundle that may leak secrets. Findings:")
            for f in findings[:20]:
                _print(f"     {f}")
            if len(findings) > 20:
                _print(f"     ... and {len(findings) - 20} more")
            _print("")
            _print("   Fix the generator/template or extend the redaction rules in")
            _print("   scripts/make_validation_bundle.py, then re-run.")
            return 1
        _print("    ✓ clean")

        write_manifest(staging, args.arch, args.site, stamp)

        _print("  Packaging...")
        out_zip.parent.mkdir(parents=True, exist_ok=True)
        if out_zip.exists():
            out_zip.unlink()
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(staging.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(staging))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    size_kb = out_zip.stat().st_size / 1024
    abs_path = out_zip.resolve()
    # Repo-relative when it sits inside the tree (the usual case), else just the
    # absolute path — `--out /tmp/x.zip` used to raise ValueError here, *after*
    # the archive had already been written.
    try:
        shown = abs_path.relative_to(REPO.resolve())
    except ValueError:
        shown = abs_path

    _print("")
    _print(f"✅ Bundle written ({size_kb:.1f} KB)")
    _print(f"   {shown}")
    _print("")
    _print("   Full path (most terminals make this clickable):")
    _print(f"   {abs_path}")
    _print(f"   file://{abs_path}")
    _print("")
    _print("   Safe to send: secrets.yml omitted, secret values redacted,")
    _print("   contents credential-scanned. See MANIFEST.txt inside.")
    _print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
