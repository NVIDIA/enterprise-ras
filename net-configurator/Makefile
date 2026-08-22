# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

SHELL := /bin/bash

.PHONY: help test generate deploy clean clean-output clean-all docs setup ztp ztp-setup ztp-update oob oob-setup \
        lint restart-ldap restart-ldap-direct \
        list-archs list-sites check-arch switch-ztp-deploy \
        help-generate help-ztp-setup help-oob-setup help-switch-ztp-deploy \
        help-deploy-servers deploy-servers deploy-servers-via-jump help-air \
        use show-context clear-context import \
        topology validate-topology validate validate-excel validate-ztp validate-ztp-direct \
        validate-config validate-servers validate-oob-bgp fix-ext-storage \
        validate-ping-matrix validate-requirements extract-requirements \
        air-setup help-air-setup air-connect air-show air-auth-test air-ssh-check air-deploy air-destroy air-list air-budget air-full-deploy deploy-exclude-servers \
        inventory status test-coverage test-fast push-switch-configs \
        deploy validate-all

# ============================================================================
# Architecture + Site Configuration
# ============================================================================
# ARCH  — deployment architecture type (e.g. 2-8-5-200)
# SITE  — deployment site name         (default: default)
#
# Priority order for each variable:
#   1. Command line:   make generate ARCH=2-8-5-200 SITE=customer-a
#   2. Context file:   .era-context   (set with: make use ARCH=... SITE=...)
#   3. Environment variable
#   4. SITE falls back to "default" if not set anywhere
#
VALID_ARCHS     := 2-4-3-200 2-4-5-800 2-8-5-200 2-8-9-400 2-8-9-800 2-8-9-400-SP

# Reusable architecture description block — keeps help/error messages DRY
define print_archs
	@echo "  2-4-3-200   (2 CPUs, 4 GPUs, 3 NICs, 200G)"
	@echo "  2-4-5-800   (2 CPUs, 4 GPUs, 5 NICs, 800G — GB300 NVL72)"
	@echo "  2-8-5-200   (2 CPUs, 8 GPUs, 5 NICs, 200G)"
	@echo "  2-8-9-400   (2 CPUs, 8 GPUs, 9 NICs, 400G)"
	@echo "  2-8-9-800   (2 CPUs, 8 GPUs, 9 NICs, 800G — dual-plane GPU fabric)"
	@echo "  2-8-9-400-SP (2 CPUs, 8 GPUs, 9 NICs, 400G — single-plane GPU fabric)"
endef

# Shell-context version for use inside if/for blocks (no @ prefix, with \)
ARCHS_ECHO = echo "  • 2-4-3-200   (2 CPUs, 4 GPUs, 3 NICs, 200G)"; \
             echo "  • 2-4-5-800   (2 CPUs, 4 GPUs, 5 NICs, 800G — GB300 NVL72)"; \
             echo "  • 2-8-5-200   (2 CPUs, 8 GPUs, 5 NICs, 200G)"; \
             echo "  • 2-8-9-400   (2 CPUs, 8 GPUs, 9 NICs, 400G)"; \
             echo "  • 2-8-9-800   (2 CPUs, 8 GPUs, 9 NICs, 800G — dual-plane GPU fabric)";	\
             echo "  • 2-8-9-400-SP (2 CPUs, 8 GPUs, 9 NICs, 400G — single-plane GPU fabric)";

