#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# ZTP per-switch collection probe (SINGLE-SESSION). Runs ON the jump, opens ONE
# `ssh 'bash -s'` session to the switch, runs the whole collection + counts +
# awk REMOTELY, and returns the RESULT|/---RAW:--- block — 1 connection instead
# of ~19. Output is byte-compatible with the serial collector.
#
# Args:  $1 = switch mgmt IP   $2 = ssh/sudo password   $3 = BGP-capable (1/0)

IP="$1"; PW="$2"; BGP="${3:-0}"
export SSHPASS="$PW"
OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=8 -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

# One session: stream the collection script (quoted heredoc -> runs verbatim on
# the switch; BGP arrives as $1). `nv show` works as the cumulus user (no sudo).
OUT=$(timeout 90 sshpass -e ssh $OPTS "cumulus@${IP}" "bash -s -- '${BGP}'" <<'REMOTE'
BGP="${1:-0}"
hostname=$(hostname 2>/dev/null)
version=$(grep DISTRIB_RELEASE /etc/lsb-release 2>/dev/null | cut -d= -f2)
nvue_exists=$(test -f /etc/nvue.d/startup.yaml && echo yes || echo no)
bridge_output=$(nv show bridge domain 2>/dev/null || echo "N/A")
bridges=$(printf '%s\n' "$bridge_output" | grep -v '^$' | tail -n +3 | wc -l)
iface_output=$(nv show interface brief 2>/dev/null || echo "N/A")
interfaces_up=$(printf '%s\n' "$iface_output" | awk 'NR>2 && $3=="up"{c++} END{print c+0}')
system_output=$(nv show system 2>/dev/null || echo "N/A")
platform_output=$(nv show platform 2>/dev/null || echo "N/A")
vrf_output=$(nv show vrf 2>/dev/null || echo "N/A")
ntp_output=$(nv show service ntp 2>/dev/null || echo "N/A")
lldp_output=$(nv show interface --view=lldp 2>/dev/null || echo "N/A")
running_config=$(nv config show 2>/dev/null || echo "N/A")
bgp_fields=""
if [ "$BGP" = "1" ]; then
  bgp_output=$(nv show vrf default router bgp 2>/dev/null || echo "N/A")
  bgp_enabled=$(printf '%s\n' "$bgp_output" | awk '/^state/{print $2}')
  bgp_configured=$(printf '%s\n' "$bgp_output" | awk '/^configured-neighbors/{print $2}')
  bgp_established=$(printf '%s\n' "$bgp_output" | awk '/^established-neighbors/{print $2}')
  evpn_output=$(nv show evpn 2>/dev/null || echo "N/A")
  evpn_l2vni=$(nv show evpn --output json 2>/dev/null | jq -r '."l2vni-count" // 0' 2>/dev/null || echo "0")
  evpn_l3vni=$(nv show evpn --output json 2>/dev/null | jq -r '."l3vni-count" // 0' 2>/dev/null || echo "0")
  bgp_neighbor_output=$(nv show vrf default router bgp neighbor 2>/dev/null || echo "N/A")
  evpn_vni_output=$(nv show evpn vni 2>/dev/null || echo "N/A")
  qos_roce_output=$(nv show qos roce 2>/dev/null || echo "N/A")
  bgp_down_neighbors=$(printf '%s\n' "$bgp_neighbor_output" | awk -v ifaces="$iface_output" '
    BEGIN {
      n = split(ifaces, lines, "\n")
      for (i = 1; i <= n; i++) { split(lines[i], f, /[[:space:]]+/); if (f[1] ~ /^swp/) port_state[f[1]] = f[3] }
    }
    /^[-]+[[:space:]]+[-]+/ { started=1; next }
    started {
      state = ""
      if ($4 ~ /^(established|idle|active|connect|opensent|openconfirm)$/) state = $4
      else if ($2 ~ /^(established|idle|active|connect|opensent|openconfirm)$/) state = $2
      if (state != "" && state != "established") { link = (port_state[$1] != "" ? port_state[$1] : "unknown"); if (out != "") out = out ","; out = out $1 ":" link }
    }
    END { print out }')
  bgp_fields="|$bgp_enabled|$bgp_configured|$bgp_established|$evpn_l2vni|$evpn_l3vni|$bgp_down_neighbors"
fi
echo "RESULT|SUCCESS|$hostname|$version|$nvue_exists|$bridges|$interfaces_up$bgp_fields"
echo "---RAW:system---"; echo "$system_output"
echo "---RAW:platform---"; echo "$platform_output"
echo "---RAW:bridge_domain---"; echo "$bridge_output"
echo "---RAW:interface_brief---"; echo "$iface_output"
echo "---RAW:vrf---"; echo "$vrf_output"
echo "---RAW:ntp---"; echo "$ntp_output"
echo "---RAW:lldp---"; echo "$lldp_output"
if [ "$BGP" = "1" ]; then
  echo "---RAW:bgp---"; echo "$bgp_output"
  echo "---RAW:bgp_neighbor---"; echo "$bgp_neighbor_output"
  echo "---RAW:evpn---"; echo "$evpn_output"
  echo "---RAW:evpn_vni---"; echo "$evpn_vni_output"
  echo "---RAW:qos_roce---"; echo "$qos_roce_output"
fi
echo "---RAW:running_config---"; echo "$running_config"
REMOTE
)

# Unreachable / failed session -> no RESULT line came back.
if ! printf '%s' "$OUT" | grep -q '^RESULT|'; then
  echo "RESULT|FAILED||||0|0"
  exit 0
fi
printf '%s\n' "$OUT"
