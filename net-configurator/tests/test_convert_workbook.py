# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""The converter must preserve every wiremap link and warn that it is
transitional."""
import sys
from pathlib import Path

import openpyxl
import pytest

REPO = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(Path(__file__).parent))
from conftest import LEGACY_SAMPLE  # noqa: E402

# The frozen legacy sample -- see conftest. `input/` holds only intake-form
# workbooks now, so there is nothing there for a legacy-only converter to read.
LEGACY_SRC = str(LEGACY_SAMPLE)
sys.path.insert(0, str(REPO / "scripts"))

from convert_workbook import DERIVED_SETTINGS, UNDERIVABLE_STRIPPED_SETTINGS, convert
from intake_reader import column_map, header_row


def test_link_count_is_preserved(tmp_path):
    src = LEGACY_SRC
    dst = tmp_path / "intake.xlsx"
    convert(src, dst)

    legacy = openpyxl.load_workbook(src, data_only=True)["Wire Map"]
    legacy_links = sum(
        1 for r in range(2, legacy.max_row + 1) if legacy.cell(r, 2).value)

    out = openpyxl.load_workbook(dst, data_only=True)["Wiremap"]
    out_links = sum(1 for r in range(3, out.max_row + 1) if out.cell(r, 4).value)

    assert out_links == legacy_links


def _has_real_rows(ws):
    """Rows below the header that are not `#` instruction lines."""
    for row in ws.iter_rows(min_row=2):
        values = [c.value for c in row if c.value not in (None, "")]
        if values and not str(values[0]).lstrip().startswith("#"):
            return True
    return False


def test_output_sheets_are_the_intake_set_plus_carried_overrides(tmp_path):
    """Sheet set: the vendor template's data sheets + ERA's override sheets.

    `Rack Elevations` and `High Level BOM` are deliberately NOT emitted -- the
    legacy workbook has no source for either, so they would only ever be empty
    padding.

    A POPULATED override sheet MUST survive. Dropping them was silent data
    loss: a customer workbook with real ACLs or route policy converted to one
    with none, no warning, detectable only by diffing sheet lists.

    An EMPTY one is dropped, per ADR-0064 D6 -- all five are unfilled in every
    shipped workbook, so carrying them adds four blank tabs an OEM scrolls
    past. "Empty" ignores `#`-prefixed instruction rows: every shipped
    Custom_Config carries a "HOW TO USE -- delete these rows" block, and
    counting that as data would keep the sheet alive and defeat D6.

    The two rules are not in tension: the risk D6 creates is losing real
    overrides, and keying off content rather than name is what removes it.
    """
    import openpyxl
    out = tmp_path / "intake.xlsx"
    convert(LEGACY_SRC, out)
    got = openpyxl.load_workbook(out).sheetnames

    for name in ["Read Me", "Wiremap", "Network Data", "Switch Data",
                 "Host Data", "Deployment", "Derived"]:
        assert name in got, f"missing intake sheet {name!r}: {got}"

    legacy = openpyxl.load_workbook(LEGACY_SRC, read_only=True)
    for name in ["Route policy", "Prefix lists", "ACLs", "Community lists",
                 "Custom_Config"]:
        if name not in legacy.sheetnames:
            continue
        populated = _has_real_rows(legacy[name])
        if populated:
            assert name in got, (
                f"override sheet {name!r} has real rows and was dropped -- that "
                f"is silent data loss for any workbook that uses it: {got}")
        else:
            assert name not in got, (
                f"override sheet {name!r} is empty and should not ship (D6): {got}")

    for name in ["Rack Elevations", "High Level BOM"]:
        assert name not in got, (
            f"{name!r} should no longer be emitted -- nothing populates it")


def test_deprecation_warning_is_emitted(tmp_path, capsys):
    src = LEGACY_SRC
    convert(src, tmp_path / "intake.xlsx")
    assert "removed in nc-v10" in capsys.readouterr().err


def test_era_extension_columns_survive_the_round_trip(tmp_path):
    """Host Data's ERA extension columns (design doc: 'Host Data needs ERA
    extension columns') must carry Prefix and Gateway for a gpu node —
    dropping them changes generated configs."""
    src = LEGACY_SRC
    dst = tmp_path / "intake.xlsx"
    convert(src, dst)

    ws = openpyxl.load_workbook(dst, data_only=True)["Host Data"]
    headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
    name_col = headers["System Name"]
    prefix_col = headers["Prefix"]
    gateway_col = headers["Gateway"]

    row = next(r for r in range(2, ws.max_row + 1)
               if ws.cell(r, name_col).value == "su-01-node-01")
    assert ws.cell(row, prefix_col).value == 24
    assert ws.cell(row, gateway_col).value == "192.168.200.1"


def test_switch_data_headers_match_the_template(tmp_path):
    """Switch Data must carry the template's own column names, not our
    legacy ones — plus the ERA extension columns after them."""
    src = LEGACY_SRC
    dst = tmp_path / "intake.xlsx"
    convert(src, dst)

    ws = openpyxl.load_workbook(dst, data_only=True)["Switch Data"]
    assert header_row(ws) == 2, "Switch Data must carry a banded 2-row header"
    cols = column_map(ws)
    for name in [
        "function", "name", "ztp mac address", "mgmt ip", "mgmt gateway",
        "loopback ip", "router-id", "asn", "oob lo", "inband (n-s) lo",
        "exit lo", "gpu lo", "storage lo", "oob in", "cpu (n-s) int",
        "support int", "storage int", "gpu (e-w) int",
    ]:
        assert name in cols, f"missing template column: {name!r}"
    # ERA extension columns keep their legacy names and sit after the
    # template's own 18 columns.
    for name in ["oob vlan", "prefix", "ztp", "enabled", "notes"]:
        assert name in cols, f"missing ERA extension column: {name!r}"
    assert cols["notes"] > cols["gpu (e-w) int"]

    # Pin the row-1 group-label positions themselves, not just that the
    # right set of labels exists — header_row() only checks the label set,
    # so a drift in *which* column a label sits over would pass that check
    # silently while still showing a human mis-grouped columns.
    assert ws.cell(1, 1).value == "Switch"
    assert ws.cell(1, 4).value == "Switch IP's"
    assert ws.cell(1, 7).value == "L3"
    assert ws.cell(1, 14).value == "L2"


def test_network_data_headers_match_the_template(tmp_path):
    """Network Data's main table must carry the template's own column
    names, not our legacy `VLANs` names."""
    src = LEGACY_SRC
    dst = tmp_path / "intake.xlsx"
    convert(src, dst)

    ws = openpyxl.load_workbook(dst, data_only=True)["Network Data"]
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)
               if ws.cell(1, c).value]
    assert headers == [
        "Fabric Name", "Use", "VLAN", "VNI(D)", "VRF", "IP Subnet",
        "Gateway Addr", "Comments", "DHCP Relay Client",
    ]


def test_orphaned_loopback_name_raises_instead_of_vanishing(tmp_path):
    """A `Loopbacks & ASNs` row with no matching `Nodes` row must raise,
    naming the orphan — not silently disappear from the output, taking
    its loopback addresses and ASN with it."""
    src = LEGACY_SRC
    wb = openpyxl.load_workbook(src)
    loopbacks = wb["Loopbacks & ASNs"]
    loopbacks.append(["orphan-switch-99", "10.99.99.1", None, None, None,
                      None, None, 4260399999])
    legacy = tmp_path / "legacy-with-orphan.xlsx"
    wb.save(legacy)

    with pytest.raises(ValueError, match="orphan-switch-99"):
        convert(legacy, tmp_path / "intake.xlsx")


def test_underivable_stripped_settings_is_computed_not_hardcoded_and_is_12_today():
    """DERIVED_SETTINGS names 14 settings safe to strip from Deployment;
    intake_derive.DERIVABLE_SETTINGS is the ground truth for how many of
    them the parser can actually reconstruct. This pins today's known gap
    (a sanity check on the computed diff, not the source of truth for it —
    the diff itself is computed in convert_workbook.py, not here) so a
    change to either set is a decision someone makes deliberately, not a
    silent drift.
    """
    assert UNDERIVABLE_STRIPPED_SETTINGS == {
        "architecture", "site_name", "ns_tiers", "ew_tiers", "loopback_base",
        "num_physical_ports", "disabled_ports", "gpu_vlan_mode",
        "oob_uplink_mode", "ztp_server", "netq_ip", "ldap_servers",
    }
    assert len(UNDERIVABLE_STRIPPED_SETTINGS) == 12
    assert UNDERIVABLE_STRIPPED_SETTINGS <= DERIVED_SETTINGS


def test_settings_without_a_derivation_are_declared_not_dropped(tmp_path, capsys):
    """The 12 settings intake_derive cannot rebuild must survive conversion.

    They are carried as DECLARED values in `Deployment`. An earlier revision
    stripped all 14 of DERIVED_SETTINGS on the theory that the parser would
    reconstruct them; it could only reconstruct 2, so the other 12 were
    destroyed and four of them silently fell back to wrong hardcoded defaults
    downstream. Assert the values are actually present, not merely that a
    warning mentions them -- the warning is not the guarantee, the data is.
    """
    import openpyxl
    from convert_workbook import NOT_YET_DERIVED_SETTINGS

    out = tmp_path / "intake.xlsx"
    convert(LEGACY_SRC, out)

    legacy = openpyxl.load_workbook(LEGACY_SRC, data_only=True)
    legacy_settings = {
        str(legacy["Settings"].cell(r, 1).value).strip():
            legacy["Settings"].cell(r, 2).value
        for r in range(1, legacy["Settings"].max_row + 1)
        if legacy["Settings"].cell(r, 1).value
    }

    dep = openpyxl.load_workbook(out, data_only=True)["Deployment"]
    declared = {
        str(dep.cell(r, 1).value).strip(): dep.cell(r, 2).value
        for r in range(1, dep.max_row + 1) if dep.cell(r, 1).value
    }

    for name in sorted(NOT_YET_DERIVED_SETTINGS):
        if name not in legacy_settings:
            continue                      # not present in this fixture
        assert name in declared, (
            f"{name!r} was dropped by conversion -- it has no derivation, so "
            f"it must be declared in Deployment")
        assert str(declared[name]) == str(legacy_settings[name]), (
            f"{name!r} changed value across conversion: "
            f"{legacy_settings[name]!r} -> {declared[name]!r}")

    stderr = capsys.readouterr().err
    assert "preserved, not dropped" in stderr


def test_convert_guards_a_missing_reference_sheet_instead_of_raising_keyerror(tmp_path, capsys):
    """All 14 shipped workbooks carry `Reference`, but a hand-authored or
    edited legacy workbook is not guaranteed to. A customer workbook
    without one must not get a raw KeyError."""
    src = LEGACY_SRC
    wb = openpyxl.load_workbook(src)
    del wb["Reference"]
    legacy = tmp_path / "legacy-no-reference.xlsx"
    wb.save(legacy)

    dst = tmp_path / "intake.xlsx"
    convert(legacy, dst)  # must not raise

    assert "Read Me" in openpyxl.load_workbook(dst).sheetnames
    assert "no 'Reference' sheet" in capsys.readouterr().err


def test_output_matches_the_vendor_template_styling(tmp_path):
    """Converted workbooks must look like the template, not like raw data.

    Operators read these next to the vendor's own workbook; a plain grid of
    values reads as broken even when every value is right. Colours are the
    ones measured from the template (scripts/intake_style.py).

    Data validation (the locked dropdowns) is deliberately NOT reproduced --
    see that module's docstring.
    """
    import openpyxl
    from intake_style import DARK, MID, TINT, WHITE

    out = tmp_path / "intake.xlsx"
    convert(LEGACY_SRC, out)
    ws = openpyxl.load_workbook(out)["Wiremap"]

    assert ws.cell(1, 1).fill.start_color.rgb == MID   # Source band
    assert ws.cell(1, 1).font.bold

    assert ws.cell(1, 10).fill.start_color.rgb == TINT  # Destination band

    hdr = ws.cell(2, 1)
    assert hdr.fill.start_color.rgb == DARK
    assert hdr.font.bold and hdr.font.color.rgb == WHITE
    assert not hdr.alignment.wrap_text, "template widens columns, not wraps"

    # Rows ALTERNATE: tinted, unfilled, tinted... Filling every row instead
    # produces a flat grey block -- which an earlier revision did, and which
    # the previous version of this assertion (checking row 3 alone) passed.
    def filled(r):
        f = ws.cell(r, 1).fill
        return f.patternType is not None and f.start_color.rgb == TINT

    assert filled(3), "first data row should be tinted"
    assert not filled(4), "second data row should be unfilled -- rows alternate"
    assert filled(5), "third data row should be tinted"
    assert not filled(6), "fourth data row should be unfilled"
    assert ws.column_dimensions["A"].width, "columns were left at default width"
    assert ws.freeze_panes == "A3", "header should stay visible when scrolling"


def test_derived_sheet_shows_what_was_derived_and_from_where(tmp_path):
    """The `Derived` tab is visibility-only, and must say where values came from.

    Two settings are absent from `Deployment` by design because they are
    computed from the wiremap. Without this sheet a reviewer cannot tell an
    intentional omission from a conversion bug without running the parser.
    """
    import openpyxl
    out = tmp_path / "intake.xlsx"
    convert(LEGACY_SRC, out)
    wb = openpyxl.load_workbook(out)

    assert "Derived" in wb.sheetnames
    ws = wb["Derived"]
    rows = {ws.cell(r, 1).value: (ws.cell(r, 2).value, ws.cell(r, 3).value)
            for r in range(2, ws.max_row + 1) if ws.cell(r, 1).value}

    for name in ("gpu_planes", "convergence"):
        assert name in rows, f"{name!r} missing from the Derived sheet"
        value, source = rows[name]
        assert value not in (None, ""), f"{name!r} has no derived value"
        assert source and "Wiremap" in str(source), (
            f"{name!r} does not say what it was derived from: {source!r}")

    # Absent from Deployment: that is the point of deriving them.
    dep = wb["Deployment"]
    declared = {str(dep.cell(r, 1).value).strip()
                for r in range(1, dep.max_row + 1) if dep.cell(r, 1).value}
    assert "gpu_planes" not in declared
    assert "convergence" not in declared


def test_group_band_merges_match_the_vendor_template(tmp_path):
    """Merged group bands are the template's most recognisable feature.

    Pinned to the spans measured from the vendor template. Without the merges
    the band renders as a flat coloured stripe with one label floating at the
    left, which is what an earlier revision produced and what made converted
    workbooks read as broken at a glance.
    """
    import openpyxl
    out = tmp_path / "intake.xlsx"
    convert(LEGACY_SRC, out)
    wb = openpyxl.load_workbook(out)

    expected = {
        "Wiremap": ["A1:I1", "J1:S1", "T1:W1"],
        "Switch Data": ["A1:C1", "D1:E1", "G1:M1", "N1:R1"],
    }
    for sheet, spans in expected.items():
        got = sorted(str(r) for r in wb[sheet].merged_cells.ranges)
        assert got == sorted(spans), (
            f"{sheet} group bands drifted from the template: "
            f"expected {sorted(spans)}, got {got}")

    # Host Data has no band row in the template; do not invent one.
    assert not wb["Host Data"].merged_cells.ranges


def test_key_value_sheets_are_not_frozen(tmp_path):
    """`Deployment` must not freeze panes.

    Its header sits well down the sheet, under the instruction block, so
    freezing at it locks a large slab of rows in place -- visually wrong and
    actively annoying to scroll. The wide data sheets still freeze, because
    there a stuck header is the point.
    """
    import openpyxl
    out = tmp_path / "intake.xlsx"
    convert(LEGACY_SRC, out)
    wb = openpyxl.load_workbook(out)

    for name in ("Deployment", "Derived"):
        assert wb[name].freeze_panes is None, (
            f"{name} should not be frozen, got {wb[name].freeze_panes}")

    assert wb["Wiremap"].freeze_panes, "Wiremap should still freeze its header"


def test_converting_a_workbook_without_air_only_does_not_crash(tmp_path):
    """`Air_Only` is optional -- the parser treats it that way.

    The converter read it unconditionally, so a legacy workbook without one
    (valid input) died on `KeyError: 'Worksheet Air_Only does not exist.'`.
    All 14 shipped workbooks have the sheet, which is why nothing caught it.
    (Greptile P1)
    """
    import openpyxl
    src = tmp_path / "no-air.xlsx"
    wb = openpyxl.load_workbook(LEGACY_SRC)
    del wb["Air_Only"]
    wb.save(src)

    out = tmp_path / "intake.xlsx"
    convert(str(src), out)          # must not raise
    assert out.is_file()
    assert "Deployment" in openpyxl.load_workbook(out).sheetnames


def test_an_empty_override_sheet_with_a_title_row_is_still_dropped(tmp_path):
    """The header is not always row 1.

    The override sheets allow a title above the header. A rule that treats
    everything below row 1 as data calls such a sheet populated and keeps it,
    which defeats ADR-0064 D6 for exactly the layout it was meant to handle.
    """
    import openpyxl
    src = tmp_path / "titled.xlsx"
    wb = openpyxl.load_workbook(LEGACY_SRC)
    ws = wb["ACLs"]
    ws.insert_rows(1)
    ws.cell(1, 1, "Access Control Lists")
    wb.save(src)
    wb.close()

    out = tmp_path / "intake.xlsx"
    convert(src, out)
    assert "ACLs" not in openpyxl.load_workbook(out).sheetnames, (
        "an empty ACLs sheet with a title row was kept -- the content check "
        "is treating its header as data")


def test_a_carried_sheet_keeps_its_formulas_and_formatting(tmp_path):
    """Carrying a populated sheet as bare strings is still data loss.

    These sheets are carried BECAUSE a user may have authored them, so
    flattening a hand-built rack layout defeats the point. The converter also
    reads the workbook with `data_only=True` for its own purposes, which
    replaces every formula with its last cached result -- carried sheets have
    to come from a formula-preserving read.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    src = tmp_path / "authored.xlsx"
    wb = openpyxl.load_workbook(LEGACY_SRC)
    ws = wb.create_sheet("Rack Elevations")
    ws.cell(1, 1, "Rack")
    ws.cell(1, 2, "Device")
    ws.cell(2, 1, "RACK-01")
    ws.cell(2, 2, "core-01")
    ws.cell(3, 2, "=COUNTA(B2:B2)")
    ws.cell(1, 1).font = Font(bold=True)
    ws.cell(1, 1).fill = PatternFill("solid", fgColor="FFFF0000")
    ws.merge_cells("A5:B5")
    ws.column_dimensions["B"].width = 33.5
    wb.save(src)
    wb.close()

    out = tmp_path / "intake.xlsx"
    convert(src, out)
    got = openpyxl.load_workbook(out)
    assert "Rack Elevations" in got.sheetnames, "authored sheet was dropped"
    r = got["Rack Elevations"]
    assert r.cell(3, 2).value == "=COUNTA(B2:B2)", "formula was flattened"
    assert r.cell(1, 1).font.bold, "formatting was lost"
    assert r.cell(1, 1).fill.fgColor.rgb == "FFFF0000", "fill was lost"
    assert "A5:B5" in [str(m) for m in r.merged_cells.ranges], "merge was lost"
    assert r.column_dimensions["B"].width == 33.5, "column width was lost"
    got.close()


def test_a_loopbacks_sheet_without_an_asn_column_converts(tmp_path, capsys):
    """The sheet grew columns over time; an older workbook lacks some.

    `public-v6.0.4` names the sheet `Loopbacks` and has no `ASN` column at
    all, so the converter died on `KeyError: 'ASN'` three frames down -- on
    the exact class of file the converter exists to migrate.
    """
    import openpyxl
    from convert_workbook import loopbacks_sheet_name

    src = tmp_path / "no-asn.xlsx"
    wb = openpyxl.load_workbook(LEGACY_SRC)
    ws = wb[loopbacks_sheet_name(wb)]
    asn = next(c for c in range(1, ws.max_column + 1)
               if ws.cell(2, c).value == "ASN")
    ws.delete_cols(asn)
    wb.save(src)

    out = tmp_path / "intake.xlsx"
    convert(str(src), out)          # must not raise
    assert out.is_file()
    assert "no ASN column" in capsys.readouterr().err
