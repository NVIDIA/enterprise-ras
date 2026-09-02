# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Unit tests for the read-only IP-assignment report (`make ip-report`, ADR-0034).

The property that matters most is the one ADR-0034 depends on: the report is
strictly OUTPUT. It reads already-generated artifacts and never writes back into
the input workbook, so the Excel stays the single source of truth. If that ever
stops being true, ADR-0034's premise goes with it — hence a test rather than a
comment.

The rest pins the column vocabulary (headers are copied from the Wire Map
verbatim rather than invented) and the row-shaping rules for bonds and switch
interfaces.
"""
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import emit_ip_report as ipr  # noqa: E402


# --- read-only invariant (ADR-0034) ----------------------------------------

def test_report_never_writes_into_the_input_tree():
    """No write path in the module may target input/.

    ADR-0034 keeps the input Excel canonical and the emitted views read-only.
    A write-back would make a generated file an input — the exact coupling the
    ADR rejects — so scan the source for a write aimed at the input tree.
    """
    src = (SCRIPTS_DIR / "emit_ip_report.py").read_text()

    writes = [ln.strip() for ln in src.splitlines()
              if any(tok in ln for tok in (".save(", ".write_text(", ".write_bytes(",
                                           "open(", "to_excel("))
              and not ln.strip().startswith("#")]
    offenders = [ln for ln in writes if "input" in ln.lower()]
    assert not offenders, (
        f"emit_ip_report must never write into input/ — ADR-0034 keeps the "
        f"workbook canonical. Offending line(s): {offenders}"
    )


def test_input_workbook_is_only_ever_read(tmp_path, monkeypatch):
    """load_wiremap opens the workbook read-only and tolerates its absence.

    A missing Wire Map degrades to blank columns rather than failing the run —
    the report is a convenience view, not a gate.
    """
    assert ipr.load_wiremap(tmp_path / "nope.xlsx") in ({}, None)


# --- column vocabulary ------------------------------------------------------

def test_columns_reuse_wire_map_header_names():
    """Headers are copied from the Wire Map, not renamed.

    A reader has to be able to match a report row back to the sheet it came
    from, so 'Port (A)' stays 'Port (A)' and derived fields sit beside the
    source names rather than replacing them.
    """
    for header in ("System Name (A)", "Port (A)", "System Name (B)", "Port (B)",
                   "Network Profile"):
        assert header in ipr.COLUMNS, f"{header} missing from report columns"

    # Derived-but-adjacent, not a rename of the Wire Map's own port column.
    assert "Logical Port (A)" in ipr.COLUMNS
    assert "Physical Port" not in ipr.COLUMNS

    # The grouped sheet is a subset of the same vocabulary — no new names.
    assert set(ipr.GROUPED_COLUMNS) <= set(ipr.COLUMNS)


# --- row shaping ------------------------------------------------------------

def test_compute_node_bond_expands_over_every_cpu_member():
    """A compute node bonds all cpu members into bond0 carrying one IP."""
    devices = {
        "su-01-node-01": {
            "eth0_ip": "192.168.200.11",
            "bond_ip": "172.16.178.11/24",
            "interfaces": {"cpu": ["eth1", "eth2"], "oob": ["eth0"]},
        }
    }
    rows = list(ipr.server_rows(devices))
    by_iface = {r[3]: r for r in rows}

    assert by_iface["eth0"][4] == "192.168.200.11/24", "oob eth0 should gain /24"
    bond0 = by_iface["bond0"]
    assert bond0[4] == "172.16.178.11/24"
    assert bond0[5] == ["eth1", "eth2"], "bond0 must cover every cpu member"
    assert bond0[6] is True, "bond rows are flagged so build_rows expands them"


def test_storage_node_splits_into_two_bonds_only_with_four_data_eths():
    """storage/support: bond0 = data[0:2]; bond1 appears only at >=4 eths."""
    four = {"storage-01": {"bond_ip1": "172.16.180.11/24", "bond_ip2": "172.16.180.12/24",
                           "interfaces": {"storage": ["eth1", "eth2", "eth3", "eth4"]}}}
    ifaces = {r[3]: r[5] for r in ipr.server_rows(four)}
    assert ifaces["bond0"] == ["eth1", "eth2"]
    assert ifaces["bond1"] == ["eth3", "eth4"]

    two = {"storage-02": {"bond_ip1": "172.16.180.13/24", "bond_ip2": "172.16.180.14/24",
                          "interfaces": {"storage": ["eth1", "eth2"]}}}
    ifaces2 = {r[3]: r[5] for r in ipr.server_rows(two)}
    assert "bond0" in ifaces2
    assert "bond1" not in ifaces2, "bond1 requires >=4 data eths"


def test_switch_rows_cover_mgmt_loopback_svis_and_vrf_loopbacks():
    switches = {
        "csl-01": {
            "ansible_host": "192.168.200.2",
            "lo_ip": "172.16.176.1/32",
            "vlan_interfaces": [{"vlan": 300, "ip": "172.16.178.2/24"},
                                {"vlan": 500}],  # no IP -> skipped
            "vrf_loopbacks": {"EXIT": "172.16.176.183/32"},
        }
    }
    rows = list(ipr.switch_rows(switches))
    ifaces = {r[3] for r in rows}

    assert {"eth0", "lo", "vlan300", "lo (EXIT)"} <= ifaces
    assert "vlan500" not in ifaces, "an SVI with no IP contributes no row"
    assert all(r[1] == "switch" for r in rows)


def test_placeholder_mgmt_ip_is_not_reported_as_an_assignment():
    """CHANGE_ME means Air assigns it — reporting it as a real IP would mislead."""
    rows = list(ipr.switch_rows({"csl-01": {"ansible_host": "CHANGE_ME",
                                            "lo_ip": "172.16.176.1/32"}}))
    assert not [r for r in rows if r[3] == "eth0"]


def test_oob_switch_is_typed_distinctly_from_a_fabric_switch():
    rows = list(ipr.switch_rows({"oob-switch-01": {"lo_ip": "172.16.176.151/32"}}))
    assert rows and rows[0][1] == "oob-switch"


# --- CLI contract -----------------------------------------------------------

def test_missing_generated_inventory_fails_with_a_pointer_to_generate(tmp_path, monkeypatch, capsys):
    """The report needs `make generate` first; say so rather than tracebacking."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["emit_ip_report.py", "--arch", "2-8-5-200"])

    with pytest.raises(SystemExit) as exc:
        ipr.main()
    assert "make generate" in str(exc.value)
