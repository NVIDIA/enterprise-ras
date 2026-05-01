#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Debug dnsmasq startup issues
# Run this ON the dhcp-oob server

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║           dnsmasq Troubleshooting Script                     ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Checking dnsmasq service status..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sudo systemctl status dnsmasq --no-pager
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Recent dnsmasq logs (last 30 lines)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sudo journalctl -u dnsmasq -n 30 --no-pager
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. Checking port 53 (DNS) usage..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sudo netstat -tulpn | grep :53 || sudo ss -tulpn | grep :53
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Checking systemd-resolved status..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sudo systemctl status systemd-resolved --no-pager || echo "systemd-resolved not running (good!)"
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. Testing dnsmasq configuration..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
sudo dnsmasq --test
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6. Checking network interfaces..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ip addr show | grep -E "^[0-9]+:|inet " | head -20
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7. Checking dnsmasq configuration files..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Main config:"
if [ -f /etc/dnsmasq.conf ]; then
    echo "✓ /etc/dnsmasq.conf exists"
    echo "Key settings:"
    grep -v "^#\|^$" /etc/dnsmasq.conf | head -20
else
    echo "✗ /etc/dnsmasq.conf missing!"
fi
echo
echo "ZTP config:"
if [ -f /etc/dnsmasq.d/ztp.conf ]; then
    echo "✓ /etc/dnsmasq.d/ztp.conf exists"
    cat /etc/dnsmasq.d/ztp.conf
else
    echo "✗ /etc/dnsmasq.d/ztp.conf missing!"
fi
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 COMMON FIXES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "If port 53 is in use by systemd-resolved:"
echo "  sudo systemctl stop systemd-resolved"
echo "  sudo systemctl disable systemd-resolved"
echo "  sudo systemctl start dnsmasq"
echo
echo "If interface name is wrong (check 'interface=' in config):"
echo "  sudo vim /etc/dnsmasq.conf"
echo "  # Change interface= to match your actual interface (shown above)"
echo "  sudo systemctl restart dnsmasq"
echo
echo "If config has syntax errors:"
echo "  sudo dnsmasq --test"
echo "  # Fix any reported errors"
echo "  sudo systemctl restart dnsmasq"
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