# Read from .era-context if not already set on command line.
#
# We route the read through scripts/_era_context.py so malformed or
# hostile context values (path traversal in site, command-substitution
# in arch, etc.) never reach make-variable assignment. The validator
# rejects such values with a non-zero exit and prints nothing on
# stdout; on success it prints shell-quoted assignments that we
# parse with make's string functions. A raw `$(shell grep | cut)`
# here would let untrusted content influence every make invocation.
ifneq ($(wildcard .era-context),)
    _CTX := $(shell python3 scripts/_era_context.py 2>/dev/null)
    ifndef ARCH
        # Extract the _ARCH='...' token, strip the prefix + surrounding
        # single quotes emitted by shlex.quote.
        _CTX_ARCH := $(patsubst _ARCH=%,%,$(filter _ARCH=%,$(_CTX)))
        _CTX_ARCH := $(subst ',,$(_CTX_ARCH))
        # Belt-and-braces: only accept values in the known arch set.
        _CTX_ARCH := $(filter $(VALID_ARCHS),$(_CTX_ARCH))
        ifneq ($(_CTX_ARCH),)
            ARCH := $(_CTX_ARCH)
        endif
    endif
    ifndef SITE
        _CTX_SITE := $(patsubst _SITE=%,%,$(filter _SITE=%,$(_CTX)))
        _CTX_SITE := $(subst ',,$(_CTX_SITE))
        ifneq ($(_CTX_SITE),)
            SITE := $(_CTX_SITE)
        endif
    endif
endif

# Default site if still not set
SITE ?= default

INPUT_XLSX        = input/$(ARCH)/$(SITE)/$(ARCH).xlsx
INVENTORY_DIR     = output/$(ARCH)/$(SITE)/inventory

# Auto-detect LDAP: explicit LDAP=1 on command line takes priority,
# otherwise detected at runtime inside targets (not at Makefile parse time).
ifdef LDAP
    _LDAP_ACTIVE := 1
endif

# Runtime LDAP detection — call this inside targets that need it.
# Checks the generated inventory only when actually needed.
define detect_ldap
	$(if $(_LDAP_ACTIVE),,$(eval _LDAP_ACTIVE := $(shell grep -A1 '^ldap:' $(INVENTORY_DIR)/group_vars/all/main.yml 2>/dev/null | grep -q 'enabled: true' && echo 1)))
endef
CONFIG_OUTPUT_DIR = output/$(ARCH)/$(SITE)/configs

# Validate ansible-core version meets minimum requirement (2.20.4)
define check_ansible
	@ANSIBLE_VER=$$(ansible --version 2>/dev/null | head -1 | grep -oP 'core \K[0-9.]+'); \
	if [ -z "$$ANSIBLE_VER" ]; then \
		echo "⚠️  WARNING: ansible not found — install with: pip install -r requirements.txt"; \
	else \
		MIN="2.20.4"; \
		if [ "$$(printf '%s\n' "$$MIN" "$$ANSIBLE_VER" | sort -V | head -1)" != "$$MIN" ]; then \
			echo "⚠️  WARNING: ansible-core $$ANSIBLE_VER is below minimum $$MIN — upgrade with: pip install -r requirements.txt"; \
		fi; \
	fi
endef

# Validate ARCH is set and input directory exists
define check_arch
	@if [ -z "$(ARCH)" ]; then \
		echo "❌ ERROR: ARCH not specified"; \
		echo ""; \
		echo "Set architecture with one of:"; \
		echo "  • make use ARCH=<type>              (saves to .era-context)"; \
		echo "  • make $(1) ARCH=<type>             (one-time override)"; \
		echo "  • make $(1) ARCH=<type> SITE=<name> (specific site)"; \
		echo ""; \
		echo "Available architectures:"; \
		$(ARCHS_ECHO) \
		echo ""; \
		exit 1; \
	fi
	@if [ ! -d "input/$(ARCH)" ]; then \
		echo "❌ ERROR: Unknown architecture '$(ARCH)'"; \
		echo ""; \
		echo "Available architectures:"; \
		ls -1 input/ | grep -E '^[0-9]' | sed 's/^/  • /'; \
		echo ""; \
		exit 1; \
	fi
endef

# ============================================================================
# Context Management
# ============================================================================

import:  ## Import a filled-out Excel file — auto-detects arch/site from the file
	@if [ -z "$(EXCEL)" ]; then \
		echo "❌ ERROR: EXCEL not specified"; \
		echo ""; \
		echo "Usage: make import EXCEL=/path/to/your-config.xlsx"; \
		echo "       make import EXCEL=/path/to/your-config.xlsx SITE=my-lab"; \
		echo ""; \
		echo "The script reads 'architecture' and 'site_name' from the Excel"; \
		echo "Settings tab and copies the file to input/<arch>/<site>/<arch>.xlsx,"; \
		echo "then saves the context so all make commands use it automatically."; \
		echo ""; \
		exit 1; \
	fi
	@# Validate before importing so a poisoned workbook is rejected at ingest
	@# (security review #6): import is the documented first step and several Excel-sourced
	@# fields reach root-executed configs. IMPORT_SKIP_VALIDATE=1 escapes it.
	@if [ "$(IMPORT_SKIP_VALIDATE)" != "1" ]; then \
		python3 scripts/validate_excel.py "$(EXCEL)" || \
			{ echo "❌ Excel validation failed — not importing. Fix the issues above (or IMPORT_SKIP_VALIDATE=1 to override)."; exit 1; }; \
	fi
	@if [ -n "$(IMPORT_SITE)" ]; then \
		python3 scripts/import-excel.py "$(EXCEL)" --site "$(IMPORT_SITE)" || \
			{ echo "❌ Import failed. Check the Excel file and try again."; exit 1; }; \
	else \
		python3 scripts/import-excel.py "$(EXCEL)" || \
			{ echo "❌ Import failed. Check the Excel file and try again."; exit 1; }; \
	fi

# IMPORT_SITE is only set when the user explicitly passes SITE= on the command line.
# This prevents the SITE ?= default fallback from overriding the Excel site_name.
ifeq ($(origin SITE),command line)
    IMPORT_SITE := $(SITE)
else
    IMPORT_SITE :=
endif

use:  ## Set current architecture and site (saves to .era-context)
	@if [ -z "$(ARCH)" ]; then \
		echo "❌ ERROR: ARCH not specified"; \
		echo ""; \
		echo "Usage: make use ARCH=<type> [SITE=<name>]"; \
		echo ""; \
		echo "Available architectures:"; \
		$(ARCHS_ECHO) \
		exit 1; \
	fi
	@if [ ! -d "input/$(ARCH)" ]; then \
		echo "❌ ERROR: Unknown architecture '$(ARCH)'"; \
		exit 1; \
	fi
	@echo "# ERA Deployment Context" > .era-context
	@echo "# Auto-generated. Do not commit to version control." >> .era-context
	@echo "# Set with: make use ARCH=<type> [SITE=<name>]" >> .era-context
	@echo "" >> .era-context
	@echo "arch: $(ARCH)" >> .era-context
	@echo "site: $(SITE)" >> .era-context
	@echo ""
	@echo "✓ Set arch=$(ARCH)  site=$(SITE)"
	@echo ""
	@echo "You can now run commands without specifying ARCH/SITE:"
	@echo "  make generate"
	@echo "  make switch-ztp-deploy"
	@echo "  make validate-ztp"
	@echo ""

show-context:  ## Show current deployment context
	@if [ -f ".era-context" ]; then \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo "  Current Deployment Context"; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo ""; \
		grep -v '^#' .era-context | grep -v '^$$'; \
		echo ""; \
		echo "  Input:     input/$(ARCH)/$(SITE)/$(ARCH).xlsx"; \
		echo "  Inventory: output/$(ARCH)/$(SITE)/inventory/"; \
		echo "  Configs:   output/$(ARCH)/$(SITE)/configs/"; \
		echo ""; \
		echo "To change: make use ARCH=<type> [SITE=<name>]"; \
		echo "To clear:  make clear-context"; \
	else \
		echo "No deployment context set."; \
		echo ""; \
		echo "Set with: make use ARCH=<type> [SITE=<name>]"; \
		echo ""; \
		echo "Available architectures:"; \
		$(ARCHS_ECHO) \
	fi

clear-context:  ## Clear deployment context (removes .era-context)
	@rm -f .era-context
	@echo "✓ Cleared deployment context"
	@echo "  You will need to specify ARCH=<type> for commands."

help:  ## Show this help message
	@echo "ERA Network Automation - Available Commands:"
	@echo ""
	@if [ -f ".era-context" ]; then \
		_ARCH=$$(grep '^arch:' .era-context 2>/dev/null | cut -d' ' -f2); \
		_SITE=$$(grep '^site:' .era-context 2>/dev/null | cut -d' ' -f2); \
		echo "Current context: arch=$$_ARCH  site=$$_SITE (from .era-context)"; \
		echo ""; \
	else \
		echo "No context set. Use: make use ARCH=<type> [SITE=<name>]"; \
		echo ""; \
	fi
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Architectures (CPUs-GPUs-NICs-Speed):"
	$(print_archs)
	@echo ""
	@echo "Quick Start (one command each):"
	@echo "  make deploy EXCEL=my-config.xlsx   # Full pipeline: validate + import + generate + Air + ZTP"
	@echo "  make validate-all                  # Validate everything: topology + ZTP + config + servers"
	@echo ""
	@echo "Step by Step:"
	@echo "  make import EXCEL=my-config.xlsx   # Import filled Excel (auto-detects arch/site)"
	@echo "  make generate                      # Generate switch configs + topology"
	@echo "  make air-full-deploy               # Generate + Air simulation + ZTP deploy"
	@echo "  make switch-ztp-deploy             # ZTP deployment only"
	@echo ""
	@echo "Manual Context:"
	@echo "  make use ARCH=2-8-5-200           # Set arch once (SITE defaults to 'default')"
	@echo "  make use ARCH=2-8-5-200 SITE=lab  # Set arch + custom site"
	@echo ""
	@echo "Detailed Help (available topics):"
	@echo "  make help-generate           make help-switch-ztp-deploy"
	@echo "  make help-ztp-setup          make help-oob-setup"
	@echo "  make help-deploy-servers     make help-air"
	@echo "  make help-air-setup          make help-air-destroy"

list-archs:  ## List available architecture types
	@echo "Available architectures:"
	@echo ""
	$(print_archs)
	@echo ""
	@echo "Naming: {CPUs}-{GPUs}-{NICs}-{B}  (B = avg per-GPU East/West bandwidth, Gbps)"
	@echo "  Exception: in 2-4-3-200 / 2-8-5-200 (1:2 NIC:GPU) the trailing"
	@echo "  number follows the per-NIC link speed instead."
	@echo ""
	@echo "Usage: make <command> ARCH=<type> [SITE=<name>]"

list-sites:  ## List existing sites for current or specified ARCH
	@if [ -z "$(ARCH)" ]; then \
		echo "Sites across all architectures:"; \
		echo ""; \
		for arch in input/*/; do \
			arch=$${arch%/}; arch=$${arch#input/}; \
			echo "  $$arch:"; \
			ls -1 input/$$arch/ 2>/dev/null | sed 's/^/    • /'; \
		done; \
	else \
		echo "Sites for arch=$(ARCH):"; \
		echo ""; \
		ls -1 input/$(ARCH)/ 2>/dev/null | sed 's/^/  • /'; \
	fi

# ============================================================================
# Detailed Help
# ============================================================================

help-switch-ztp-deploy:  ## Show detailed help for switch-ztp-deploy
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  make switch-ztp-deploy - Complete ZTP Deployment Workflow"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "DESCRIPTION:"
	@echo "  Orchestrates the complete ZTP deployment process in one command."
	@echo "  Sets up OOB server, generates configs, and configures ZTP server."
	@echo ""
	@echo "REQUIRED:"
	@echo "  ARCH=<type>    Architecture type (2-4-3-200, 2-4-5-800, 2-8-5-200, 2-8-9-400, 2-8-9-800, 2-8-9-400-SP)"
	@echo ""
	@echo "OPTIONAL:"
	@echo "  SITE=<name>    Site name (default: 'default')"
	@echo "  LDAP=1         Force LDAP setup (auto-detected from Excel ldap_enabled)"
	@echo ""
	@echo "EXAMPLES:"
	@echo "  make switch-ztp-deploy ARCH=2-8-5-200"
	@echo "  make switch-ztp-deploy ARCH=2-8-5-200 SITE=customer-a"
	@echo "  make switch-ztp-deploy ARCH=2-8-5-200 LDAP=1"
	@echo ""
	@echo "WORKFLOW STEPS:"
	@echo "  1. Configure OOB Server"
	@echo "  2. Configure LDAP (if LDAP=1)"
	@echo "  3. Generate Inventory from Excel"
	@echo "  4. Generate Switch Configs + Topology"
	@echo "  5. Setup ZTP Server"
	@echo ""

help-generate:  ## Show detailed help for generate
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  make generate - Generate Inventory, Configs & Topology"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "DESCRIPTION:"
	@echo "  Three-step pipeline that regenerates everything from the Excel source:"
	@echo "    1. Parse Excel → Ansible inventory (host_vars, group_vars, hosts)"
	@echo "    2. Generate NVUE CLI configuration scripts for all switches"
	@echo "    3. Generate NVIDIA Air topology file"
	@echo ""
	@echo "REQUIRED:"
	@echo "  ARCH=<type>    Architecture type"
	@echo ""
	@echo "OPTIONAL:"
	@echo "  SITE=<name>    Site name (default: 'default')"
	@echo ""
	@echo "EXAMPLES:"
	@echo "  make generate ARCH=2-8-5-200"
	@echo "  make generate ARCH=2-8-5-200 SITE=customer-a"
	@echo ""
	@echo "OUTPUT:"
	@echo "  output/<arch>/<site>/inventory/   (hosts, host_vars/, group_vars/)"
	@echo "  output/<arch>/<site>/configs/     (core-01-config.sh, oob-switch-01-config.sh, etc.)"
	@echo "  output/<arch>/<site>/topology/    (Air topology JSON)"
	@echo ""

help-ztp-setup:  ## Show detailed help for ztp-setup
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  make ztp-setup - Setup ZTP Server"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "DESCRIPTION:"
	@echo "  One-time setup of ZTP server with dnsmasq (DHCP) and nginx."
	@echo "  Generates switch configs and copies them to ZTP server."
	@echo ""
	@echo "REQUIRED:"
	@echo "  ARCH=<type>    Architecture type"
	@echo ""
	@echo "OPTIONAL:"
	@echo "  SITE=<name>    Site name (default: 'default')"
	@echo ""
	@echo "EXAMPLES:"
	@echo "  make ztp-setup ARCH=2-8-5-200"
	@echo ""
	@echo "⚠️  WARNING: This will configure dnsmasq for DHCP"
	@echo "⚠️  Do NOT use if you already have isc-dhcp-server running!"
	@echo ""

help-oob-setup:  ## Show detailed help for oob-setup
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  make oob-setup - Setup OOB Server"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "DESCRIPTION:"
	@echo "  Configures OOB server as gateway/router for management networks."
	@echo ""
	@echo "REQUIRED:"
	@echo "  ARCH=<type>    Architecture type"
	@echo ""
	@echo "OPTIONAL:"
	@echo "  SITE=<name>    Site name (default: 'default')"
	@echo ""
	@echo "EXAMPLES:"
	@echo "  make oob-setup ARCH=2-8-5-200"
	@echo ""

help-deploy-servers:  ## Show detailed help for deploy-servers
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Deploy Server Configurations"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "TWO VARIANTS:"
	@echo ""
	@echo "  make deploy-servers ARCH=<type>"
	@echo "    Direct SSH from the control host to each server's ansible_host."
	@echo "    Use when:"
	@echo "      • running on-prem with workstation→server reachability, OR"
	@echo "      • running from inside an Air sim on dhcp-oob (recommended"
	@echo "        for manual fallback — no jump-host bottleneck)"
	@echo ""
	@echo "  make deploy-servers-via-jump ARCH=<type>"
	@echo "    SSH from the laptop through oob-server-01 as a ProxyJump."
	@echo "    Use when running from a laptop with an Air sim (no dhcp-oob"
	@echo "    access). Throughput is limited by oob-server-01's SSH concurrency"
	@echo "    (~3 parallel connections)."
	@echo ""
	@echo "REQUIRED:"
	@echo "  ARCH=<type>    Architecture type (2-4-3-200, 2-4-5-800, 2-8-5-200, 2-8-9-400, 2-8-9-800, 2-8-9-400-SP)"
	@echo ""
	@echo "OPTIONAL:"
	@echo "  SITE=<name>    Site name (default: 'default')"
	@echo ""
	@echo "Both variants prompt for a BECOME password — press Enter for"
	@echo "Air Ubuntu VMs (NOPASSWD sudo), or type the real sudo password"
	@echo "for on-prem hardware."
	@echo ""

help-air:  ## Show NVIDIA Air deployment guide
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  NVIDIA Air Deployment - Quick Reference"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "AUTOMATED WORKFLOW (recommended):"
	@echo ""
	@echo "  Setup (one-time):"
	@echo "    1. make air-setup                        # vault-encrypt NGC API key"
	@echo "    2. Set air_url in Excel Settings tab (AIR DEPLOYMENT section)"
	@echo "    3. make air-auth-test ARCH=<type>        # verify credentials"
	@echo ""
	@echo "  Deploy:"
	@echo "    make generate ARCH=<type>                # Excel -> configs + topology"
	@echo "    make air-deploy ARCH=<type>              # create Air sim + configure SSH"
	@echo "    make switch-ztp-deploy ARCH=<type>       # push configs to switches"
	@echo ""
	@echo "  Or all at once:"
	@echo "    make air-full-deploy ARCH=<type>         # generate + deploy + ZTP"
	@echo ""
	@echo "  Management:"
	@echo "    make air-list ARCH=<type>                # list simulations"
	@echo "    make air-budget ARCH=<type>              # check resource budget"
	@echo "    make air-ssh-check ARCH=<type>           # check SSH key auth on jump hosts"
	@echo "    make air-ssh-check ARCH=<type> FIX=1    # auto-inject SSH key if auth fails"
	@echo "    make air-destroy ARCH=<type>             # teardown simulation (auto-detect)"
	@echo "    make air-destroy ARCH=<type> SIM=<name-or-id>  # destroy specific simulation"
	@echo ""
	@echo "  Tip: run 'make air-list' first to see simulation names and IDs."
	@echo "       Use 'make help-air-destroy' for full usage."
	@echo ""
	@echo "MANUAL WORKFLOW (fallback):"
	@echo "  1. Upload topology JSON at air.nvidia.com"
	@echo "  2. Add SSH services to oob-server-01 and dhcp-oob"
	@echo "  3. make air-connect ARCH=<type>            # enter SSH details"
	@echo "  4. make switch-ztp-deploy ARCH=<type>"
	@echo ""
	@echo "FULL GUIDE: docs/AIR_DEPLOYMENT_GUIDE.md"
	@echo ""

# ============================================================================
# Test Environment
# ============================================================================

setup:  ## Setup test environment
	@echo "Setting up test environment..."
	python3 -m venv .venv-test
	.venv-test/bin/pip install -r tests/requirements.txt
	@echo "✅ Test environment ready!"

test:  ## Run all tests
	@if [ ! -f .venv-test/bin/pytest ]; then \
		echo "❌ Test environment not set up. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Running tests..."
	.venv-test/bin/pytest -v

test-coverage:  ## Run tests with coverage report
	@echo "Running tests with coverage..."
	.venv-test/bin/pytest --cov=scripts --cov-report=html --cov-report=term
	@echo "✅ Coverage report: htmlcov/index.html"

test-fast:  ## Run tests in parallel
	@echo "Running tests in parallel..."
	.venv-test/bin/pytest -v -n auto

# ============================================================================
# Core Workflow
# ============================================================================

generate:  ## Generate inventory + switch configs + Air topology - requires ARCH, optional SITE
	$(call check_arch,$@)
	$(call check_ansible)
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "Step 0: Validating Excel before generation..."
	@python3 scripts/validate_excel.py input/$(ARCH)/$(SITE)/$(ARCH).xlsx || { \
		echo ""; \
		echo "❌ Validation failed. Refusing to generate from an invalid Excel."; \
		echo "   Set GENERATE_SKIP_VALIDATE=1 to bypass (not recommended)."; \
		[ -z "$(GENERATE_SKIP_VALIDATE)" ] && exit 1; \
		echo "   GENERATE_SKIP_VALIDATE=1 set — proceeding anyway."; \
	}
	@echo ""
	@echo "Step 1: Generating inventory from Excel for arch=$(ARCH) site=$(SITE)..."
	python3 scripts/excel_parser.py --arch $(ARCH) --site $(SITE) --skip-validate
	@echo ""
	@echo "Step 2: Generating NVUE CLI configurations..."
	@mkdir -p $(CONFIG_OUTPUT_DIR)
	ansible-playbook playbooks/generate-cli-configs.yml \
		-i $(INVENTORY_DIR)/hosts \
		-e "config_output_dir=../$(CONFIG_OUTPUT_DIR)"
	@echo "✅ CLI configurations generated in $(CONFIG_OUTPUT_DIR)/"
	@echo ""
	@echo "Step 3: Generating Air topology..."
	python3 scripts/topology_generator.py generate --arch $(ARCH) --site $(SITE) $(if $(SWITCHES_ONLY),--switches-only,)
	@if [ -n "$(SWITCHES_ONLY)" ]; then touch "output/$(ARCH)/$(SITE)/.switches-only"; \
	 else rm -f "output/$(ARCH)/$(SITE)/.switches-only"; fi
ifdef SWITCHES_ONLY
	@echo "  SWITCHES_ONLY: server VMs omitted; switch configs unchanged (server-facing ports kept as unconnected stubs)."
	@echo "  SWITCHES_ONLY: patching breakout parents -> sub-port stubs..."
	@python3 scripts/patch-air-breakout-stubs.py --arch $(ARCH) --site $(SITE)
endif
ifdef AIR_SWITCHES_ONLY
	@echo "  AIR_SWITCHES_ONLY: patching OOB to L3 mode..."
	@sed -i 's/oob_uplink_mode: l2/oob_uplink_mode: l3/' $(INVENTORY_DIR)/group_vars/oob.yml $(INVENTORY_DIR)/group_vars/all/main.yml 2>/dev/null || true
	@for f in $(INVENTORY_DIR)/host_vars/leaf*smn*ipp6.yml; do \
		src="inventories/$(ARCH)/host_vars/$$(basename $$f .yml | sed 's/-ipp6//').yml"; \
		if [ -f "$$src" ] && ! grep -q "^lo_ip:" "$$f"; then \
			lo=$$(grep "^lo_ip:" "$$src" | awk '{print $$2}'); \
			asn=$$(grep "^asn:" "$$src" | awk '{print $$2}'); \
			rid=$$(echo $$lo | cut -d/ -f1); \
			echo "lo_ip: $$lo" >> "$$f"; \
			echo "router_id: $$rid" >> "$$f"; \
			echo "bgp_asn: $$asn" >> "$$f"; \
		fi; \
	done
	@ansible-playbook playbooks/generate-cli-configs.yml \
		-i $(INVENTORY_DIR) \
		-e "config_output_dir=../$(CONFIG_OUTPUT_DIR)" \
		--limit "oob" > /dev/null 2>&1
	@echo "  AIR_SWITCHES_ONLY: patching topology with breakout sub-port stubs..."
	@python3 scripts/patch-air-breakout-stubs.py --arch $(ARCH) --site $(SITE)
endif
	@echo "✅ Air topology generated"
	@echo ""
	@echo "Step 4: Generating Node Instruction scripts..."
	python3 scripts/generate-node-instructions.py --arch $(ARCH) --site $(SITE)
	@echo "✅ Node Instructions generated"
	@echo ""
ifdef SWITCHES_ONLY
	@echo "Step 5: Skipping netplan ↔ topology eth-check (SWITCHES_ONLY: no server VMs)."
else
	@echo "Step 5: Cross-check netplan ↔ topology eth-numbering..."
	@python3 scripts/check-eth-consistency.py --arch $(ARCH) --site $(SITE)
endif

generate-ocp:  ## Generate OCP Ansible inventory + ABI manifests from ERA inventory - requires ARCH, optional SITE
	$(call check_arch,$@)
	@if [ ! -d "output/$(ARCH)/$(SITE)/inventory" ]; then \
		echo "❌ ERROR: ERA inventory not found for arch=$(ARCH) site=$(SITE)"; \
		echo "   Run 'make generate ARCH=$(ARCH) SITE=$(SITE)' first."; \
		exit 1; \
	fi
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Generating OCP inventory  arch=$(ARCH)  site=$(SITE)"
	@if [ -f "input/$(ARCH)/$(SITE)/ocp-settings.yml" ]; then \
		echo "  ocp-settings.yml found — explicit node_roles will be used"; \
	else \
		echo "  No ocp-settings.yml — OCP roles will be auto-inferred from hostnames"; \
	fi
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	python3 scripts/generate-ocp-inventory.py --arch $(ARCH) --site $(SITE) \
		$(if $(OCP_SETTINGS),--ocp-settings $(OCP_SETTINGS),)

topology:  ## Generate Air topology only - requires ARCH, optional SITE
	$(call check_arch,$@)
	python3 scripts/topology_generator.py generate --arch $(ARCH) --site $(SITE)

validate-excel:  ## Validate Excel file before import/generate - requires EXCEL=<path> or ARCH
	@if [ -n "$(EXCEL)" ]; then \
		python3 scripts/validate_excel.py "$(EXCEL)"; \
	elif [ -n "$(ARCH)" ]; then \
		python3 scripts/validate_excel.py input/$(ARCH)/$(SITE)/$(ARCH).xlsx; \
	else \
		echo "Usage: make validate-excel EXCEL=/path/to/file.xlsx"; \
		echo "       make validate-excel ARCH=2-8-5-200 [SITE=default]"; \
		exit 1; \
	fi

validate-topology:  ## Validate Air topology against wiremap - requires ARCH, optional SITE
	$(call check_arch,$@)
	@echo "Validating Air topology for arch=$(ARCH) site=$(SITE)..."
	python3 scripts/topology_generator.py validate --arch $(ARCH) --site $(SITE) $(if $(wildcard output/$(ARCH)/$(SITE)/.switches-only),--switches-only,)

push-switch-configs:  ## Push and apply generated NVUE configs to core + OOB switches - requires ARCH, optional SITE
	$(call check_arch,$@)
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Pushing switch configs  arch=$(ARCH)  site=$(SITE)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	ansible-playbook playbooks/push-switch-configs.yml \
		-i $(INVENTORY_DIR)/hosts \
		-e "config_output_dir=../$(CONFIG_OUTPUT_DIR)"

deploy-servers:  ## Deploy server configs (direct SSH) - requires ARCH, optional SITE
	$(call check_arch,$@)
	@echo "Deploying to servers (direct) for arch=$(ARCH) site=$(SITE)..."
	ansible-playbook playbooks/era-servers.yml -i $(INVENTORY_DIR)/hosts --ask-become-pass

deploy-servers-via-jump:  ## Deploy server configs via ProxyJump through oob-server-01 (Air from laptop) - requires ARCH
	$(call check_arch,$@)
	@echo "Deploying to servers (ProxyJump via oob-server-01) for arch=$(ARCH) site=$(SITE)..."
	ansible-playbook playbooks/era-servers.yml -i $(INVENTORY_DIR)/hosts --ask-become-pass \
		-e "via_server=true" -f 5

ztp-setup:  ## Setup ZTP server (dnsmasq + nginx) - requires ARCH, optional SITE
	$(call check_arch,$@)
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Setting up ZTP Server  arch=$(ARCH)  site=$(SITE)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "⚠️  WARNING: This will configure dnsmasq for DHCP"
	@echo "⚠️  Do NOT use if you already have isc-dhcp-server running!"
	@echo ""
	@mkdir -p $(CONFIG_OUTPUT_DIR)
	@ansible-playbook playbooks/setup-ztp-server.yml -i $(INVENTORY_DIR)/hosts \
		-e "config_output_dir=../$(CONFIG_OUTPUT_DIR)" \
		--ask-become-pass
	@echo "✅ ZTP server ready!"

air-setup:  ## Onboarding wizard: create encrypted shared Air credentials vault
	@python3 scripts/air-setup.py

help-air-setup:  ## Show air-setup usage
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  make air-setup — One-time NVIDIA Air credentials onboarding"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "  Interactively collects your NGC API key, username, and SSH key path,"
	@echo "  then saves them encrypted to:"
	@echo "      .era-secrets/air-secrets.yml  (in this repo; gitignored)"
	@echo ""
	@echo "  Run this once per checkout — every 'make air-*' command across every"
	@echo "  arch and site in this repo will read from this shared vault."
	@echo ""
	@echo "  You'll be asked whether to save the vault password so it's not"
	@echo "  prompted every time. Saved passwords live at:"
	@echo "      .era-secrets/vault-pass  (mode 0600, gitignored)"
	@echo ""
	@echo "  Re-run any time to update fields — existing values are preserved"
	@echo "  for fields you don't change."
	@echo ""

air-connect:  ## Set Air SSH connection details - requires ARCH, optional SITE
	$(call check_arch,$@)
	@python3 scripts/air-connect.py --arch $(ARCH) --site $(SITE)

air-show:  ## Show current Air connection settings - requires ARCH, optional SITE
	$(call check_arch,$@)
	@python3 scripts/air-connect.py --arch $(ARCH) --site $(SITE) --show

# ============================================================================
# NVIDIA Air Simulation Management (API-driven)
# ============================================================================

air-auth-test:  ## Test Air API credentials and connectivity - requires ARCH
	$(call check_arch,$@)
	@python3 scripts/air-auth-test.py --arch $(ARCH) --site $(SITE)

air-deploy:  ## Create Air simulation, configure SSH, and connect - requires ARCH
	$(call check_arch,$@)
	@python3 scripts/air-deploy.py --arch $(ARCH) --site $(SITE) $(if $(SERVER_CONFIG),--server-config,) $(if $(NOZTP),--no-ztp,) $(if $(RETRIES),--retry-on-capacity $(RETRIES),) $(if $(RETRY_DELAY),--retry-delay $(RETRY_DELAY),)

air-deploy-retry:  ## Same as air-deploy but retries on capacity errors - RETRIES=3 RETRY_DELAY=300 by default
	$(call check_arch,$@)
	@python3 scripts/air-deploy.py --arch $(ARCH) --site $(SITE) $(if $(SERVER_CONFIG),--server-config,) $(if $(NOZTP),--no-ztp,) --retry-on-capacity $(or $(RETRIES),3) --retry-delay $(or $(RETRY_DELAY),300)

air-deploy-switches-only:  ## Deploy a switches-only, no-ZTP Air sim (no server VMs; full switch config + unconnected stubs) - requires ARCH
	$(call check_arch,$@)
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Switches-only / no-ZTP deploy  arch=$(ARCH)  site=$(SITE)"
	@echo "  (server VMs omitted; switch configs unchanged; server-facing ports"
	@echo "   kept as unconnected stubs. Validate with: make validate-switch-health)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@$(MAKE) --no-print-directory generate ARCH=$(ARCH) SITE=$(SITE) SWITCHES_ONLY=1 AIR_SWITCHES_ONLY=1
	@python3 scripts/air-deploy.py --arch $(ARCH) --site $(SITE) --no-ztp $(if $(RETRIES),--retry-on-capacity $(RETRIES),) $(if $(RETRY_DELAY),--retry-delay $(RETRY_DELAY),)

air-destroy:  ## Destroy Air simulation and clean up - requires ARCH
	$(call check_arch,$@)
	@python3 scripts/air-destroy.py --arch $(ARCH) --site $(SITE) $(if $(SIM),--sim $(SIM),) $(if $(FORCE),--force,)

help-air-destroy:  ## Show air-destroy usage and examples
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  make air-destroy — Destroy an Air simulation"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "Usage:"
	@echo "  make air-destroy ARCH=<type>                       # auto-detect simulation"
	@echo "  make air-destroy ARCH=<type> SIM=<name>            # by simulation name"
	@echo "  make air-destroy ARCH=<type> SIM=<uuid>            # by simulation ID"
	@echo "  make air-destroy ARCH=<type> SIM=<name> FORCE=1    # skip confirmation"
	@echo ""
	@echo "Options:"
	@echo "  ARCH    Architecture type (required)"
	@echo "  SITE    Site name (default: default)"
	@echo "  SIM     Simulation name or UUID (auto-detects if omitted)"
	@echo "  FORCE   Skip confirmation prompt (set to 1)"
	@echo ""
	@echo "What it does (scripts/air-destroy.py):"
	@echo "  1. Loads Air credentials (AIR_API_KEY env var or .era-secrets vault)"
	@echo "  2. Authenticates against Air (validates key with a 2xx health check)"
	@echo "  3. Finds the simulation — first match wins:"
	@echo "       - SIM=<name-or-uuid> if provided"
	@echo "       - else lookup by title 'ERA-<SITE>-<ARCH>'"
	@echo "       - else fall back to the single LOADED simulation in your account"
	@echo "         (errors if multiple loaded sims exist — pass SIM= to disambiguate)"
	@echo "  4. Prompts 'Continue? [y/N]' unless FORCE=1 is set"
	@echo "  5. Sends a single DELETE to /api/v3/simulations/<id>/"
	@echo "     NGC Air v3 deletes from any state (LOADED, INACTIVE, RUNNING) —"
	@echo "     no stop-then-delete sequence required"
	@echo "  6. Sweeps orphaned UserConfigs whose name starts with the sim's title"
	@echo "     (cloud-init scripts uploaded by air-deploy)"
	@echo ""
	@echo "What it does NOT do:"
	@echo "  - Does not reset local inventory: ansible_host / ansible_port in"
	@echo "    host_vars/oob-server-01.yml and dhcp-oob.yml remain as stale"
	@echo "    pointers until the next 'make air-deploy' overwrites them"
	@echo "  - Does not remove status_page_url from group_vars/all/main.yml"
	@echo ""
	@echo "Examples:"
	@echo "  make air-destroy ARCH=2-4-3-200 SITE=sample"
	@echo "  make air-destroy ARCH=2-4-3-200 SIM=ERA-sample-2-4-3-200"
	@echo "  make air-destroy ARCH=2-4-3-200 SIM=9bead738-d107-4784-9b9c-f72c3e89a4f0"
	@echo ""
	@echo "Related:"
	@echo "  make air-list ARCH=<type>       Show all simulations and their IDs"
	@echo "  python3 scripts/air-destroy.py --arch <type> --cleanup-only"
	@echo "      Sweep orphaned UserConfigs without touching any simulation."
	@echo "      Use after a destroy that crashed mid-flight. (Not wired into Make.)"
	@echo ""
	@echo "If multiple simulations exist with the same name, specify by UUID."
	@echo ""

air-list:  ## List Air simulations with SSH info - requires ARCH
	$(call check_arch,$@)
	@python3 scripts/air-list.py --arch $(ARCH) --site $(SITE)

air-budget:  ## Check Air resource budget and project topology - requires ARCH
	$(call check_arch,$@)
	@python3 scripts/air-budget-check.py --arch $(ARCH) --site $(SITE)

air-ssh-check:  ## Check and fix SSH key access to Air jump hosts - requires ARCH
	$(call check_arch,$@)
	@python3 scripts/air-ssh-check.py --arch $(ARCH) --site $(SITE) $(if $(FIX),--fix,)

deploy:  ## One-command deployment: import Excel + generate + create Air sim + ZTP deploy + server config - requires EXCEL
	@if [ -z "$(EXCEL)" ]; then \
		echo "❌ ERROR: EXCEL not specified"; \
		echo ""; \
		echo "Usage: make deploy EXCEL=/path/to/your-config.xlsx"; \
		echo "       make deploy EXCEL=/path/to/your-config.xlsx SITE=my-lab"; \
		echo ""; \
		echo "This runs the full pipeline:"; \
		echo "  1. Validate Excel"; \
		echo "  2. Import Excel (sets ARCH/SITE from spreadsheet)"; \
		echo "  3. Generate inventory + configs + topology"; \
		echo "  4. Create Air simulation"; \
		echo "  5. Deploy via ZTP"; \
		echo ""; \
		exit 1; \
	fi
	@# Pre-flight: check Air credentials exist before starting the pipeline
	@_HAS_CREDS=0; \
	if [ -n "$$AIR_API_KEY" ]; then \
		_HAS_CREDS=1; \
	elif [ -f ".era-secrets/air-secrets.yml" ]; then \
		_HAS_CREDS=1; \
	fi; \
	if [ "$$_HAS_CREDS" = "0" ]; then \
		echo ""; \
		echo "❌ ERROR: Air API credentials not configured"; \
		echo ""; \
		echo "Run the onboarding wizard (one-time per machine):"; \
		echo ""; \
		echo "  make air-setup"; \
		echo ""; \
		echo "Or, for a one-off override:"; \
		echo ""; \
		echo "  export AIR_API_KEY=<your-ngc-key>"; \
		echo ""; \
		echo "Then re-run:  make deploy EXCEL=$(EXCEL)"; \
		echo ""; \
		exit 1; \
	fi
	@echo ""
	@echo "╔════════════════════════════════════════════════════════════════════╗"
	@echo "║           ERA One-Command Deployment                              ║"
	@echo "╚════════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Step 1/8: Validating Excel..."
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@python3 scripts/validate_excel.py "$(EXCEL)" || \
		{ echo ""; echo "❌ Excel validation failed. Fix the issues above and try again."; exit 1; }
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Step 2/8: Importing Excel..."
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@if [ -n "$(IMPORT_SITE)" ]; then \
		python3 scripts/import-excel.py "$(EXCEL)" --site "$(IMPORT_SITE)" --yes || \
			{ echo "❌ Import failed."; exit 1; }; \
	else \
		python3 scripts/import-excel.py "$(EXCEL)" --yes || \
			{ echo "❌ Import failed."; exit 1; }; \
	fi
	@echo ""
	@set -e; eval "$$(python3 scripts/_excel_context.py '$(EXCEL)')"; \
	_LDAP=$$(python3 scripts/_check_ldap_enabled.py "$$_ARCH" "$$_SITE"); \
	echo "╔════════════════════════════════════════════════════════════════════╗"; \
	echo "║           ERA Full Deployment Pipeline (with server config)        ║"; \
	echo "║           arch=$$_ARCH  site=$$_SITE"; \
	echo "╚════════════════════════════════════════════════════════════════════╝"; \
	echo ""; \
	echo "This will:"; \
	echo "  ✓ Step 1: Validate Excel input"; \
	echo "  ✓ Step 2: Import Excel (auto-detect arch/site)"; \
	echo "  ✓ Step 3: Generate inventory + configs + topology"; \
	if [ "$(NOZTP)" = "1" ]; then \
		echo "  ✓ Step 4: Create Air sim + inject switch+server configs (NOZTP=1, no DHCP/HTTP fetch)"; \
	else \
		echo "  ✓ Step 4: Create Air simulation + configure SSH + inject server config"; \
	fi; \
	echo "  ✓ Step 5: Configure OOB Server (gateway/routing)"; \
	if [ "$$_LDAP" = "1" ]; then \
		echo "  ✓ Step 6: Configure LDAP Server"; \
	else \
		echo "  ○ Step 6: LDAP Server (skipped - set ldap_enabled=Yes in Excel or add LDAP=1)"; \
	fi; \
	if [ "$(NOZTP)" = "1" ]; then \
		echo "  ⏭  Step 7: Generate switch configs (on target)  — SKIPPED (NOZTP=1)"; \
		echo "  ⏭  Step 8: Setup ZTP Server (DHCP + nginx)      — SKIPPED (NOZTP=1)"; \
	else \
		echo "  ✓ Step 7: Generate switch configs (on target)"; \
		echo "  ✓ Step 8: Setup ZTP Server (DHCP + nginx)"; \
	fi; \
	echo ""; \
	echo "  Server config (hostname, netplan, lldp) injected via Node Instructions."; \
	echo "  deploy-servers-via-jump is NOT needed."; \
	if [ "$(NOZTP)" = "1" ]; then \
		echo "  Switch configs injected via Node Instructions — no DHCP/ZTP server."; \
	fi; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	if [ "$(AUTO_CONFIRM)" != "1" ]; then \
		echo "Press Enter to continue, or Ctrl+C to cancel..."; \
		bash -c 'read -r'; \
	fi; \
	echo ""; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "  Step 3/8: Generating inventory + configs + topology..."; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	$(MAKE) generate ARCH=$$_ARCH SITE=$$_SITE && \
	echo "" && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	if [ "$(NOZTP)" = "1" ]; then \
		echo "  Step 4/8: Creating Air sim + injecting switch+server configs (NOZTP=1)..."; \
	else \
		echo "  Step 4/8: Creating Air simulation + injecting server config..."; \
	fi && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	python3 scripts/air-deploy.py --arch $$_ARCH --site $$_SITE --server-config $(if $(NOZTP),--no-ztp,) && \
	echo "" && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	echo "  Step 4b/8: Injecting SSH key into Air jump hosts..." && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	$(MAKE) air-ssh-check ARCH=$$_ARCH SITE=$$_SITE FIX=1 && \
	echo "" && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	if [ "$(NOZTP)" = "1" ]; then \
		echo "  Steps 5-8: OOB+LDAP only (ZTP server skipped)..."; \
	else \
		echo "  Steps 5-8: ZTP deployment..."; \
	fi && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	$(MAKE) switch-ztp-deploy ARCH=$$_ARCH SITE=$$_SITE AUTO_CONFIRM=1 NOZTP=$(NOZTP) && \
	echo "" && \
	echo "╔════════════════════════════════════════════════════════════════════╗" && \
	echo "║  ✅ Deployment complete (with server config)!                     ║" && \
	echo "║                                                                    ║" && \
	echo "║  Next steps:                                                       ║" && \
	echo "║    make validate-all    — validate everything                      ║" && \
	echo "║    make air-list        — show SSH connection info                 ║" && \
	echo "╚════════════════════════════════════════════════════════════════════╝" && \
	if [ "$(NOZTP)" = "1" ]; then \
		echo ""; \
		echo "⚠️  NOZTP=1 deferred-apply notice"; \
		echo "   Switch configs apply via era-apply.service AFTER multi-user.target"; \
		echo "   on each switch — typically 2–3 minutes after the sim reaches LOADED."; \
		echo "   Wait for that window before SSH'ing in or running validate-all."; \
		echo "   If you log in early and change the password manually, the deferred"; \
		echo "   apply's chpasswd will overwrite it — out-of-sync state, hard to debug."; \
		echo ""; \
		echo "   Quick check from a switch console:"; \
		echo "     systemctl status era-apply.service   # 'active (exited)' = applied"; \
		echo ""; \
	fi && \
	_STATUS_URL=$$(grep 'status_page_url:' output/$$_ARCH/$$_SITE/inventory/group_vars/all/main.yml 2>/dev/null | sed 's/.*: *//'); \
	if [ -n "$$_STATUS_URL" ]; then \
		echo ""; \
		echo "  ZTP Status Page: $$_STATUS_URL"; \
	fi

air-full-deploy:  ## Full pipeline: generate + air-deploy + switch-ztp-deploy - requires ARCH
	$(call check_arch,$@)
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Full Air Deployment Pipeline  arch=$(ARCH)  site=$(SITE)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	$(MAKE) generate ARCH=$(ARCH) SITE=$(SITE) && \
	$(MAKE) air-deploy ARCH=$(ARCH) SITE=$(SITE) && \
	$(MAKE) switch-ztp-deploy ARCH=$(ARCH) SITE=$(SITE)

deploy-switches-only:  ## EXCEL-driven switches-only no-ZTP pipeline: import + generate (switches-only) + air-deploy --no-ztp - requires EXCEL
	@if [ -z "$(EXCEL)" ]; then \
		echo "❌ ERROR: EXCEL not specified"; \
		echo ""; \
		echo "Usage: make deploy-switches-only EXCEL=/path/to/your-config.xlsx"; \
		echo "       make deploy-switches-only EXCEL=/path/to/your-config.xlsx IMPORT_SITE=my-lab"; \
		echo ""; \
		echo "Switches-only / no-ZTP one-command pipeline (mirrors 'make deploy'):"; \
		echo "  1. Validate + import Excel (auto-detects arch/site, sets context)"; \
		echo "  2. Generate inventory + configs + SWITCHES-ONLY topology"; \
		echo "  3. Create Air sim (NOZTP, server VMs omitted; server-facing ports"; \
		echo "     kept as unconnected stubs so the full switch config still applies)"; \
		echo ""; \
		echo "Then validate (Servers auto-detected as N/A):"; \
		echo "  make validate-all SKIP_UPLOAD=1"; \
		echo "  make validate-switch-health    # targeted fabric-health layer"; \
		echo ""; \
		exit 1; \
	fi
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Switches-only / no-ZTP pipeline   EXCEL=$(EXCEL)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@python3 scripts/validate_excel.py "$(EXCEL)" || \
		{ echo ""; echo "❌ Excel validation failed. Fix the issues above and try again."; exit 1; }
	@if [ -n "$(IMPORT_SITE)" ]; then \
		python3 scripts/import-excel.py "$(EXCEL)" --site "$(IMPORT_SITE)" --yes || { echo "❌ Import failed."; exit 1; }; \
	else \
		python3 scripts/import-excel.py "$(EXCEL)" --yes || { echo "❌ Import failed."; exit 1; }; \
	fi
	@set -e; eval "$$(python3 scripts/_excel_context.py '$(EXCEL)')"; \
	_DEPLOY_SITE="$(IMPORT_SITE)"; \
	[ -n "$$_DEPLOY_SITE" ] || _DEPLOY_SITE="$$_SITE"; \
	echo ""; \
	echo "  arch=$$_ARCH  site=$$_DEPLOY_SITE  — deploying switches-only (no server VMs, no ZTP)"; \
	$(MAKE) air-deploy-switches-only ARCH=$$_ARCH SITE=$$_DEPLOY_SITE

deploy-exclude-servers:  ## Deploy switches only (no server config) - requires EXCEL
	@if [ -z "$(EXCEL)" ]; then \
		echo "❌ ERROR: EXCEL not specified"; \
		echo ""; \
		echo "Usage: make deploy-exclude-servers EXCEL=/path/to/your-config.xlsx"; \
		echo ""; \
		echo "Same as 'make deploy' but skips server config (hostname, netplan, lldp)."; \
		echo "Use 'make deploy-servers-via-jump' afterwards to configure servers."; \
		echo ""; \
		exit 1; \
	fi
	@# Pre-flight: check Air credentials exist before starting the pipeline
	@_HAS_CREDS=0; \
	if [ -n "$$AIR_API_KEY" ]; then \
		_HAS_CREDS=1; \
	elif [ -f ".era-secrets/air-secrets.yml" ]; then \
		_HAS_CREDS=1; \
	fi; \
	if [ "$$_HAS_CREDS" = "0" ]; then \
		echo ""; \
		echo "❌ ERROR: Air API credentials not configured"; \
		echo ""; \
		echo "Run the onboarding wizard (one-time per machine):"; \
		echo ""; \
		echo "  make air-setup"; \
		echo ""; \
		echo "Or, for a one-off override:"; \
		echo ""; \
		echo "  export AIR_API_KEY=<your-ngc-key>"; \
		echo ""; \
		echo "Then re-run:  make deploy-exclude-servers EXCEL=$(EXCEL)"; \
		echo ""; \
		exit 1; \
	fi
	@echo ""
	@echo "╔════════════════════════════════════════════════════════════════════╗"
	@echo "║           ERA Deployment (switches only)                           ║"
	@echo "╚════════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Step 1/8: Validating Excel..."
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@python3 scripts/validate_excel.py "$(EXCEL)" || \
		{ echo ""; echo "❌ Excel validation failed. Fix the issues above and try again."; exit 1; }
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Step 2/8: Importing Excel..."
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@if [ -n "$(IMPORT_SITE)" ]; then \
		python3 scripts/import-excel.py "$(EXCEL)" --site "$(IMPORT_SITE)" --yes || \
			{ echo "❌ Import failed."; exit 1; }; \
	else \
		python3 scripts/import-excel.py "$(EXCEL)" --yes || \
			{ echo "❌ Import failed."; exit 1; }; \
	fi
	@echo ""
	@set -e; \
	if [ -n "$(ARCH)" ] && [ -n "$(SITE)" ]; then \
		_ARCH="$(ARCH)"; _SITE="$(SITE)"; \
	elif [ -n "$(EXCEL)" ]; then \
		eval "$$(python3 scripts/_excel_context.py '$(EXCEL)')"; \
	else \
		eval "$$(python3 scripts/_era_context.py)"; \
	fi; \
	_LDAP=$$(python3 scripts/_check_ldap_enabled.py "$$_ARCH" "$$_SITE"); \
	echo "╔════════════════════════════════════════════════════════════════════╗"; \
	echo "║           ERA Deployment Pipeline (switches only)                  ║"; \
	echo "║           arch=$$_ARCH  site=$$_SITE"; \
	echo "╚════════════════════════════════════════════════════════════════════╝"; \
	echo ""; \
	echo "This will:"; \
	echo "  ✓ Step 1: Validate Excel input"; \
	echo "  ✓ Step 2: Import Excel (auto-detect arch/site)"; \
	echo "  ✓ Step 3: Generate inventory + configs + topology"; \
	if [ "$(NOZTP)" = "1" ]; then \
		echo "  ✓ Step 4: Create Air sim + inject switch configs (NOZTP=1)"; \
	else \
		echo "  ✓ Step 4: Create Air simulation + configure SSH"; \
	fi; \
	echo "  ✓ Step 5: Configure OOB Server (gateway/routing)"; \
	if [ "$$_LDAP" = "1" ]; then \
		echo "  ✓ Step 6: Configure LDAP Server"; \
	else \
		echo "  ○ Step 6: LDAP Server (skipped - set ldap_enabled=Yes in Excel or add LDAP=1)"; \
	fi; \
	if [ "$(NOZTP)" = "1" ]; then \
		echo "  ⏭  Step 7: Generate switch configs (on target)  — SKIPPED (NOZTP=1)"; \
		echo "  ⏭  Step 8: Setup ZTP Server (DHCP + nginx)      — SKIPPED (NOZTP=1)"; \
	else \
		echo "  ✓ Step 7: Generate switch configs (on target)"; \
		echo "  ✓ Step 8: Setup ZTP Server (DHCP + nginx)"; \
	fi; \
	echo ""; \
	echo "  Server config skipped — run 'make deploy-servers-via-jump' afterwards"; \
	echo "  to configure server hostnames, netplan, and lldp."; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	if [ "$(AUTO_CONFIRM)" != "1" ]; then \
		echo "Press Enter to continue, or Ctrl+C to cancel..."; \
		bash -c 'read -r'; \
	fi; \
	echo ""; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "  Step 3/8: Generating inventory + configs + topology..."; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	$(MAKE) generate ARCH=$$_ARCH SITE=$$_SITE && \
	echo "" && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	echo "  Step 4/8: Creating Air simulation..." && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	$(MAKE) air-deploy ARCH=$$_ARCH SITE=$$_SITE && \
	echo "" && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	echo "  Step 4b/8: Injecting SSH key into Air jump hosts..." && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	$(MAKE) air-ssh-check ARCH=$$_ARCH SITE=$$_SITE FIX=1 && \
	echo "" && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	echo "  Steps 5-8: ZTP deployment..." && \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" && \
	$(MAKE) switch-ztp-deploy ARCH=$$_ARCH SITE=$$_SITE AUTO_CONFIRM=1 && \
	echo "" && \
	echo "╔════════════════════════════════════════════════════════════════════╗" && \
	echo "║  ✅ Deployment complete (switches only)!                          ║" && \
	echo "║                                                                    ║" && \
	echo "║  Next steps:                                                       ║" && \
	echo "║    make deploy-servers-via-jump — configure servers               ║" && \
	echo "║    make validate-all    — validate everything                      ║" && \
	echo "║    make air-list        — show SSH connection info                 ║" && \
	echo "╚════════════════════════════════════════════════════════════════════╝" && \
	_STATUS_URL=$$(grep 'status_page_url:' output/$$_ARCH/$$_SITE/inventory/group_vars/all/main.yml 2>/dev/null | sed 's/.*: *//'); \
	if [ -n "$$_STATUS_URL" ]; then \
		echo ""; \
		echo "  ZTP Status Page: $$_STATUS_URL"; \
	fi

# Internal: check if Air connection is configured, prompt if not.
# Mode-aware: reads `_oob_uplink_mode` from the generated topology JSON
# and verifies the right jump-host host_vars file is configured. In L2
# the jump host is oob-server-01; in L3 it's utility. Without consulting
# the mode we'd risk accepting a stale L2 file in a site that's been
# reconfigured to L3 (or vice versa) and silently use the wrong target.
define check_air_connection
	@_MODE=$$(python3 scripts/_show_oob_mode.py "output/$(ARCH)/$(SITE)/topology/$(ARCH)-topology.json"); \
	case "$$_MODE" in l3) _CHECK="$(INVENTORY_DIR)/host_vars/utility.yml" ;; \
	                    *) _CHECK="$(INVENTORY_DIR)/host_vars/oob-server-01.yml" ;; esac; \
	if [ ! -f "$$_CHECK" ] || grep -q 'CHANGE_ME' "$$_CHECK" 2>/dev/null; then \
		echo ""; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo "  Air SSH not configured (mode=$$_MODE) — running air-connect..."; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		python3 scripts/air-connect.py --arch $(ARCH) --site $(SITE); \
	fi
