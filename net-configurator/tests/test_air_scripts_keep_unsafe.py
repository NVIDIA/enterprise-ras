# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Air scripts that rewrite generated inventory keep workbook text ``!unsafe``
(ADR-0090). On the validation-bypass path the inventory can hold ``!unsafe``
scalars; a plain ``yaml.safe_load`` raises ``ConstructorError`` on them and a
plain ``yaml.dump`` would drop the tag, making the text a template again.
"""
import importlib.util
import sys
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import inventory_yaml  # noqa: E402

PAYLOAD = "{{ lookup('pipe', 'touch /tmp/era-b1-marker') }}"
HOST_VARS = f"---\nhostname: sw1\npre_login_message: !unsafe \"{PAYLOAD}\"\nkeep: '{{{{ ansible_host }}}}'\n"


def _module(filename, name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _assert_roundtrip(text):
    lines = {ln.split(":", 1)[0]: ln for ln in text.splitlines() if ":" in ln}
    assert lines["pre_login_message"].startswith("pre_login_message: !unsafe "), text
    assert "!unsafe" not in lines["keep"], "tool-authored expression was tagged unsafe"
    data = inventory_yaml.load(text)
    assert isinstance(data["pre_login_message"], inventory_yaml.UnsafeText)
    assert data["pre_login_message"] == PAYLOAD
    assert data["keep"] == "{{ ansible_host }}"


def test_air_deploy_update_host_vars_keeps_unsafe(tmp_path):
    air_deploy = _module("air-deploy.py", "air_deploy_under_test")
    path = tmp_path / "host_vars" / "sw1.yml"
    path.parent.mkdir()
    path.write_text(HOST_VARS)
    air_deploy.update_host_vars(tmp_path, "sw1", "worker.air", 2222)
    text = path.read_text()
    _assert_roundtrip(text)
    assert "ansible_port: 2222" in text


def test_air_connect_load_save_keeps_unsafe(tmp_path):
    air_connect = _module("air-connect.py", "air_connect_under_test")
    path = tmp_path / "sw1.yml"
    path.write_text(HOST_VARS)
    data = air_connect.load_yaml(path)
    assert data["pre_login_message"] == PAYLOAD
    data["ansible_port"] = 2200
    air_connect.save_yaml(path, data)
    _assert_roundtrip(path.read_text())


def test_plain_safe_load_would_refuse_this_inventory():
    try:
        yaml.safe_load(HOST_VARS)
    except yaml.constructor.ConstructorError:
        return
    raise AssertionError("expected safe_load to refuse !unsafe")
