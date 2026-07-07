# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Integration tests for the complete config generation workflow.
"""
import pytest
import subprocess
import yaml
from pathlib import Path

# Collapsed-core archs use the standard [core] group + core.yml + core-01/02.yml
# host_vars. Dedicated-GPU archs (2-8-9-400-SP, 2-8-9-800) use csl/gsl instead,
# and 2-4-5-800 uses OEM-named host_vars — so the core-shaped structural checks
# below intentionally target ONLY this subset. The arch-agnostic checks
# (hosts-file present, group_vars valid YAML) run across ALL archs via
# _all_inventory_archs() so structural breakage in any shipped arch is caught.
COLLAPSED_CORE_ARCHS = ['2-4-3-200', '2-8-5-200', '2-8-9-400']


def _all_inventory_archs(project_root):
    """Every arch with a source inventory on disk (so new archs are auto-covered)."""
    inv = project_root / "inventories"
    return sorted(p.name for p in inv.iterdir() if p.is_dir() and (p / "hosts").exists())


class TestPlaybookIntegration:
    """Test integration with Ansible playbooks."""

    def test_playbook_syntax_check(self, project_root):
        """Test that the generate-cli-configs playbook has valid syntax."""
        playbook = project_root / "playbooks" / "generate-cli-configs.yml"
        
        # Check file exists
        assert playbook.exists()
        
        # Validate YAML syntax
        with open(playbook) as f:
            content = yaml.safe_load(f)
        
        assert content is not None
        assert isinstance(content, list)

    def test_all_playbooks_have_valid_yaml(self, project_root):
        """Test that all playbooks are valid YAML."""
        playbooks_dir = project_root / "playbooks"
        
        for playbook in playbooks_dir.glob("*.yml"):
            with open(playbook) as f:
                content = yaml.safe_load(f)
            assert content is not None, f"Playbook {playbook.name} is empty or invalid"

    def test_inventory_structure(self, project_root):
        """Test that collapsed-core deployment inventory files are structured correctly."""
        deployments = COLLAPSED_CORE_ARCHS

        for deployment in deployments:
            hosts_file = project_root / "inventories" / deployment / "hosts"
            
            assert hosts_file.exists(), f"hosts file missing for {deployment}"
            
            # Read and validate basic structure
            content = hosts_file.read_text()
            
            # Should contain expected groups
            assert '[core]' in content, f"[core] group missing in {deployment}"
            assert '[oob]' in content, f"[oob] group missing in {deployment}"

    def test_template_files_exist(self, project_root):
        """Test that all required template files exist."""
        templates = [
            project_root / "roles" / "core" / "templates" / "core_nvue_cli.j2",
            project_root / "roles" / "oob-switch" / "templates" / "oob_nvue_cli.j2"
        ]
        
        for template in templates:
            assert template.exists(), f"Template not found: {template}"


class TestInventoryValidation:
    """Test validation of inventory files."""

    def test_group_vars_exist_for_all_deployments(self, project_root):
        """Test that all deployments have required group_vars."""
        deployments = COLLAPSED_CORE_ARCHS
        required_files = ['all.yml', 'core.yml']
        
        for deployment in deployments:
            for required_file in required_files:
                file_path = project_root / "inventories" / deployment / "group_vars" / required_file
                assert file_path.exists(), f"{required_file} missing for {deployment}"

    def test_host_vars_exist_for_core_switches(self, project_root):
        """Test that core switch host_vars exist."""
        deployments = COLLAPSED_CORE_ARCHS
        core_switches = ['core-01.yml', 'core-02.yml']
        
        for deployment in deployments:
            for switch in core_switches:
                file_path = project_root / "inventories" / deployment / "host_vars" / switch
                assert file_path.exists(), f"{switch} missing for {deployment}"

    def test_group_vars_are_valid_yaml(self, project_root):
        """Every shipped arch's group_vars must be valid, non-empty YAML."""
        deployments = _all_inventory_archs(project_root)
        assert deployments, "no inventories found"

        for deployment in deployments:
            group_vars_dir = project_root / "inventories" / deployment / "group_vars"
            for yaml_file in group_vars_dir.rglob("*.yml"):
                with open(yaml_file) as f:
                    content = yaml.safe_load(f)
                assert content is not None, f"{yaml_file} is empty or invalid"

    def test_every_inventory_has_valid_hosts_file(self, project_root):
        """Every shipped arch must have a non-empty hosts file with an [oob]
        group (universal across collapsed-core and dedicated-GPU archs)."""
        deployments = _all_inventory_archs(project_root)
        assert deployments, "no inventories found"

        for deployment in deployments:
            hosts = project_root / "inventories" / deployment / "hosts"
            content = hosts.read_text().strip()
            assert content, f"hosts file empty for {deployment}"
            assert '[oob]' in content, f"[oob] group missing in {deployment}"


class TestScriptsExist:
    """Test that required scripts exist and are valid Python."""

    def test_excel_parser_exists(self, project_root):
        """Test that excel_parser.py exists."""
        script = project_root / "scripts" / "excel_parser.py"
        assert script.exists()

    def test_topology_generator_exists(self, project_root):
        """Test that topology_generator.py exists."""
        script = project_root / "scripts" / "topology_generator.py"
        assert script.exists()

    def test_scripts_have_valid_python_syntax(self, project_root):
        """Every Python script under scripts/ must compile.

        Globbed (not a hardcoded list) so the large untested deploy-path scripts
        — air-deploy.py, air-ssh-check.py, the airlib package — are at least
        smoke-checked for syntax/parse errors, and new scripts are auto-covered.
        """
        scripts = sorted((project_root / "scripts").rglob("*.py"))
        assert scripts, "no scripts found"
        failed = []
        for script in scripts:
            result = subprocess.run(
                ['python3', '-m', 'py_compile', str(script)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                failed.append(f"{script.relative_to(project_root)}: {result.stderr.strip()}")
        assert not failed, "Python syntax errors:\n" + "\n".join(failed)

    def test_shell_scripts_have_valid_syntax(self, project_root):
        """Every shell script under scripts/ must pass `bash -n` (catches the
        validate-all probe scripts and other .sh that have no other tests)."""
        shells = sorted((project_root / "scripts").rglob("*.sh"))
        assert shells, "no shell scripts found"
        failed = []
        for sh in shells:
            result = subprocess.run(['bash', '-n', str(sh)], capture_output=True, text=True)
            if result.returncode != 0:
                failed.append(f"{sh.relative_to(project_root)}: {result.stderr.strip()}")
        assert not failed, "Shell syntax errors:\n" + "\n".join(failed)


