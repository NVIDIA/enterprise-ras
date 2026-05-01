#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# NVUE CLI Configuration for core-02
# Generated: 2026-04-22T18:42:54Z
# Format: NVUE CLI commands (Simplified with Pure Jinja2)

#============================================================================
# Bridge and VLANs
#============================================================================
nv set bridge domain br_default type vlan-aware
nv set bridge domain br_default vlan 200 vni 4200
nv set bridge domain br_default vlan 300 vni 4300
nv set bridge domain br_default vlan 400 vni 4400
nv set bridge domain br_default vlan 500 vni 4500
nv set bridge domain br_default vlan 900 vni 4900

#============================================================================
# EVPN
#============================================================================
nv set evpn state enabled
nv set evpn multihoming state enabled

#============================================================================
# Breakout Configuration
#============================================================================
nv set interface swp52,swp53,swp1,swp2,swp3,swp57 link breakout 4x lanes-per-port 2
nv set interface swp4,swp5,swp6,swp7,swp8,swp9,swp10,swp11,swp12,swp13,swp14,swp15,swp16,swp17,swp18,swp19,swp20,swp21,swp22,swp23,swp24,swp25,swp26,swp27,swp28,swp29,swp30,swp31,swp32,swp33,swp34,swp35,swp36,swp37,swp38,swp39,swp40,swp41,swp42,swp43,swp44,swp45,swp46,swp47,swp48,swp49,swp50,swp51 link breakout 2x lanes-per-port 4
nv set interface swp55,swp61,swp63 link breakout 8x lanes-per-port 1

nv set interface swp54,swp56,swp58,swp60,swp62,swp64 link breakout disabled

#============================================================================
# Bond Interfaces - Auto-Generated from Network Roles
#============================================================================

nv set interface bond52s0 bond member swp52s0
nv set interface bond52s0 evpn multihoming segment local-id 520
nv set interface bond52s1 bond member swp52s1
nv set interface bond52s1 evpn multihoming segment local-id 521
nv set interface bond52s2 bond member swp52s2
nv set interface bond52s2 evpn multihoming segment local-id 522
nv set interface bond52s3 bond member swp52s3
nv set interface bond52s3 evpn multihoming segment local-id 523

nv set interface bond53s0 bond member swp53s0
nv set interface bond53s0 evpn multihoming segment local-id 530
nv set interface bond53s1 bond member swp53s1
nv set interface bond53s1 evpn multihoming segment local-id 531
nv set interface bond53s2 bond member swp53s2
nv set interface bond53s2 evpn multihoming segment local-id 532
nv set interface bond53s3 bond member swp53s3
nv set interface bond53s3 evpn multihoming segment local-id 533

# SUPPORT role - 2 ports, 8 bonds
nv set interface bond52s0,bond52s1,bond52s2,bond52s3,bond53s0,bond53s1,bond53s2,bond53s3 evpn multihoming segment state enabled
nv set interface bond52s0,bond52s1,bond52s2,bond52s3,bond53s0,bond53s1,bond53s2,bond53s3 evpn multihoming segment mac-address 44:38:39:FF:00:AA
nv set interface bond52s0,bond52s1,bond52s2,bond52s3,bond53s0,bond53s1,bond53s2,bond53s3 type bond
nv set interface bond52s0,bond52s1,bond52s2,bond52s3,bond53s0,bond53s1,bond53s2,bond53s3 bridge domain br_default vlan 400
nv set interface bond52s0,bond52s1,bond52s2,bond52s3,bond53s0,bond53s1,bond53s2,bond53s3 bridge domain br_default untagged 300
nv set interface bond52s0,bond52s1,bond52s2,bond52s3,bond53s0,bond53s1,bond53s2,bond53s3 bond lacp-bypass enabled

