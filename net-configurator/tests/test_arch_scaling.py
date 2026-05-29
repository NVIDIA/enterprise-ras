# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Tests for the SU-scaling pipeline:

  * scripts/arch_scaling.py  — single-tier fan-out tables + helpers
  * scripts/scale_sample_excel.py  — sample-Excel generator
  * scripts/validate_excel.py — single-tier-cap + Air-OOB-single-cable
    validators

All tests run end-to-end against the real default Excels under input/
so a schema drift surfaces here before it surfaces in CI.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from arch_scaling import (
    ARCH_SCALING,
    ScalingTier,
    get_tier,
    is_supported_single_tier,
    max_single_tier_su,
    node_name_to_su,
)
from validate_excel import validate_excel


def _wm_cols(ws):
    """Resolve Wire Map B-side column indices from header row.

    Returns (SWNAME_COL, SWPORT_COL). After the 2026-05-28 schema
    revision added `Cable Split (A)` between Port Side (A) and System
    Name (B), B-side columns shifted from (5, 6) to (6, 7). Header
    lookup keeps the tests resilient to further column changes.
    """
    headers = {}
    for c in range(1, ws.max_column + 1):
        h = (ws.cell(1, c).value or "")
        headers[str(h).strip().lower()] = c
    swname = headers.get("system name (b)",
              headers.get("switch name", 5))
    swport = headers.get("port (b)",
              headers.get("switch port", 6))
    return swname, swport


# ---------------------------------------------------------------------------
# arch_scaling helpers
# ---------------------------------------------------------------------------

class TestNodeNameToSu:
    def test_su_pattern(self):
        assert node_name_to_su("su-1-node-1") == 1
        assert node_name_to_su("su-5-node-3") == 5
        assert node_name_to_su("su-12-node-99") == 12

    def test_gpu_pattern_quarters(self):
        # 4 GPU nodes per SU on 2-8-9-800
        assert node_name_to_su("gpu-1") == 1
        assert node_name_to_su("gpu-2") == 1
        assert node_name_to_su("gpu-3") == 1
        assert node_name_to_su("gpu-4") == 1
        assert node_name_to_su("gpu-5") == 2
        assert node_name_to_su("gpu-8") == 2
        assert node_name_to_su("gpu-9") == 3
        assert node_name_to_su("gpu-16") == 4
        assert node_name_to_su("gpu-17") == 5

    def test_non_compute_returns_none(self):
        for n in ("core-01", "oob-switch-02", "csl-01", "gsl-plane1-02",
                  "dhcp-oob", "oob-server-01", "external-conn-01"):
            assert node_name_to_su(n) is None, f"{n} should not match SU pattern"

    def test_edges(self):
        assert node_name_to_su("") is None
        assert node_name_to_su(None) is None
        # gpu without index → not a compute node
        assert node_name_to_su("gpu") is None
        assert node_name_to_su("gpu-abc") is None

    def test_whitespace_tolerated(self):
        assert node_name_to_su("  su-3-node-2  ") == 3
        assert node_name_to_su("  gpu-5  ") == 2


class TestMaxSingleTierSu:
    def test_each_arch_returns_documented_max(self):
        # These caps are baked in arch_scaling.py from the architecture PDFs;
        # changing them here means the table moved → review with arch docs.
        assert max_single_tier_su("2-4-3-200") == 8
        assert max_single_tier_su("2-8-5-200") == 5
        assert max_single_tier_su("2-8-9-400") == 3
        assert max_single_tier_su("2-8-9-800") == 4

    def test_unknown_arch_returns_none(self):
        assert max_single_tier_su("9-9-9-999") is None
        assert max_single_tier_su("") is None


