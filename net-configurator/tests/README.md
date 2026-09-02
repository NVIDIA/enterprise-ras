<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Test Suite for ERA Switch Configuration

This directory contains the complete test suite for the ERA switch configuration generation system.

## Test Structure

```
tests/
├── __init__.py                  # Test package initialization
├── conftest.py                  # Pytest fixtures and configuration
├── test_parser_functions.py     # Parser & utility unit tests (40 tests)
├── test_templates.py            # Tests for Jinja2 templates
├── test_config_validation.py    # Configuration validation tests
├── test_integration.py          # End-to-end integration tests
├── requirements.txt             # Test dependencies
└── README.md                    # This file
```

## Setup

### Install Test Dependencies

```bash
# From project root
make setup

# Or manually:
python3 -m venv .venv-test
.venv-test/bin/pip install -r tests/requirements.txt
```

## Running Tests

### Run All Tests

```bash
make test
# Or:
.venv-test/bin/pytest -v
```

### Run Specific Test File

```bash
# Parser function unit tests
.venv-test/bin/pytest tests/test_parser_functions.py

# Template tests
.venv-test/bin/pytest tests/test_templates.py

# Configuration validation
.venv-test/bin/pytest tests/test_config_validation.py

# Integration
.venv-test/bin/pytest tests/test_integration.py
```

### Run with Coverage

```bash
make test-coverage
# Or:
.venv-test/bin/pytest --cov=scripts --cov-report=html
```

This generates a coverage report in `htmlcov/index.html`.

### Run with Verbose Output

```bash
.venv-test/bin/pytest -vv
```

### Run Tests in Parallel

```bash
make test-fast
```

## Test Categories

### Parser & Utility Unit Tests (`test_parser_functions.py`)

Tests shared functions from `scripts/utils.py` and `scripts/excel_parser.py` (plus `scripts/compare_excel_inventory_and_configs.py` when present — those classes skip automatically if the internal-only compare script is absent):

- `generate_mac()` — deterministic MAC generation
- `classify_node()` — node role classification
- `is_switch()`, `is_valid_hostname()` — helper checks
- `classify_host_role()` — Excel parser role mapping
- `ports_to_range_string()` — NVUE swp range notation
- `_expand_iface_token()` — interface range expansion
- `normalize_nvue_line()` — NVUE command normalization
- `_natural_key()` — natural sort ordering

### Template Tests (`test_templates.py`)

- Template file existence
- Jinja2 syntax validation
- Templates contain `nv set` commands

### Configuration Validation Tests (`test_config_validation.py`)

- NVUE command format validation
- IP address, MAC address, VLAN ID, BGP ASN validation
- VLAN/VNI mapping consistency
- Interface and VRF naming conventions
- Configuration section completeness

### Integration Tests (`test_integration.py`)

- Playbook YAML syntax validation
- Inventory file structure
- Script existence and Python syntax
- Exported configuration structure

## Test Fixtures

Reusable test fixtures defined in `conftest.py`:

| Fixture | Description |
|---------|-------------|
| `project_root` | Path to project root directory |
| `sample_nvue_cli_config` | Sample NVUE CLI configuration string |
| `core_cli_template` | Path to core switch CLI Jinja2 template |
| `oob_cli_template` | Path to OOB switch CLI Jinja2 template |

## Writing New Tests

### Example Unit Test

```python
from utils import generate_mac

def test_mac_is_deterministic():
    """Same inputs produce same MAC."""
    mac1 = generate_mac("core-01", "swp1")
    mac2 = generate_mac("core-01", "swp1")
    assert mac1 == mac2
```

### Example Integration Test

```python
def test_all_playbooks_valid(project_root):
    """All playbooks parse as valid YAML."""
    for playbook in (project_root / "playbooks").glob("*.yml"):
        with open(playbook) as f:
            content = yaml.safe_load(f)
        assert content is not None
```

## Debugging Tests

```bash
# Single test with full output
.venv-test/bin/pytest tests/test_parser_functions.py::TestGenerateMac::test_format -vv -s

# Drop into debugger on failure
.venv-test/bin/pytest --pdb

# Show local variables on failure
.venv-test/bin/pytest --showlocals
```

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
