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
    """Every shipped arch (so new archs are auto-covered).

    The per-arch seed is now empty (secrets are now one shared
    inventories/secrets.yml), so the stable anchor is the committed default
    output inventory.
    """
    out = project_root / "output"
    return sorted(p.name for p in out.iterdir()
                  if p.is_dir() and (p / "default" / "inventory" / "hosts").exists())


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
            # The seed hosts file is gone; the parser generates the
            # real hosts into output/. Validate the committed output hosts.
            hosts_file = (project_root / "output" / deployment / "default"
                          / "inventory" / "hosts")
            assert hosts_file.exists(), f"output hosts file missing for {deployment}"
            content = hosts_file.read_text()
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

    def test_invariant_group_vars_live_in_single_home(self, project_root):
        """The per-arch seed group_vars (all/oob/core/csl/servers/
        switches) are eliminated — their content lives in the single-home
        scripts/inventory_defaults.yml, keyed by section -> arch. Every
        collapsed-core arch must have its 'all' and 'core' sections there, and no
        top-level seed group_vars may remain (only all/secrets.yml stays). Seedless
        generation being byte-identical is proven by test_seedless_generation.py.
        """
        defaults = yaml.safe_load(
            (project_root / "scripts" / "inventory_defaults.yml").read_text())
        # 'all' infra is a single arch-independent shared block (no per-arch keying).
        assert defaults.get("all_shared"), "all_shared block missing from defaults"
        for deployment in COLLAPSED_CORE_ARCHS:
            assert deployment in defaults["core"], f"{deployment} absent from defaults 'core'"
            gv = project_root / "inventories" / deployment / "group_vars"
            leftover = sorted(p.name for p in gv.glob("*.yml"))
            assert leftover == [], f"seed group_vars still present for {deployment}: {leftover}"

    def test_group_vars_are_valid_yaml(self, project_root):
        """The single-home defaults + each shipped arch's generated group_vars
        must be valid, non-empty YAML.

        The per-arch seed group_vars are gone; their content lives in
        scripts/inventory_defaults.yml. Validate that single home plus the
        generated output group_vars.
        """
        defaults = project_root / "scripts" / "inventory_defaults.yml"
        assert yaml.safe_load(defaults.read_text()), "inventory_defaults.yml invalid/empty"

        deployments = _all_inventory_archs(project_root)
        assert deployments, "no shipped archs found"
        for deployment in deployments:
            gv_dir = project_root / "output" / deployment / "default" / "inventory" / "group_vars"
            for yaml_file in gv_dir.rglob("*.yml"):
                with open(yaml_file) as f:
                    content = yaml.safe_load(f)
                assert content is not None, f"{yaml_file} is empty or invalid"

    def test_every_inventory_has_valid_hosts_file(self, project_root):
        """Every shipped arch must have a non-empty hosts file with an [oob]
        group (universal across collapsed-core and dedicated-GPU archs)."""
        deployments = _all_inventory_archs(project_root)
        assert deployments, "no inventories found"

        for deployment in deployments:
            # Validate the generated output hosts (seed hosts removed).
            hosts = (project_root / "output" / deployment / "default"
                     / "inventory" / "hosts")
            content = hosts.read_text().strip()
            assert content, f"output hosts file empty for {deployment}"
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


