#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# NVUE CLI Configuration for csl-02
# Generated: 2026-07-02T12:37:03Z
# Format: NVUE CLI commands (Simplified with Pure Jinja2)

#============================================================================
# Bridge and VLANs
#============================================================================
nv set bridge domain br_default type vlan-aware
nv set bridge domain br_default vlan 200 vni 4200
nv set bridge domain br_default vlan 300 vni 4300
nv set bridge domain br_default vlan 400 vni 4400
nv set bridge domain br_default vlan 500 vni 4500

#============================================================================
# EVPN
#============================================================================
nv set evpn state enabled
nv set evpn multihoming state enabled

#============================================================================
# Breakout Configuration
#============================================================================
nv set interface swp1,swp2,swp3,swp4,swp5,swp6 link breakout 4x lanes-per-port 2
nv set interface swp56,swp57,swp58 link breakout 2x lanes-per-port 4
nv set interface swp59,swp64,swp63 link breakout 8x lanes-per-port 1

# WARNING: The following ports are adjacent to 8x breakout ports and should be in interfaces_disabled:
# swp65

nv set interface swp60 link breakout disabled

#============================================================================
# Bond Interfaces - Auto-Generated from Network Roles
#============================================================================

nv set interface bond1s0 bond member swp1s0
nv set interface bond1s0 evpn multihoming segment local-id 10
nv set interface bond1s0 description su-01-node-01
nv set interface bond1s1 bond member swp1s1
nv set interface bond1s1 evpn multihoming segment local-id 11
nv set interface bond1s1 description su-01-node-02

nv set interface bond2s0 bond member swp2s0
nv set interface bond2s0 evpn multihoming segment local-id 20
nv set interface bond2s0 description su-01-node-03
nv set interface bond2s1 bond member swp2s1
nv set interface bond2s1 evpn multihoming segment local-id 21
nv set interface bond2s1 description su-01-node-04

nv set interface bond3s0 bond member swp3s0
nv set interface bond3s0 evpn multihoming segment local-id 30
nv set interface bond3s0 description su-02-node-01
nv set interface bond3s1 bond member swp3s1
nv set interface bond3s1 evpn multihoming segment local-id 31
nv set interface bond3s1 description su-02-node-02

nv set interface bond4s0 bond member swp4s0
nv set interface bond4s0 evpn multihoming segment local-id 40
nv set interface bond4s0 description su-02-node-03
nv set interface bond4s1 bond member swp4s1
nv set interface bond4s1 evpn multihoming segment local-id 41
nv set interface bond4s1 description su-02-node-04

# CPU role - 4 ports, 8 bonds
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1 evpn multihoming segment state enabled
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1 evpn multihoming segment mac-address 44:38:39:FF:00:AA
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1 type bond
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1 bridge domain br_default vlan 300,400
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1 bridge domain br_default untagged 300
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1 bond lacp-bypass enabled

nv set interface bond5s0 bond member swp5s0
nv set interface bond5s0 evpn multihoming segment local-id 50
nv set interface bond5s0 description support-01
nv set interface bond5s1 bond member swp5s1
nv set interface bond5s1 evpn multihoming segment local-id 51
nv set interface bond5s1 description support-02
nv set interface bond5s2 bond member swp5s2
nv set interface bond5s2 evpn multihoming segment local-id 52
nv set interface bond5s2 description support-03
nv set interface bond5s3 bond member swp5s3
nv set interface bond5s3 evpn multihoming segment local-id 53
nv set interface bond5s3 description support-04

nv set interface bond6s0 bond member swp6s0
nv set interface bond6s0 evpn multihoming segment local-id 60
nv set interface bond6s0 description support-05
nv set interface bond6s1 bond member swp6s1
nv set interface bond6s1 evpn multihoming segment local-id 61
nv set interface bond6s1 description support-06
nv set interface bond6s2 bond member swp6s2
nv set interface bond6s2 evpn multihoming segment local-id 62
nv set interface bond6s2 description support-07

# SUPPORT role - 2 ports, 7 bonds
nv set interface bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2 evpn multihoming segment state enabled
nv set interface bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2 evpn multihoming segment mac-address 44:38:39:FF:00:AA
nv set interface bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2 type bond
nv set interface bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2 bridge domain br_default vlan 200,300,400
nv set interface bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2 bridge domain br_default untagged 300
nv set interface bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2 bond lacp-bypass enabled

