<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Testing Quick Start Guide

Get started with testing in 3 minutes!

## Setup (One-Time)

```bash
# 1. Navigate to project root
cd /path/to/net-configurator

# 2. Create test virtual environment and install deps
make setup

# Or manually:
python3 -m venv .venv-test
.venv-test/bin/pip install -r tests/requirements.txt
```

## Run Tests

### All Tests
```bash
make test
# Or:
.venv-test/bin/pytest -v
```

**Expected**: 73 passed in ~0.5s

### With Coverage
```bash
make test-coverage
```

### Specific Tests
```bash
# Parser function unit tests (generate_mac, classify_node, ports_to_range, etc.)
.venv-test/bin/pytest tests/test_parser_functions.py

# Templates only
.venv-test/bin/pytest tests/test_templates.py

# Validation only
.venv-test/bin/pytest tests/test_config_validation.py

# Integration only
.venv-test/bin/pytest tests/test_integration.py
```

## Test a Feature Manually

### Test Config Generation Pipeline

```bash
# Generate configs from Excel for a specific architecture
make generate ARCH=2-8-5-200

# Review generated configs
cat output/2-8-5-200/default/configs/core-01-config.sh | head -20

# Validate the Air topology
make validate-topology ARCH=2-8-5-200
```

### Test Template Rendering

```bash
# Generate only the CLI configs (assumes inventory already exists)
ansible-playbook playbooks/generate-cli-configs.yml \
  -i output/2-8-5-200/default/inventory/hosts \
  -e "config_output_dir=../output/2-8-5-200/default/configs"

# Check generated files
ls -lh output/2-8-5-200/default/configs/
```

## Common Commands

| Command | Purpose |
|---------|---------|
| `make test` | Run all tests |
| `make test-coverage` | Tests with coverage report |
| `make test-fast` | Run tests in parallel |
| `.venv-test/bin/pytest -v` | Verbose output |
| `.venv-test/bin/pytest -s` | Show print statements |
| `.venv-test/bin/pytest -k "mac"` | Run tests matching "mac" |
| `.venv-test/bin/pytest --lf` | Run last failed tests |

## Test Status

**73 tests** | **~0.5s runtime**

## Need More Help?

See [TESTING.md](TESTING.md) for comprehensive documentation.
