#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Import an ERA Excel configuration file into the correct input directory.

Reads the 'architecture' and 'site_name' fields from the Settings tab,
then creates input/<arch>/<site>/ and copies the Excel there.

Also writes .era-context so subsequent make commands pick up the new
arch/site automatically.

Usage:
  python3 scripts/import-excel.py /path/to/your-config.xlsx
  python3 scripts/import-excel.py /path/to/your-config.xlsx --site acme-lab
"""

import argparse
import datetime
import re
import shutil
import sys
from pathlib import Path

# Reuse parse_settings from excel_parser (same repo) to avoid duplication
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from excel_parser import parse_settings as _parse_settings
from excel_parser import load_workbook_safe

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / "input"
VALID_ARCHS = ("2-4-3-200", "2-4-5-400", "2-4-5-800", "2-8-5-200", "2-8-9-400", "2-8-9-800", "2-8-9-400-SP")

# Characters not allowed in site directory names
_INVALID_SITE_CHARS = re.compile(r'[^\w\-]')


def _safe_site_name(raw: str) -> str:
    """Sanitize a site name for use as a directory name.

    Case is PRESERVED. This used to `.lower()`, and nothing downstream did: the
    Makefile uses `$(SITE)` verbatim and `make generate` reads
    `input/<arch>/$(SITE)/<arch>.xlsx`, so import wrote one directory and
    generate read another whenever the site name contained an uppercase letter.

    Surfaced by the first e2e run of `2-8-9-400-SP` — the only arch whose NAME
    carries uppercase, so `SITE=ci-<id>-2-8-9-400-SP-noztp` landed on disk as
    `...-2-8-9-400-sp-noztp` and generate failed with a bare `[File] Not found`.
    Not CI-only: any operator using a mixed-case site name hit it.

    Sanitisation of genuinely unsafe characters is unchanged — the output still
    matches the Makefile's SITE guard charset, `[A-Za-z0-9._-]`.
    """
    sanitized = _INVALID_SITE_CHARS.sub('-', raw.strip())
    sanitized = re.sub(r'-+', '-', sanitized).strip('-')
    return sanitized or "default"


def _path_derived_site(xlsx_path: Path, arch: str) -> str | None:
    """If xlsx_path already lives under input/<arch>/<site>/, return <site>.

    Returns None when the file is outside input/<arch>/ or sits directly in
    input/<arch>/ with no site subdirectory — in those cases there is no folder
    to infer from and the caller falls back to the Excel site_name cell. (#33)
    """
    try:
        rel = xlsx_path.resolve().relative_to((INPUT_DIR / arch).resolve())
    except ValueError:
        return None
    parts = rel.parts
    # Normal layout: ("<site>", "<arch>.xlsx"); a bare ("<arch>.xlsx",) → no site.
    if len(parts) >= 2:
        return _safe_site_name(parts[0])
    return None


def read_excel_settings(xlsx_path: Path) -> dict:
    """Return a dict of key→value from the Settings sheet (snake_case keys)."""
    wb = load_workbook_safe(xlsx_path, data_only=True)
    if 'Settings' not in wb.sheetnames:
        wb.close()
        return {}
    settings = _parse_settings(wb['Settings'])
    wb.close()
    return settings


def _archive_existing_template(dest_file: Path, arch: str, site: str):
    """Timestamped-backup an existing dest_file into archive/<date>/ before it
    is overwritten. Returns the backup Path, or None if there was nothing to
    back up. Honors the CLAUDE.md hard backup rule for the committed templates."""
    if not dest_file.exists():
        return None
    backup_dir = BASE_DIR / "archive" / datetime.date.today().isoformat()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%H%M%S")
    backup = backup_dir / f"{arch}.{site}.{stamp}.xlsx.bak"
    shutil.copy2(dest_file, backup)
    return backup


def import_excel(xlsx_path: Path, site_override: str | None = None,
                  auto_confirm: bool = False) -> None:
    xlsx_path = xlsx_path.resolve()

    if not xlsx_path.exists():
        print(f"❌  File not found: {xlsx_path}")
        sys.exit(1)
    if xlsx_path.suffix.lower() not in ('.xlsx', '.xlsm'):
        print(f"❌  Not an Excel file: {xlsx_path.name}")
        sys.exit(1)

    print(f"Reading settings from: {xlsx_path.name}")
    settings = read_excel_settings(xlsx_path)

    # Determine architecture
    arch = settings.get('architecture', '').strip()
    if not arch:
        print("❌  'architecture' key not found in Settings tab.")
        print("    Make sure you are using the ERA Excel template.")
        sys.exit(1)
    if arch not in VALID_ARCHS:
        print(f"❌  Unknown architecture: '{arch}'")
        print(f"    Valid values: {', '.join(VALID_ARCHS)}")
        sys.exit(1)

    # Determine site name. Precedence: --site override > the folder the Excel
    # already lives in (input/<arch>/<site>/) > the Excel site_name cell. The
    # folder wins over the cell so an Excel whose site_name says "sample" can't
    # silently route a file the user placed in input/<arch>/customer-x/ to the
    # wrong site (#33).
    if site_override:
        site = _safe_site_name(site_override)
        print(f"  Using site override: {site!r}")
    else:
        raw_site = str(settings.get('site_name', '') or '').strip()
        excel_site = _safe_site_name(raw_site) if raw_site else ''
        path_site = _path_derived_site(xlsx_path, arch)
        if path_site:
            site = path_site
            if excel_site and excel_site != path_site:
                print(f"⚠️  Excel site_name ({excel_site!r}) differs from the "
                      f"folder it lives in ({path_site!r}); using the folder.")
                print("   Pass --site <name> to choose explicitly.")
            else:
                print(f"  Site from path: {site!r}")
        else:
            site = excel_site or 'default'
            print(f"  Site from Excel (site_name): {raw_site!r} → {site!r}")

    if site == 'default':
        print("⚠️  Importing to 'default' site.")
        print("   This will overwrite the committed template.")
        print("   Use --site <name> to import to a custom site instead.")
        if auto_confirm:
            print("   Continue? [y/N]: y (auto-confirmed)")
        else:
            answer = input("   Continue? [y/N]: ").strip().lower()
            if answer != 'y':
                print("Aborted.")
                sys.exit(1)

    dest_dir = INPUT_DIR / arch / site
    dest_file = dest_dir / f"{arch}.xlsx"

    print(f"\n  Architecture : {arch}")
    print(f"  Site         : {site}")
    print(f"  Destination  : {dest_file.relative_to(BASE_DIR)}")

    # Create destination directory
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Copy the Excel (don't move — leave original in place).
    # If the source IS the destination (e.g. re-running make deploy with the
    # already-imported file), skip the copy and just refresh the context.
    if xlsx_path.resolve() == dest_file.resolve():
        print(f"\n✓ Already at: {dest_file.relative_to(BASE_DIR)} (no copy needed)")
    else:
        # Back up an existing template before overwriting it — importing a
        # different Excel to a site (esp. `default`) would otherwise silently
        # destroy the committed reference template (CLAUDE.md hard backup rule).
        backup = _archive_existing_template(dest_file, arch, site)
        if backup is not None:
            print(f"  ↳ backed up existing template → {backup.relative_to(BASE_DIR)}")
        shutil.copy2(xlsx_path, dest_file)
        print(f"\n✓ Copied to: {dest_file.relative_to(BASE_DIR)}")

    # Write .era-context
    context_path = BASE_DIR / '.era-context'
    context_path.write_text(
        "# ERA Deployment Context\n"
        "# Auto-generated by scripts/import-excel.py\n"
        "# Set manually with: make use ARCH=<type> [SITE=<name>]\n"
        "\n"
        f"arch: {arch}\n"
        f"site: {site}\n"
    )
    print(f"✓ Context set: arch={arch}  site={site}")
    print()
    print("Next steps:")
    print()
    print("  Validate your Excel (recommended):")
    print("    make validate-excel                   Check for errors before generating")
    print()
    print("  Generate configs only (no deployment):")
    print("    make generate                         Excel → inventory + switch configs + topology")
    print()
    print("  Deploy to NVIDIA Air (automated):")
    print("    make air-full-deploy                  Generate + create Air sim + ZTP deploy (all-in-one)")
    print()
    print("  Deploy step by step:")
    print("    make generate                         1. Generate configs + topology")
    print("    make air-deploy                       2. Create Air simulation + configure SSH")
    print("    make switch-ztp-deploy                3. Setup OOB, ZTP server, push configs")
    print()
    print("  Deploy to physical hardware (no Air):")
    print("    make generate                         1. Generate configs + topology")
    print("    make switch-ztp-deploy                2. Setup OOB, ZTP server, push configs")
    print()
    print("  LDAP is auto-detected from Excel. Override with: make switch-ztp-deploy LDAP=1")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Import an ERA Excel file into the correct input/ directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('excel', metavar='EXCEL', help="Path to the Excel file to import")
    parser.add_argument('--site', metavar='NAME', default=None,
                        help="Override site name (default: read from Excel site_name field)")
    parser.add_argument('--yes', '-y', action='store_true', default=False,
                        help="Auto-confirm default site overwrite (used by make deploy)")
    args = parser.parse_args()

    import_excel(Path(args.excel), site_override=args.site,
                  auto_confirm=args.yes)


if __name__ == '__main__':
    main()