#============================================================================
# Management Interface
#============================================================================
nv set interface eth0 type eth
nv set interface eth0 vrf mgmt

#============================================================================
# Loopback
#============================================================================
nv set interface lo ipv4 address 172.16.176.12/32
nv set interface lo type loopback

#============================================================================
# Physical Interfaces - State Up
#============================================================================

#============================================================================
# Direct Interfaces (Non-Bonded) - GPU, ISL, Edge
#============================================================================

# ISL role - direct interfaces
nv set interface swp56s0,swp56s1,swp57s0,swp57s1,swp58s0 description 'ISL to other core switch'
nv set interface swp56s0,swp56s1,swp57s0,swp57s1,swp58s0 evpn multihoming uplink enabled

# EDGE role - direct interfaces
nv set interface swp64s0,swp64s1 description 'Edge uplinks'
nv set interface swp64s0,swp64s1 vrf EXIT

# OOB role - direct L3 uplinks
nv set interface swp59s0,swp59s1 description 'OOB uplinks'

# STORAGE role - L3 external uplinks
nv set interface swp63s0,swp63s1 description 'External Uplink - STORAGE VRF'
nv set interface swp63s0,swp63s1 vrf STORAGE

#============================================================================
# Disabled Interfaces / Link State Down
#============================================================================

#============================================================================
# All Switch Ports Type and Telemetry
#============================================================================

nv set interface swp7,swp8,swp9,swp10,swp11,swp12,swp13,swp14,swp15,swp16,swp17,swp18,swp19,swp20,swp21,swp22,swp23,swp24,swp25,swp26,swp27,swp28,swp29,swp30,swp31,swp32,swp33,swp34,swp35,swp36,swp37,swp38,swp39,swp40,swp41,swp42,swp43,swp44,swp45,swp46,swp47,swp48,swp49,swp50,swp51,swp52,swp53,swp54,swp55,swp61,swp62,swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp56s0,swp56s1,swp57s0,swp57s1,swp58s0,swp59s0,swp59s1,swp64s0,swp64s1 type swp

nv set interface swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp56s0,swp56s1,swp57s0,swp57s1,swp58s0,swp59s0,swp59s1,swp64s0,swp64s1 telemetry histogram counter counter-type rx-packet
nv set interface swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp56s0,swp56s1,swp57s0,swp57s1,swp58s0,swp59s0,swp59s1,swp64s0,swp64s1 telemetry histogram counter counter-type tx-packet
nv set interface swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp56s0,swp56s1,swp57s0,swp57s1,swp58s0,swp59s0,swp59s1,swp64s0,swp64s1 telemetry histogram egress-buffer traffic-class 0
nv set interface swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp56s0,swp56s1,swp57s0,swp57s1,swp58s0,swp59s0,swp59s1,swp64s0,swp64s1 telemetry histogram ingress-buffer priority-group 0
nv set interface swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp56s0,swp56s1,swp57s0,swp57s1,swp58s0,swp59s0,swp59s1,swp64s0,swp64s1 telemetry histogram ingress-buffer priority-group 1

#============================================================================
# VLAN SVIs (from host_vars)
#============================================================================
nv set interface vlan300 ipv4 address 172.16.178.3/24
nv set interface vlan300 ipv4 vrr address 172.16.178.1/24
nv set interface vlan300 ipv4 vrr state enabled
nv set interface vlan300 ipv4 vrr vrr-state up
nv set interface vlan300 type svi
nv set interface vlan300 vlan 300
nv set interface vlan300 vrf INBAND
nv set interface vlan400 ipv4 address 172.16.179.3/24
nv set interface vlan400 ipv4 vrr address 172.16.179.1/24
nv set interface vlan400 ipv4 vrr state enabled
nv set interface vlan400 ipv4 vrr vrr-state up
nv set interface vlan400 type svi
nv set interface vlan400 vlan 400
nv set interface vlan400 vrf INBAND
nv set interface vlan500 ipv4 address 172.16.180.3/24
nv set interface vlan500 ipv4 vrr address 172.16.180.1/24
nv set interface vlan500 ipv4 vrr state enabled
nv set interface vlan500 ipv4 vrr vrr-state up
nv set interface vlan500 type svi
nv set interface vlan500 vlan 500
nv set interface vlan500 vrf STORAGE

