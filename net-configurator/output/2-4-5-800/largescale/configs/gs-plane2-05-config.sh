#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# NVUE CLI Configuration for gs-plane2-05
# Generated: 2026-09-02T02:44:01Z
# Format: NVUE CLI commands (Spine, Plane 2, EVPN Relay)
#============================================================================
# EVPN (relay — no local VTEPs)
#============================================================================
nv set evpn state enabled

#============================================================================
# Interfaces - eth0 (mgmt), loopback, breakout
#============================================================================
nv set interface eth0 vrf mgmt
nv set interface eth0 type eth

nv set interface lo ipv4 address 10.2.1.45/32
nv set interface lo type loopback

# Breakout 2x on ISL ports (leaves)
nv set interface swp1,swp2,swp3,swp4,swp5,swp6,swp7,swp8,swp9,swp10,swp11,swp12,swp13,swp14,swp15,swp16,swp17,swp18,swp19,swp20,swp21,swp22,swp23,swp24,swp25,swp26,swp27,swp28,swp29,swp30,swp31,swp32,swp33,swp34,swp35,swp36,swp37,swp38,swp39,swp40,swp41,swp42,swp43,swp44,swp45,swp46,swp47,swp48 link breakout 2x

#============================================================================
# QoS - RoCE
#============================================================================
nv set qos roce state enabled
nv set qos roce mode lossless
nv set qos traffic-pool default-lossy memory-percent 10
nv set qos traffic-pool roce-lossless memory-percent 90

#============================================================================
# BFD Profiles
#============================================================================
nv set router bfd state enabled
nv set router bfd profile overlay detect-multiplier 3
nv set router bfd profile overlay min-rx-interval 1000
nv set router bfd profile overlay min-tx-interval 1000
nv set router bfd profile underlay detect-multiplier 3
nv set router bfd profile underlay min-rx-interval 300
nv set router bfd profile underlay min-tx-interval 300

#============================================================================
# BGP Global
#============================================================================
nv set router bgp autonomous-system 4200102100
nv set router bgp state enabled
nv set router bgp router-id 10.2.1.45

#============================================================================
# Route Maps
#============================================================================
nv set router policy route-map LOOPBACK_BGP rule 10 action permit
nv set router policy route-map LOOPBACK_BGP rule 10 description permit_loopback_interface_routes
nv set router policy route-map LOOPBACK_BGP rule 10 match interface lo
nv set router policy route-map LOOPBACK_BGP rule 10 match type ipv4

#============================================================================
# NTP
#============================================================================
nv set system ntp server 0.cumulusnetworks.pool.ntp.org association-type server
nv set system ntp server 1.cumulusnetworks.pool.ntp.org association-type server
nv set system ntp server 2.cumulusnetworks.pool.ntp.org association-type server
nv set system ntp server 3.cumulusnetworks.pool.ntp.org association-type server
nv set system ntp vrf mgmt

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
nv set system aaa user cumulus state enabled

#============================================================================
# System
#============================================================================
nv set system api state enabled
nv set system config auto-save state enabled
nv set system control-plane acl acl-default-dos inbound
nv set system control-plane acl acl-default-whitelist inbound
nv set acl acl-default-whitelist rule 200 match ip tcp dest-port 8251
nv set acl acl-default-whitelist type ipv4
nv set system hostname gs-plane2-05
nv set system message pre-login '##############################################################################
#      You are accessing an Information System (IS) that is provided for authorized use only.
##############################################################################'
nv set system message post-login '####################################################################
#       You are successfully logged in to: gs-plane2-05 - site: largescale / arch: 2-4-5-800
####################################################################'
nv set system ssh-server state enabled

#============================================================================
# WJH
#============================================================================
nv set system wjh channel forwarding trigger l2
nv set system wjh channel forwarding trigger l3
nv set system wjh channel forwarding trigger tunnel
nv set system wjh state enabled

#============================================================================
# Default VRF - BGP address families
#============================================================================
nv set vrf default router bgp address-family ipv4-unicast state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected route-map LOOPBACK_BGP
nv set vrf default router bgp address-family l2vpn-evpn state enabled
nv set vrf default router bgp state enabled