class TestGetTier:
    @pytest.mark.parametrize(
        "arch, su, expect_oob",
        [
            ("2-4-3-200", 1, 2),
            ("2-4-3-200", 4, 2),
            ("2-4-3-200", 5, 3),
            ("2-4-3-200", 6, 3),
            ("2-4-3-200", 7, 4),
            ("2-4-3-200", 8, 4),
            ("2-8-5-200", 1, 2),
            ("2-8-5-200", 4, 2),
            ("2-8-5-200", 5, 3),
            ("2-8-9-400", 1, 2),
            ("2-8-9-400", 2, 2),
            ("2-8-9-400", 3, 3),
            ("2-8-9-800", 1, 2),
            ("2-8-9-800", 4, 2),
        ],
    )
    def test_tier_oob_switches(self, arch, su, expect_oob):
        tier = get_tier(arch, su)
        assert tier is not None, f"{arch} su={su} should have a tier"
        assert tier.oob_switches == expect_oob

    def test_over_max_returns_none(self):
        assert get_tier("2-4-3-200", 9) is None
        assert get_tier("2-8-5-200", 6) is None
        assert get_tier("2-8-9-400", 4) is None
        assert get_tier("2-8-9-800", 5) is None

    def test_invalid_inputs_return_none(self):
        assert get_tier("2-4-3-200", 0) is None
        assert get_tier("2-4-3-200", -1) is None
        assert get_tier("bogus", 1) is None


class TestIsSupportedSingleTier:
    def test_supported_range(self):
        for su in range(1, 9):
            assert is_supported_single_tier("2-4-3-200", su)

    def test_unsupported_above_cap(self):
        assert not is_supported_single_tier("2-4-3-200", 9)
        assert not is_supported_single_tier("2-8-9-400", 4)

    def test_unsupported_below_one(self):
        assert not is_supported_single_tier("2-4-3-200", 0)


class TestScalingTableStructure:
    """Catch table-edit mistakes before they ship."""

    @pytest.mark.parametrize("arch", list(ARCH_SCALING.keys()))
    def test_tiers_ascending_contiguous(self, arch):
        tiers = ARCH_SCALING[arch]
        assert tiers, f"{arch} has no tiers"
        prev_max = 0
        for t in tiers:
            assert isinstance(t, ScalingTier)
            assert t.min_su == prev_max + 1, (
                f"{arch}: tier min_su={t.min_su} should be {prev_max + 1} "
                f"(no gaps, no overlaps)")
            assert t.max_su >= t.min_su
            assert t.core_or_csl_leaves == 2  # documented invariant
            assert t.oob_switches >= 1
            prev_max = t.max_su


# ---------------------------------------------------------------------------
# scale_sample_excel.py generator — exercise against real defaults
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
ALL_ARCHS = ["2-4-3-200", "2-8-5-200", "2-8-9-400", "2-8-9-800"]


def _run_generator(arch: str, sus: int, output: Path):
    script = REPO_ROOT / "scripts" / "scale_sample_excel.py"
    cmd = [sys.executable, str(script), "--arch", arch,
           "--sus", str(sus), "--output", str(output)]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return res