#============================================================================
# NVE / VXLAN
#============================================================================
nv set nve vxlan arp-nd-suppress enabled
nv set nve vxlan decapsulation dscp action preserve
nv set nve vxlan state enabled
nv set nve vxlan encapsulation dscp action copy
nv set nve vxlan flooding state enabled
nv set nve vxlan flooding head-end-replication evpn
nv set nve vxlan source address 172.16.176.12

#============================================================================
# BGP - Underlay and EVPN
#============================================================================
nv set router bgp state enabled
nv set router bgp autonomous-system 4260394788
nv set router bgp router-id 172.16.176.12

nv set router bfd state enabled
nv set router bfd profile default detect-multiplier 3
nv set router bfd profile default min-rx-interval 300
nv set router bfd profile default min-tx-interval 300
nv set router bfd profile overlay detect-multiplier 3
nv set router bfd profile overlay min-rx-interval 1000
nv set router bfd profile overlay min-tx-interval 1000
nv set router bfd offload enabled

nv set vrf default router bgp path-selection multipath aspath-ignore enabled
nv set vrf default router bgp address-family ipv4-unicast multipaths ebgp 128

nv set router policy prefix-list ALL_PREFIXES rule 10 action permit
nv set router policy prefix-list ALL_PREFIXES rule 10 match 0.0.0.0/0 max-prefix-len 32
nv set router policy prefix-list EXIT_LOCAL_IF rule 10 action permit
nv set router policy prefix-list EXIT_LOCAL_IF rule 10 match 172.16.176.6/32 max-prefix-len 32
nv set router policy prefix-list INBAND_LOCAL_IF rule 10 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 10 match 172.16.176.4/32 max-prefix-len 32
nv set router policy prefix-list INBAND_LOCAL_IF rule 20 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 20 match 172.16.178.3/32 max-prefix-len 32
nv set router policy prefix-list INBAND_LOCAL_IF rule 30 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 30 match 172.16.179.3/32 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 10 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 10 match 172.16.178.0/24 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 20 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 20 match 172.16.179.0/24 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 30 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 30 match 172.16.176.4/32 max-prefix-len 32
nv set router policy prefix-list ERA_PREFIXES rule 10 action permit
nv set router policy prefix-list ERA_PREFIXES rule 10 match 172.16.176.0/21 max-prefix-len 24
nv set router policy prefix-list ERA_PREFIXES rule 20 action permit
nv set router policy prefix-list ERA_PREFIXES rule 20 match 172.16.176.0/24 max-prefix-len 32
nv set router policy prefix-list ERA_PREFIXES rule 30 action permit
nv set router policy prefix-list ERA_PREFIXES rule 30 match 192.168.200.0/24 max-prefix-len 32
nv set router policy prefix-list LOCAL_OOB_LOOPBACK rule 10 action permit
nv set router policy prefix-list LOCAL_OOB_LOOPBACK rule 10 match 172.16.176.2/32 max-prefix-len 32
nv set router policy prefix-list OOB_LOCAL_IF rule 10 action permit
nv set router policy prefix-list OOB_LOCAL_IF rule 10 match 172.16.176.2/32 max-prefix-len 32
nv set router policy prefix-list OOB_PREFIXES rule 10 action permit
nv set router policy prefix-list OOB_PREFIXES rule 10 match 172.16.177.0/24 max-prefix-len 32
nv set router policy prefix-list OOB_PREFIXES rule 20 action permit
nv set router policy prefix-list OOB_PREFIXES rule 20 match 172.16.176.2/32 max-prefix-len 32
nv set router policy prefix-list VTEP_PREFIXES rule 5 action permit
nv set router policy prefix-list VTEP_PREFIXES rule 5 match 172.16.176.8/29 max-prefix-len 32

nv set router policy community-list 11 rule 100 action permit
nv set router policy community-list 11 rule 100 community 11:11

