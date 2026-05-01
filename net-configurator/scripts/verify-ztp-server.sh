#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# ZTP Server Verification Script
# Run this ON THE ZTP SERVER to verify configuration

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ZTP SERVER VERIFICATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -e "\n1. Checking dnsmasq service status..."
if systemctl is-active --quiet dnsmasq; then
    echo "✓ dnsmasq is running"
else
    echo "✗ dnsmasq is NOT running!"
    echo "  Start with: sudo systemctl start dnsmasq"
    exit 1
fi

echo -e "\n2. Checking dnsmasq configuration files..."
if [ -f /etc/dnsmasq.conf ]; then
    echo "✓ /etc/dnsmasq.conf exists"
else
    echo "✗ /etc/dnsmasq.conf NOT found!"
fi

if [ -f /etc/dnsmasq.d/ztp.conf ]; then
    echo "✓ /etc/dnsmasq.d/ztp.conf exists"
else
    echo "✗ /etc/dnsmasq.d/ztp.conf NOT found!"
fi

echo -e "\n3. Checking switch-specific DHCP entries..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -f /etc/dnsmasq.d/ztp.conf ]; then
    grep "^dhcp-host=" /etc/dnsmasq.d/ztp.conf | while read line; do
        # Extract MAC, hostname, IP
        MAC=$(echo "$line" | cut -d'=' -f2 | cut -d',' -f1)
        HOSTNAME=$(echo "$line" | cut -d',' -f2)
        IP=$(echo "$line" | cut -d',' -f3)
        
        echo "Switch: $HOSTNAME"
        echo "  MAC: $MAC"
        echo "  IP: $IP"
        
        # Check if config file exists
        if [ -f "/var/www/ztp/configs/${HOSTNAME}.yaml" ]; then
            echo "  Config: ✓ /var/www/ztp/configs/${HOSTNAME}.yaml"
        else
            echo "  Config: ✗ MISSING /var/www/ztp/configs/${HOSTNAME}.yaml"
        fi
        echo ""
    done
else
    echo "✗ Cannot check - ztp.conf not found"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Checking ZTP directories..."
for dir in /var/www/ztp /var/www/ztp/scripts /var/www/ztp/configs; do
    if [ -d "$dir" ]; then
        echo "✓ $dir exists"
    else
        echo "✗ $dir NOT found!"
    fi
done

echo -e "\n5. Checking ZTP script..."
if [ -f /var/www/ztp/scripts/ztp.sh ]; then
    echo "✓ /var/www/ztp/scripts/ztp.sh exists"
    if head -1 /var/www/ztp/scripts/ztp.sh | grep -q "CUMULUS-AUTOPROVISIONING"; then
        echo "✓ ZTP script has correct marker"
    else
        echo "✗ ZTP script missing CUMULUS-AUTOPROVISIONING marker!"
    fi
else
    echo "✗ /var/www/ztp/scripts/ztp.sh NOT found!"
fi

echo -e "\n6. Checking nginx service..."
if systemctl is-active --quiet nginx; then
    echo "✓ nginx is running"
else
    echo "✗ nginx is NOT running!"
    echo "  Start with: sudo systemctl start nginx"
fi

echo -e "\n7. Checking config files in /var/www/ztp/configs/..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -d /var/www/ztp/configs ]; then
    CONFIG_COUNT=$(ls -1 /var/www/ztp/configs/*.yaml 2>/dev/null | wc -l)
    if [ $CONFIG_COUNT -gt 0 ]; then
        echo "✓ Found $CONFIG_COUNT config files:"
        ls -lh /var/www/ztp/configs/*.yaml | awk '{print "  - " $9 " (" $5 ")"}'
    else
        echo "✗ NO config files found in /var/www/ztp/configs/"
        echo ""
        echo "  Generate configs with:"
        echo "    make generate"
        echo "    make ztp-setup"
    fi
else
    echo "✗ /var/www/ztp/configs/ directory NOT found!"
fi

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8. Checking DHCP options for ZTP..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -f /etc/dnsmasq.d/ztp.conf ]; then
    echo "DHCP option 239 (cumulus-provision-url):"
    grep "dhcp-option=239" /etc/dnsmasq.d/ztp.conf || echo "  (not found)"
    echo ""
    echo "DHCP option 66 (default-url for ONIE):"
    grep "dhcp-option=66" /etc/dnsmasq.d/ztp.conf || echo "  (not configured)"
fi

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "9. Testing HTTP access to ZTP resources..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "Testing from server IP: ${SERVER_IP}"
echo ""

# Test ZTP script
if curl --connect-timeout 2 -I "http://localhost/scripts/ztp.sh" 2>/dev/null | grep -q "200 OK"; then
    echo "✓ ZTP script accessible via HTTP"
else
    echo "✗ ZTP script NOT accessible via HTTP"
fi

# Test a config file (if any exist)
FIRST_CONFIG=$(ls -1 /var/www/ztp/configs/*.yaml 2>/dev/null | head -1)
if [ -n "$FIRST_CONFIG" ]; then
    CONFIG_NAME=$(basename "$FIRST_CONFIG")
    if curl --connect-timeout 2 -I "http://localhost/configs/${CONFIG_NAME}" 2>/dev/null | grep -q "200 OK"; then
        echo "✓ Config files accessible via HTTP (tested: ${CONFIG_NAME})"
    else
        echo "✗ Config files NOT accessible via HTTP"
    fi
fi

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "10. Checking dnsmasq logs (last 20 lines)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -f /var/log/dnsmasq.log ]; then
    tail -20 /var/log/dnsmasq.log
else
    echo "(no dnsmasq.log found - check systemd journal)"
    echo "Run: sudo journalctl -u dnsmasq -n 20"
fi

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "For a switch to successfully ZTP:"
echo "  1. dnsmasq must be running and configured with MAC→hostname mapping"
echo "  2. Config file must exist: /var/www/ztp/configs/{hostname}.yaml"
echo "  3. nginx must be serving files from /var/www/ztp/"
echo "  4. Switch must receive hostname via DHCP option 12"
echo ""
echo "If switches aren't getting hostnames:"
echo "  - Check dnsmasq logs: sudo journalctl -u dnsmasq -f"
echo "  - Verify MAC addresses match: cat /etc/dnsmasq.d/ztp.conf"
echo "  - Test DHCP: sudo tcpdump -i <interface> port 67 or port 68"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

