#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Detect the correct network interface for dnsmasq ZTP server
# Run this ON the dhcp-oob server

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║        Network Interface Detection for ZTP Server            ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Available Network Interfaces:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
ip addr show | grep -E "^[0-9]+: |inet " | grep -v "127.0.0.1" | while read line; do
    echo "$line"
done
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Interface Summary:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
ip -o addr show | awk '/inet / && !/127.0.0.1/ {print $2, $4}' | while read iface ip; do
    state=$(ip link show "$iface" | grep -oP "state \K\w+")
    printf "%-15s %-20s %s\n" "$iface" "$ip" "[$state]"
done
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Default Route:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
default_iface=$(ip route | grep default | awk '{print $5}')
default_gw=$(ip route | grep default | awk '{print $3}')
echo "Interface: $default_iface"
echo "Gateway:   $default_gw"
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 RECOMMENDATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "For ZTP server, use the interface where switches/servers connect."
echo
echo "If you're serving DHCP to the same network as your default route:"
echo "  → Use interface: $default_iface"
echo
echo "If you have a separate management/provisioning network:"
echo "  → Use that dedicated interface (check IPs above)"
echo
echo "Update in: inventories/group_vars/all/ztp.yml"
echo "  dnsmasq_interface: \"$default_iface\"  # or your chosen interface"
echo

