#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# NVUE CLI Configuration for gsl-plane1-02
# Generated: 2026-09-02T02:44:28Z
# Format: NVUE CLI commands (GSL - GPU Spine/Leaf, plane 1)
#============================================================================
# Bridge and VLAN
#============================================================================
nv set bridge domain br_default type vlan-aware
nv set bridge domain br_default vlan 901 vni 4901
nv set bridge domain br_default vlan 902 vni 4902
nv set bridge domain br_default vlan 903 vni 4903
nv set bridge domain br_default vlan 904 vni 4904
nv set bridge domain br_default vlan 905 vni 4905
nv set bridge domain br_default vlan 906 vni 4906
nv set bridge domain br_default vlan 907 vni 4907
nv set bridge domain br_default vlan 908 vni 4908

#============================================================================
# EVPN
#============================================================================
nv set evpn state enabled
nv set evpn route-advertise svi-ip enabled

#============================================================================
# Interfaces - eth0 (mgmt), loopback, breakout, GPU access ports, SVI
#============================================================================
nv set interface eth0 type eth
nv set interface eth0 vrf mgmt

nv set interface lo ipv4 address 10.1.1.2/32
nv set interface lo type loopback

# 2x breakout on GPU access ports + ISL ports
nv set interface swp1,swp2,swp3,swp4,swp5,swp6,swp7,swp8,swp9,swp10,swp11,swp12,swp13,swp14,swp15,swp16,swp33,swp34,swp35,swp36,swp37,swp38,swp39,swp40,swp41,swp42,swp43,swp44,swp45,swp46,swp47,swp48 link breakout 2x

nv set interface swp17,swp18,swp19,swp20,swp21,swp22,swp23,swp24,swp25,swp26,swp27,swp28,swp29,swp30,swp31,swp32,swp49,swp50,swp51,swp52,swp53,swp54,swp55,swp56,swp57,swp58,swp59,swp60,swp61,swp62,swp63,swp64,swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1 type swp

# GPU access ports per rail - gpu_vlan_mode = per_rail
nv set interface swp1s0,swp3s0,swp5s0,swp7s0,swp9s0,swp11s0,swp13s0,swp15s0 bridge domain br_default access 902
# vlan902 SVI (rail2)
nv set interface vlan902 ipv4 address 192.168.2.3/24
nv set interface vlan902 vrf GPU
nv set interface vlan902 ipv4 vrr address 192.168.2.1/24
nv set interface vlan902 ipv4 vrr state enabled
nv set interface vlan902 ipv4 vrr vrr-state up
nv set interface vlan902 type svi
nv set interface vlan902 vlan 902
nv set interface swp1s1,swp3s1,swp5s1,swp7s1,swp9s1,swp11s1,swp13s1,swp15s1 bridge domain br_default access 904
# vlan904 SVI (rail4)
nv set interface vlan904 ipv4 address 192.168.4.3/24
nv set interface vlan904 vrf GPU
nv set interface vlan904 ipv4 vrr address 192.168.4.1/24
nv set interface vlan904 ipv4 vrr state enabled
nv set interface vlan904 ipv4 vrr vrr-state up
nv set interface vlan904 type svi
nv set interface vlan904 vlan 904
nv set interface swp2s0,swp4s0,swp6s0,swp8s0,swp10s0,swp12s0,swp14s0,swp16s0 bridge domain br_default access 906
# vlan906 SVI (rail6)
nv set interface vlan906 ipv4 address 192.168.6.3/24
nv set interface vlan906 vrf GPU
nv set interface vlan906 ipv4 vrr address 192.168.6.1/24
nv set interface vlan906 ipv4 vrr state enabled
nv set interface vlan906 ipv4 vrr vrr-state up
nv set interface vlan906 type svi
nv set interface vlan906 vlan 906
nv set interface swp2s1,swp4s1,swp6s1,swp8s1,swp10s1,swp12s1,swp14s1,swp16s1 bridge domain br_default access 908
# vlan908 SVI (rail8)
nv set interface vlan908 ipv4 address 192.168.8.3/24
nv set interface vlan908 vrf GPU
nv set interface vlan908 ipv4 vrr address 192.168.8.1/24
nv set interface vlan908 ipv4 vrr state enabled
nv set interface vlan908 ipv4 vrr vrr-state up
nv set interface vlan908 type svi
nv set interface vlan908 vlan 908

