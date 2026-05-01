#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# NVUE CLI Configuration for oob-switch-03
# Generated: 2026-04-22T18:42:28Z
# Format: NVUE CLI commands

#============================================================================
# Bridge and VLAN
#============================================================================
nv set bridge domain br_default vlan 200

#============================================================================
# Management Interface
#============================================================================
nv set interface eth0 type eth
nv set interface eth0 vrf mgmt

#============================================================================
# Access Ports (1G, VLAN 200)
#============================================================================
nv set interface swp1-46 bridge domain br_default access 200
nv set interface swp1-46 link speed 1G
nv set interface swp1-46,swp49,swp50,swp51,swp52 type swp

#============================================================================
# Spine Bond (L2 uplink to core)
#============================================================================
nv set interface spine_bond bond member swp49,swp50,swp51,swp52
nv set interface spine_bond type bond
nv set interface spine_bond bridge domain br_default access 200
nv set interface spine_bond link state down
nv set interface swp49,swp50,swp51,swp52 link state down

#============================================================================
# VLAN SVI
#============================================================================
nv set interface vlan200 ipv4 address 192.168.200.4/24
nv set interface vlan200 type svi
nv set interface vlan200 vlan 200

#============================================================================
# NTP (servers from Settings ntp_servers comma-separated, or default)
#============================================================================
nv set system ntp server 0.cumulusnetworks.pool.ntp.org
nv set system ntp server 1.cumulusnetworks.pool.ntp.org
nv set system ntp server 2.cumulusnetworks.pool.ntp.org
nv set system ntp server 3.cumulusnetworks.pool.ntp.org

#============================================================================
# AAA
#============================================================================
nv set system aaa class nvapply action allow
nv set system aaa class nvapply command-path / permission all
nv set system aaa class nvshow action allow
nv set system aaa class nvshow command-path / permission ro
nv set system aaa class sudo action allow
nv set system aaa class sudo command-path / permission all
nv set system aaa role nvue-admin class nvapply
nv set system aaa role nvue-monitor class nvshow
nv set system aaa role system-admin class nvapply
nv set system aaa role system-admin class sudo
nv set system aaa user cumulus full-name cumulus,,,
nv set system aaa user cumulus role system-admin

#============================================================================
# System
#============================================================================
nv set system api state enabled
nv set system config auto-save state enabled
nv set system control-plane acl acl-default-dos inbound
nv set system control-plane acl acl-default-whitelist inbound
nv set system hostname oob-switch-03
nv set system message post-login '#####################################################################################
#                     You are successfully logged in to: oob-switch-03              #
#####################################################################################
'
nv set system message pre-login '#####################################################################################
#  Welcome to NVIDIA Cumulus VX (TM)                                                #
#  NVIDIA Cumulus VX (TM) is a community supported virtual appliance designed       #
#  for experiencing, testing and prototyping NVIDIA Cumulus'"'"' latest technology. #
#  For any questions or technical support, visit our community site at:             #
#  https://www.nvidia.com/en-us/support                                             #
#####################################################################################
'
nv set system ssh-server state enabled
nv set system date-time timezone Etc/Zulu
nv set system wjh channel forwarding trigger l2
nv set system wjh channel forwarding trigger l3
nv set system wjh channel forwarding trigger tunnel
nv set system wjh state enabled

#============================================================================
# Default Route
#============================================================================
nv set vrf default router static 0.0.0.0/0 address-family ipv4-unicast
nv set vrf default router static 0.0.0.0/0 via 192.168.200.1 type ipv4-address

