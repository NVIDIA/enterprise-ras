# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Integration tests for the complete config generation workflow.
"""
import pytest
import subprocess
import yaml
from pathlib import Path


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
        """Test that deployment inventory files are structured correctly."""
        deployments = ['2-4-3-200', '2-8-5-200', '2-8-9-400']
        
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
        deployments = ['2-4-3-200', '2-8-5-200', '2-8-9-400']
        required_files = ['all.yml', 'core.yml']
        
        for deployment in deployments:
            for required_file in required_files:
                file_path = project_root / "inventories" / deployment / "group_vars" / required_file
                assert file_path.exists(), f"{required_file} missing for {deployment}"

    def test_host_vars_exist_for_core_switches(self, project_root):
        """Test that core switch host_vars exist."""
        deployments = ['2-4-3-200', '2-8-5-200', '2-8-9-400']
        core_switches = ['core-01.yml', 'core-02.yml']
        
        for deployment in deployments:
            for switch in core_switches:
                file_path = project_root / "inventories" / deployment / "host_vars" / switch
                assert file_path.exists(), f"{switch} missing for {deployment}"

    def test_group_vars_are_valid_yaml(self, project_root):
        """Test that all group_vars files are valid YAML."""
        deployments = ['2-4-3-200', '2-8-5-200', '2-8-9-400']
        
        for deployment in deployments:
            group_vars_dir = project_root / "inventories" / deployment / "group_vars"
            
            for yaml_file in group_vars_dir.glob("*.yml"):
                with open(yaml_file) as f:
                    content = yaml.safe_load(f)
                assert content is not None, f"{yaml_file} is empty or invalid"


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
        """Test that Python scripts have valid syntax."""
        scripts = [
            project_root / "scripts" / "excel_parser.py",
            project_root / "scripts" / "topology_generator.py",
            project_root / "scripts" / "compare_excel_inventory_and_configs.py",
        ]

        for script in scripts:
            result = subprocess.run(
                ['python3', '-m', 'py_compile', str(script)],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Syntax error in {script.name}: {result.stderr}"