endef

oob-setup:  ## Setup OOB server - requires ARCH, optional SITE
	$(call check_arch,$@)
	$(check_air_connection)
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Setting up OOB Server  arch=$(ARCH)  site=$(SITE)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@ansible-playbook playbooks/setup-oob-server.yml -i $(INVENTORY_DIR)/hosts --ask-become-pass
	@echo "✅ OOB server configured!"

ztp-update:  ## Update ZTP configurations - requires ARCH, optional SITE
	$(call check_arch,$@)
	@echo "Generating CLI configurations for arch=$(ARCH) site=$(SITE)..."
	@mkdir -p $(CONFIG_OUTPUT_DIR)
	ansible-playbook playbooks/generate-cli-configs.yml \
		-i $(INVENTORY_DIR)/hosts \
		-e "config_output_dir=../$(CONFIG_OUTPUT_DIR)"
	@echo "Updating ZTP server..."
	ansible-playbook playbooks/setup-ztp-server.yml -i $(INVENTORY_DIR)/hosts \
		-e "config_output_dir=../$(CONFIG_OUTPUT_DIR)"
	@echo "✅ ZTP configurations updated!"

REPORT_DIR = output/$(ARCH)/$(SITE)/reports

validate-ztp-direct:  ## Validate ZTP by SSHing directly to each switch (on-prem / non-Air) - requires ARCH, optional SITE
	$(call check_arch,$@)
	@mkdir -p $(REPORT_DIR)
	@echo "Validating ZTP configuration (direct SSH) for arch=$(ARCH) site=$(SITE)..."
	@ANSIBLE_STDOUT_CALLBACK=minimal PYTHONUNBUFFERED=1 ansible-playbook -i $(INVENTORY_DIR)/hosts \
		playbooks/validate-ztp-direct.yml \
		-e '{"report_file": "$(CURDIR)/$(REPORT_DIR)/ztp-validation.txt"}' 2>&1 | \
		grep --line-buffered -v '^\[WARNING\]' | grep --line-buffered -v 'Callback dispatch' | grep --line-buffered -v '^$$'
	@echo ""
	@if [ -f $(REPORT_DIR)/ztp-validation.txt ]; then \
		sed '/RAW COMMAND OUTPUT/,$$d' $(REPORT_DIR)/ztp-validation.txt; \
		echo ""; \
		echo "📄 Full report with raw command output: $(REPORT_DIR)/ztp-validation.txt"; \
	fi

