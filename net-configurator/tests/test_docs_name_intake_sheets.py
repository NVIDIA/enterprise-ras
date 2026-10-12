# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""User-facing docs describe the intake-form sheets, not the legacy layout.

ADR-0064 made the intake form (`Read Me`, `Wiremap`, `Network Data`,
`Switch Data`, `Host Data`, `Deployment`, `Derived`) the only accepted input;
`validate-excel` refuses a `Settings`/`Nodes`/`VLANs & Profiles`/`Wire Map`
workbook. The quick-start bullets, the validator description and the Air
guide's "key tabs" table must therefore name the sheets an operator actually
edits. Legacy names may still appear where they are explicitly presented as
the *older* layout (conversion notes, `intake_to_legacy` views).
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from excel_parser import REQUIRED_INTAKE_SHEETS  # noqa: E402

INTAKE_REQUIRED = ("Wiremap", "Deployment", "Switch Data", "Host Data",
                   "Network Data")

# (doc, legacy phrasing presented as current)
LEGACY_AS_CURRENT = [
    ("README.md", r"^- \*\*(Settings|Nodes|Loopbacks|VLANs & Profiles|Wire Map)\*\* --"),
    ("README.md", r"on the Nodes tab"),
    ("scripts/README.md", r"Parses Settings, Nodes"),
    ("scripts/README.md", r"required sheets exist \(Settings, Nodes"),
    ("scripts/README.md", r"from the Excel Settings tab"),
    ("docs/AIR_DEPLOYMENT_GUIDE.md", r"^\| \*\*(Settings|VLANs & Profiles|Wire Map)\*\* \|"),
    ("docs/ZTP_MAC_ADDRESSES.md", r"\*\*Nodes\*\* tab"),
    ("docs/EXCEL_CONFIGURATION_GUIDE.md", r"^\*\*(Settings|Nodes):\*\*"),
    ("docs/EXCEL_CONFIGURATION_GUIDE.md", r"\*\*Loopbacks\*\* tab's `ASN`"),
    ("docs/MANUAL_FALLBACK_GUIDE.md", r"in\s+\"VLANs & Profiles\""),
    ("docs/LOOPBACKS.md", r"Add an optional \*\*Loopbacks\*\* sheet"),
]


@pytest.mark.parametrize("doc,pattern", LEGACY_AS_CURRENT,
                         ids=[f"{d}:{p}" for d, p in LEGACY_AS_CURRENT])
def test_legacy_sheet_names_not_presented_as_current(doc, pattern):
    text = (ROOT / doc).read_text(encoding="utf-8")
    hits = [m.group(0) for m in re.finditer(pattern, text, re.MULTILINE)]
    assert hits == [], f"{doc} still presents the legacy sheet layout as current: {hits}"


# (doc, heading opening the operator-facing section) -- scoped so a mention
# elsewhere in the file (e.g. converter notes) cannot satisfy the check.
SECTIONS = [
    ("README.md", "Update the sheets for your deployment"),
    ("scripts/README.md", "## excel_parser.py"),
    ("docs/AIR_DEPLOYMENT_GUIDE.md", "Key tabs:"),
]


@pytest.mark.parametrize("doc,heading", SECTIONS, ids=[d for d, _ in SECTIONS])
def test_docs_name_every_required_intake_sheet(doc, heading):
    text = (ROOT / doc).read_text(encoding="utf-8")
    start = text.find(heading)
    assert start >= 0, f"{doc}: section {heading!r} not found"
    section = text[start:start + 1500]
    missing = [s for s in INTAKE_REQUIRED if s not in section]
    assert missing == [], f"{doc} {heading!r} never names intake sheet(s): {missing}"


def test_required_intake_sheets_match_parser():
    assert set(REQUIRED_INTAKE_SHEETS) == set(INTAKE_REQUIRED)
