#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Manual ZTP Helper Script
# For switches with static IP addresses that need to fetch configs from ZTP server
#
# Usage:
#   ./manual-ztp.sh <switch-name> [ztp-server-ip]
#
# Examples:
#   ./manual-ztp.sh core-01 192.168.200.1
#   ./manual-ztp.sh oob-switch-02 192.168.200.1
#
# <ztp-server-ip> is this server's address as the SWITCH reaches it: the
# switch, not this host, fetches the URL. Without it the helper only checks the
# served files and prints the options with a placeholder.
#
# ztp.sh fetches configs/<hostname>-config.sh using the hostname from the
# switch's DHCP lease, and exits if it finds no lease. On a switch with a static
# management address, use push-switch-configs instead.
#
# The SSH option reads the switch password (switch_ansible_password from
# secrets.yml) from $SSHPASS, or prompts for it without echo, and hands it to
# `sshpass -e`, so it never appears in the process list.
#
# ZTP_WEB_ROOT overrides where the served files live (default /var/www/ztp,
# the nginx root set up by the ztp-server role).

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Banner
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}         Manual ZTP Helper - Push Config to Switch${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo

# Check arguments
if [ -z "$1" ]; then
    echo -e "${RED}❌ Error: Switch name required${NC}"
    echo
    echo "Usage: $0 <switch-name> [ztp-server-ip]"
    echo
    echo "Examples:"
    echo "  $0 core-01 192.168.200.1"
    echo "  $0 oob-switch-02 192.168.200.1"
    echo
    exit 1
fi

SWITCH_NAME="$1"
ZTP_SERVER="${2:-}"
ZTP_WEB_ROOT="${ZTP_WEB_ROOT:-/var/www/ztp}"

echo -e "${YELLOW}Switch:${NC} $SWITCH_NAME"
echo -e "${YELLOW}ZTP Server:${NC} ${ZTP_SERVER:-<not given>}"
echo

# Every switch runs the one unified ztp.sh; it fetches configs/<hostname>-config.sh,
# with <hostname> taken from the switch's DHCP lease.
ZTP_SCRIPT="${ZTP_WEB_ROOT}/scripts/ztp.sh"
if [ ! -f "$ZTP_SCRIPT" ]; then
    echo -e "${RED}❌ Error: ZTP script not found: $ZTP_SCRIPT${NC}"
    echo "   Run setup-ztp-server first."
    exit 1
fi

CONFIG_FILE="${ZTP_WEB_ROOT}/configs/${SWITCH_NAME}-config.sh"
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ Error: Config file not found: $CONFIG_FILE${NC}"
    echo "Available switches:"
    ls -1 "${ZTP_WEB_ROOT}"/configs/*-config.sh 2>/dev/null | xargs -n1 basename | sed 's/-config\.sh$//' | sed 's/^/  /'
    exit 1
fi

echo -e "${GREEN}✓ ZTP script found${NC}"
echo -e "${GREEN}✓ Config file found${NC}"
echo

# Display script URL
SCRIPT_URL="http://${ZTP_SERVER:-<ztp-server-ip>}/scripts/ztp.sh"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}         MANUAL EXECUTION OPTIONS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo
echo -e "${YELLOW}Option 1: SSH to switch and run:${NC}"
echo -e "  ${GREEN}curl ${SCRIPT_URL} | sudo bash${NC}"
echo
echo -e "${YELLOW}Option 2: Download then execute:${NC}"
echo -e "  ${GREEN}wget ${SCRIPT_URL}${NC}"
echo -e "  ${GREEN}sudo bash ztp.sh${NC}"
echo
echo -e "${YELLOW}Option 3: Use SSH from ZTP server (requires sshpass):${NC}"
echo -e "  ${GREEN}read -rs SSHPASS && export SSHPASS${NC}   # switch_ansible_password from secrets.yml"
echo -e "  ${GREEN}sshpass -e ssh cumulus@${SWITCH_NAME} \"curl ${SCRIPT_URL} | sudo bash\"${NC}"
echo
echo -e "${YELLOW}Note:${NC} ztp.sh names the config after the hostname in the switch's DHCP"
echo "      lease and stops if there is none. For a static management address, use"
echo "      push-switch-configs instead."
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo

if [ -z "$ZTP_SERVER" ]; then
    echo -e "${YELLOW}Pass the ZTP server address the switch can reach to run it from here:${NC}"
    echo "  $0 ${SWITCH_NAME} <ztp-server-ip>"
    exit 0
fi

# Ask if user wants to SSH and execute
read -p "Do you want to SSH to the switch and execute now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Check if sshpass is installed
    if ! command -v sshpass &> /dev/null; then
        echo -e "${RED}❌ sshpass not installed${NC}"
        echo "   Install with: sudo apt install sshpass"
        exit 1
    fi
    
    if [ -z "${SSHPASS:-}" ]; then
        read -rsp "Switch password for cumulus@${SWITCH_NAME} (switch_ansible_password): " SSHPASS
        echo
    fi
    if [ -z "${SSHPASS:-}" ]; then
        echo -e "${RED}❌ No switch password given${NC}"
        exit 1
    fi
    export SSHPASS

    echo
    echo -e "${YELLOW}Connecting to ${SWITCH_NAME}...${NC}"
    echo
    
    # Try to SSH and execute
    if sshpass -e ssh -o StrictHostKeyChecking=no \
        cumulus@${SWITCH_NAME} "curl -s ${SCRIPT_URL} | sudo bash" 2>&1; then
        echo
        echo -e "${GREEN}✅ ZTP executed successfully on ${SWITCH_NAME}!${NC}"
    else
        echo
        echo -e "${RED}❌ Failed to execute ZTP on ${SWITCH_NAME}${NC}"
        echo "   Try manual execution using one of the options above"
        exit 1
    fi
else
    echo
    echo -e "${BLUE}Use one of the manual execution options above${NC}"
fi

echo
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✓ Done${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