validate-switch-health:  ## Tier-1 switch operational-health checks (apply/BGP/EVPN-ES/VNI/intf) via jump - requires ARCH, optional SITE
	$(call check_arch,$@)
	@mkdir -p $(REPORT_DIR)
	@echo ""
	@echo "========================================"
	@echo "Switch Health (Tier 1)  arch=$(ARCH)  site=$(SITE)"
	@echo "========================================"
	@ANSIBLE_STDOUT_CALLBACK=minimal PYTHONUNBUFFERED=1 ansible-playbook -i $(INVENTORY_DIR)/hosts \
		playbooks/validate-switch-health.yml \
		-e "arch=$(ARCH) site=$(SITE)" \
		-e '{"report_file": "$(CURDIR)/$(REPORT_DIR)/switch-health.txt"}'

validate-oob-bgp:  ## Gating OOB↔CSL BGP check (L3 OOB only; N/A otherwise) via jump - requires ARCH, optional SITE
	$(call check_arch,$@)
	@mkdir -p $(REPORT_DIR)
	@_MODE=$$(python3 scripts/_show_oob_mode.py output/$(ARCH)/$(SITE)/topology/$(ARCH)-topology.json 2>/dev/null); \
	if [ "$$_MODE" != "l3" ]; then \
		echo "  ⏭️  OOB↔CSL BGP check N/A (OOB uplink mode = $${_MODE:-l2}, not l3)"; \
		exit 0; \
	fi; \
	echo ""; \
	echo "========================================"; \
	echo "OOB↔CSL BGP (gating)  arch=$(ARCH)  site=$(SITE)"; \
	echo "========================================"; \
	ANSIBLE_STDOUT_CALLBACK=minimal PYTHONUNBUFFERED=1 ansible-playbook -i $(INVENTORY_DIR)/hosts \
		playbooks/validate-oob-bgp.yml \
		-e "arch=$(ARCH) site=$(SITE)" \
		-e '{"report_file": "$(CURDIR)/$(REPORT_DIR)/oob-bgp-validation.txt"}'