nv set router policy route-map BLOCK_VTEPS rule 10 action deny
nv set router policy route-map BLOCK_VTEPS rule 10 match ip-prefix-list VTEP_PREFIXES
nv set router policy route-map BLOCK_VTEPS rule 10 match type ipv4
nv set router policy route-map BLOCK_VTEPS rule 20 action permit
nv set router policy route-map BLOCK_VTEPS rule 20 match ip-prefix-list ALL_PREFIXES
nv set router policy route-map BLOCK_VTEPS rule 20 match type ipv4
nv set router policy route-map EXIT_FILTER rule 10 action deny
nv set router policy route-map EXIT_FILTER rule 10 match ip-prefix-list EXIT_LOCAL_IF
nv set router policy route-map EXIT_FILTER rule 10 match type ipv4
nv set router policy route-map EXIT_FILTER rule 20 action permit
nv set router policy route-map EXIT_FILTER rule 20 set community 11:11
nv set router policy route-map INBAND_FILTER rule 5 action deny
nv set router policy route-map INBAND_FILTER rule 5 match community-list 11
nv set router policy route-map INBAND_FILTER rule 10 action deny
nv set router policy route-map INBAND_FILTER rule 10 match ip-prefix-list OOB_PREFIXES
nv set router policy route-map INBAND_FILTER rule 10 match type ipv4
nv set router policy route-map INBAND_FILTER rule 15 action deny
nv set router policy route-map INBAND_FILTER rule 15 match ip-prefix-list INBAND_LOCAL_IF
nv set router policy route-map INBAND_FILTER rule 15 match type ipv4
nv set router policy route-map INBAND_FILTER rule 20 action permit
nv set router policy route-map INBAND_FILTER rule 20 match ip-prefix-list ALL_PREFIXES
nv set router policy route-map INBAND_FILTER rule 20 match type ipv4
nv set router policy route-map OOB_FILTER rule 5 action deny
nv set router policy route-map OOB_FILTER rule 5 match community-list 11
nv set router policy route-map OOB_FILTER rule 10 action deny
nv set router policy route-map OOB_FILTER rule 10 match ip-prefix-list INBAND_PREFIXES
nv set router policy route-map OOB_FILTER rule 10 match type ipv4
nv set router policy route-map OOB_FILTER rule 15 action deny
nv set router policy route-map OOB_FILTER rule 15 match ip-prefix-list OOB_LOCAL_IF
nv set router policy route-map OOB_FILTER rule 15 match type ipv4
nv set router policy route-map OOB_FILTER rule 20 action permit
nv set router policy route-map OOB_FILTER rule 20 match ip-prefix-list ALL_PREFIXES
nv set router policy route-map OOB_FILTER rule 20 match type ipv4
nv set router policy route-map OUTBOUND_ERA_PREFIXES rule 10 action permit
nv set router policy route-map OUTBOUND_ERA_PREFIXES rule 10 match ip-prefix-list ERA_PREFIXES
nv set router policy route-map OUTBOUND_ERA_PREFIXES rule 10 match type ipv4
nv set router policy route-map WEIGHTED_ECMP rule 10 action permit
nv set router policy route-map WEIGHTED_ECMP rule 10 set ext-community-bw multipaths

nv set router vrr state enabled

#============================================================================
# VRFs
#============================================================================
nv set vrf EXIT evpn state enabled
nv set vrf EXIT evpn vlan 3004
nv set vrf EXIT evpn vni 5004

nv set vrf EXIT loopback ip address 172.16.176.6/32

nv set vrf EXIT router bgp address-family ipv4-unicast state enabled
nv set vrf EXIT router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf EXIT router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf state enabled
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf list INBAND
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf list OOB
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf route-map EXIT_FILTER
nv set vrf EXIT router bgp address-family l2vpn-evpn state enabled

nv set vrf EXIT router bgp autonomous-system 4260394788
nv set vrf EXIT router bgp state enabled

nv set vrf EXIT router bgp neighbor swp64s0 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp64s0 type unnumbered
nv set vrf EXIT router bgp neighbor swp64s1 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp64s1 type unnumbered