nv set interface bond1s0 bond member swp1s0
nv set interface bond1s0 evpn multihoming segment local-id 10
nv set interface bond1s1 bond member swp1s1
nv set interface bond1s1 evpn multihoming segment local-id 11
nv set interface bond1s2 bond member swp1s2
nv set interface bond1s2 evpn multihoming segment local-id 12
nv set interface bond1s3 bond member swp1s3
nv set interface bond1s3 evpn multihoming segment local-id 13

nv set interface bond2s0 bond member swp2s0
nv set interface bond2s0 evpn multihoming segment local-id 20
nv set interface bond2s1 bond member swp2s1
nv set interface bond2s1 evpn multihoming segment local-id 21
nv set interface bond2s2 bond member swp2s2
nv set interface bond2s2 evpn multihoming segment local-id 22
nv set interface bond2s3 bond member swp2s3
nv set interface bond2s3 evpn multihoming segment local-id 23

nv set interface bond3s0 bond member swp3s0
nv set interface bond3s0 evpn multihoming segment local-id 30
nv set interface bond3s1 bond member swp3s1
nv set interface bond3s1 evpn multihoming segment local-id 31
nv set interface bond3s2 bond member swp3s2
nv set interface bond3s2 evpn multihoming segment local-id 32
nv set interface bond3s3 bond member swp3s3
nv set interface bond3s3 evpn multihoming segment local-id 33

# CPU role - 3 ports, 12 bonds
nv set interface bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3,bond3s0,bond3s1,bond3s2,bond3s3 evpn multihoming segment state enabled
nv set interface bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3,bond3s0,bond3s1,bond3s2,bond3s3 evpn multihoming segment mac-address 44:38:39:FF:00:AA
nv set interface bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3,bond3s0,bond3s1,bond3s2,bond3s3 type bond
nv set interface bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3,bond3s0,bond3s1,bond3s2,bond3s3 bridge domain br_default access 300
nv set interface bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3,bond3s0,bond3s1,bond3s2,bond3s3 bond lacp-bypass enabled

nv set interface bond55s0 bond member swp55s0
nv set interface bond55s0 evpn multihoming segment local-id 550
nv set interface bond55s1 bond member swp55s1
nv set interface bond55s1 evpn multihoming segment local-id 551
nv set interface bond55s2 bond member swp55s2
nv set interface bond55s2 evpn multihoming segment local-id 552
nv set interface bond55s3 bond member swp55s3
nv set interface bond55s3 evpn multihoming segment local-id 553
nv set interface bond55s4 bond member swp55s4
nv set interface bond55s4 evpn multihoming segment local-id 554
nv set interface bond55s5 bond member swp55s5
nv set interface bond55s5 evpn multihoming segment local-id 555
nv set interface bond55s6 bond member swp55s6
nv set interface bond55s6 evpn multihoming segment local-id 556
nv set interface bond55s7 bond member swp55s7
nv set interface bond55s7 evpn multihoming segment local-id 557

# OOB role - 1 ports, 8 bonds
nv set interface bond55s0,bond55s1,bond55s2,bond55s3,bond55s4,bond55s5,bond55s6,bond55s7 evpn multihoming segment state enabled
nv set interface bond55s0,bond55s1,bond55s2,bond55s3,bond55s4,bond55s5,bond55s6,bond55s7 evpn multihoming segment mac-address 44:38:39:FF:00:AA
nv set interface bond55s0,bond55s1,bond55s2,bond55s3,bond55s4,bond55s5,bond55s6,bond55s7 type bond
nv set interface bond55s0,bond55s1,bond55s2,bond55s3,bond55s4,bond55s5,bond55s6,bond55s7 bridge domain br_default access 200

nv set interface bond57s0 bond member swp57s0
nv set interface bond57s0 evpn multihoming segment local-id 570
nv set interface bond57s1 bond member swp57s1
nv set interface bond57s1 evpn multihoming segment local-id 571
nv set interface bond57s2 bond member swp57s2
nv set interface bond57s2 evpn multihoming segment local-id 572
nv set interface bond57s3 bond member swp57s3
nv set interface bond57s3 evpn multihoming segment local-id 573
nv set interface bond57s4 bond member swp57s4
nv set interface bond57s4 evpn multihoming segment local-id 574
nv set interface bond57s5 bond member swp57s5
nv set interface bond57s5 evpn multihoming segment local-id 575
nv set interface bond57s6 bond member swp57s6
nv set interface bond57s6 evpn multihoming segment local-id 576
nv set interface bond57s7 bond member swp57s7
nv set interface bond57s7 evpn multihoming segment local-id 577