fix-ext-storage:  ## Auto-remediate ext-storage nodes missing/inactive FRR via the jump (idempotent) - requires ARCH, optional SITE
	$(call check_arch,$@)
	python3 scripts/fix-ext-storage-frr.py --arch $(ARCH) --site $(SITE)

validate-ztp:  ## Validate ZTP via dhcp-oob bastion (works from laptop or inside Air) - requires ARCH, optional SITE
	$(call check_arch,$@)
	@mkdir -p $(REPORT_DIR)
	@echo ""
	@echo "========================================"
	@echo "ZTP Validation  arch=$(ARCH)  site=$(SITE)"
	@echo "========================================"
	@ANSIBLE_STDOUT_CALLBACK=minimal PYTHONUNBUFFERED=1 ansible-playbook -i $(INVENTORY_DIR)/hosts \
		playbooks/validate-ztp.yml \
		-e '{"report_file": "$(CURDIR)/$(REPORT_DIR)/ztp-validation.txt"}' 2>&1 | \
		grep --line-buffered -v '^\[WARNING\]' | grep --line-buffered -v 'Callback dispatch' | grep --line-buffered -v '^$$'; \
		_STATUS=$${PIPESTATUS[0]}; \
		echo ""; \
		if [ -f $(REPORT_DIR)/ztp-validation.txt ]; then \
			sed '/RAW COMMAND OUTPUT/,$$d' $(REPORT_DIR)/ztp-validation.txt; \
			echo ""; \
			echo "📄 Full report with raw command output: $(REPORT_DIR)/ztp-validation.txt"; \
		fi; \
		_STATUS_PAGE=$$(grep -q 'status_page_enabled.*[Yy]es\|status_page_enabled.*[Tt]rue' $(INVENTORY_DIR)/group_vars/all/main.yml 2>/dev/null && echo 1); \
		if [ -z "$(SKIP_UPLOAD)" ] && [ "$$_STATUS_PAGE" = "1" ] && [ -f "$(REPORT_DIR)/ztp-validation.txt" ]; then \
			echo ""; \
			echo "Uploading ZTP validation report to status page..."; \
			ansible-playbook -i $(INVENTORY_DIR)/hosts playbooks/upload-reports.yml \
				-e '{"reports_dir": "$(CURDIR)/$(REPORT_DIR)"}' 2>/dev/null && \
				echo "  ✅ Report uploaded to status page" || \
				echo "  ⚠️  Report upload failed (non-critical)"; \
		fi; \
		if ! $(MAKE) --no-print-directory validate-oob-bgp ARCH=$(ARCH) SITE=$(SITE); then _STATUS=1; fi; \
		exit $$_STATUS

