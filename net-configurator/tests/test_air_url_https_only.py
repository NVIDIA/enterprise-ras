# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""The NGC bearer token only goes to https:// Air URLs; SSH helpers don't forward the agent (GitLab #103, F5).

Every Air API call sends `Authorization: Bearer <NGC API key>`. A custom
`http://` Air URL used to be accepted by `make air-setup` and by
`AIR_BASE_URL`, which sent that key in cleartext. `build_ssh_args` also
defaulted to `-A`, so the printed "ssh to your sim" command forwarded the
operator's local agent to the Air VM.
"""
import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from airlib import env as airlib_env  # noqa: E402
from airlib.errors import AirConfigError  # noqa: E402
from airlib.ssh import build_ssh_args  # noqa: E402


def _load_air_setup():
    spec = importlib.util.spec_from_file_location("air_setup_https", SCRIPTS / "air-setup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


air_setup = _load_air_setup()


def _feed(monkeypatch, *answers):
    it = iter(answers)

    def fake_input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise AssertionError(f"prompt asked for more input than fed: {prompt!r}")

    monkeypatch.setattr("builtins.input", fake_input)


# ---------------------------------------------------------------- wizard ---

def test_wizard_refuses_custom_http_url(monkeypatch):
    _feed(monkeypatch, "3", "http://air.example.com", "3", "https://air.example.com/")
    assert air_setup.prompt_air_url() == "https://air.example.com"


def test_wizard_refuses_to_keep_a_stored_http_url(monkeypatch):
    """[Enter] on the custom prompt keeps the current value only if it is https."""
    _feed(monkeypatch, "3", "", "3", "https://air.example.com")
    assert air_setup.prompt_air_url("http://air.example.com") == "https://air.example.com"


def test_wizard_keeps_a_stored_https_url(monkeypatch):
    _feed(monkeypatch, "3", "")
    assert air_setup.prompt_air_url("https://air.example.com/") == "https://air.example.com"


def _ni_args(air_url):
    return argparse.Namespace(api_key="nvapi-x", vault_password="pw", ssh_key="",  # pragma: allowlist secret
                              air_url=air_url, username="", org="", save_password=False)


def test_non_interactive_refuses_http_url(monkeypatch):
    monkeypatch.setattr(air_setup, "ensure_ansible_vault", lambda **_: None)
    wrote = []
    monkeypatch.setattr(air_setup, "write_encrypted_vault", lambda *a: wrote.append(a))
    assert air_setup.run_non_interactive(_ni_args("http://air.example.com")) == 2
    assert wrote == []


def test_non_interactive_accepts_https_url(monkeypatch, tmp_path):
    monkeypatch.setattr(air_setup, "ensure_ansible_vault", lambda **_: None)
    monkeypatch.setattr(air_setup, "shared_config_dir", lambda: tmp_path)
    monkeypatch.setattr(air_setup, "find_existing_vault", lambda: None)
    monkeypatch.setattr(air_setup, "remove_password_file", lambda _d: None)
    wrote = []
    monkeypatch.setattr(air_setup, "write_encrypted_vault", lambda p, d, pw: wrote.append(d))
    assert air_setup.run_non_interactive(_ni_args("https://air.example.com/")) == 0
    assert wrote[0]["air_url"] == "https://air.example.com"


# ------------------------------------------------------- config loading ---

@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    for var in ("AIR_API_KEY", "AIR_USERNAME", "AIR_SSH_KEY_PATH", "AIR_BASE_URL",
                "AIR_NGC_ORG", "ANSIBLE_VAULT_PASSWORD_FILE"):
        monkeypatch.delenv(var, raising=False)
    return root


def _vault(root, air_url):
    d = root / airlib_env.SHARED_VAULT_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    (d / airlib_env.SHARED_VAULT_FILENAME).write_text(
        f"air_api_key: 'nvapi-test-key-longer-than-20'\nair_url: '{air_url}'\n")  # pragma: allowlist secret


def test_http_url_from_vault_is_refused(project):
    _vault(project, "http://air.example.com")
    with pytest.raises(AirConfigError, match="not https://"):
        airlib_env.load_air_config("2-8-5-200", project_root=project)


def test_http_url_from_environment_is_refused(project, monkeypatch):
    _vault(project, "https://air.example.com")
    monkeypatch.setenv("AIR_BASE_URL", "http://air.example.com")
    with pytest.raises(AirConfigError, match="not https://"):
        airlib_env.load_air_config("2-8-5-200", project_root=project)


def test_https_url_loads(project):
    _vault(project, "https://air.example.com/")
    assert airlib_env.load_air_config("2-8-5-200", project_root=project)["base_url"] == "https://air.example.com"


def test_missing_url_is_left_to_require_config(project):
    """No URL at all is a `require_config` error, not an https one."""
    (project / airlib_env.SHARED_VAULT_DIRNAME).mkdir()
    (project / airlib_env.SHARED_VAULT_DIRNAME / airlib_env.SHARED_VAULT_FILENAME).write_text(
        "air_api_key: 'nvapi-test-key-longer-than-20'\n")  # pragma: allowlist secret
    cfg = airlib_env.load_air_config("2-8-5-200", project_root=project)
    with pytest.raises(AirConfigError, match="base_url"):
        airlib_env.require_config(cfg, "base_url", "api_key")


# ----------------------------------------------------------- ssh helper ---

def test_ssh_args_do_not_forward_the_agent_by_default():
    assert "-A" not in build_ssh_args("h", 22, "ubuntu")


def test_agent_forwarding_is_opt_in():
    assert "-A" in build_ssh_args("h", 22, "ubuntu", forward_agent=True)
