# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""H5 / GitLab #93: a physical site's ZTP NIC names survive `make switch-ztp-deploy`.

Physical `ztp_interfaces` are generated as `eth1`... and the operator renames
them to the ZTP server's real NICs. Step 3 of `switch-ztp-deploy` regenerates
the inventory, which used to put `eth1` back before step 6 configured DHCP on
it. These cases run the real Make workflow with a recording `ansible-playbook`
and inspect the interfaces `setup-ztp-server.yml` actually receives.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_physical_ztp_dhcp import ARCH, _site  # noqa: E402

NC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NC / "scripts"))
import inventory_yaml  # noqa: E402

REAL_NIC = "enp65s0f0"


def _rename_first_nic(inv, name):
    main = inv / "group_vars" / "all" / "main.yml"
    data = inventory_yaml.load(main.read_text())
    data["ztp_interfaces"][0]["name"] = name
    with main.open("w") as f:
        f.write("---\n")
        inventory_yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return data["ztp_interfaces"]


def _recorder(tmp_path):
    record = tmp_path / "setup-ztp-server.json"
    stub = tmp_path / "ansible-playbook-recorder"
    stub.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, 'scripts')\n"
        "import inventory_yaml\n"
        "args = sys.argv[1:]\n"
        "if any(a.endswith('setup-ztp-server.yml') for a in args):\n"
        "    inv = Path(args[args.index('-i') + 1]).parent\n"
        "    main = inventory_yaml.load((inv / 'group_vars/all/main.yml').read_text())\n"
        f"    Path({str(record)!r}).write_text(json.dumps(main['ztp_interfaces']))\n")
    stub.chmod(0o755)
    return stub, record


@pytest.mark.parametrize("oob_mode", ["L2", "L3"])
def test_renamed_nic_reaches_ztp_setup_through_switch_ztp_deploy(tmp_path, oob_mode):
    dst, inv, _ = _site(tmp_path, deploy_in_air=False, oob_mode=oob_mode)
    edited = _rename_first_nic(inv, REAL_NIC)
    stub, record = _recorder(tmp_path)
    env = {**os.environ, "ERA_DEV_ALLOW_PLACEHOLDER_SECRETS": "1"}  # disposable test tree
    # A comment-only recipe line exits with whatever a BASH_ENV script returns.
    env.pop("BASH_ENV", None)
    r = subprocess.run(
        ["make", "switch-ztp-deploy", f"ARCH={ARCH}", "SITE=default", "AUTO_CONFIRM=1",
         f"ANSIBLE_PLAYBOOK={stub}"],
        cwd=dst, env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert "STEP 3/6" in r.stdout, "the workflow must still regenerate the inventory"
    received = json.loads(record.read_text())
    assert [i["name"] for i in received] == [i["name"] for i in edited], received
    assert received[0]["name"] == REAL_NIC


def test_invalid_nic_name_stops_generation(tmp_path):
    dst, inv, _ = _site(tmp_path, deploy_in_air=False, oob_mode="L2")
    _rename_first_nic(inv, "eth1; reboot")
    r = subprocess.run([sys.executable, "scripts/excel_parser.py", "--arch", ARCH,
                        "--site", "default", "--skip-validate"],
                       cwd=dst, capture_output=True, text=True)
    assert r.returncode != 0
    assert "not a valid Linux interface name" in r.stdout + r.stderr


def test_air_site_names_are_not_carried_forward(tmp_path):
    dst, inv, _ = _site(tmp_path, deploy_in_air=True, oob_mode="L2")
    _rename_first_nic(inv, REAL_NIC)
    r = subprocess.run([sys.executable, "scripts/excel_parser.py", "--arch", ARCH,
                        "--site", "default", "--skip-validate"],
                       cwd=dst, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    main = inventory_yaml.load((inv / "group_vars" / "all" / "main.yml").read_text())
    assert main["ztp_interfaces"][0]["name"] == "eth1", \
        "Air names follow the simulated topology, not operator edits"