#============================================================================
# NVE / VxLAN
#============================================================================
nv set nve vxlan arp-nd-suppress enabled
nv set nve vxlan decapsulation dscp action preserve
nv set nve vxlan state enabled
nv set nve vxlan encapsulation dscp action copy
nv set nve vxlan source address 10.1.1.2

#============================================================================
# QoS - RoCE lossless for GPU traffic
#============================================================================
nv set qos roce state enabled
nv set qos roce mode lossless
nv set qos traffic-pool default-lossy memory-percent 10
nv set qos traffic-pool roce-lossless memory-percent 90

# GPU role - QoS PFC watchdog
nv set interface swp1s0,swp3s0,swp5s0,swp7s0,swp9s0,swp11s0,swp13s0,swp15s0 qos pfc-watchdog state enable
nv set interface swp1s1,swp3s1,swp5s1,swp7s1,swp9s1,swp11s1,swp13s1,swp15s1 qos pfc-watchdog state enable
nv set interface swp2s0,swp4s0,swp6s0,swp8s0,swp10s0,swp12s0,swp14s0,swp16s0 qos pfc-watchdog state enable
nv set interface swp2s1,swp4s1,swp6s1,swp8s1,swp10s1,swp12s1,swp14s1,swp16s1 qos pfc-watchdog state enable

#============================================================================
# Router policy
#============================================================================
nv set router bgp autonomous-system 4260395888
nv set router bgp state enabled
nv set router bgp router-id 10.1.1.2
nv set router policy route-map LOOPBACK_BGP rule 10 action permit
nv set router policy route-map LOOPBACK_BGP rule 10 description permit_loopback_interface_routes
nv set router policy route-map LOOPBACK_BGP rule 10 match interface lo
nv set router policy route-map LOOPBACK_BGP rule 10 match type ipv4
nv set router vrr state enabled

#============================================================================
# NTP
#============================================================================
nv set system ntp server 0.cumulusnetworks.pool.ntp.org association-type server
nv set system ntp server 1.cumulusnetworks.pool.ntp.org association-type server
nv set system ntp server 2.cumulusnetworks.pool.ntp.org association-type server
nv set system ntp server 3.cumulusnetworks.pool.ntp.org association-type server

#============================================================================
# AAA - local user 'cumulus' (password set via ZTP)
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
nv set system aaa user cumulus state enabled

#============================================================================
# System
#============================================================================
nv set system api state enabled
nv set system config auto-save state enabled
nv set system control-plane acl acl-default-dos inbound
nv set system control-plane acl acl-default-whitelist inbound
nv set system hostname gsl-plane1-02
nv set system message pre-login '##############################################################################
#      You are accessing an Information System (IS) that is provided for authorized use only.
##############################################################################'
nv set system message post-login '####################################################################
#       You are successfully logged in to: gsl-plane1-02 - site: default / arch: 2-8-9-400-SP
####################################################################'
nv set system ssh-server state enabled

#============================================================================
# WJH - what just happened, forwarding triggers
#============================================================================
nv set system wjh channel forwarding trigger l2
nv set system wjh channel forwarding trigger l3
nv set system wjh channel forwarding trigger tunnel
nv set system wjh state enabled

#============================================================================
# GPU VRF - EVPN, BGP
#============================================================================
nv set vrf GPU evpn state enabled
nv set vrf GPU evpn vlan 3003
nv set vrf GPU evpn vni 5003
nv set vrf GPU loopback ip address 10.1.1.22/32
nv set vrf GPU router bgp address-family ipv4-unicast state enabled
nv set vrf GPU router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf GPU router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf GPU router bgp address-family l2vpn-evpn state enabled
nv set vrf GPU router bgp autonomous-system 4260395888
nv set vrf GPU router bgp state enabled
nv set vrf GPU router bgp router-id 10.1.1.2
nv set vrf GPU table auto