validate-config:  ## Compare running config vs generated config (runs on dhcp-oob) - requires ARCH, optional SITE
	$(call check_arch,$@)
	@mkdir -p $(REPORT_DIR)
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Config Validation  arch=$(ARCH)  site=$(SITE)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@set -o pipefail; \
	ansible-playbook -i $(INVENTORY_DIR)/hosts playbooks/validate-config.yml \
		-e "config_output_dir=../$(CONFIG_OUTPUT_DIR)" \
		-e '{"report_file": "$(CURDIR)/$(REPORT_DIR)/config-validation.txt"}'; \
	_AP=$$?; \
	echo ""; \
	if [ -f $(REPORT_DIR)/config-validation.txt ]; then \
		cat $(REPORT_DIR)/config-validation.txt; \
	else \
		echo "  (no validation report generated)"; \
	fi; \
	_STATUS_PAGE=$$(grep -q 'status_page_enabled.*[Yy]es\|status_page_enabled.*[Tt]rue' $(INVENTORY_DIR)/group_vars/all/main.yml 2>/dev/null && echo 1); \
	if [ -z "$(SKIP_UPLOAD)" ] && [ "$$_STATUS_PAGE" = "1" ] && [ -f "$(REPORT_DIR)/config-validation.txt" ]; then \
		echo ""; \
		echo "Uploading config validation report to status page..."; \
		ansible-playbook -i $(INVENTORY_DIR)/hosts playbooks/upload-reports.yml \
			-e '{"reports_dir": "$(CURDIR)/$(REPORT_DIR)"}' 2>/dev/null && \
			echo "  ✅ Report uploaded to status page" || \
			echo "  ⚠️  Report upload failed (non-critical)"; \
	fi; \
	exit $$_AP

validate-requirements:  ## Validate generated config against architecture requirements - optional ARCH
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Architecture Requirements Validation"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ifdef ARCH
	@if [ ! -f scripts/validate_requirements.py ]; then \
		echo "  Internal-only target — requires architecture reference docs"; \
		echo "  that are not included in the public release. Skipping."; \
	elif [ ! -d "input/$(ARCH)" ]; then \
		echo "❌ ERROR: Unknown architecture '$(ARCH)'"; \
		echo ""; \
		echo "Available architectures:"; \
		ls -1 input/ | grep -E '^[0-9]' | sed 's/^/  • /'; \
		echo ""; \
		exit 1; \
	else \
		python3 scripts/validate_requirements.py --arch $(ARCH) --site $(SITE); \
	fi
