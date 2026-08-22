#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Per-server validation probe (SINGLE-SESSION). Runs ON the jump, opens ONE
# `ssh 'bash -s'` session to the server and runs the whole gather + gateway/OOB/
# internet ping sequence REMOTELY, returning the RESULT|/---RAW:--- block — 1
# connection instead of ~8. Byte-compatible with the serial collector.
#
# Args:  $1 IP   $2 PW   $3 NAME   $4 SRC_IP   $5 EXPECTED_GW   $6 ROLE

IP="$1"; PW="$2"; NAME="$3"; SRC_IP="$4"; EXPECTED_GW="$5"; ROLE="${6:-unknown}"; SSH_USER="${7:-ubuntu}"
export SSHPASS="$PW"
OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

# One session: stream the collection (quoted heredoc runs verbatim on the
# server; NAME/SRC_IP/EXPECTED_GW/ROLE/HOST arrive as $1..$5).
OUT=$(timeout 90 sshpass -e ssh $OPTS "${SSH_USER}@${IP}" "bash -s -- '${NAME}' '${SRC_IP}' '${EXPECTED_GW}' '${ROLE}' '${IP}'" <<'REMOTE'
NAME="$1"; SRC_IP="$2"; EXPECTED_GW="$3"; ROLE="$4"; HOST="$5"

HOSTNAME=$(hostname 2>/dev/null)
ETH0_IP=$(ip -4 addr show eth0 2>/dev/null | grep -oP 'inet \K[0-9./]+')
ALL_IPS=$(ip -4 -br addr show 2>/dev/null | grep -v '127.0.0' | awk '{printf "%s=%s ", $1, $3}')
BOND_MODE=$(cat /proc/net/bonding/bond0 2>/dev/null | grep "Bonding Mode" | sed "s/.*: //")
BOND_ACTIVE=$(cat /proc/net/bonding/bond0 2>/dev/null | grep "Currently Active" | sed "s/.*: //")
VLAN_IFACES=$(ip -br link show type vlan 2>/dev/null | awk '{print $1}' | tr '\n' ',' | sed 's/,$//')
LLDPD=$(systemctl is-active lldpd 2>/dev/null)

GW_PING="SKIP"; PING_RESULT=""
if [ -n "$EXPECTED_GW" ] && [ -n "$SRC_IP" ]; then
  for _attempt in 1 2 3; do
    IFACE=$(ip -o route get "$EXPECTED_GW" from "$SRC_IP" 2>/dev/null | grep -oP 'dev \K\S+' | head -1)
    ping -c 1 -W 10 "$EXPECTED_GW" -I "$SRC_IP" >/dev/null 2>&1
    sudo -n ip neigh del "$EXPECTED_GW" dev "$IFACE" 2>/dev/null || true
    PING_RESULT=$(ping -c 2 -W 5 "$EXPECTED_GW" -I "$SRC_IP" 2>&1)
    if printf '%s' "$PING_RESULT" | grep -q "bytes from"; then GW_PING="PASS"; break; fi
    GW_PING="FAIL"
    [ "$_attempt" -lt 3 ] && sleep 10
  done
fi

OOB_PING="SKIP"; OOB_RESULT=""
if [ -n "$ETH0_IP" ]; then
  ping -c 1 -W 3 192.168.200.1 -I eth0 >/dev/null 2>&1
  OOB_RESULT=$(ping -c 2 -W 5 192.168.200.1 -I eth0 2>&1)
  if printf '%s' "$OOB_RESULT" | grep -q "bytes from"; then OOB_PING="PASS"; else OOB_PING="FAIL"; fi
fi

INET_PING="SKIP"; INET_RESULT=""
if [ "$OOB_PING" = "PASS" ]; then
  ping -c 1 -W 3 8.8.8.8 -I eth0 >/dev/null 2>&1
  INET_RESULT=$(ping -c 2 -W 5 8.8.8.8 -I eth0 2>&1)
  if printf '%s' "$INET_RESULT" | grep -q "bytes from"; then INET_PING="PASS"; else INET_PING="FAIL"; fi
fi

echo "RESULT|$NAME|OK|$HOST|$HOSTNAME|$ETH0_IP|$BOND_MODE|$BOND_ACTIVE|$VLAN_IFACES|$LLDPD|$GW_PING|$OOB_PING|$INET_PING|$ROLE|$ALL_IPS"
echo "---RAW:ip_brief---"; ip -br a 2>/dev/null
echo "---RAW:ip_full---"; ip -4 a 2>/dev/null
echo "---RAW:routes---"; ip route show table all 2>/dev/null
echo "---RAW:bond---"; for f in /proc/net/bonding/*; do [ -e "$f" ] && echo "=== $f ===" && cat "$f" 2>/dev/null; done
echo "---RAW:lldp---"; command -v lldpctl >/dev/null 2>&1 && lldpctl 2>/dev/null || echo "(lldpctl not installed)"
echo "---RAW:ping_gw---"; echo "${PING_RESULT:-(not run - no source IP or no gateway)}"
echo "---RAW:ping_oob---"; echo "${OOB_RESULT:-(not run - no eth0 IP)}"
echo "---RAW:ping_inet---"; echo "${INET_RESULT:-(not run - OOB ping did not pass)}"
REMOTE
)

if ! printf '%s' "$OUT" | grep -q '^RESULT|'; then
  echo "RESULT|$NAME|UNREACHABLE|$IP||||||||"
  exit 0
fi
printf '%s\n' "$OUT"
