# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-138 / ERA-139: two import-gate hygiene findings from the offline review.

* ``ztp_server`` in Settings passed the IP-format check and was then ignored by
  every generator; an operator who moved it got no signal. The validator now
  warns when it is set off the fixed ZTP slot (``<oob-subnet>.100``).
* ``import-excel.py`` on a workbook resolving to the ``default`` site asks
  ``Continue? [y/N]`` via ``input()``; with a closed stdin (CI, ``make`` from a
  script) that raised an uncaught ``EOFError`` traceback instead of an abort.
"""
import importlib.util
import sys
from pathlib import Path

import openpyxl
import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_excel import ValidationResult, validate_cross_sheet_data  # noqa: E402

VLAN_OOB = {'id': 200, 'name': 'oob', 'subnet': '192.168.200.0/24',
            'gateway': '192.168.200.1', 'vrf': 'OOB', 'network': None,
            'dhcp_relay_client': '', 'row': 3}


def _node(name, ip, row):
    return {'function': 'oob-switch', 'name': name, 'row': row, 'ip': ip,
            'prefix': 24, 'gateway': None, 'enabled': True,
            'is_air_documentary': False, 'oob_vlan': ''}


def _ztp_warnings(ztp_value, mode='l3'):
    result = ValidationResult()
    settings = {'oob_uplink_mode': mode}
    if ztp_value is not None:
        settings['ztp_server'] = ztp_value
    validate_cross_sheet_data(settings, [_node('oob-switch-01', '192.168.200.10', 2)],
                              [VLAN_OOB], result)
    return [w for w in result.warnings if 'ztp_server' in w]


@pytest.mark.parametrize("mode", ["l2", "l3"])
def test_ztp_server_moved_off_fixed_slot_warns(mode):
    warns = _ztp_warnings('192.168.200.110', mode)
    assert len(warns) == 1, warns
    assert 'no effect' in warns[0] and '192.168.200.100' in warns[0]


@pytest.mark.parametrize("value", [None, '', '192.168.200.100'])
def test_ztp_server_blank_or_on_fixed_slot_is_silent(value):
    assert _ztp_warnings(value) == []


# ---------------------------------------------------------------------------
# import-excel.py: closed stdin on the 'default' site confirmation
# ---------------------------------------------------------------------------

def _load_import_excel():
    spec = importlib.util.spec_from_file_location(
        "import_excel_under_test", SCRIPTS / "import-excel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _external_workbook(tmp_path, site_name):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Settings"
    ws.append(["Setting", "Value"])
    ws.append(["architecture", "2-4-3-200"])
    ws.append(["site_name", site_name])
    path = tmp_path / "external" / "2-4-3-200.xlsx"
    path.parent.mkdir(parents=True)
    wb.save(str(path))
    return path


def test_blank_site_name_with_closed_stdin_aborts_cleanly(tmp_path, monkeypatch, capsys):
    mod = _load_import_excel()
    monkeypatch.setattr(mod, "INPUT_DIR", tmp_path / "input")
    monkeypatch.setattr(mod, "read_excel_settings",
                        lambda p: {"architecture": "2-4-3-200", "site_name": ""})

    def _closed_stdin(prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", _closed_stdin)

    with pytest.raises(SystemExit) as exc:
        mod.import_excel(_external_workbook(tmp_path, ""))
    assert exc.value.code == 1
    assert "--site" in capsys.readouterr().out
    assert not (tmp_path / "input" / "2-4-3-200" / "default").exists()
