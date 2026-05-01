# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Pytest configuration and fixtures for ERA switch configuration tests.
"""
import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def sample_nvue_cli_config():
    """Return a sample NVUE CLI configuration."""
    return """#!/bin/bash
# Sample NVUE CLI configuration

nv set system hostname test-switch
nv set system timezone Etc/Zulu
nv set interface lo ip address 10.10.10.1/32
nv set interface lo type loopback
nv set interface swp1 link state up
nv set interface swp1 type swp
nv set bridge domain br_default vlan 100
nv set bridge domain br_default vlan 200
nv config apply -y
"""


@pytest.fixture
def core_cli_template(project_root):
    """Return path to core switch CLI template."""
    return project_root / "roles" / "core" / "templates" / "core_nvue_cli.j2"


@pytest.fixture
def oob_cli_template(project_root):
    """Return path to OOB switch CLI template."""
    return project_root / "roles" / "oob-switch" / "templates" / "oob_nvue_cli.j2"


@pytest.fixture
def ztp_sh_template(project_root):
    """Return path to the ZTP bootstrap shell-script template."""
    return project_root / "roles" / "ztp-server" / "templates" / "ztp.sh.j2"


