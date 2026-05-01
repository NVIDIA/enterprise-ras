#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# ZTP Hostname Debug Script
# Run this ON THE SWITCH during ZTP to see what's happening

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ZTP HOSTNAME DEBUG"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -e "\n1. Checking DHCP lease file..."
if [ -f /var/lib/dhcp/dhclient.eth0.leases ]; then
    echo "✓ DHCP lease file exists"
    echo ""
    cat /var/lib/dhcp/dhclient.eth0.leases
else
    echo "✗ DHCP lease file NOT found!"
fi

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Extracting hostname from DHCP..."
hostname=$(awk '/option host-name/ {name = $3} END {print name}' /var/lib/dhcp/dhclient.eth0.leases | tr -d '";')
if [ -n "$hostname" ]; then
    echo "✓ Hostname found: ${hostname}"
else
    echo "✗ Hostname NOT found in DHCP leases!"
    echo ""
    echo "Checking for 'option host-name' lines:"
    grep "option host-name" /var/lib/dhcp/dhclient.eth0.leases || echo "  (none found)"
fi

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. Extracting PROVISION_URL from DHCP..."
PROVISION_URL=$(cat /var/lib/dhcp/dhclient.eth0.leases | grep 'cumulus-provision-url' | tail -1 | awk -F "/" '{print $3}')
if [ -n "$PROVISION_URL" ]; then
    echo "✓ Provision URL found: ${PROVISION_URL}"
else
    echo "✗ Provision URL NOT found!"
    echo ""
    echo "Checking for 'cumulus-provision-url' lines:"
    grep "cumulus-provision-url" /var/lib/dhcp/dhclient.eth0.leases || echo "  (none found)"
fi

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Constructing config URL..."
if [ -n "$hostname" ] && [ -n "$PROVISION_URL" ]; then
    CONFIG_URL="http://${PROVISION_URL}/configs/${hostname}.yaml"
    echo "✓ Config URL: ${CONFIG_URL}"
    echo ""
    echo "Testing connectivity..."
    if curl --connect-timeout 5 --head --silent "${CONFIG_URL}" > /dev/null; then
        echo "  ✓ Config file is reachable!"
    else
        echo "  ✗ Config file is NOT reachable"
        echo "  Try: curl -I ${CONFIG_URL}"
    fi
else
    echo "✗ Cannot construct config URL (missing hostname or provision URL)"
fi

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. Checking current hostname..."
echo "  /etc/hostname: $(cat /etc/hostname 2>/dev/null || echo 'not set')"
echo "  hostname command: $(hostname)"

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6. Checking MAC address..."
MAC=$(ip link show eth0 | awk '/ether/ {print $2}')
echo "  eth0 MAC: ${MAC}"

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7. Testing ZTP server connectivity..."
if [ -n "$PROVISION_URL" ]; then
    echo "  Pinging ${PROVISION_URL}..."
    if ping -c 2 "${PROVISION_URL}" > /dev/null 2>&1; then
        echo "  ✓ ZTP server is reachable"
    else
        echo "  ✗ ZTP server is NOT reachable"
    fi
    
    echo ""
    echo "  Testing HTTP access..."
    if curl --connect-timeout 5 "http://${PROVISION_URL}/scripts/ztp.sh" | head -1 | grep -q "CUMULUS-AUTOPROVISIONING"; then
        echo "  ✓ ZTP script is accessible"
    else
        echo "  ✗ ZTP script is NOT accessible"
    fi
else
    echo "  Cannot test (PROVISION_URL not found)"
fi

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8. Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Expected workflow:"
echo "    1. DHCP assigns IP + sends hostname via option 12"
echo "    2. ZTP script extracts hostname from lease file"
echo "    3. ZTP script downloads http://\${PROVISION_URL}/configs/\${hostname}.yaml"
echo "    4. ZTP script applies config"
echo ""
if [ -n "$hostname" ] && [ -n "$PROVISION_URL" ]; then
    echo "  ✓ Hostname and Provision URL extracted successfully"
    echo "  Expected config file: http://${PROVISION_URL}/configs/${hostname}.yaml"
else
    echo "  ✗ PROBLEM: Missing hostname or provision URL from DHCP"
    echo ""
    echo "  Troubleshooting steps:"
    echo "    1. Check dnsmasq config on ZTP server:"
    echo "       ssh <ztp-server> 'cat /etc/dnsmasq.d/ztp.conf | grep \"${MAC}\"'"
    echo ""
    echo "    2. Check dnsmasq is running:"
    echo "       ssh <ztp-server> 'sudo systemctl status dnsmasq'"
    echo ""
    echo "    3. Check dnsmasq logs:"
    echo "       ssh <ztp-server> 'sudo tail -50 /var/log/dnsmasq.log'"
    echo ""
    echo "    4. Verify config file exists on ZTP server:"
    echo "       ssh <ztp-server> 'ls -la /var/www/ztp/configs/'"
fi

echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