# STORAGE role - 1 ports, 8 bonds
nv set interface bond57s0,bond57s1,bond57s2,bond57s3,bond57s4,bond57s5,bond57s6,bond57s7 evpn multihoming segment state enabled
nv set interface bond57s0,bond57s1,bond57s2,bond57s3,bond57s4,bond57s5,bond57s6,bond57s7 evpn multihoming segment mac-address 44:38:39:FF:00:AA
nv set interface bond57s0,bond57s1,bond57s2,bond57s3,bond57s4,bond57s5,bond57s6,bond57s7 type bond
nv set interface bond57s0,bond57s1,bond57s2,bond57s3,bond57s4,bond57s5,bond57s6,bond57s7 bridge domain br_default access 500
nv set interface bond57s0,bond57s1,bond57s2,bond57s3,bond57s4,bond57s5,bond57s6,bond57s7 bond lacp-bypass enabled

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
nv set interface swp1,4-11,28-53,55,57,61,63 link state up

#============================================================================
# Direct Interfaces (Non-Bonded) - GPU, ISL, Edge
#============================================================================
# GPU role - direct interfaces
nv set interface swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp18s0,swp18s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1 bridge domain br_default access 900

# GPU role - QoS PFC watchdog
nv set interface swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp18s0,swp18s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1 qos pfc-watchdog state enable

# ISL role - direct interfaces
nv set interface swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp51s0,swp51s1 description 'ISL to other core switch'
nv set interface swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp51s0,swp51s1 evpn multihoming uplink enabled

# EDGE role - direct interfaces
nv set interface swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5 description 'Edge uplinks'
nv set interface swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5 vrf EXIT

#============================================================================
# Disabled Interfaces / Link State Down
#============================================================================
nv set interface swp2-3,12-27 link state down

#============================================================================
# All Switch Ports Type and Telemetry
#============================================================================

nv set interface swp1-64,swp52s0,swp52s1,swp52s2,swp52s3,swp53s0,swp53s1,swp53s2,swp53s3,swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp57s6,swp57s7,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp18s0,swp18s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp51s0,swp51s1,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5 type swp

nv set interface swp52s0,swp52s1,swp52s2,swp52s3,swp53s0,swp53s1,swp53s2,swp53s3,swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp57s6,swp57s7,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp18s0,swp18s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp51s0,swp51s1,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5 telemetry histogram counter counter-type rx-packet
nv set interface swp52s0,swp52s1,swp52s2,swp52s3,swp53s0,swp53s1,swp53s2,swp53s3,swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp57s6,swp57s7,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp18s0,swp18s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp51s0,swp51s1,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5 telemetry histogram counter counter-type tx-packet
nv set interface swp52s0,swp52s1,swp52s2,swp52s3,swp53s0,swp53s1,swp53s2,swp53s3,swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp57s6,swp57s7,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp18s0,swp18s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp51s0,swp51s1,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5 telemetry histogram egress-buffer traffic-class 0
nv set interface swp52s0,swp52s1,swp52s2,swp52s3,swp53s0,swp53s1,swp53s2,swp53s3,swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp57s6,swp57s7,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp18s0,swp18s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp51s0,swp51s1,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5 telemetry histogram ingress-buffer priority-group 0
nv set interface swp52s0,swp52s1,swp52s2,swp52s3,swp53s0,swp53s1,swp53s2,swp53s3,swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp57s6,swp57s7,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp18s0,swp18s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp51s0,swp51s1,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5 telemetry histogram ingress-buffer priority-group 1

