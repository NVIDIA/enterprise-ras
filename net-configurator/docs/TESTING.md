<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Testing Guide for ERA Switch Configuration

This document provides a comprehensive guide to running and writing tests for the ERA switch configuration generation system.

## Quick Start

### 1. Setup Test Environment

```bash
# Create a virtual environment for testing
python3 -m venv .venv-test

# Install test dependencies
.venv-test/bin/pip install -r tests/requirements.txt
```

Or use the Makefile:

```bash
make setup
```

### 2. Run All Tests

```bash
make test
# Or directly:
.venv-test/bin/pytest -v
```

### 3. Run Specific Test Categories

```bash
# Parser function unit tests
.venv-test/bin/pytest tests/test_parser_functions.py

# Template tests
.venv-test/bin/pytest tests/test_templates.py

# Configuration validation tests
.venv-test/bin/pytest tests/test_config_validation.py

# Integration tests
.venv-test/bin/pytest tests/test_integration.py
```

### 4. View Test Coverage

```bash
make test-coverage
# Or:
.venv-test/bin/pytest --cov=scripts --cov-report=html --cov-report=term
xdg-open htmlcov/index.html
```

## Test Structure

```
tests/
├── __init__.py                  # Test package
├── conftest.py                  # Pytest fixtures
├── test_parser_functions.py     # Parser & utility unit tests (40 tests)
├── test_templates.py            # Jinja2 template tests (8 tests)
├── test_config_validation.py    # Configuration validation (13 tests)
├── test_integration.py          # End-to-end integration (12 tests)
├── requirements.txt             # Test dependencies
└── README.md                    # Test documentation
```

## Test Categories

### 1. Parser & Utility Function Tests (40 tests)

Tests the shared utility and parser functions that drive config generation:

```bash
.venv-test/bin/pytest tests/test_parser_functions.py -v
```

**Coverage:**
- `generate_mac()` — deterministic MAC generation, format, uniqueness
- `classify_node()` — role classification for all node types (core, oob, edge, compute, storage, support, k8s, bcme, infra, unknown)
- `is_switch()` — switch vs server detection
- `is_valid_hostname()` — RFC1123 hostname validation
- `classify_host_role()` — Excel parser wrapper (maps switch roles)
- `ports_to_range_string()` — NVUE swp range notation (e.g., `{1,2,3,5}` → `swp1-3,swp5`)
- `_expand_iface_token()` — interface range expansion (e.g., `swp49-52` → `swp49,swp50,swp51,swp52`)
- `normalize_nvue_line()` — NVUE command normalization for config comparison
- `_natural_key()` — natural sort for port names

### 2. Template Tests (8 tests)

Tests Jinja2 template validity and content:

```bash
.venv-test/bin/pytest tests/test_templates.py -v
```

**Coverage:**
- Template file existence
- Jinja2 syntax validation (all templates parse without errors)
- Core and OOB templates contain `nv set` commands
- All role templates exist

### 3. Configuration Validation Tests (13 tests)

Tests validation of configuration data formats:

```bash
.venv-test/bin/pytest tests/test_config_validation.py -v
```

**Coverage:**
- NVUE command format validation
- IP address and MAC address format validation
- VLAN ID and BGP ASN range validation
- Port range syntax validation
- VLAN/VNI mapping consistency (VNI = VLAN_ID + 4000)
- Interface and VRF naming conventions
- Configuration section completeness

### 4. Integration Tests (12 tests)

Tests end-to-end structure and workflow validity:

```bash
.venv-test/bin/pytest tests/test_integration.py -v
```

**Coverage:**
- Playbook YAML syntax validation
- Inventory file structure (hosts, group_vars, host_vars)
- Script existence and Python syntax validation
- Exported configuration structure

## Test Fixtures

Fixtures defined in `conftest.py`:

| Fixture | Description |
|---------|-------------|
| `project_root` | Path to project root directory |
| `sample_nvue_cli_config` | Sample NVUE CLI configuration string |
| `core_cli_template` | Path to core switch CLI Jinja2 template |
| `oob_cli_template` | Path to OOB switch CLI Jinja2 template |

## Common Testing Workflows

### Running Tests During Development

```bash
# Verbose output
.venv-test/bin/pytest -vv

# Show print statements
.venv-test/bin/pytest -s

# Run only failed tests from last run
.venv-test/bin/pytest --lf

# Run tests matching a keyword
.venv-test/bin/pytest -k "mac"

# Run tests in parallel
make test-fast
```

### Debugging Failed Tests

```bash
# Show local variables on failure
.venv-test/bin/pytest --showlocals

# Drop into debugger on failure
.venv-test/bin/pytest --pdb

# Verbose traceback
.venv-test/bin/pytest -vv --tb=long
```

## Writing New Tests

### Adding a Parser Unit Test

```python
# tests/test_parser_functions.py
from utils import generate_mac

class TestGenerateMac:
    def test_format(self):
        """MAC should be in 48:b0:2d:xx:xx:xx format."""
        mac = generate_mac("core-01", "swp1")
        assert re.match(r'^48:b0:2d:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}$', mac)
```

### Adding a Template Test

```python
# tests/test_templates.py
def test_template_has_nv_commands(self, core_cli_template):
    content = core_cli_template.read_text()
    assert 'nv set' in content
```

### Adding an Integration Test

```python
# tests/test_integration.py
def test_all_playbooks_have_valid_yaml(self, project_root):
    for playbook in (project_root / "playbooks").glob("*.yml"):
        with open(playbook) as f:
            content = yaml.safe_load(f)
        assert content is not None
```

## Continuous Integration

### GitHub Actions

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r tests/requirements.txt
      - run: pytest --cov=scripts --cov-report=term
```

## Test Metrics

| Metric | Value |
|--------|-------|
| Total Tests | 73 |
| Passing | 73 (100%) |
| Avg Runtime | ~0.5s |

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Jinja2 Testing](https://jinja.palletsprojects.com/en/3.0.x/api/#testing)
- [Test Quick Start](TESTING_QUICKSTART.md)