class TestScaleSampleGenerator:
    # The matrix below covers SU sizes for which the default Excel
    # *already templates* the per-node cabling. The CRA promotion pass
    # walks every BMC row per node so 2-4-3-200 SU=8 works even though
    # the default has only 2 oob-switches (the validator emits a
    # tier-mismatch warning advising 4 oob-switches; not blocking).
    #
    # 2-8-9-800 caps at SU=2 because (a) the default templates only
    # gpu-01..gpu-08 and (b) GSL plane-2 leaves already host the
    # plane-1/plane-2 ISLs in the high-port range, leaving no room for
    # additional gpu rails without architectural redesign.
    @pytest.mark.parametrize("arch, sus", [
        ("2-4-3-200", 1),
        ("2-4-3-200", 4),
        ("2-4-3-200", 8),
        ("2-8-5-200", 1),
        ("2-8-5-200", 4),
        ("2-8-5-200", 5),
        ("2-8-9-400", 1),
        ("2-8-9-400", 3),
        ("2-8-9-800", 1),
        ("2-8-9-800", 2),
    ])
    def test_produces_validatable_excel(self, arch, sus, tmp_path):
        # Run the generator into tmp_path, then run validate_excel on it.
        # The generator's *correctness* is best measured by "does the
        # validator accept the file it just produced?"
        # validate_excel reads sibling Excels (e.g. truth set) by path,
        # but it only opens the target file passed in, so tmp_path works.
        out = tmp_path / f"{arch}.xlsx"
        res = _run_generator(arch, sus, out)
        assert res.returncode == 0, f"generator failed: {res.stderr}"
        assert out.exists()
        result = validate_excel(str(out))
        # The generator must produce a clean Excel.
        assert result.ok, (
            f"generated {arch}@su={sus} did not validate clean:\n"
            f"{result.summary()}")

    def test_rejects_over_cap_without_force(self, tmp_path):
        # 2-8-9-400 single-tier max is 3. su=4 must error w/o --force.
        out = tmp_path / "over.xlsx"
        res = _run_generator("2-8-9-400", 4, out)
        assert res.returncode == 2
        assert "exceeds single-tier max" in res.stderr
        assert not out.exists()

    def test_rejects_unknown_arch(self, tmp_path):
        out = tmp_path / "bogus.xlsx"
        res = _run_generator("9-9-9-999", 1, out)
        assert res.returncode == 1
        assert "unknown arch" in res.stderr

    def test_rejects_zero_sus(self, tmp_path):
        out = tmp_path / "zero.xlsx"
        res = _run_generator("2-4-3-200", 0, out)
        assert res.returncode == 1


class TestCraOobLayout:
    """Verify the new CRA OOB strategy is actually applied."""

    def test_bmc_has_display_yes_lom_does_not(self, tmp_path):
        out = tmp_path / "2-4-3-200.xlsx"
        res = _run_generator("2-4-3-200", 1, out)
        assert res.returncode == 0, res.stderr
        wb = openpyxl.load_workbook(out)
        ws = wb["Wire Map"]
        swname, swport = _wm_cols(ws)
        # SU-1 nodes' OOB rows. Inspect what survives + their Display flag.
        for r in range(2, ws.max_row + 1):
            sysname = ws.cell(r, 2).value or ""
            sw = ws.cell(r, swname).value or ""
            if "oob-switch" not in str(sw):
                continue
            su = node_name_to_su(sysname)
            if su != 1:
                continue
            port_desc = str(ws.cell(r, 3).value or "")
            display = str(ws.cell(r, 1).value or "").strip().lower()
            # LOM Port 2 / OCP Port 2 should be DELETED — there should be
            # no surviving rows containing those keywords for active SUs.
            for lom2 in ("LOM Port 2", "OCP 3.0 NIC Port 2", "OCP 3.0 SL1 P2"):
                assert lom2 not in port_desc, (
                    f"LOM2-style row survived for {sysname}: {port_desc}")
            # BMC rows should be Display=Yes; LOM/iLO/iDRAC should be No.
            if any(k in port_desc for k in ("BMC", "IPMI")):
                assert display == "yes", (
                    f"{sysname}: BMC row should be Display=Yes, got {display}")
            elif any(k in port_desc for k in ("LOM", "iLO", "iDRAC")):
                assert display == "no", (
                    f"{sysname}: {port_desc} should be Display=No (real-HW "
                    f"only), got {display}")
        wb.close()

    def test_unique_switch_port_per_bmc(self, tmp_path):
        # Port allocation must not reuse switch ports across BMC rows.
        out = tmp_path / "2-4-3-200.xlsx"
        res = _run_generator("2-4-3-200", 4, out)
        assert res.returncode == 0, res.stderr
        wb = openpyxl.load_workbook(out)
        ws = wb["Wire Map"]
        swname, swport = _wm_cols(ws)
        seen = {}  # (switch, port) -> system_name
        for r in range(2, ws.max_row + 1):
            sw = ws.cell(r, swname).value
            port = ws.cell(r, swport).value
            if not sw or not port or "oob-switch" not in str(sw):
                continue
            key = (str(sw), str(port))
            if key in seen:
                pytest.fail(
                    f"Port {key} reused: rows for {seen[key]} and "
                    f"{ws.cell(r, 2).value}")
            seen[key] = ws.cell(r, 2).value
        wb.close()


