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
#   ./manual-ztp.sh core-01
#   ./manual-ztp.sh oob-switch-02 192.168.200.1

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
    echo "  $0 core-01"
    echo "  $0 oob-switch-02 192.168.200.1"
    echo
    exit 1
fi

SWITCH_NAME="$1"
ZTP_SERVER="${2:-localhost}"

echo -e "${YELLOW}Switch:${NC} $SWITCH_NAME"
echo -e "${YELLOW}ZTP Server:${NC} $ZTP_SERVER"
echo

# Check if ZTP script exists
ZTP_SCRIPT="/var/www/html/ztp/scripts/${SWITCH_NAME}.sh"
if [ ! -f "$ZTP_SCRIPT" ]; then
    echo -e "${RED}❌ Error: ZTP script not found: $ZTP_SCRIPT${NC}"
    echo "Available switches:"
    ls -1 /var/www/html/ztp/scripts/*.sh 2>/dev/null | xargs -n1 basename | sed 's/\.sh$//' | sed 's/^/  /'
    exit 1
fi

# Check if config exists
CONFIG_FILE="/var/www/html/ztp/configs/${SWITCH_NAME}.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}⚠  Warning: Config file not found: $CONFIG_FILE${NC}"
    echo "   The ZTP script may still work, but configuration won't be applied."
    echo
fi

echo -e "${GREEN}✓ ZTP script found${NC}"
if [ -f "$CONFIG_FILE" ]; then
    echo -e "${GREEN}✓ Config file found${NC}"
fi
echo

# Display script URL
SCRIPT_URL="http://${ZTP_SERVER}/scripts/${SWITCH_NAME}.sh"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}         MANUAL EXECUTION OPTIONS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo
echo -e "${YELLOW}Option 1: SSH to switch and run:${NC}"
echo -e "  ${GREEN}curl ${SCRIPT_URL} | bash${NC}"
echo
echo -e "${YELLOW}Option 2: Download then execute:${NC}"
echo -e "  ${GREEN}wget ${SCRIPT_URL}${NC}"
echo -e "  ${GREEN}bash ${SWITCH_NAME}.sh${NC}"
echo
echo -e "${YELLOW}Option 3: Use SSH from ZTP server (requires sshpass):${NC}"
echo -e "  ${GREEN}sshpass -p 'Cumu1usLinux!' ssh cumulus@${SWITCH_NAME} \"curl ${SCRIPT_URL} | bash\"${NC}"
echo
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo

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
    
    echo
    echo -e "${YELLOW}Connecting to ${SWITCH_NAME}...${NC}"
    echo
    
    # Try to SSH and execute
    if sshpass -p 'Cumu1usLinux!' ssh -o StrictHostKeyChecking=no \
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