else
	@if [ -f scripts/validate_requirements.py ]; then \
		python3 scripts/validate_requirements.py; \
	else \
		echo "  Internal-only target — requires architecture reference docs"; \
		echo "  that are not included in the public release. Skipping."; \
	fi
endif

validate-servers:  ## Validate server config — bonds, VLANs, connectivity (runs on dhcp-oob) - requires ARCH
	$(call check_arch,$@)
	@mkdir -p $(REPORT_DIR)
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Validating server architecture  arch=$(ARCH)  site=$(SITE)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@set -o pipefail; \
	ansible-playbook playbooks/validate-servers.yml \
		-i $(INVENTORY_DIR)/hosts \
		-e '{"report_file": "$(CURDIR)/$(REPORT_DIR)/server-validation.txt"}'; \
	_AP=$$?; \
	echo ""; \
	if [ -f $(REPORT_DIR)/server-validation.txt ]; then \
		cat $(REPORT_DIR)/server-validation.txt; \
	else \
		echo "  (no validation report generated)"; \
	fi; \
	_STATUS_PAGE=$$(grep -q 'status_page_enabled.*[Yy]es\|status_page_enabled.*[Tt]rue' $(INVENTORY_DIR)/group_vars/all/main.yml 2>/dev/null && echo 1); \
	if [ -z "$(SKIP_UPLOAD)" ] && [ "$$_STATUS_PAGE" = "1" ] && [ -f "$(REPORT_DIR)/server-validation.txt" ]; then \
		echo ""; \
		echo "Uploading server validation report to status page..."; \
		ansible-playbook -i $(INVENTORY_DIR)/hosts playbooks/upload-reports.yml \
			-e '{"reports_dir": "$(CURDIR)/$(REPORT_DIR)"}' 2>/dev/null && \
			echo "  ✅ Report uploaded to status page" || \
			echo "  ⚠️  Report upload failed (non-critical)"; \
	fi; \
	exit $$_AP

validate-ping-matrix:  ## Run full server-to-server ping matrix (all VLANs) - requires ARCH
	$(call check_arch,$@)
	@mkdir -p $(REPORT_DIR)
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Server Ping Matrix  arch=$(ARCH)  site=$(SITE)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@ansible-playbook playbooks/validate-ping-matrix.yml \
		-i $(INVENTORY_DIR)/hosts \
		-e '{"local_report": "$(CURDIR)/$(REPORT_DIR)/ping-matrix-report.txt"}' && \
	echo "" && \
	cat $(REPORT_DIR)/ping-matrix-report.txt && \
	_STATUS_PAGE=$$(grep -q 'status_page_enabled.*[Yy]es\|status_page_enabled.*[Tt]rue' $(INVENTORY_DIR)/group_vars/all/main.yml 2>/dev/null && echo 1); \
	if [ -z "$(SKIP_UPLOAD)" ] && [ "$$_STATUS_PAGE" = "1" ] && [ -f "$(REPORT_DIR)/ping-matrix-report.txt" ]; then \
		echo ""; \
		echo "Uploading ping matrix report to ZTP server..."; \
		ansible-playbook -i $(INVENTORY_DIR)/hosts playbooks/upload-reports.yml \
			-e '{"reports_dir": "$(CURDIR)/$(REPORT_DIR)"}' 2>/dev/null && \
			echo "  ✅ Report uploaded to ZTP status page" || \
			echo "  ⚠️  Report upload failed (non-critical)"; \
	fi

validate-all:  ## Run all 5 validations: topology + config (canary) + ZTP + switch-health + servers (Servers N/A for switches-only) - requires ARCH
	$(call check_arch,$@)
	@mkdir -p $(REPORT_DIR)
	@if ls $(REPORT_DIR)/*.txt 1>/dev/null 2>&1; then \
		_TS=$$(date +%Y%m%d-%H%M%S); \
		mkdir -p $(REPORT_DIR)/report-archive; \
		for f in $(REPORT_DIR)/*.txt; do \
			mv "$$f" "$(REPORT_DIR)/report-archive/$$(basename $$f .txt)-$$_TS.txt"; \
		done; \
		echo "  Archived previous reports to $(REPORT_DIR)/report-archive/ ($$_TS)"; \
		echo ""; \
	fi
	@echo ""
	@echo "╔════════════════════════════════════════════════════════════════════╗"
	@echo "║           ERA Full Validation  arch=$(ARCH)  site=$(SITE)"
	@echo "╚════════════════════════════════════════════════════════════════════╝"
	@echo ""
	@set -o pipefail; \
	_TOPO=PASS; _CFG=PASS; _ZTP=PASS; _SWH=PASS; _SRV=PASS; \
	_SWONLY=$$([ -f output/$(ARCH)/$(SITE)/.switches-only ] && echo 1 || echo 0); \
	[ "$$_SWONLY" = "1" ] && echo "  (switches-only sim — server data-plane validation will be N/A; switch-health is the fabric gate)" && echo ""; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "  1/5: Validating topology against wiremap..."; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	{ echo "Report generated: $$(date '+%Y-%m-%d %H:%M:%S')"; echo ""; \
	$(MAKE) validate-topology ARCH=$(ARCH) SITE=$(SITE) SKIP_UPLOAD=1 2>&1; } | tee $(REPORT_DIR)/topology-validation.txt && \
		echo "  ✅ Topology validation passed" || \
		{ echo "  ❌ Topology validation failed"; _TOPO=FAIL; }; \
	echo ""; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "  2/5: Comparing running config vs generated config (root canary)..."; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	_CFG_OK=0; \
	for _i in 1 2 3; do \
		if [ "$$_i" -gt 1 ]; then \
			echo ""; \
			echo "  (attempt $$_i/3 — sleeping 15s to absorb NVUE apply lag)"; \
			sleep 15; \
		fi; \
		if $(MAKE) validate-config ARCH=$(ARCH) SITE=$(SITE) SKIP_UPLOAD=1; then \
			_CFG_OK=1; break; \
		fi; \
	done; \
	if [ "$$_CFG_OK" = "1" ]; then \
		echo "  ✅ Config comparison passed"; \
	else \
		echo "  ❌ Config comparison failed after 3 attempts"; _CFG=FAIL; \
	fi; \
	echo ""; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "  3/5: Validating ZTP on switches..."; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	if [ "$$_CFG" = "FAIL" ]; then \
		echo "  ⏭️  Skipped — config validation failed (downstream tests would be noise)"; _ZTP=SKIP; \
	elif $(MAKE) validate-ztp ARCH=$(ARCH) SITE=$(SITE) SKIP_UPLOAD=1; then \
		echo "  ✅ ZTP validation passed"; \
	else \
		echo "  ❌ ZTP validation failed"; _ZTP=FAIL; \
	fi; \
	echo ""; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "  4/5: Validating switch operational health (apply/BGP/EVPN)..."; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	if [ "$$_CFG" = "FAIL" ]; then \
		echo "  ⏭️  Skipped — config validation failed (downstream tests would be noise)"; _SWH=SKIP; \
	elif $(MAKE) validate-switch-health ARCH=$(ARCH) SITE=$(SITE); then \
		echo "  ✅ Switch health passed"; \
	else \
		echo "  ❌ Switch health failed"; _SWH=FAIL; \
	fi; \
	echo ""; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "  5/5: Validating server architecture..."; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	if [ "$$_SWONLY" = "1" ]; then \
		echo "  ⏭️  N/A — switches-only sim (no server VMs deployed)"; _SRV=NA; \
	elif [ "$$_CFG" = "FAIL" ]; then \
		echo "  ⏭️  Skipped — config validation failed (downstream tests would be noise)"; _SRV=SKIP; \
	elif $(MAKE) validate-servers ARCH=$(ARCH) SITE=$(SITE) SKIP_UPLOAD=1; then \
		echo "  ✅ Server validation passed"; \
	else \
		echo "  ❌ Server validation failed"; _SRV=FAIL; \
	fi; \
	echo ""; \
	_STATUS_PAGE=$$(grep -q 'status_page_enabled.*[Yy]es\|status_page_enabled.*[Tt]rue' $(INVENTORY_DIR)/group_vars/all/main.yml 2>/dev/null && echo 1); \
	if [ -z "$(SKIP_UPLOAD)" ] && [ "$$_STATUS_PAGE" = "1" ] && [ -d "$(REPORT_DIR)" ]; then \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo "  Uploading reports to ZTP server..."; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		ansible-playbook -i $(INVENTORY_DIR)/hosts playbooks/upload-reports.yml \
			-e '{"reports_dir": "$(CURDIR)/$(REPORT_DIR)"}' 2>/dev/null && \
			echo "  ✅ Reports uploaded to ZTP status page" || \
			echo "  ⚠️  Report upload failed (non-critical)"; \
		echo ""; \
	fi; \
	_mark() { case "$$1" in PASS) echo "✅ passed";; FAIL) echo "❌ failed";; SKIP) echo "⏭️  skipped (config canary failed)";; NA) echo "➖ n/a (switches-only)";; esac; }; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "                      Validation Summary"; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	printf "  1/5  Topology            %s\n" "$$(_mark $$_TOPO)"; \
	printf "  2/5  Config Comparison   %s\n" "$$(_mark $$_CFG)"; \
	printf "  3/5  ZTP                 %s\n" "$$(_mark $$_ZTP)"; \
	printf "  4/5  Switch Health       %s\n" "$$(_mark $$_SWH)"; \
	printf "  5/5  Servers             %s\n" "$$(_mark $$_SRV)"; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo ""; \
	if [ "$$_TOPO" = "FAIL" ] || [ "$$_ZTP" = "FAIL" ] || [ "$$_CFG" = "FAIL" ] || [ "$$_SWH" = "FAIL" ] || [ "$$_SRV" = "FAIL" ]; then \
		echo "╔════════════════════════════════════════════════════════════════════╗"; \
		echo "║  ⚠️  Some validations failed — review the output above            ║"; \
		echo "╚════════════════════════════════════════════════════════════════════╝"; \
		_OVERALL=1; \
	else \
		echo "╔════════════════════════════════════════════════════════════════════╗"; \
		echo "║  ✅ All validations passed!                                        ║"; \
		echo "╚════════════════════════════════════════════════════════════════════╝"; \
		_OVERALL=0; \
	fi; \
	_STATUS_URL=$$(grep 'status_page_url:' $(INVENTORY_DIR)/group_vars/all/main.yml 2>/dev/null | sed 's/.*: *//'); \
	if [ -n "$$_STATUS_URL" ]; then \
		echo ""; \
		echo "  ZTP Status Page: $$_STATUS_URL"; \
		echo "  Reports:         $$_STATUS_URL/reports/"; \
	fi; \
	exit $$_OVERALL

extract-requirements:  ## Extract requirements from architecture PDFs into drafts for review
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Extracting Requirements from Architecture PDFs"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@if [ ! -f scripts/extract_requirements.py ]; then \
		echo "  Internal-only target — requires architecture reference docs"; \
		echo "  that are not included in the public release. Skipping."; \
	else \
		python3 scripts/extract_requirements.py --all --draft; \
		echo ""; \
		echo "Drafts written to docs/requirements/drafts/"; \
		echo "Review port assignments (OCR can misparse), then copy to docs/requirements/"; \
	fi
	@echo ""