# ---------------------------------------------------------------------------
# validate_excel: single-tier-cap + Air-OOB-single-cable
# ---------------------------------------------------------------------------

class TestSingleTierValidator:
    def test_default_excels_under_cap_pass(self):
        # Each default Excel ships at su=2 (or smaller); should not warn
        # about over-cap. We assert the validator runs to completion.
        for arch in ALL_ARCHS:
            path = REPO_ROOT / "input" / arch / "default" / f"{arch}.xlsx"
            result = validate_excel(str(path))
            # Defaults must validate. (`ok` accepts warnings, only fails
            # on errors.)
            assert result.ok, f"{arch} default failed: {result.summary()}"

    def test_over_cap_emits_error(self, tmp_path):
        # Cook a fake Excel: copy a default, then flip enabled=Yes on a
        # node beyond the single-tier max. Validator must error.
        src = REPO_ROOT / "input" / "2-8-9-400" / "default" / "2-8-9-400.xlsx"
        dst = tmp_path / "over.xlsx"
        shutil.copyfile(src, dst)
        wb = openpyxl.load_workbook(dst)
        ws = wb["Nodes"]
        col = {}
        for c in range(1, ws.max_column + 1):
            h = (ws.cell(1, c).value or "").strip().lower()
            if h:
                col[h] = c
        # Synthesize an SU-4 row beyond the templates. The validator
        # cares about *the highest* active SU index, not whether the
        # wire-map is consistent — so just shoehorn one in. Function
        # column is required (parser skips rows with blank function).
        target_row = ws.max_row + 1
        ws.cell(target_row, col["function"]).value = "server"
        ws.cell(target_row, col["name"]).value = "su-4-node-1"
        ws.cell(target_row, col["enabled"]).value = "Yes"
        # Give it a valid IP so the parser doesn't error on it.
        if "mgmt ip address" in col:
            ws.cell(target_row, col["mgmt ip address"]).value = "192.168.200.99"
        if "prefix" in col:
            ws.cell(target_row, col["prefix"]).value = 24
        if "gateway" in col:
            ws.cell(target_row, col["gateway"]).value = "192.168.200.1"
        wb.save(dst)
        wb.close()
        result = validate_excel(str(dst))
        joined = " ".join(result.errors)
        assert "exceeds the single-tier max" in joined, (
            f"expected over-cap error, got: {result.summary()}")


class TestAirOobSingleCableValidator:
    def test_two_display_yes_per_node_warns(self, tmp_path):
        src = REPO_ROOT / "input" / "2-4-3-200" / "default" / "2-4-3-200.xlsx"
        dst = tmp_path / "two-yes.xlsx"
        shutil.copyfile(src, dst)
        wb = openpyxl.load_workbook(dst)
        ws = wb["Wire Map"]
        swname, swport = _wm_cols(ws)
        # Find one SU-1 node's OOB rows and force two of them Display=Yes
        # with distinct ports on the same oob-switch.
        target = None
        oob_rows = []
        for r in range(2, ws.max_row + 1):
            sw = ws.cell(r, swname).value or ""
            sysname = ws.cell(r, 2).value or ""
            if "oob-switch" not in str(sw):
                continue
            if node_name_to_su(sysname) != 1:
                continue
            if target is None:
                target = sysname
            if sysname == target:
                oob_rows.append(r)
        # Mark two of the target node's OOB rows Display=Yes w/ different ports
        assert len(oob_rows) >= 2, (
            "default 2-4-3-200 must have ≥2 OOB rows for an SU-1 node")
        # Use high port numbers (SN2201 has 48 ports + 4 uplinks 49-52)
        # that the default doesn't claim, to avoid duplicate-port errors.
        used = set()
        for r in range(2, ws.max_row + 1):
            sw = ws.cell(r, swname).value or ""
            port = str(ws.cell(r, swport).value or "")
            if "oob-switch" in str(sw):
                used.add(port)
        free = [f"swp{p}" for p in range(40, 49) if f"swp{p}" not in used][:2]
        assert len(free) == 2, f"expected 2 free OOB ports, found {free}"
        ws.cell(oob_rows[0], 1).value = "Yes"
        ws.cell(oob_rows[0], swport).value = free[0]
        ws.cell(oob_rows[1], 1).value = "Yes"
        ws.cell(oob_rows[1], swport).value = free[1]
        wb.save(dst)
        wb.close()
        result = validate_excel(str(dst))
        joined = " ".join(result.warnings)
        assert "Air's plain Ubuntu can't bond" in joined, (
            f"expected Air-OOB-single-cable warning, got: "
            f"{result.summary()}")