#============================================================================
# Default VRF - BGP underlay + overlay (plane-internal)
#============================================================================
nv set vrf default router bgp address-family ipv4-unicast state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected route-map LOOPBACK_BGP
nv set vrf default router bgp address-family l2vpn-evpn state enabled
nv set vrf default router bgp autonomous-system 4260395888
nv set vrf default router bgp state enabled

# Overlay peers (numbered, loopback-to-loopback)
nv set vrf default router bgp neighbor 10.1.1.1 peer-group overlay
nv set vrf default router bgp neighbor 10.1.1.1 type numbered
# internal_isl peers - every breakout subport on the ISL trunk ports (unnumbered)
nv set vrf default router bgp neighbor swp33s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp33s0 type unnumbered
nv set vrf default router bgp neighbor swp33s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp33s1 type unnumbered
nv set vrf default router bgp neighbor swp34s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp34s0 type unnumbered
nv set vrf default router bgp neighbor swp34s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp34s1 type unnumbered
nv set vrf default router bgp neighbor swp35s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp35s0 type unnumbered
nv set vrf default router bgp neighbor swp35s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp35s1 type unnumbered
nv set vrf default router bgp neighbor swp36s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp36s0 type unnumbered
nv set vrf default router bgp neighbor swp36s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp36s1 type unnumbered
nv set vrf default router bgp neighbor swp37s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp37s0 type unnumbered
nv set vrf default router bgp neighbor swp37s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp37s1 type unnumbered
nv set vrf default router bgp neighbor swp38s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp38s0 type unnumbered
nv set vrf default router bgp neighbor swp38s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp38s1 type unnumbered
nv set vrf default router bgp neighbor swp39s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp39s0 type unnumbered
nv set vrf default router bgp neighbor swp39s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp39s1 type unnumbered
nv set vrf default router bgp neighbor swp40s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp40s0 type unnumbered
nv set vrf default router bgp neighbor swp40s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp40s1 type unnumbered
nv set vrf default router bgp neighbor swp41s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp41s0 type unnumbered
nv set vrf default router bgp neighbor swp41s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp41s1 type unnumbered
nv set vrf default router bgp neighbor swp42s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp42s0 type unnumbered
nv set vrf default router bgp neighbor swp42s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp42s1 type unnumbered
nv set vrf default router bgp neighbor swp43s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp43s0 type unnumbered
nv set vrf default router bgp neighbor swp43s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp43s1 type unnumbered
nv set vrf default router bgp neighbor swp44s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp44s0 type unnumbered
nv set vrf default router bgp neighbor swp44s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp44s1 type unnumbered
nv set vrf default router bgp neighbor swp45s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp45s0 type unnumbered
nv set vrf default router bgp neighbor swp45s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp45s1 type unnumbered
nv set vrf default router bgp neighbor swp46s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp46s0 type unnumbered
nv set vrf default router bgp neighbor swp46s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp46s1 type unnumbered
nv set vrf default router bgp neighbor swp47s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp47s0 type unnumbered
nv set vrf default router bgp neighbor swp47s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp47s1 type unnumbered
nv set vrf default router bgp neighbor swp48s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp48s0 type unnumbered
nv set vrf default router bgp neighbor swp48s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp48s1 type unnumbered

nv set vrf default router bgp path-selection multipath aspath-ignore enabled

# Peer-group definitions
nv set vrf default router bgp peer-group internal_isl address-family ipv4-unicast state enabled
nv set vrf default router bgp peer-group internal_isl remote-as internal
nv set vrf default router bgp peer-group overlay address-family ipv4-unicast state disabled
nv set vrf default router bgp peer-group overlay address-family l2vpn-evpn state enabled
nv set router bfd state enabled
nv set router bfd profile overlay min-rx-interval 1000
nv set router bfd profile overlay min-tx-interval 1000
nv set vrf default router bgp peer-group overlay bfd profile overlay
nv set vrf default router bgp peer-group overlay multihop-ttl 2
nv set vrf default router bgp peer-group overlay remote-as internal
nv set vrf default router bgp peer-group overlay update-source lo
nv set vrf default router bgp router-id 10.1.1.2