#============================================================================
# VLAN SVIs (from host_vars)
#============================================================================
nv set interface vlan200 ipv4 address 172.16.177.3/24
nv set interface vlan200 ipv4 vrr address 172.16.177.1/24
nv set interface vlan200 ipv4 vrr state enabled
nv set interface vlan200 ipv4 vrr vrr-state up
nv set interface vlan200 type svi
nv set interface vlan200 vlan 200
nv set interface vlan200 vrf OOB
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
nv set interface vlan500 vrf INBAND
nv set interface vlan900 ipv4 address 192.168.110.3/24
nv set interface vlan900 ipv4 vrr address 192.168.110.1/24
nv set interface vlan900 ipv4 vrr state enabled
nv set interface vlan900 ipv4 vrr vrr-state up
nv set interface vlan900 type svi
nv set interface vlan900 vlan 900
nv set interface vlan900 vrf GPU

#============================================================================
# NVE / VXLAN
#============================================================================
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
nv set router policy prefix-list INBAND_LOCAL_IF rule 40 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 40 match 172.16.180.3/32 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 10 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 10 match 172.16.178.0/24 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 20 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 20 match 172.16.179.0/24 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 30 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 30 match 172.16.180.0/24 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 40 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 40 match 172.16.176.4/32 max-prefix-len 32
nv set router policy prefix-list ERA_PREFIXES rule 10 action permit
nv set router policy prefix-list ERA_PREFIXES rule 10 match 172.16.176.0/21 max-prefix-len 24
nv set router policy prefix-list ERA_PREFIXES rule 20 action permit
nv set router policy prefix-list ERA_PREFIXES rule 20 match 172.16.176.0/24 max-prefix-len 32
nv set router policy prefix-list LOCAL_OOB_LOOPBACK rule 10 action permit
nv set router policy prefix-list LOCAL_OOB_LOOPBACK rule 10 match 172.16.176.2/32 max-prefix-len 32
nv set router policy prefix-list OOB_LOCAL_IF rule 10 action permit
nv set router policy prefix-list OOB_LOCAL_IF rule 10 match 172.16.176.2/32 max-prefix-len 32
nv set router policy prefix-list OOB_LOCAL_IF rule 20 action permit
nv set router policy prefix-list OOB_LOCAL_IF rule 20 match 172.16.177.3/32 max-prefix-len 32
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

nv set vrf EXIT router bgp neighbor swp61s0-5,swp63s0-5 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp61s0-5,swp63s0-5 type unnumbered
nv set vrf EXIT router bgp neighbor swp61s0-5,swp63s0-5 update-source 172.16.176.12

nv set vrf EXIT router bgp peer-group underlay-esl-external address-family ipv4-unicast state enabled
nv set vrf EXIT router bgp peer-group underlay-esl-external address-family ipv4-unicast policy outbound route-map OUTBOUND_ERA_PREFIXES
nv set vrf EXIT router bgp peer-group underlay-esl-external remote-as external

nv set vrf EXIT router bgp rd 172.16.176.12:5004
nv set vrf EXIT router bgp route-export
nv set vrf EXIT router bgp router-id 172.16.176.12

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

nv set vrf INBAND router bgp rd 172.16.176.12:5002
nv set vrf INBAND router bgp route-export
nv set vrf INBAND router bgp route-import
nv set vrf INBAND router bgp router-id 172.16.176.12

nv set vrf GPU evpn state enabled
nv set vrf GPU evpn vlan 3003
nv set vrf GPU evpn vni 5003

nv set vrf GPU loopback ip address 192.168.110.6/32

nv set vrf GPU router bgp address-family ipv4-unicast state enabled
nv set vrf GPU router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf GPU router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf GPU router bgp address-family l2vpn-evpn state enabled

nv set vrf GPU router bgp autonomous-system 4260394788
nv set vrf GPU router bgp state enabled

nv set vrf GPU router bgp rd 172.16.176.12:5003
nv set vrf GPU router bgp router-id 172.16.176.12

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