# ---------------------------------------------------------------------------
# Lockdown: committed sample-su-N Excels must keep validating clean.
# Without this test, a future generator change could silently rot the
# committed samples.
# ---------------------------------------------------------------------------

def _discover_committed_samples():
    """Return list of (arch, site, excel_path) for every input/<arch>/sample-su-*."""
    out = []
    for arch_dir in sorted((REPO_ROOT / "input").glob("*/")):
        for site_dir in sorted(arch_dir.glob("sample-su-*")):
            arch = arch_dir.name
            site = site_dir.name
            excel = site_dir / f"{arch}.xlsx"
            if excel.exists():
                out.append((arch, site, excel))
    return out


class TestCommittedSamples:
    """Every committed sample must still validate clean (warnings OK)."""

    @pytest.mark.parametrize("arch, site, excel",
                             _discover_committed_samples(),
                             ids=lambda v: v if isinstance(v, str) else "")
    def test_committed_sample_validates(self, arch, site, excel):
        result = validate_excel(str(excel))
        assert result.ok, (
            f"Committed sample {arch}/{site} failed validation. "
            f"Either the generator output drifted or this sample needs "
            f"regenerating via "
            f"`python3 scripts/scale_sample_excel.py --arch {arch} "
            f"--sus {site.split('-')[-1]}`.\n"
            f"Details:\n{result.summary()}")


class TestForceMultiTier:
    """The --force-multi-tier bypass must succeed where the default refuses."""

    def test_force_multi_tier_succeeds(self, tmp_path):
        out = tmp_path / "force.xlsx"
        script = REPO_ROOT / "scripts" / "scale_sample_excel.py"
        cmd = [sys.executable, str(script), "--arch", "2-4-3-200",
               "--sus", "9", "--output", str(out),
               "--force-multi-tier"]
        res = subprocess.run(cmd, capture_output=True, text=True,
                             cwd=REPO_ROOT)
        assert res.returncode == 0, (
            f"--force-multi-tier should bypass cap; got rc={res.returncode}, "
            f"stderr={res.stderr}")
        assert out.exists()

    def test_without_force_refuses(self, tmp_path):
        # Mirror of test_rejects_over_cap_without_force at a different SU
        # to confirm the cap-check is per-arch (2-4-3-200 cap=8 so 9 is over).
        out = tmp_path / "over.xlsx"
        res = _run_generator("2-4-3-200", 9, out)
        assert res.returncode == 2
        assert "exceeds single-tier max" in res.stderr
        assert not out.exists()


class TestTierMismatchWarning:
    """validate_single_tier_su's tier-fan-out warning must fire when the
    OOB-switch count doesn't match the tier table."""

    def test_su8_on_2_4_3_200_warns_oob_count(self):
        # Default 2-4-3-200 ships 2 oob-switches; tier table calls for
        # 4 at SU=8. Sample-su-8 should validate clean with this warning.
        excel = REPO_ROOT / "input" / "2-4-3-200" / "sample-su-8" / "2-4-3-200.xlsx"
        if not excel.exists():
            pytest.skip("sample-su-8 not present; generate it first")
        result = validate_excel(str(excel))
        joined = " ".join(result.warnings)
        assert "doesn't match the expected 4" in joined, (
            f"expected OOB-count tier-mismatch warning, got:\n"
            f"{result.summary()}")