#============================================================================
# BGP Overlay Peers (numbered, loopback-to-loopback)
#============================================================================
nv set vrf default router bgp neighbor 10.2.1.1 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.1 type numbered
nv set vrf default router bgp neighbor 10.2.1.2 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.2 type numbered
nv set vrf default router bgp neighbor 10.2.1.3 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.3 type numbered
nv set vrf default router bgp neighbor 10.2.1.4 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.4 type numbered
nv set vrf default router bgp neighbor 10.2.1.5 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.5 type numbered
nv set vrf default router bgp neighbor 10.2.1.6 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.6 type numbered
nv set vrf default router bgp neighbor 10.2.1.7 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.7 type numbered
nv set vrf default router bgp neighbor 10.2.1.8 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.8 type numbered
nv set vrf default router bgp neighbor 10.2.1.9 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.9 type numbered
nv set vrf default router bgp neighbor 10.2.1.10 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.10 type numbered
nv set vrf default router bgp neighbor 10.2.1.11 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.11 type numbered
nv set vrf default router bgp neighbor 10.2.1.12 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.12 type numbered
nv set vrf default router bgp neighbor 10.2.1.13 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.13 type numbered
nv set vrf default router bgp neighbor 10.2.1.14 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.14 type numbered
nv set vrf default router bgp neighbor 10.2.1.15 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.15 type numbered
nv set vrf default router bgp neighbor 10.2.1.16 peer-group overlay
nv set vrf default router bgp neighbor 10.2.1.16 type numbered