nv set vrf OOB router bgp rd 172.16.176.12:5001
nv set vrf OOB router bgp router-id 172.16.176.12

#============================================================================
# Default VRF BGP (ISL Underlay)
#============================================================================
nv set vrf default router bgp address-family ipv4-unicast state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf default router bgp address-family l2vpn-evpn state enabled

nv set vrf default router bgp state enabled

nv set vrf default router bgp neighbor swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1,swp48s0-1,swp49s0-1,swp50s0-1,swp51s0-1 peer-group underlay
nv set vrf default router bgp neighbor swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1,swp48s0-1,swp49s0-1,swp50s0-1,swp51s0-1 ttl-security hops 1
nv set vrf default router bgp neighbor swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1,swp48s0-1,swp49s0-1,swp50s0-1,swp51s0-1 type unnumbered
nv set vrf default router bgp neighbor swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1,swp48s0-1,swp49s0-1,swp50s0-1,swp51s0-1 update-source 172.16.176.12

nv set vrf default router bgp peer-group underlay address-family l2vpn-evpn state enabled
nv set vrf default router bgp peer-group underlay bfd profile default
nv set vrf default router bgp peer-group underlay description underlay_switch_interconnect
nv set vrf default router bgp peer-group underlay remote-as internal
nv set vrf default router bgp peer-group underlay-esl-external address-family ipv4-unicast state enabled
nv set vrf default router bgp peer-group underlay-esl-external address-family ipv4-unicast policy outbound route-map OUTBOUND_ERA_PREFIXES
nv set vrf default router bgp peer-group underlay-esl-external bfd profile default
nv set vrf default router bgp peer-group underlay-esl-external description underlay_esl_external_interconnect
nv set vrf default router bgp peer-group underlay-esl-external remote-as external

#============================================================================
# DHCP Relay
#============================================================================
nv set service dhcp-relay EXIT server-group exit-servers server 192.168.210.41
nv set service dhcp-relay EXIT server-group exit-servers server 192.168.220.42
nv set service dhcp-relay EXIT server-group exit-servers upstream-interface vlan3004_l3
nv set service dhcp-relay EXIT downstream-interface swp61s0 server-group-name exit-servers
nv set service dhcp-relay EXIT downstream-interface swp61s1 server-group-name exit-servers
nv set service dhcp-relay EXIT downstream-interface swp61s2 server-group-name exit-servers
nv set service dhcp-relay EXIT downstream-interface swp61s3 server-group-name exit-servers
nv set service dhcp-relay EXIT downstream-interface swp61s4 server-group-name exit-servers
nv set service dhcp-relay EXIT downstream-interface swp61s5 server-group-name exit-servers
nv set service dhcp-relay EXIT downstream-interface swp63s0 server-group-name exit-servers
nv set service dhcp-relay EXIT downstream-interface swp63s1 server-group-name exit-servers
nv set service dhcp-relay EXIT downstream-interface swp63s2 server-group-name exit-servers
nv set service dhcp-relay EXIT downstream-interface swp63s3 server-group-name exit-servers
nv set service dhcp-relay EXIT downstream-interface swp63s4 server-group-name exit-servers
nv set service dhcp-relay EXIT downstream-interface swp63s5 server-group-name exit-servers
nv set service dhcp-relay EXIT gateway-interface vlan3004_l3
nv set service dhcp-relay OOB server-group oob-servers server 192.168.200.2
nv set service dhcp-relay OOB server-group oob-servers server 192.168.200.3
nv set service dhcp-relay OOB server-group oob-servers server 192.168.200.4
nv set service dhcp-relay OOB server-group oob-servers upstream-interface vlan3001_l3
nv set service dhcp-relay OOB downstream-interface vlan200 server-group-name oob-servers
nv set service dhcp-relay OOB gateway-interface vlan3001_l3

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
nv set system hostname core-02
nv set system message post-login '#####################################################################################
#                     You are successfully logged in to: core-02                    #
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