class TestEth0Preservation:
    """2-8-9-800 default uses `eth0` rows as the Air management cable
    (Display=Yes). The CRA generator must NOT promote BMC to Display=Yes
    on top of eth0 — it should demote the BMC rows so each gpu node has
    exactly one Display=Yes OOB row (the eth0)."""

    def test_2_8_9_800_eth0_stays_primary(self, tmp_path):
        out = tmp_path / "2-8-9-800.xlsx"
        res = _run_generator("2-8-9-800", 2, out)
        assert res.returncode == 0, res.stderr
        wb = openpyxl.load_workbook(out)
        ws = wb["Wire Map"]
        swname, swport = _wm_cols(ws)
        for gpu_n in range(1, 9):
            gpu = f"gpu-{gpu_n:02d}"
            yes_rows = []
            for r in range(2, ws.max_row + 1):
                if str(ws.cell(r, 2).value or "").strip() != gpu:
                    continue
                if "oob-switch" not in str(ws.cell(r, swname).value or ""):
                    continue
                if str(ws.cell(r, 1).value or "").strip().lower() != "yes":
                    continue
                yes_rows.append((r, str(ws.cell(r, 3).value or "")))
            assert len(yes_rows) == 1, (
                f"{gpu} should have exactly 1 Display=Yes OOB row; "
                f"got {yes_rows}")
            assert yes_rows[0][1].strip() == "eth0", (
                f"{gpu}'s Display=Yes OOB row should be the `eth0` "
                f"convention, got {yes_rows[0][1]!r}")
        wb.close()


class TestCraAppliesToAllServers:
    """CRA Rule 1 (LOM2 delete) must apply to EVERY active server,
    not just SU/gpu compute nodes. Support/storage/bcm-style names
    should also lose their LOM2 rows."""

    def test_support_lom2_deleted(self, tmp_path):
        out = tmp_path / "2-4-3-200.xlsx"
        res = _run_generator("2-4-3-200", 4, out)
        assert res.returncode == 0, res.stderr
        wb = openpyxl.load_workbook(out)
        ws = wb["Wire Map"]
        # Build set of active server names (Nodes Enabled = Yes, function
        # != switch). support-NN and storage-NN are enabled by default.
        nws = wb["Nodes"]
        # Use lower-case header lookup
        cols = {(nws.cell(1, c).value or "").strip().lower(): c
                for c in range(1, nws.max_column + 1)}
        active = set()
        for r in range(2, nws.max_row + 1):
            n = str(nws.cell(r, cols["name"]).value or "").strip()
            f = str(nws.cell(r, cols["function"]).value or "").lower()
            en = str(nws.cell(r, cols.get("enabled", 0)).value or "Yes")
            if n and "switch" not in f and en.strip().lower() in (
                "yes", "true", "1", ""):
                active.add(n)
        # LOM2 keyword set (same as scale_sample_excel.py)
        LOM2 = ("LOM Port 2", "OCP 3.0 NIC Port 2", "OCP 3.0 SL1 P2")
        swname, swport = _wm_cols(ws)
        surviving = []
        for r in range(2, ws.max_row + 1):
            sysname = str(ws.cell(r, 2).value or "").strip()
            port = str(ws.cell(r, 3).value or "")
            sw = str(ws.cell(r, swname).value or "")
            if (sysname in active
                    and "oob-switch" in sw
                    and any(k in port for k in LOM2)):
                surviving.append((sysname, port))
        wb.close()
        assert not surviving, (
            f"Active servers should have ZERO surviving LOM2 OOB rows; "
            f"these still exist: {surviving}")