restart-ldap:  ## Restart LDAP via OOB server - requires ARCH, optional SITE
	$(call check_arch,$@)
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Restarting LDAP  arch=$(ARCH)  site=$(SITE)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@ansible-playbook playbooks/restart-ldap-switches.yml -i $(INVENTORY_DIR)/hosts
	@echo "✅ LDAP service restart process complete!"

restart-ldap-direct:  ## Restart LDAP via direct SSH - requires ARCH, optional SITE
	$(call check_arch,$@)
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Restarting LDAP (direct)  arch=$(ARCH)  site=$(SITE)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@ansible-playbook playbooks/restart-ldap-switches-direct.yml -i $(INVENTORY_DIR)/hosts --ask-become-pass
	@echo "✅ LDAP service restart process complete!"

# ============================================================================
# ============================================================================
# Complete ZTP Deployment Workflow
# ============================================================================

switch-ztp-deploy:  ## Complete ZTP deployment - requires ARCH, optional SITE LDAP=1
	$(call check_arch,$@)
	$(check_air_connection)
	$(detect_ldap)
	@echo ""
	@echo "╔════════════════════════════════════════════════════════════════════╗"
	@echo "║           ERA Switch ZTP Deployment                                ║"
	@echo "║           arch=$(ARCH)  site=$(SITE)"
	@echo "╚════════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "This workflow will:"
	@echo "  ✓ Step 1: Configure OOB Server (gateway/routing)"
	@if [ "$(_LDAP_ACTIVE)" = "1" ]; then \
		echo "  ✓ Step 2: Configure LDAP Server"; \
	else \
		echo "  ○ Step 2: LDAP Server (skipped - set ldap_enabled=Yes in Excel or add LDAP=1)"; \
	fi
	@echo "  ✓ Step 3: Generate Inventory from Excel"
	@echo "  ✓ Step 4: Generate Switch Configurations + Topology"
	@if [ "$(NOZTP)" = "1" ]; then \
		echo "  ✓ Step 5: Install Operator Status Page (nginx + /reports/)"; \
		echo "  ⏭  Step 6: Setup ZTP Server (DHCP + ztp.sh)  — SKIPPED (NOZTP=1)"; \
		echo "      Switch configs were already injected directly into Air via Node Instructions."; \
	else \
		echo "  ✓ Step 5: Install Operator Status Page (nginx + /reports/)"; \
		echo "  ✓ Step 6: Setup ZTP Server (DHCP + ztp.sh)"; \
	fi
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@if [ "$(AUTO_CONFIRM)" != "1" ]; then \
		echo "Press Enter to continue, or Ctrl+C to cancel..."; \
		bash -c 'read -r'; \
	fi
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  STEP 1/6: Configure OOB Server"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@ansible-playbook playbooks/setup-oob-server.yml -i $(INVENTORY_DIR)/hosts
	@echo ""
	@if [ "$(_LDAP_ACTIVE)" = "1" ]; then \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo "  STEP 2/6: Configure LDAP Server"; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		ansible-playbook playbooks/era-servers.yml -i $(INVENTORY_DIR)/hosts --tags ldap; \
		echo ""; \
	fi
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  STEP 3/6: Generate Inventory from Excel"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@# Validate before parsing configs onto hardware (security review #6): this is the
	@# documented `make import && make switch-ztp-deploy` path, which otherwise
	@# never runs the validator. DEPLOY_SKIP_VALIDATE=1 escapes it.
	@if [ "$(DEPLOY_SKIP_VALIDATE)" != "1" ]; then \
		python3 scripts/validate_excel.py input/$(ARCH)/$(SITE)/$(ARCH).xlsx || \
			{ echo "❌ Excel validation failed — aborting deploy. Fix the issues above (or DEPLOY_SKIP_VALIDATE=1 to override)."; exit 1; }; \
	fi
	python3 scripts/excel_parser.py --arch $(ARCH) --site $(SITE) --skip-validate
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  STEP 4/6: Generate Switch Configurations + Topology"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@mkdir -p $(CONFIG_OUTPUT_DIR)
	ansible-playbook playbooks/generate-cli-configs.yml \
		-i $(INVENTORY_DIR)/hosts \
		-e "config_output_dir=../$(CONFIG_OUTPUT_DIR)"
	python3 scripts/topology_generator.py generate --arch $(ARCH) --site $(SITE)
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  STEP 5/6: Install Operator Status Page"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Status page is independent of ZTP — runs even in NOZTP=1 so the"
	@echo "  operator dashboard + /reports/ landing zone exist for validate-*."
	@ansible-playbook playbooks/setup-status-page.yml -i $(INVENTORY_DIR)/hosts \
		-e "config_output_dir=../$(CONFIG_OUTPUT_DIR)"
	@echo ""
	@if [ "$(NOZTP)" = "1" ]; then \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo "  STEP 6/6: Setup ZTP Server  ⏭  SKIPPED (NOZTP=1)"; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo "  Switch configs were injected directly into Air via Node Instructions."; \
		echo "  No DHCP/HTTP ZTP server needed."; \
	else \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo "  STEP 6/6: Setup ZTP Server"; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		ansible-playbook playbooks/setup-ztp-server.yml -i $(INVENTORY_DIR)/hosts \
			-e "config_output_dir=../$(CONFIG_OUTPUT_DIR)"; \
	fi
	@echo ""
	@echo "╔════════════════════════════════════════════════════════════════════╗"
	@echo "║           ✅ ZTP DEPLOYMENT COMPLETE!                              ║"
	@echo "╚════════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "  arch=$(ARCH)  site=$(SITE)"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Power on switches — they will auto-configure via ZTP"
	@echo "  2. Verify ZTP server: curl http://<ztp-server-ip>/"
	@echo "  3. Validate switches after boot:"
	@echo ""
	@echo "     make validate-ztp ARCH=$(ARCH) SITE=$(SITE)"
	@echo ""
	@echo "     or directly (requires SSH access to each switch):"
	@echo ""
	@echo "     make validate-ztp-direct ARCH=$(ARCH) SITE=$(SITE)"
	@echo ""
	@echo "  4. Run full validation suite:"
	@echo ""
	@echo "     make validate-all ARCH=$(ARCH) SITE=$(SITE)"
	@echo ""
	@echo "Other useful commands:"
	@echo "  • Update configs:   make ztp-update ARCH=$(ARCH) SITE=$(SITE)"
	@echo "  • Push configs:     make push-switch-configs ARCH=$(ARCH) SITE=$(SITE)"
	@echo "  • Compare configs:  make validate-config ARCH=$(ARCH) SITE=$(SITE)"
	@if [ "$(_LDAP_ACTIVE)" = "1" ]; then \
		echo "  • Restart LDAP:     make restart-ldap ARCH=$(ARCH) SITE=$(SITE)"; \
	fi
	@_STATUS_URL=$$(grep 'status_page_url:' $(INVENTORY_DIR)/group_vars/all/main.yml 2>/dev/null | sed 's/.*: *//'); \
	if [ -n "$$_STATUS_URL" ]; then \
		echo ""; \
		echo "  ZTP Status Page: $$_STATUS_URL"; \
	fi
	@echo ""

# ============================================================================
# Utilities
# ============================================================================

lint:  ## Lint YAML and Python files
	@echo "Linting YAML files..."
	@if command -v yamllint >/dev/null 2>&1; then \
		yamllint -c .yamllint playbooks/ roles/; \
	else \
		echo "❌ yamllint not installed — cannot lint. Run: pip install yamllint (or: make setup)"; \
		exit 1; \
	fi
	@echo "Linting Python files..."
	@if command -v flake8 >/dev/null 2>&1; then \
		flake8 scripts/ --max-line-length=120; \
	else \
		echo "❌ flake8 not installed — cannot lint. Run: pip install flake8 (or: make setup)"; \
		exit 1; \
	fi

clean:  ## Clean caches and temp files
	@echo "Cleaning generated files..."
	rm -rf .pytest_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Cleaned!"

clean-output:  ## Remove generated output (inventory, configs, topology, reports) - requires ARCH
	$(call check_arch,$@)
	@if [ -d "output/$(ARCH)/$(SITE)" ]; then \
		echo "This will delete: output/$(ARCH)/$(SITE)/"; \
		echo "  inventory/  configs/  topology/  reports/"; \
		if bash -c 'read -r -p "  Continue? [y/N]: " _confirm; [ "$$_confirm" = "y" ] || [ "$$_confirm" = "Y" ]'; then \
			rm -rf "output/$(ARCH)/$(SITE)"; \
			echo "✅ Removed output/$(ARCH)/$(SITE)/"; \
		else \
			echo "  Cancelled."; \
		fi; \
	else \
		echo "Nothing to clean: output/$(ARCH)/$(SITE)/ does not exist"; \
	fi

clean-all:  ## Clean everything including test venv
	$(MAKE) clean
	rm -rf .venv-test/
	@echo "✅ All cleaned!"

validate:  ## Validate Ansible syntax - requires ARCH, optional SITE
	$(call check_arch,$@)
	@echo "Validating Ansible syntax for arch=$(ARCH) site=$(SITE)..."
	@for playbook in playbooks/*.yml; do \
		echo "  Checking $$playbook..."; \
		ansible-playbook $$playbook --syntax-check -i $(INVENTORY_DIR)/hosts; \
	done
	@echo "✅ Syntax validation complete"

inventory:  ## Show inventory summary - requires ARCH, optional SITE
	$(call check_arch,$@)
	@echo "📋 Inventory Summary for arch=$(ARCH) site=$(SITE)"
	@echo ""
	@ansible-inventory -i $(INVENTORY_DIR)/hosts --list --yaml | head -50

status:  ## Show project status
	@echo "📊 ERA Network Automation - Project Status"
	@echo ""
	@echo "Repository:"
	@du -sh . | awk '{print "  Size: " $$1}'
	@find . -name "*.yml" -o -name "*.yaml" | wc -l | awk '{print "  YAML files: " $$1}'
	@find . -name "*.md" | wc -l | awk '{print "  Documentation: " $$1}'
	@echo ""
	@echo "Input templates:"
	@for arch in input/*/; do \
		arch=$${arch%/}; arch=$${arch#input/}; \
		sites=$$(ls -1 input/$$arch/ 2>/dev/null | tr '\n' ' '); \
		echo "  $$arch: $$sites"; \
	done
	@echo ""
	@echo "Output sites:"
	@for arch in output/*/; do \
		arch=$${arch%/}; arch=$${arch#output/}; \
		sites=$$(ls -1 output/$$arch/ 2>/dev/null | tr '\n' ' '); \
		echo "  $$arch: $$sites"; \
	done
	@echo ""

docs:  ## Show documentation links
	@echo "📚 ERA Network Documentation"
	@echo ""
	@echo "Main Documentation:"
	@echo "  - README.md                          Project overview"
	@echo ""
	@echo "Playbooks:"
	@echo "  - playbooks/README.md                Playbook documentation"
	@echo ""
	@echo "Zero Touch Provisioning:"
	@echo "  - docs/ZTP_INTERFACE_CONFIGURATION.md  Multi-interface ZTP setup"
	@echo "  - docs/AIR_DEPLOYMENT_GUIDE.md         NVIDIA Air deployment guide"

.DEFAULT_GOAL := help

# Internal-only targets. The leading dash means a checkout without this file
# (e.g. a public release) silently skips it.
-include Makefile.internal