#============================================================================
# BGP Underlay Peers (unnumbered, on breakout sub-ports)
#============================================================================
nv set vrf default router bgp neighbor swp1s0 peer-group underlay
nv set vrf default router bgp neighbor swp1s0 type unnumbered
nv set vrf default router bgp neighbor swp1s1 peer-group underlay
nv set vrf default router bgp neighbor swp1s1 type unnumbered
nv set vrf default router bgp neighbor swp2s0 peer-group underlay
nv set vrf default router bgp neighbor swp2s0 type unnumbered
nv set vrf default router bgp neighbor swp2s1 peer-group underlay
nv set vrf default router bgp neighbor swp2s1 type unnumbered
nv set vrf default router bgp neighbor swp3s0 peer-group underlay
nv set vrf default router bgp neighbor swp3s0 type unnumbered
nv set vrf default router bgp neighbor swp3s1 peer-group underlay
nv set vrf default router bgp neighbor swp3s1 type unnumbered
nv set vrf default router bgp neighbor swp4s0 peer-group underlay
nv set vrf default router bgp neighbor swp4s0 type unnumbered
nv set vrf default router bgp neighbor swp4s1 peer-group underlay
nv set vrf default router bgp neighbor swp4s1 type unnumbered
nv set vrf default router bgp neighbor swp5s0 peer-group underlay
nv set vrf default router bgp neighbor swp5s0 type unnumbered
nv set vrf default router bgp neighbor swp5s1 peer-group underlay
nv set vrf default router bgp neighbor swp5s1 type unnumbered
nv set vrf default router bgp neighbor swp6s0 peer-group underlay
nv set vrf default router bgp neighbor swp6s0 type unnumbered
nv set vrf default router bgp neighbor swp6s1 peer-group underlay
nv set vrf default router bgp neighbor swp6s1 type unnumbered
nv set vrf default router bgp neighbor swp7s0 peer-group underlay
nv set vrf default router bgp neighbor swp7s0 type unnumbered
nv set vrf default router bgp neighbor swp7s1 peer-group underlay
nv set vrf default router bgp neighbor swp7s1 type unnumbered
nv set vrf default router bgp neighbor swp8s0 peer-group underlay
nv set vrf default router bgp neighbor swp8s0 type unnumbered
nv set vrf default router bgp neighbor swp8s1 peer-group underlay
nv set vrf default router bgp neighbor swp8s1 type unnumbered
nv set vrf default router bgp neighbor swp9s0 peer-group underlay
nv set vrf default router bgp neighbor swp9s0 type unnumbered
nv set vrf default router bgp neighbor swp9s1 peer-group underlay
nv set vrf default router bgp neighbor swp9s1 type unnumbered
nv set vrf default router bgp neighbor swp10s0 peer-group underlay
nv set vrf default router bgp neighbor swp10s0 type unnumbered
nv set vrf default router bgp neighbor swp10s1 peer-group underlay
nv set vrf default router bgp neighbor swp10s1 type unnumbered
nv set vrf default router bgp neighbor swp11s0 peer-group underlay
nv set vrf default router bgp neighbor swp11s0 type unnumbered
nv set vrf default router bgp neighbor swp11s1 peer-group underlay
nv set vrf default router bgp neighbor swp11s1 type unnumbered
nv set vrf default router bgp neighbor swp12s0 peer-group underlay
nv set vrf default router bgp neighbor swp12s0 type unnumbered
nv set vrf default router bgp neighbor swp12s1 peer-group underlay
nv set vrf default router bgp neighbor swp12s1 type unnumbered
nv set vrf default router bgp neighbor swp13s0 peer-group underlay
nv set vrf default router bgp neighbor swp13s0 type unnumbered
nv set vrf default router bgp neighbor swp13s1 peer-group underlay
nv set vrf default router bgp neighbor swp13s1 type unnumbered
nv set vrf default router bgp neighbor swp14s0 peer-group underlay
nv set vrf default router bgp neighbor swp14s0 type unnumbered
nv set vrf default router bgp neighbor swp14s1 peer-group underlay
nv set vrf default router bgp neighbor swp14s1 type unnumbered
nv set vrf default router bgp neighbor swp15s0 peer-group underlay
nv set vrf default router bgp neighbor swp15s0 type unnumbered
nv set vrf default router bgp neighbor swp15s1 peer-group underlay
nv set vrf default router bgp neighbor swp15s1 type unnumbered
nv set vrf default router bgp neighbor swp16s0 peer-group underlay
nv set vrf default router bgp neighbor swp16s0 type unnumbered
nv set vrf default router bgp neighbor swp16s1 peer-group underlay
nv set vrf default router bgp neighbor swp16s1 type unnumbered
nv set vrf default router bgp neighbor swp17s0 peer-group underlay
nv set vrf default router bgp neighbor swp17s0 type unnumbered
nv set vrf default router bgp neighbor swp17s1 peer-group underlay
nv set vrf default router bgp neighbor swp17s1 type unnumbered
nv set vrf default router bgp neighbor swp18s0 peer-group underlay
nv set vrf default router bgp neighbor swp18s0 type unnumbered
nv set vrf default router bgp neighbor swp18s1 peer-group underlay
nv set vrf default router bgp neighbor swp18s1 type unnumbered
nv set vrf default router bgp neighbor swp19s0 peer-group underlay
nv set vrf default router bgp neighbor swp19s0 type unnumbered
nv set vrf default router bgp neighbor swp19s1 peer-group underlay
nv set vrf default router bgp neighbor swp19s1 type unnumbered
nv set vrf default router bgp neighbor swp20s0 peer-group underlay
nv set vrf default router bgp neighbor swp20s0 type unnumbered
nv set vrf default router bgp neighbor swp20s1 peer-group underlay
nv set vrf default router bgp neighbor swp20s1 type unnumbered
nv set vrf default router bgp neighbor swp21s0 peer-group underlay
nv set vrf default router bgp neighbor swp21s0 type unnumbered
nv set vrf default router bgp neighbor swp21s1 peer-group underlay
nv set vrf default router bgp neighbor swp21s1 type unnumbered
nv set vrf default router bgp neighbor swp22s0 peer-group underlay
nv set vrf default router bgp neighbor swp22s0 type unnumbered
nv set vrf default router bgp neighbor swp22s1 peer-group underlay
nv set vrf default router bgp neighbor swp22s1 type unnumbered
nv set vrf default router bgp neighbor swp23s0 peer-group underlay
nv set vrf default router bgp neighbor swp23s0 type unnumbered
nv set vrf default router bgp neighbor swp23s1 peer-group underlay
nv set vrf default router bgp neighbor swp23s1 type unnumbered
nv set vrf default router bgp neighbor swp24s0 peer-group underlay
nv set vrf default router bgp neighbor swp24s0 type unnumbered
nv set vrf default router bgp neighbor swp24s1 peer-group underlay
nv set vrf default router bgp neighbor swp24s1 type unnumbered
nv set vrf default router bgp neighbor swp25s0 peer-group underlay
nv set vrf default router bgp neighbor swp25s0 type unnumbered
nv set vrf default router bgp neighbor swp25s1 peer-group underlay
nv set vrf default router bgp neighbor swp25s1 type unnumbered
nv set vrf default router bgp neighbor swp26s0 peer-group underlay
nv set vrf default router bgp neighbor swp26s0 type unnumbered
nv set vrf default router bgp neighbor swp26s1 peer-group underlay
nv set vrf default router bgp neighbor swp26s1 type unnumbered
nv set vrf default router bgp neighbor swp27s0 peer-group underlay
nv set vrf default router bgp neighbor swp27s0 type unnumbered
nv set vrf default router bgp neighbor swp27s1 peer-group underlay
nv set vrf default router bgp neighbor swp27s1 type unnumbered
nv set vrf default router bgp neighbor swp28s0 peer-group underlay
nv set vrf default router bgp neighbor swp28s0 type unnumbered
nv set vrf default router bgp neighbor swp28s1 peer-group underlay
nv set vrf default router bgp neighbor swp28s1 type unnumbered
nv set vrf default router bgp neighbor swp29s0 peer-group underlay
nv set vrf default router bgp neighbor swp29s0 type unnumbered
nv set vrf default router bgp neighbor swp29s1 peer-group underlay
nv set vrf default router bgp neighbor swp29s1 type unnumbered
nv set vrf default router bgp neighbor swp30s0 peer-group underlay
nv set vrf default router bgp neighbor swp30s0 type unnumbered
nv set vrf default router bgp neighbor swp30s1 peer-group underlay
nv set vrf default router bgp neighbor swp30s1 type unnumbered
nv set vrf default router bgp neighbor swp31s0 peer-group underlay
nv set vrf default router bgp neighbor swp31s0 type unnumbered
nv set vrf default router bgp neighbor swp31s1 peer-group underlay
nv set vrf default router bgp neighbor swp31s1 type unnumbered
nv set vrf default router bgp neighbor swp32s0 peer-group underlay
nv set vrf default router bgp neighbor swp32s0 type unnumbered
nv set vrf default router bgp neighbor swp32s1 peer-group underlay
nv set vrf default router bgp neighbor swp32s1 type unnumbered
nv set vrf default router bgp neighbor swp33s0 peer-group underlay
nv set vrf default router bgp neighbor swp33s0 type unnumbered
nv set vrf default router bgp neighbor swp33s1 peer-group underlay
nv set vrf default router bgp neighbor swp33s1 type unnumbered
nv set vrf default router bgp neighbor swp34s0 peer-group underlay
nv set vrf default router bgp neighbor swp34s0 type unnumbered
nv set vrf default router bgp neighbor swp34s1 peer-group underlay
nv set vrf default router bgp neighbor swp34s1 type unnumbered
nv set vrf default router bgp neighbor swp35s0 peer-group underlay
nv set vrf default router bgp neighbor swp35s0 type unnumbered
nv set vrf default router bgp neighbor swp35s1 peer-group underlay
nv set vrf default router bgp neighbor swp35s1 type unnumbered
nv set vrf default router bgp neighbor swp36s0 peer-group underlay
nv set vrf default router bgp neighbor swp36s0 type unnumbered
nv set vrf default router bgp neighbor swp36s1 peer-group underlay
nv set vrf default router bgp neighbor swp36s1 type unnumbered
nv set vrf default router bgp neighbor swp37s0 peer-group underlay
nv set vrf default router bgp neighbor swp37s0 type unnumbered
nv set vrf default router bgp neighbor swp37s1 peer-group underlay
nv set vrf default router bgp neighbor swp37s1 type unnumbered
nv set vrf default router bgp neighbor swp38s0 peer-group underlay
nv set vrf default router bgp neighbor swp38s0 type unnumbered
nv set vrf default router bgp neighbor swp38s1 peer-group underlay
nv set vrf default router bgp neighbor swp38s1 type unnumbered
nv set vrf default router bgp neighbor swp39s0 peer-group underlay
nv set vrf default router bgp neighbor swp39s0 type unnumbered
nv set vrf default router bgp neighbor swp39s1 peer-group underlay
nv set vrf default router bgp neighbor swp39s1 type unnumbered
nv set vrf default router bgp neighbor swp40s0 peer-group underlay
nv set vrf default router bgp neighbor swp40s0 type unnumbered
nv set vrf default router bgp neighbor swp40s1 peer-group underlay
nv set vrf default router bgp neighbor swp40s1 type unnumbered
nv set vrf default router bgp neighbor swp41s0 peer-group underlay
nv set vrf default router bgp neighbor swp41s0 type unnumbered
nv set vrf default router bgp neighbor swp41s1 peer-group underlay
nv set vrf default router bgp neighbor swp41s1 type unnumbered
nv set vrf default router bgp neighbor swp42s0 peer-group underlay
nv set vrf default router bgp neighbor swp42s0 type unnumbered
nv set vrf default router bgp neighbor swp42s1 peer-group underlay
nv set vrf default router bgp neighbor swp42s1 type unnumbered
nv set vrf default router bgp neighbor swp43s0 peer-group underlay
nv set vrf default router bgp neighbor swp43s0 type unnumbered
nv set vrf default router bgp neighbor swp43s1 peer-group underlay
nv set vrf default router bgp neighbor swp43s1 type unnumbered
nv set vrf default router bgp neighbor swp44s0 peer-group underlay
nv set vrf default router bgp neighbor swp44s0 type unnumbered
nv set vrf default router bgp neighbor swp44s1 peer-group underlay
nv set vrf default router bgp neighbor swp44s1 type unnumbered
nv set vrf default router bgp neighbor swp45s0 peer-group underlay
nv set vrf default router bgp neighbor swp45s0 type unnumbered
nv set vrf default router bgp neighbor swp45s1 peer-group underlay
nv set vrf default router bgp neighbor swp45s1 type unnumbered
nv set vrf default router bgp neighbor swp46s0 peer-group underlay
nv set vrf default router bgp neighbor swp46s0 type unnumbered
nv set vrf default router bgp neighbor swp46s1 peer-group underlay
nv set vrf default router bgp neighbor swp46s1 type unnumbered
nv set vrf default router bgp neighbor swp47s0 peer-group underlay
nv set vrf default router bgp neighbor swp47s0 type unnumbered
nv set vrf default router bgp neighbor swp47s1 peer-group underlay
nv set vrf default router bgp neighbor swp47s1 type unnumbered
nv set vrf default router bgp neighbor swp48s0 peer-group underlay
nv set vrf default router bgp neighbor swp48s0 type unnumbered
nv set vrf default router bgp neighbor swp48s1 peer-group underlay
nv set vrf default router bgp neighbor swp48s1 type unnumbered

#============================================================================
# BGP Path Selection
#============================================================================
nv set vrf default router bgp path-selection multipath aspath-ignore enabled

#============================================================================
# Peer Group Definitions
#============================================================================
nv set vrf default router bgp peer-group overlay address-family ipv4-unicast state disabled
nv set vrf default router bgp peer-group overlay address-family l2vpn-evpn state enabled
nv set vrf default router bgp peer-group overlay bfd profile overlay
nv set vrf default router bgp peer-group overlay multihop-ttl 2
nv set vrf default router bgp peer-group overlay remote-as external
nv set vrf default router bgp peer-group overlay update-source lo
nv set vrf default router bgp peer-group underlay address-family ipv4-unicast state enabled
nv set vrf default router bgp peer-group underlay remote-as external
nv set vrf default router bgp router-id 10.2.1.45