nv set vrf EXIT router bgp peer-group underlay-esl-external address-family ipv4-unicast state enabled
nv set vrf EXIT router bgp peer-group underlay-esl-external address-family ipv4-unicast policy outbound route-map OUTBOUND_ERA_PREFIXES
nv set vrf EXIT router bgp peer-group underlay-esl-external remote-as external

nv set vrf EXIT router bgp route-export
nv set vrf EXIT router bgp router-id 172.16.176.6

nv set vrf INBAND evpn state enabled
nv set vrf INBAND evpn vlan 3002
nv set vrf INBAND evpn vni 5002

nv set vrf INBAND loopback ip address 172.16.176.4/32

nv set vrf INBAND router bgp address-family ipv4-unicast state enabled
nv set vrf INBAND router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf INBAND router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf INBAND router bgp address-family ipv4-unicast route-import from-vrf state enabled
nv set vrf INBAND router bgp address-family ipv4-unicast route-import from-vrf list EXIT
nv set vrf INBAND router bgp address-family ipv4-unicast route-import from-vrf route-map INBAND_FILTER
nv set vrf INBAND router bgp address-family l2vpn-evpn state enabled

nv set vrf INBAND router bgp autonomous-system 4260394788
nv set vrf INBAND router bgp state enabled

nv set vrf INBAND router bgp route-export
nv set vrf INBAND router bgp route-import
nv set vrf INBAND router bgp router-id 172.16.176.4

nv set vrf OOB evpn state enabled
nv set vrf OOB evpn vlan 3001
nv set vrf OOB evpn vni 5001

nv set vrf OOB loopback ip address 172.16.176.2/32

nv set vrf OOB router bgp address-family ipv4-unicast state enabled
nv set vrf OOB router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf OOB router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf state enabled
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf list EXIT
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf route-map OOB_FILTER
nv set vrf OOB router bgp address-family l2vpn-evpn state enabled

nv set vrf OOB router bgp autonomous-system 4260394788
nv set vrf OOB router bgp state enabled

nv set vrf OOB router bgp router-id 172.16.176.2

nv set vrf STORAGE evpn state enabled
nv set vrf STORAGE evpn vlan 3005
nv set vrf STORAGE evpn vni 5005

nv set vrf STORAGE loopback ip address 172.16.176.8/32

nv set vrf STORAGE router bgp address-family ipv4-unicast state enabled
nv set vrf STORAGE router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf STORAGE router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf STORAGE router bgp address-family l2vpn-evpn state enabled

nv set vrf STORAGE router bgp autonomous-system 4260394788
nv set vrf STORAGE router bgp state enabled

nv set vrf STORAGE router bgp neighbor swp63s0 peer-group underlay-era-storage
nv set vrf STORAGE router bgp neighbor swp63s0 type unnumbered
nv set vrf STORAGE router bgp neighbor swp63s1 peer-group underlay-era-storage
nv set vrf STORAGE router bgp neighbor swp63s1 type unnumbered

nv set vrf STORAGE router bgp peer-group underlay-era-storage address-family ipv4-unicast state enabled
nv set vrf STORAGE router bgp peer-group underlay-era-storage address-family l2vpn-evpn state enabled
nv set vrf STORAGE router bgp peer-group underlay-era-storage bfd profile default
nv set vrf STORAGE router bgp peer-group underlay-era-storage remote-as external

nv set vrf STORAGE router bgp route-export
nv set vrf STORAGE router bgp router-id 172.16.176.8

nv set vrf STORAGE table auto

#============================================================================
# Default VRF BGP (ISL Underlay)
#============================================================================
nv set vrf default router bgp address-family ipv4-unicast state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf default router bgp address-family l2vpn-evpn state enabled

nv set vrf default router bgp state enabled

nv set vrf default router bgp neighbor swp56s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp56s0 type unnumbered
nv set vrf default router bgp neighbor swp56s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp56s1 type unnumbered
nv set vrf default router bgp neighbor swp57s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp57s0 type unnumbered
nv set vrf default router bgp neighbor swp57s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp57s1 type unnumbered
nv set vrf default router bgp neighbor swp58s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp58s0 type unnumbered
nv set vrf default router bgp neighbor swp59s0 peer-group underlay
nv set vrf default router bgp neighbor swp59s0 type unnumbered
nv set vrf default router bgp neighbor swp59s1 peer-group underlay
nv set vrf default router bgp neighbor swp59s1 type unnumbered
nv set vrf default router bgp neighbor 172.16.176.21 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.21 type numbered
nv set vrf default router bgp neighbor 172.16.176.22 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.22 type numbered

