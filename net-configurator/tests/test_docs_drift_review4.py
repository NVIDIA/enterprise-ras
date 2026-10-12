# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Docs and help text match the code (release review #4 F1-F3, F17-F21; GitLab #104).

Each check pins one statement the review found false: an arch missing from a
list, a naming "exception" the models contradict, a setting described two
ways, a prompt the docs say is gone, or a hint that points at internal-only
tooling.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
MONOREPO = ROOT.parent
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
DOCS = ROOT / "docs"
VALID_ARCHS = yaml.safe_load((ROOT / "scripts" / "valid_archs.yml").read_text())["archs"]


def _block(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


# F2 / F3: every list of supported archs names every supported arch.
@pytest.mark.parametrize("where,text", [
    ("Makefile print_archs", _block(MAKEFILE, "define print_archs", "endef")),
    ("Makefile ARCHS_ECHO", _block(MAKEFILE, "ARCHS_ECHO =", "\n\n")),
    ("AIR_DEPLOYMENT_GUIDE arch list",
     _block((DOCS / "AIR_DEPLOYMENT_GUIDE.md").read_text(), "Replace `{ARCH}` with one of", "\n\n")),
])
def test_arch_lists_name_every_supported_arch(where, text):
    named = set(re.findall(r"\b\d-\d-\d-\d{3}(?:-SP)?\b", text))
    assert set(VALID_ARCHS) - named == set(), f"{where} omits archs"


def test_2_8_5_400_air_coverage_matches_completed_campaign():
    para = _block(README, "**Largescale samples**", "```")
    assert "including `2-8-5-400`" in para
    assert "not yet deployed" not in para
    assert "48 final Air runs" in README
    assert "LDAP and the status page were disabled" in README


def test_missing_registry_hint_does_not_point_at_internal_tooling(tmp_path):
    if shutil.which("make") is None:
        pytest.fail("GNU make is required")
    tool = tmp_path / "net-configurator"
    (tool / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "Makefile", tool / "Makefile")
    r = subprocess.run(["make", "-C", str(tool), "help"], capture_output=True, text=True)
    assert r.returncode != 0
    assert "valid_archs.yml is missing" in r.stderr
    assert "data-models" not in r.stderr and "make valid-archs" not in r.stderr
    assert "git checkout -- scripts/valid_archs.yml" in r.stderr
    assert "release tarball" in r.stderr


# F18: `200` follows the normal naming rule (400G E/W NICs shared by 2 GPUs).
_EXCEPTION = re.compile(r"per-NIC link speed|documented exception", re.IGNORECASE)


@pytest.mark.parametrize("rel", ["README.md", "docs/ARCH_SUPPORT_MATRIX.md", "Makefile"])
def test_no_per_nic_naming_exception_in_public_docs(rel):
    assert not _EXCEPTION.search((ROOT / rel).read_text(encoding="utf-8"))


@pytest.mark.internal_only("AGENTS.md", "oem-audit/era_submission/deployed_vs_ra.py")
@pytest.mark.parametrize("rel", ["AGENTS.md", "oem-audit/era_submission/deployed_vs_ra.py"])
def test_no_per_nic_naming_exception_in_internal_copies(rel):
    assert not _EXCEPTION.search((MONOREPO / rel).read_text(encoding="utf-8"))


# F19
def test_arch_scaling_docstring_cites_no_missing_directory():
    head = (ROOT / "scripts" / "arch_scaling.py").read_text().split('"""')[1]
    assert "architectural_docs" not in head
    assert "do NOT model multi-tier" not in head


# F20
def test_disabled_ports_described_one_way():
    guide = (DOCS / "EXCEL_CONFIGURATION_GUIDE.md").read_text()
    assert "Highest usable port index" not in guide
    row = next(line for line in guide.splitlines() if line.startswith("| `disabled_ports` |"))
    assert "port numbers" in row


def test_guide_and_readme_agree_on_where_to_start():
    guide = (DOCS / "EXCEL_CONFIGURATION_GUIDE.md").read_text()
    first = next(line for line in guide.splitlines() if line.startswith("1. "))
    assert "sample-<arch>.xlsx" in first
    assert "do not edit directly" in README


def test_guide_says_wiremap_name_typo_is_only_a_warning():
    guide = (DOCS / "EXCEL_CONFIGURATION_GUIDE.md").read_text()
    para = _block(guide, "Use those same `Name` values in the Wiremap", "\n\n")
    assert "warning" in para


def test_readme_does_not_claim_both_planes_share_vlan_900():
    assert "Same\n  VLAN ID (900) on both planes" not in README
    assert "920" in _block(README, "**Dual-plane (`csl-*`", "\n\n")


# F21
def _ask_become_targets():
    targets, current = set(), None
    for line in MAKEFILE.splitlines():
        m = re.match(r"^([a-zA-Z0-9_.-]+):", line)
        if m:
            current = m.group(1)
        elif "--ask-become-pass" in line and current:
            targets.add(current)
    return targets


def test_become_password_docs_name_every_target_that_still_prompts():
    targets = _ask_become_targets()
    assert targets
    for doc in (README, (DOCS / "SECRETS_AND_VAULT.md").read_text()):
        assert "eliminates `--ask-become-pass`" not in doc
        assert "no --ask-become-pass needed" not in doc
    row = next(line for line in (DOCS / "SECRETS_AND_VAULT.md").read_text().splitlines()
               if line.startswith("| `ansible_become_password` |"))
    assert {t for t in targets if f"`{t}`" not in row and f"make {t}" not in row} == set()


def test_validate_all_troubleshooting_lists_five_phases():
    para = _block(README, "After deploying, `make validate-all`", "```bash")
    assert "five" in para and "switch health" in para


def test_make_docs_lists_excel_guide_and_security():
    recipe = _block(MAKEFILE, "\ndocs:", "\n\n")
    assert "EXCEL_CONFIGURATION_GUIDE.md" in recipe and "SECURITY.md" in recipe


def test_case_insensitivity_claim_names_make_secrets_exception():
    para = _block(README, "**Case doesn't matter.**", "```bash")
    assert "make secrets" in para


def test_cumulus_floor_doc_says_it_is_not_checked():
    compat = (DOCS / "NVUE_VERSION_COMPAT.md").read_text()
    assert "Nothing checks this" in compat


# F1
def test_security_checklist_names_the_real_argv_exposures():
    sec = (ROOT / "SECURITY.md").read_text()
    item = next(line for line in sec.splitlines() if "not shared with untrusted local users" in line)
    assert "ProxyCommand" in item and "restart-ldap-switches" in item
    assert "some playbook tasks pass passwords to `sshpass` via CLI args" not in item


# ZTP docs show the option 239 / reservation lines dnsmasq actually renders:
# one `scripts/ztp.sh` URL per interface, `dhcp-host=<mac>,<host>,<ip>,12h`.
def test_ztp_mac_doc_matches_rendered_dnsmasq():
    doc = (DOCS / "ZTP_MAC_ADDRESSES.md").read_text()
    assert not re.search(r"scripts/(core|oob-switch)-\d+\.sh", doc)
    assert "set:core_" not in doc and "tag:core_" not in doc
    assert "dhcp-host=50:6B:4B:12:34:01,core-01,192.168.200.201,12h" in doc
    # option 239 points at the ZTP server's own address, never the .1 gateway
    assert "http://192.168.200.1/" not in doc
    assert "# /etc/dnsmasq.conf" in doc and "# /etc/dnsmasq.d/ztp.conf" in doc
    tmpl = (ROOT / "roles" / "ztp-server" / "templates" / "dnsmasq-ztp.conf.j2").read_text()
    assert "dhcp-host={{ switch_vars.mac_address }},{{ switch_hostname }},{{ switch_vars.ansible_host }},12h" in tmpl


def test_ztp_modes_dnsmasq_example_matches_rendered_dnsmasq():
    example = _block((DOCS / "ZTP_MODES.md").read_text(), "### DHCP Server Configuration", "### Workflow")
    assert "tag:core_01" not in example and "scripts/core-01.sh" not in example
    assert "239,http://10.0.0.100/scripts/ztp.sh" in example
