# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
#36 trivial-defensive batch:
  * validate_requirements._load_yaml → friendly SystemExit on missing/malformed
    YAML instead of a raw FileNotFoundError / yaml.YAMLError traceback.
  * reset_mac_registry() clears the MAC collision registry and is wired into
    excel_parser.process_excel_template so repeated in-process runs start clean.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(modname, filename, base=SCRIPTS):
    path = Path(base) / filename
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# validate_requirements is an internal-only script: in the monorepo it lives in
# the sibling data-models/ tree; in the public distribution it is absent. Load it
# from there when present, otherwise skip the vr-specific tests below.
_DATA_MODELS = Path(__file__).resolve().parents[2] / "data-models"
vr = _load("validate_requirements_mod", "validate_requirements.py", _DATA_MODELS)
_needs_vr = pytest.mark.skipif(vr is None, reason="validate_requirements.py is internal-only (data-models/)")


@_needs_vr
def test_load_yaml_missing_file_friendly(tmp_path):
    with pytest.raises(SystemExit) as exc:
        vr._load_yaml(tmp_path / "nope.yml")
    assert "not found" in str(exc.value)


@_needs_vr
def test_load_yaml_malformed_friendly(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("key: [unterminated\n  : : :\n")
    with pytest.raises(SystemExit) as exc:
        vr._load_yaml(bad)
    assert "Malformed YAML" in str(exc.value)


@_needs_vr
def test_load_yaml_valid_roundtrip(tmp_path):
    good = tmp_path / "ok.yml"
    good.write_text("a: 1\nb: [2, 3]\n")
    assert vr._load_yaml(good) == {"a": 1, "b": [2, 3]}


# --- reset_mac_registry ---

import utils  # noqa: E402


def test_reset_mac_registry_clears():
    utils.generate_mac("node-x", "eth0")
    assert utils._mac_registry, "registry should be populated after generate_mac"
    utils.reset_mac_registry()
    assert utils._mac_registry == {}


def test_process_excel_template_resets_registry():
    """excel_parser must import + call reset_mac_registry so a fresh run starts
    with a clean registry (regression guard for the wiring)."""
    import excel_parser
    assert hasattr(excel_parser, "reset_mac_registry")
    src = Path(excel_parser.__file__).read_text()
    # reset_mac_registry() is invoked inside process_excel_template
    body = src[src.index("def process_excel_template"):]
    body = body[:body.index("\ndef ", 1)]
    assert "reset_mac_registry()" in body