nv set vrf default router bgp peer-group internal-isl address-family ipv4-unicast state enabled
nv set vrf default router bgp peer-group internal-isl address-family l2vpn-evpn state enabled
nv set vrf default router bgp peer-group internal-isl bfd profile default
nv set vrf default router bgp peer-group internal-isl description internal_isl_interconnect
nv set vrf default router bgp peer-group internal-isl remote-as internal
nv set vrf default router bgp peer-group underlay address-family ipv4-unicast state enabled
nv set vrf default router bgp peer-group underlay address-family ipv4-unicast policy outbound route-map WEIGHTED_ECMP
nv set vrf default router bgp peer-group underlay bfd profile default
nv set vrf default router bgp peer-group underlay description oob_underlay_interconnect
nv set vrf default router bgp peer-group underlay remote-as external
nv set vrf default router bgp peer-group overlay address-family ipv4-unicast state disabled
nv set vrf default router bgp peer-group overlay address-family l2vpn-evpn state enabled
nv set vrf default router bgp peer-group overlay bfd profile overlay
nv set vrf default router bgp peer-group overlay update-source lo
nv set vrf default router bgp peer-group overlay multihop-ttl 2
nv set vrf default router bgp peer-group overlay description oob_overlay_interconnect
nv set vrf default router bgp peer-group overlay remote-as external

#============================================================================
# DHCP Relay (VRF-aware, Excel-driven)
#============================================================================
nv set service dhcp-relay OOB server-group oob-dhcp-servers server 192.168.200.78
nv set service dhcp-relay OOB server-group oob-dhcp-servers upstream-interface vlan3001_l3
nv set service dhcp-relay OOB downstream-interface vlan200 server-group-name oob-dhcp-servers
nv set service dhcp-relay OOB source-ip giaddress
nv set service dhcp-relay EXIT server-group exit-dhcp-servers server 10.88.88.88
nv set service dhcp-relay EXIT server-group exit-dhcp-servers upstream-interface vlan3004_l3
nv set service dhcp-relay EXIT downstream-interface vlan400 server-group-name exit-dhcp-servers
nv set service dhcp-relay EXIT source-ip giaddress

#============================================================================
# QoS / RoCE Configuration
#============================================================================
nv set qos roce state enabled
nv set qos roce mode lossless
nv set qos traffic-pool default-lossy memory-percent 10
nv set qos traffic-pool roce-lossless memory-percent 90

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
nv set system aaa authentication order local
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
nv set system global anycast-mac 44:38:39:ff:00:ff
nv set system hostname csl-02
nv set system message pre-login '##############################################################################
#      You are accessing an Information System (IS) that is provided for authorized use only.
##############################################################################'
nv set system message post-login '####################################################################
#       You are successfully logged in to: csl-02 - site: default / arch: 2-8-9-400-SP
####################################################################'
nv set system ssh-server state enabled
nv set system telemetry state enabled
nv set system telemetry histogram counter bin-min-boundary 3552
nv set system telemetry histogram counter histogram-size 55008
nv set system telemetry histogram counter sample-interval 1024
nv set system telemetry histogram egress-buffer bin-min-boundary 960
nv set system telemetry histogram egress-buffer histogram-size 9830400
nv set system telemetry histogram egress-buffer sample-interval 1024
nv set system telemetry histogram ingress-buffer bin-min-boundary 960
nv set system telemetry histogram ingress-buffer histogram-size 2457600
nv set system telemetry histogram ingress-buffer sample-interval 1024
nv set system telemetry snapshot-file count 120
nv set system telemetry snapshot-file name /var/run/cumulus/histogram_stats
nv set system telemetry snapshot-interval 10
nv set system date-time timezone Etc/Zulu
nv set system wjh channel forwarding trigger l2
nv set system wjh channel forwarding trigger l3
nv set system wjh channel forwarding trigger tunnel
nv set system wjh state enabled
