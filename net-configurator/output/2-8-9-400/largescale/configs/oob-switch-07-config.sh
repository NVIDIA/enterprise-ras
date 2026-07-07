#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# NVUE CLI Configuration for oob-switch-07
# Generated: 2026-07-03T00:13:08Z
# Format: NVUE CLI commands

#============================================================================
# Bridge and VLAN
#============================================================================
nv set bridge domain br_default vlan 200 vni 4200

#============================================================================
# EVPN
#============================================================================
nv set evpn state enabled
nv set evpn multihoming state enabled

#============================================================================
# Management Interface
#============================================================================
nv set interface eth0 type eth
nv set interface eth0 vrf mgmt

#============================================================================
# Loopback
#============================================================================
nv set interface lo ipv4 address 172.16.176.107/32
nv set interface lo type loopback

#============================================================================
# Access Ports (1G, VLAN 200)
#============================================================================
nv set interface swp1-48 bridge domain br_default access 200
nv set interface swp1-48 link speed 1G
nv set interface swp1-48,swp49 type swp

#============================================================================
# VLAN SVI
#============================================================================
nv set interface vlan200 ipv4 address 192.168.200.8/24
nv set interface vlan200 ipv4 vrr address 192.168.200.1/24
nv set interface vlan200 ipv4 vrr state enabled
nv set interface vlan200 ipv4 vrr vrr-state up
nv set interface vlan200 vrf OOB
nv set interface vlan200 type svi
nv set interface vlan200 vlan 200

#============================================================================
# NVE / VXLAN
#============================================================================
nv set nve vxlan arp-nd-suppress enabled
nv set nve vxlan state enabled
nv set nve vxlan flooding state enabled
nv set nve vxlan flooding head-end-replication evpn
nv set nve vxlan source address 172.16.176.107

#============================================================================
# Router / BGP global
#============================================================================
nv set router bfd state enabled
nv set router bfd profile default detect-multiplier 3
nv set router bfd profile default min-rx-interval 300
nv set router bfd profile default min-tx-interval 300
nv set router bfd profile overlay detect-multiplier 3
nv set router bfd profile overlay min-rx-interval 1000
nv set router bfd profile overlay min-tx-interval 1000
nv set router bgp autonomous-system 4260394795
nv set router bgp state enabled
nv set router bgp router-id 172.16.176.107
nv set router policy route-map LOOPBACK_BGP rule 10 action permit
nv set router policy route-map LOOPBACK_BGP rule 10 match interface lo
nv set router policy route-map LOOPBACK_BGP rule 10 match type ipv4
nv set router policy route-map WEIGHTED_ECMP rule 10 action permit
nv set router policy route-map WEIGHTED_ECMP rule 10 set ext-community-bw multipaths
nv set router vrr state enabled

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
nv set system hostname oob-switch-07
nv set system message pre-login '##############################################################################
#      You are accessing an Information System (IS) that is provided for authorized use only.
##############################################################################'
nv set system message post-login '####################################################################
#       You are successfully logged in to: oob-switch-07 - site: largescale / arch: 2-8-9-400
####################################################################'
nv set system ssh-server state enabled
nv set system date-time timezone Etc/Zulu
nv set system wjh channel forwarding trigger l2
nv set system wjh channel forwarding trigger l3
nv set system wjh channel forwarding trigger tunnel
nv set system wjh state enabled

#============================================================================
# VRF OOB
#============================================================================
nv set vrf OOB evpn state enabled
nv set vrf OOB evpn vlan 3001
nv set vrf OOB evpn vni 5001
nv set vrf OOB loopback ip address 172.16.176.127/32
nv set vrf OOB router bgp address-family ipv4-unicast state enabled
nv set vrf OOB router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf OOB router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf OOB router bgp address-family l2vpn-evpn state enabled
nv set vrf OOB router bgp autonomous-system 4260394795
nv set vrf OOB router bgp state enabled
nv set vrf OOB router bgp router-id 172.16.176.127

#============================================================================
# Default VRF BGP
#============================================================================
nv set vrf default router bgp address-family ipv4-unicast state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected route-map LOOPBACK_BGP
nv set vrf default router bgp address-family l2vpn-evpn state enabled
nv set vrf default router bgp state enabled

# Overlay peers — numbered EVPN to CSL loopbacks
nv set vrf default router bgp neighbor 172.16.176.11 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.11 type numbered
nv set vrf default router bgp neighbor 172.16.176.12 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.12 type numbered

# Underlay peers — unnumbered eBGP to CSLs
nv set vrf default router bgp neighbor swp49 peer-group underlay
nv set vrf default router bgp neighbor swp49 type unnumbered

nv set vrf default router bgp path-selection multipath aspath-ignore enabled

# Peer-group: overlay
nv set vrf default router bgp peer-group overlay address-family ipv4-unicast state disabled
nv set vrf default router bgp peer-group overlay address-family l2vpn-evpn state enabled
nv set vrf default router bgp peer-group overlay bfd profile overlay
nv set vrf default router bgp peer-group overlay multihop-ttl 2
nv set vrf default router bgp peer-group overlay remote-as external
nv set vrf default router bgp peer-group overlay update-source lo

# Peer-group: underlay
nv set vrf default router bgp peer-group underlay address-family ipv4-unicast state enabled
nv set vrf default router bgp peer-group underlay address-family ipv4-unicast policy outbound route-map WEIGHTED_ECMP
nv set vrf default router bgp peer-group underlay bfd profile default
nv set vrf default router bgp peer-group underlay remote-as external

