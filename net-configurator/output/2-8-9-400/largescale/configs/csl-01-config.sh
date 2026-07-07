#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# NVUE CLI Configuration for csl-01
# Generated: 2026-07-03T00:13:08Z
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
nv set interface swp1,swp2,swp3,swp4,swp5,swp6,swp7,swp8,swp9,swp10,swp11,swp12,swp13,swp14,swp15,swp16,swp19,swp17,swp18 link breakout 4x lanes-per-port 2
nv set interface swp23,swp24,swp25,swp26,swp27,swp28,swp29,swp30,swp31,swp32,swp33,swp34,swp35,swp36,swp37,swp38 link breakout 2x lanes-per-port 4
nv set interface swp55,swp61,swp63 link breakout 8x lanes-per-port 1

nv set interface swp56,swp62,swp64 link breakout disabled

#============================================================================
# Bond Interfaces - Auto-Generated from Network Roles
#============================================================================

nv set interface bond1s0 bond member swp1s0
nv set interface bond1s0 evpn multihoming segment local-id 10
nv set interface bond1s0 description su-01-node-01
nv set interface bond1s1 bond member swp1s1
nv set interface bond1s1 evpn multihoming segment local-id 11
nv set interface bond1s1 description su-01-node-02
nv set interface bond1s2 bond member swp1s2
nv set interface bond1s2 evpn multihoming segment local-id 12
nv set interface bond1s2 description su-01-node-03
nv set interface bond1s3 bond member swp1s3
nv set interface bond1s3 evpn multihoming segment local-id 13
nv set interface bond1s3 description su-01-node-04

nv set interface bond2s0 bond member swp2s0
nv set interface bond2s0 evpn multihoming segment local-id 20
nv set interface bond2s0 description su-02-node-01
nv set interface bond2s1 bond member swp2s1
nv set interface bond2s1 evpn multihoming segment local-id 21
nv set interface bond2s1 description su-02-node-02
nv set interface bond2s2 bond member swp2s2
nv set interface bond2s2 evpn multihoming segment local-id 22
nv set interface bond2s2 description su-02-node-03
nv set interface bond2s3 bond member swp2s3
nv set interface bond2s3 evpn multihoming segment local-id 23
nv set interface bond2s3 description su-02-node-04

nv set interface bond3s0 bond member swp3s0
nv set interface bond3s0 evpn multihoming segment local-id 30
nv set interface bond3s0 description su-03-node-01
nv set interface bond3s1 bond member swp3s1
nv set interface bond3s1 evpn multihoming segment local-id 31
nv set interface bond3s1 description su-03-node-02
nv set interface bond3s2 bond member swp3s2
nv set interface bond3s2 evpn multihoming segment local-id 32
nv set interface bond3s2 description su-03-node-03
nv set interface bond3s3 bond member swp3s3
nv set interface bond3s3 evpn multihoming segment local-id 33
nv set interface bond3s3 description su-03-node-04

nv set interface bond4s0 bond member swp4s0
nv set interface bond4s0 evpn multihoming segment local-id 40
nv set interface bond4s0 description su-04-node-01
nv set interface bond4s1 bond member swp4s1
nv set interface bond4s1 evpn multihoming segment local-id 41
nv set interface bond4s1 description su-04-node-02
nv set interface bond4s2 bond member swp4s2
nv set interface bond4s2 evpn multihoming segment local-id 42
nv set interface bond4s2 description su-04-node-03
nv set interface bond4s3 bond member swp4s3
nv set interface bond4s3 evpn multihoming segment local-id 43
nv set interface bond4s3 description su-04-node-04

nv set interface bond5s0 bond member swp5s0
nv set interface bond5s0 evpn multihoming segment local-id 50
nv set interface bond5s0 description su-05-node-01
nv set interface bond5s1 bond member swp5s1
nv set interface bond5s1 evpn multihoming segment local-id 51
nv set interface bond5s1 description su-05-node-02
nv set interface bond5s2 bond member swp5s2
nv set interface bond5s2 evpn multihoming segment local-id 52
nv set interface bond5s2 description su-05-node-03
nv set interface bond5s3 bond member swp5s3
nv set interface bond5s3 evpn multihoming segment local-id 53
nv set interface bond5s3 description su-05-node-04

nv set interface bond6s0 bond member swp6s0
nv set interface bond6s0 evpn multihoming segment local-id 60
nv set interface bond6s0 description su-06-node-01
nv set interface bond6s1 bond member swp6s1
nv set interface bond6s1 evpn multihoming segment local-id 61
nv set interface bond6s1 description su-06-node-02
nv set interface bond6s2 bond member swp6s2
nv set interface bond6s2 evpn multihoming segment local-id 62
nv set interface bond6s2 description su-06-node-03
nv set interface bond6s3 bond member swp6s3
nv set interface bond6s3 evpn multihoming segment local-id 63
nv set interface bond6s3 description su-06-node-04

nv set interface bond7s0 bond member swp7s0
nv set interface bond7s0 evpn multihoming segment local-id 70
nv set interface bond7s0 description su-07-node-01
nv set interface bond7s1 bond member swp7s1
nv set interface bond7s1 evpn multihoming segment local-id 71
nv set interface bond7s1 description su-07-node-02
nv set interface bond7s2 bond member swp7s2
nv set interface bond7s2 evpn multihoming segment local-id 72
nv set interface bond7s2 description su-07-node-03
nv set interface bond7s3 bond member swp7s3
nv set interface bond7s3 evpn multihoming segment local-id 73
nv set interface bond7s3 description su-07-node-04

nv set interface bond8s0 bond member swp8s0
nv set interface bond8s0 evpn multihoming segment local-id 80
nv set interface bond8s0 description su-08-node-01
nv set interface bond8s1 bond member swp8s1
nv set interface bond8s1 evpn multihoming segment local-id 81
nv set interface bond8s1 description su-08-node-02
nv set interface bond8s2 bond member swp8s2
nv set interface bond8s2 evpn multihoming segment local-id 82
nv set interface bond8s2 description su-08-node-03
nv set interface bond8s3 bond member swp8s3
nv set interface bond8s3 evpn multihoming segment local-id 83
nv set interface bond8s3 description su-08-node-04

nv set interface bond9s0 bond member swp9s0
nv set interface bond9s0 evpn multihoming segment local-id 90
nv set interface bond9s0 description su-09-node-01
nv set interface bond9s1 bond member swp9s1
nv set interface bond9s1 evpn multihoming segment local-id 91
nv set interface bond9s1 description su-09-node-02
nv set interface bond9s2 bond member swp9s2
nv set interface bond9s2 evpn multihoming segment local-id 92
nv set interface bond9s2 description su-09-node-03
nv set interface bond9s3 bond member swp9s3
nv set interface bond9s3 evpn multihoming segment local-id 93
nv set interface bond9s3 description su-09-node-04

nv set interface bond10s0 bond member swp10s0
nv set interface bond10s0 evpn multihoming segment local-id 100
nv set interface bond10s0 description su-10-node-01
nv set interface bond10s1 bond member swp10s1
nv set interface bond10s1 evpn multihoming segment local-id 101
nv set interface bond10s1 description su-10-node-02
nv set interface bond10s2 bond member swp10s2
nv set interface bond10s2 evpn multihoming segment local-id 102
nv set interface bond10s2 description su-10-node-03
nv set interface bond10s3 bond member swp10s3
nv set interface bond10s3 evpn multihoming segment local-id 103
nv set interface bond10s3 description su-10-node-04

nv set interface bond11s0 bond member swp11s0
nv set interface bond11s0 evpn multihoming segment local-id 110
nv set interface bond11s0 description su-11-node-01
nv set interface bond11s1 bond member swp11s1
nv set interface bond11s1 evpn multihoming segment local-id 111
nv set interface bond11s1 description su-11-node-02
nv set interface bond11s2 bond member swp11s2
nv set interface bond11s2 evpn multihoming segment local-id 112
nv set interface bond11s2 description su-11-node-03
nv set interface bond11s3 bond member swp11s3
nv set interface bond11s3 evpn multihoming segment local-id 113
nv set interface bond11s3 description su-11-node-04

nv set interface bond12s0 bond member swp12s0
nv set interface bond12s0 evpn multihoming segment local-id 120
nv set interface bond12s0 description su-12-node-01
nv set interface bond12s1 bond member swp12s1
nv set interface bond12s1 evpn multihoming segment local-id 121
nv set interface bond12s1 description su-12-node-02
nv set interface bond12s2 bond member swp12s2
nv set interface bond12s2 evpn multihoming segment local-id 122
nv set interface bond12s2 description su-12-node-03
nv set interface bond12s3 bond member swp12s3
nv set interface bond12s3 evpn multihoming segment local-id 123
nv set interface bond12s3 description su-12-node-04

nv set interface bond13s0 bond member swp13s0
nv set interface bond13s0 evpn multihoming segment local-id 130
nv set interface bond13s0 description su-13-node-01
nv set interface bond13s1 bond member swp13s1
nv set interface bond13s1 evpn multihoming segment local-id 131
nv set interface bond13s1 description su-13-node-02
nv set interface bond13s2 bond member swp13s2
nv set interface bond13s2 evpn multihoming segment local-id 132
nv set interface bond13s2 description su-13-node-03
nv set interface bond13s3 bond member swp13s3
nv set interface bond13s3 evpn multihoming segment local-id 133
nv set interface bond13s3 description su-13-node-04

nv set interface bond14s0 bond member swp14s0
nv set interface bond14s0 evpn multihoming segment local-id 140
nv set interface bond14s0 description su-14-node-01
nv set interface bond14s1 bond member swp14s1
nv set interface bond14s1 evpn multihoming segment local-id 141
nv set interface bond14s1 description su-14-node-02
nv set interface bond14s2 bond member swp14s2
nv set interface bond14s2 evpn multihoming segment local-id 142
nv set interface bond14s2 description su-14-node-03
nv set interface bond14s3 bond member swp14s3
nv set interface bond14s3 evpn multihoming segment local-id 143
nv set interface bond14s3 description su-14-node-04

nv set interface bond15s0 bond member swp15s0
nv set interface bond15s0 evpn multihoming segment local-id 150
nv set interface bond15s0 description su-15-node-01
nv set interface bond15s1 bond member swp15s1
nv set interface bond15s1 evpn multihoming segment local-id 151
nv set interface bond15s1 description su-15-node-02
nv set interface bond15s2 bond member swp15s2
nv set interface bond15s2 evpn multihoming segment local-id 152
nv set interface bond15s2 description su-15-node-03
nv set interface bond15s3 bond member swp15s3
nv set interface bond15s3 evpn multihoming segment local-id 153
nv set interface bond15s3 description su-15-node-04

nv set interface bond16s0 bond member swp16s0
nv set interface bond16s0 evpn multihoming segment local-id 160
nv set interface bond16s0 description su-16-node-01
nv set interface bond16s1 bond member swp16s1
nv set interface bond16s1 evpn multihoming segment local-id 161
nv set interface bond16s1 description su-16-node-02
nv set interface bond16s2 bond member swp16s2
nv set interface bond16s2 evpn multihoming segment local-id 162
nv set interface bond16s2 description su-16-node-03
nv set interface bond16s3 bond member swp16s3
nv set interface bond16s3 evpn multihoming segment local-id 163
nv set interface bond16s3 description su-16-node-04

nv set interface bond19s0 bond member swp19s0
nv set interface bond19s0 evpn multihoming segment local-id 190
nv set interface bond19s0 description support-01
nv set interface bond19s1 bond member swp19s1
nv set interface bond19s1 evpn multihoming segment local-id 191
nv set interface bond19s1 description support-02

# CPU role - 17 ports, 66 bonds
nv set interface bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3,bond3s0,bond3s1,bond3s2,bond3s3,bond4s0,bond4s1,bond4s2,bond4s3,bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2,bond6s3,bond7s0,bond7s1,bond7s2,bond7s3,bond8s0,bond8s1,bond8s2,bond8s3,bond9s0,bond9s1,bond9s2,bond9s3,bond10s0,bond10s1,bond10s2,bond10s3,bond11s0,bond11s1,bond11s2,bond11s3,bond12s0,bond12s1,bond12s2,bond12s3,bond13s0,bond13s1,bond13s2,bond13s3,bond14s0,bond14s1,bond14s2,bond14s3,bond15s0,bond15s1,bond15s2,bond15s3,bond16s0,bond16s1,bond16s2,bond16s3,bond19s0,bond19s1 evpn multihoming segment state enabled
nv set interface bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3,bond3s0,bond3s1,bond3s2,bond3s3,bond4s0,bond4s1,bond4s2,bond4s3,bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2,bond6s3,bond7s0,bond7s1,bond7s2,bond7s3,bond8s0,bond8s1,bond8s2,bond8s3,bond9s0,bond9s1,bond9s2,bond9s3,bond10s0,bond10s1,bond10s2,bond10s3,bond11s0,bond11s1,bond11s2,bond11s3,bond12s0,bond12s1,bond12s2,bond12s3,bond13s0,bond13s1,bond13s2,bond13s3,bond14s0,bond14s1,bond14s2,bond14s3,bond15s0,bond15s1,bond15s2,bond15s3,bond16s0,bond16s1,bond16s2,bond16s3,bond19s0,bond19s1 evpn multihoming segment mac-address 44:38:39:FF:00:AA
nv set interface bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3,bond3s0,bond3s1,bond3s2,bond3s3,bond4s0,bond4s1,bond4s2,bond4s3,bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2,bond6s3,bond7s0,bond7s1,bond7s2,bond7s3,bond8s0,bond8s1,bond8s2,bond8s3,bond9s0,bond9s1,bond9s2,bond9s3,bond10s0,bond10s1,bond10s2,bond10s3,bond11s0,bond11s1,bond11s2,bond11s3,bond12s0,bond12s1,bond12s2,bond12s3,bond13s0,bond13s1,bond13s2,bond13s3,bond14s0,bond14s1,bond14s2,bond14s3,bond15s0,bond15s1,bond15s2,bond15s3,bond16s0,bond16s1,bond16s2,bond16s3,bond19s0,bond19s1 type bond
nv set interface bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3,bond3s0,bond3s1,bond3s2,bond3s3,bond4s0,bond4s1,bond4s2,bond4s3,bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2,bond6s3,bond7s0,bond7s1,bond7s2,bond7s3,bond8s0,bond8s1,bond8s2,bond8s3,bond9s0,bond9s1,bond9s2,bond9s3,bond10s0,bond10s1,bond10s2,bond10s3,bond11s0,bond11s1,bond11s2,bond11s3,bond12s0,bond12s1,bond12s2,bond12s3,bond13s0,bond13s1,bond13s2,bond13s3,bond14s0,bond14s1,bond14s2,bond14s3,bond15s0,bond15s1,bond15s2,bond15s3,bond16s0,bond16s1,bond16s2,bond16s3,bond19s0,bond19s1 bridge domain br_default vlan 300,400
nv set interface bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3,bond3s0,bond3s1,bond3s2,bond3s3,bond4s0,bond4s1,bond4s2,bond4s3,bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2,bond6s3,bond7s0,bond7s1,bond7s2,bond7s3,bond8s0,bond8s1,bond8s2,bond8s3,bond9s0,bond9s1,bond9s2,bond9s3,bond10s0,bond10s1,bond10s2,bond10s3,bond11s0,bond11s1,bond11s2,bond11s3,bond12s0,bond12s1,bond12s2,bond12s3,bond13s0,bond13s1,bond13s2,bond13s3,bond14s0,bond14s1,bond14s2,bond14s3,bond15s0,bond15s1,bond15s2,bond15s3,bond16s0,bond16s1,bond16s2,bond16s3,bond19s0,bond19s1 bridge domain br_default untagged 300
nv set interface bond1s0,bond1s1,bond1s2,bond1s3,bond2s0,bond2s1,bond2s2,bond2s3,bond3s0,bond3s1,bond3s2,bond3s3,bond4s0,bond4s1,bond4s2,bond4s3,bond5s0,bond5s1,bond5s2,bond5s3,bond6s0,bond6s1,bond6s2,bond6s3,bond7s0,bond7s1,bond7s2,bond7s3,bond8s0,bond8s1,bond8s2,bond8s3,bond9s0,bond9s1,bond9s2,bond9s3,bond10s0,bond10s1,bond10s2,bond10s3,bond11s0,bond11s1,bond11s2,bond11s3,bond12s0,bond12s1,bond12s2,bond12s3,bond13s0,bond13s1,bond13s2,bond13s3,bond14s0,bond14s1,bond14s2,bond14s3,bond15s0,bond15s1,bond15s2,bond15s3,bond16s0,bond16s1,bond16s2,bond16s3,bond19s0,bond19s1 bond lacp-bypass enabled

nv set interface bond17s0 bond member swp17s0
nv set interface bond17s0 evpn multihoming segment local-id 170
nv set interface bond17s0 description storage-01
nv set interface bond17s1 bond member swp17s1
nv set interface bond17s1 evpn multihoming segment local-id 171
nv set interface bond17s1 description storage-01
nv set interface bond17s2 bond member swp17s2
nv set interface bond17s2 evpn multihoming segment local-id 172
nv set interface bond17s2 description storage-02
nv set interface bond17s3 bond member swp17s3
nv set interface bond17s3 evpn multihoming segment local-id 173
nv set interface bond17s3 description storage-02

nv set interface bond18s0 bond member swp18s0
nv set interface bond18s0 evpn multihoming segment local-id 180
nv set interface bond18s0 description storage-03
nv set interface bond18s1 bond member swp18s1
nv set interface bond18s1 evpn multihoming segment local-id 181
nv set interface bond18s1 description storage-03
nv set interface bond18s2 bond member swp18s2
nv set interface bond18s2 evpn multihoming segment local-id 182
nv set interface bond18s2 description storage-04
nv set interface bond18s3 bond member swp18s3
nv set interface bond18s3 evpn multihoming segment local-id 183
nv set interface bond18s3 description storage-04

# STORAGE role - 2 ports, 8 bonds
nv set interface bond17s0,bond17s1,bond17s2,bond17s3,bond18s0,bond18s1,bond18s2,bond18s3 evpn multihoming segment state enabled
nv set interface bond17s0,bond17s1,bond17s2,bond17s3,bond18s0,bond18s1,bond18s2,bond18s3 evpn multihoming segment mac-address 44:38:39:FF:00:AA
nv set interface bond17s0,bond17s1,bond17s2,bond17s3,bond18s0,bond18s1,bond18s2,bond18s3 type bond
nv set interface bond17s0,bond17s1,bond17s2,bond17s3,bond18s0,bond18s1,bond18s2,bond18s3 bridge domain br_default vlan 400,500
nv set interface bond17s0,bond17s1,bond17s2,bond17s3,bond18s0,bond18s1,bond18s2,bond18s3 bridge domain br_default untagged 300
nv set interface bond17s0,bond17s1,bond17s2,bond17s3,bond18s0,bond18s1,bond18s2,bond18s3 bond lacp-bypass enabled

#============================================================================
# Management Interface
#============================================================================
nv set interface eth0 type eth
nv set interface eth0 vrf mgmt

#============================================================================
# Loopback
#============================================================================
nv set interface lo ipv4 address 172.16.176.11/32
nv set interface lo type loopback

#============================================================================
# Physical Interfaces - State Up
#============================================================================

#============================================================================
# Direct Interfaces (Non-Bonded) - GPU, ISL, Edge
#============================================================================

# ISL role - direct interfaces
nv set interface swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1 description 'ISL to other core switch'
nv set interface swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1 evpn multihoming uplink enabled

# EDGE role - direct interfaces
nv set interface swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp61s6,swp61s7,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5,swp63s6,swp63s7 description 'Edge uplinks'
nv set interface swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp61s6,swp61s7,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5,swp63s6,swp63s7 vrf EXIT

# OOB role - direct L3 uplinks
nv set interface swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7 description 'OOB uplinks'

#============================================================================
# Disabled Interfaces / Link State Down
#============================================================================

#============================================================================
# All Switch Ports Type and Telemetry
#============================================================================

nv set interface swp20,swp21,swp22,swp39,swp40,swp41,swp42,swp43,swp44,swp45,swp46,swp47,swp48,swp49,swp50,swp51,swp52,swp53,swp54,swp57,swp58,swp59,swp60,swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp4s0,swp4s1,swp4s2,swp4s3,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp6s3,swp7s0,swp7s1,swp7s2,swp7s3,swp8s0,swp8s1,swp8s2,swp8s3,swp9s0,swp9s1,swp9s2,swp9s3,swp10s0,swp10s1,swp10s2,swp10s3,swp11s0,swp11s1,swp11s2,swp11s3,swp12s0,swp12s1,swp12s2,swp12s3,swp13s0,swp13s1,swp13s2,swp13s3,swp14s0,swp14s1,swp14s2,swp14s3,swp15s0,swp15s1,swp15s2,swp15s3,swp16s0,swp16s1,swp16s2,swp16s3,swp19s0,swp19s1,swp17s0,swp17s1,swp17s2,swp17s3,swp18s0,swp18s1,swp18s2,swp18s3,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp61s6,swp61s7,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5,swp63s6,swp63s7 type swp

nv set interface swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp4s0,swp4s1,swp4s2,swp4s3,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp6s3,swp7s0,swp7s1,swp7s2,swp7s3,swp8s0,swp8s1,swp8s2,swp8s3,swp9s0,swp9s1,swp9s2,swp9s3,swp10s0,swp10s1,swp10s2,swp10s3,swp11s0,swp11s1,swp11s2,swp11s3,swp12s0,swp12s1,swp12s2,swp12s3,swp13s0,swp13s1,swp13s2,swp13s3,swp14s0,swp14s1,swp14s2,swp14s3,swp15s0,swp15s1,swp15s2,swp15s3,swp16s0,swp16s1,swp16s2,swp16s3,swp19s0,swp19s1,swp17s0,swp17s1,swp17s2,swp17s3,swp18s0,swp18s1,swp18s2,swp18s3,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp61s6,swp61s7,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5,swp63s6,swp63s7 telemetry histogram counter counter-type rx-packet
nv set interface swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp4s0,swp4s1,swp4s2,swp4s3,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp6s3,swp7s0,swp7s1,swp7s2,swp7s3,swp8s0,swp8s1,swp8s2,swp8s3,swp9s0,swp9s1,swp9s2,swp9s3,swp10s0,swp10s1,swp10s2,swp10s3,swp11s0,swp11s1,swp11s2,swp11s3,swp12s0,swp12s1,swp12s2,swp12s3,swp13s0,swp13s1,swp13s2,swp13s3,swp14s0,swp14s1,swp14s2,swp14s3,swp15s0,swp15s1,swp15s2,swp15s3,swp16s0,swp16s1,swp16s2,swp16s3,swp19s0,swp19s1,swp17s0,swp17s1,swp17s2,swp17s3,swp18s0,swp18s1,swp18s2,swp18s3,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp61s6,swp61s7,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5,swp63s6,swp63s7 telemetry histogram counter counter-type tx-packet
nv set interface swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp4s0,swp4s1,swp4s2,swp4s3,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp6s3,swp7s0,swp7s1,swp7s2,swp7s3,swp8s0,swp8s1,swp8s2,swp8s3,swp9s0,swp9s1,swp9s2,swp9s3,swp10s0,swp10s1,swp10s2,swp10s3,swp11s0,swp11s1,swp11s2,swp11s3,swp12s0,swp12s1,swp12s2,swp12s3,swp13s0,swp13s1,swp13s2,swp13s3,swp14s0,swp14s1,swp14s2,swp14s3,swp15s0,swp15s1,swp15s2,swp15s3,swp16s0,swp16s1,swp16s2,swp16s3,swp19s0,swp19s1,swp17s0,swp17s1,swp17s2,swp17s3,swp18s0,swp18s1,swp18s2,swp18s3,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp61s6,swp61s7,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5,swp63s6,swp63s7 telemetry histogram egress-buffer traffic-class 0
nv set interface swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp4s0,swp4s1,swp4s2,swp4s3,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp6s3,swp7s0,swp7s1,swp7s2,swp7s3,swp8s0,swp8s1,swp8s2,swp8s3,swp9s0,swp9s1,swp9s2,swp9s3,swp10s0,swp10s1,swp10s2,swp10s3,swp11s0,swp11s1,swp11s2,swp11s3,swp12s0,swp12s1,swp12s2,swp12s3,swp13s0,swp13s1,swp13s2,swp13s3,swp14s0,swp14s1,swp14s2,swp14s3,swp15s0,swp15s1,swp15s2,swp15s3,swp16s0,swp16s1,swp16s2,swp16s3,swp19s0,swp19s1,swp17s0,swp17s1,swp17s2,swp17s3,swp18s0,swp18s1,swp18s2,swp18s3,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp61s6,swp61s7,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5,swp63s6,swp63s7 telemetry histogram ingress-buffer priority-group 0
nv set interface swp1s0,swp1s1,swp1s2,swp1s3,swp2s0,swp2s1,swp2s2,swp2s3,swp3s0,swp3s1,swp3s2,swp3s3,swp4s0,swp4s1,swp4s2,swp4s3,swp5s0,swp5s1,swp5s2,swp5s3,swp6s0,swp6s1,swp6s2,swp6s3,swp7s0,swp7s1,swp7s2,swp7s3,swp8s0,swp8s1,swp8s2,swp8s3,swp9s0,swp9s1,swp9s2,swp9s3,swp10s0,swp10s1,swp10s2,swp10s3,swp11s0,swp11s1,swp11s2,swp11s3,swp12s0,swp12s1,swp12s2,swp12s3,swp13s0,swp13s1,swp13s2,swp13s3,swp14s0,swp14s1,swp14s2,swp14s3,swp15s0,swp15s1,swp15s2,swp15s3,swp16s0,swp16s1,swp16s2,swp16s3,swp19s0,swp19s1,swp17s0,swp17s1,swp17s2,swp17s3,swp18s0,swp18s1,swp18s2,swp18s3,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp55s0,swp55s1,swp55s2,swp55s3,swp55s4,swp55s5,swp55s6,swp55s7,swp61s0,swp61s1,swp61s2,swp61s3,swp61s4,swp61s5,swp61s6,swp61s7,swp63s0,swp63s1,swp63s2,swp63s3,swp63s4,swp63s5,swp63s6,swp63s7 telemetry histogram ingress-buffer priority-group 1

#============================================================================
# VLAN SVIs (from host_vars)
#============================================================================
nv set interface vlan300 ipv4 address 172.16.178.2/24
nv set interface vlan300 ipv4 vrr address 172.16.178.1/24
nv set interface vlan300 ipv4 vrr state enabled
nv set interface vlan300 ipv4 vrr vrr-state up
nv set interface vlan300 type svi
nv set interface vlan300 vlan 300
nv set interface vlan300 vrf INBAND
nv set interface vlan400 ipv4 address 172.16.179.2/24
nv set interface vlan400 ipv4 vrr address 172.16.179.1/24
nv set interface vlan400 ipv4 vrr state enabled
nv set interface vlan400 ipv4 vrr vrr-state up
nv set interface vlan400 type svi
nv set interface vlan400 vlan 400
nv set interface vlan400 vrf INBAND
nv set interface vlan500 ipv4 address 172.16.180.2/24
nv set interface vlan500 ipv4 vrr address 172.16.180.1/24
nv set interface vlan500 ipv4 vrr state enabled
nv set interface vlan500 ipv4 vrr vrr-state up
nv set interface vlan500 type svi
nv set interface vlan500 vlan 500
nv set interface vlan500 vrf INBAND

#============================================================================
# NVE / VXLAN
#============================================================================
nv set nve vxlan arp-nd-suppress enabled
nv set nve vxlan decapsulation dscp action preserve
nv set nve vxlan state enabled
nv set nve vxlan encapsulation dscp action copy
nv set nve vxlan flooding state enabled
nv set nve vxlan flooding head-end-replication evpn
nv set nve vxlan source address 172.16.176.11

#============================================================================
# BGP - Underlay and EVPN
#============================================================================
nv set router bgp state enabled
nv set router bgp autonomous-system 4260394788
nv set router bgp router-id 172.16.176.11

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
nv set router policy prefix-list EXIT_LOCAL_IF rule 10 match 172.16.176.5/32 max-prefix-len 32
nv set router policy prefix-list INBAND_LOCAL_IF rule 10 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 10 match 172.16.176.41/32 max-prefix-len 32
nv set router policy prefix-list INBAND_LOCAL_IF rule 20 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 20 match 172.16.178.2/32 max-prefix-len 32
nv set router policy prefix-list INBAND_LOCAL_IF rule 30 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 30 match 172.16.179.2/32 max-prefix-len 32
nv set router policy prefix-list INBAND_LOCAL_IF rule 40 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 40 match 172.16.180.2/32 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 10 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 10 match 172.16.178.0/24 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 20 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 20 match 172.16.179.0/24 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 30 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 30 match 172.16.180.0/24 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 40 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 40 match 172.16.176.41/32 max-prefix-len 32
nv set router policy prefix-list ERA_PREFIXES rule 10 action permit
nv set router policy prefix-list ERA_PREFIXES rule 10 match 172.16.176.0/21 max-prefix-len 24
nv set router policy prefix-list ERA_PREFIXES rule 20 action permit
nv set router policy prefix-list ERA_PREFIXES rule 20 match 172.16.176.0/24 max-prefix-len 32
nv set router policy prefix-list ERA_PREFIXES rule 30 action permit
nv set router policy prefix-list ERA_PREFIXES rule 30 match 192.168.200.0/24 max-prefix-len 32
nv set router policy prefix-list LOCAL_OOB_LOOPBACK rule 10 action permit
nv set router policy prefix-list LOCAL_OOB_LOOPBACK rule 10 match 172.16.176.31/32 max-prefix-len 32
nv set router policy prefix-list OOB_LOCAL_IF rule 10 action permit
nv set router policy prefix-list OOB_LOCAL_IF rule 10 match 172.16.176.31/32 max-prefix-len 32
nv set router policy prefix-list OOB_PREFIXES rule 10 action permit
nv set router policy prefix-list OOB_PREFIXES rule 10 match 172.16.177.0/24 max-prefix-len 32
nv set router policy prefix-list OOB_PREFIXES rule 20 action permit
nv set router policy prefix-list OOB_PREFIXES rule 20 match 172.16.176.31/32 max-prefix-len 32
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

nv set vrf EXIT loopback ip address 172.16.176.5/32

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

nv set vrf EXIT router bgp neighbor swp61s0 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp61s0 type unnumbered
nv set vrf EXIT router bgp neighbor swp61s1 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp61s1 type unnumbered
nv set vrf EXIT router bgp neighbor swp61s2 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp61s2 type unnumbered
nv set vrf EXIT router bgp neighbor swp61s3 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp61s3 type unnumbered
nv set vrf EXIT router bgp neighbor swp61s4 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp61s4 type unnumbered
nv set vrf EXIT router bgp neighbor swp61s5 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp61s5 type unnumbered
nv set vrf EXIT router bgp neighbor swp61s6 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp61s6 type unnumbered
nv set vrf EXIT router bgp neighbor swp61s7 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp61s7 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s0 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp63s0 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s1 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp63s1 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s2 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp63s2 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s3 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp63s3 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s4 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp63s4 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s5 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp63s5 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s6 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp63s6 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s7 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp63s7 type unnumbered

nv set vrf EXIT router bgp peer-group underlay-esl-external address-family ipv4-unicast state enabled
nv set vrf EXIT router bgp peer-group underlay-esl-external address-family ipv4-unicast policy outbound route-map OUTBOUND_ERA_PREFIXES
nv set vrf EXIT router bgp peer-group underlay-esl-external remote-as external

nv set vrf EXIT router bgp route-export
nv set vrf EXIT router bgp router-id 172.16.176.5

nv set vrf INBAND evpn state enabled
nv set vrf INBAND evpn vlan 3002
nv set vrf INBAND evpn vni 5002

nv set vrf INBAND loopback ip address 172.16.176.41/32

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
nv set vrf INBAND router bgp router-id 172.16.176.41

nv set vrf OOB evpn state enabled
nv set vrf OOB evpn vlan 3001
nv set vrf OOB evpn vni 5001

nv set vrf OOB loopback ip address 172.16.176.31/32

nv set vrf OOB router bgp address-family ipv4-unicast state enabled
nv set vrf OOB router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf OOB router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf state enabled
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf list EXIT
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf route-map OOB_FILTER
nv set vrf OOB router bgp address-family l2vpn-evpn state enabled

nv set vrf OOB router bgp autonomous-system 4260394788
nv set vrf OOB router bgp state enabled

nv set vrf OOB router bgp router-id 172.16.176.31

#============================================================================
# Default VRF BGP (ISL Underlay)
#============================================================================
nv set vrf default router bgp address-family ipv4-unicast state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf default router bgp address-family l2vpn-evpn state enabled

nv set vrf default router bgp state enabled

nv set vrf default router bgp neighbor swp23s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp23s0 type unnumbered
nv set vrf default router bgp neighbor swp23s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp23s1 type unnumbered
nv set vrf default router bgp neighbor swp24s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp24s0 type unnumbered
nv set vrf default router bgp neighbor swp24s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp24s1 type unnumbered
nv set vrf default router bgp neighbor swp25s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp25s0 type unnumbered
nv set vrf default router bgp neighbor swp25s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp25s1 type unnumbered
nv set vrf default router bgp neighbor swp26s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp26s0 type unnumbered
nv set vrf default router bgp neighbor swp26s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp26s1 type unnumbered
nv set vrf default router bgp neighbor swp27s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp27s0 type unnumbered
nv set vrf default router bgp neighbor swp27s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp27s1 type unnumbered
nv set vrf default router bgp neighbor swp28s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp28s0 type unnumbered
nv set vrf default router bgp neighbor swp28s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp28s1 type unnumbered
nv set vrf default router bgp neighbor swp29s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp29s0 type unnumbered
nv set vrf default router bgp neighbor swp29s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp29s1 type unnumbered
nv set vrf default router bgp neighbor swp30s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp30s0 type unnumbered
nv set vrf default router bgp neighbor swp30s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp30s1 type unnumbered
nv set vrf default router bgp neighbor swp31s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp31s0 type unnumbered
nv set vrf default router bgp neighbor swp31s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp31s1 type unnumbered
nv set vrf default router bgp neighbor swp32s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp32s0 type unnumbered
nv set vrf default router bgp neighbor swp32s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp32s1 type unnumbered
nv set vrf default router bgp neighbor swp33s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp33s0 type unnumbered
nv set vrf default router bgp neighbor swp33s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp33s1 type unnumbered
nv set vrf default router bgp neighbor swp34s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp34s0 type unnumbered
nv set vrf default router bgp neighbor swp34s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp34s1 type unnumbered
nv set vrf default router bgp neighbor swp35s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp35s0 type unnumbered
nv set vrf default router bgp neighbor swp35s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp35s1 type unnumbered
nv set vrf default router bgp neighbor swp36s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp36s0 type unnumbered
nv set vrf default router bgp neighbor swp36s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp36s1 type unnumbered
nv set vrf default router bgp neighbor swp37s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp37s0 type unnumbered
nv set vrf default router bgp neighbor swp37s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp37s1 type unnumbered
nv set vrf default router bgp neighbor swp38s0 peer-group internal-isl
nv set vrf default router bgp neighbor swp38s0 type unnumbered
nv set vrf default router bgp neighbor swp38s1 peer-group internal-isl
nv set vrf default router bgp neighbor swp38s1 type unnumbered
nv set vrf default router bgp neighbor swp55s0 peer-group underlay
nv set vrf default router bgp neighbor swp55s0 type unnumbered
nv set vrf default router bgp neighbor swp55s1 peer-group underlay
nv set vrf default router bgp neighbor swp55s1 type unnumbered
nv set vrf default router bgp neighbor swp55s2 peer-group underlay
nv set vrf default router bgp neighbor swp55s2 type unnumbered
nv set vrf default router bgp neighbor swp55s3 peer-group underlay
nv set vrf default router bgp neighbor swp55s3 type unnumbered
nv set vrf default router bgp neighbor swp55s4 peer-group underlay
nv set vrf default router bgp neighbor swp55s4 type unnumbered
nv set vrf default router bgp neighbor swp55s5 peer-group underlay
nv set vrf default router bgp neighbor swp55s5 type unnumbered
nv set vrf default router bgp neighbor swp55s6 peer-group underlay
nv set vrf default router bgp neighbor swp55s6 type unnumbered
nv set vrf default router bgp neighbor swp55s7 peer-group underlay
nv set vrf default router bgp neighbor swp55s7 type unnumbered
nv set vrf default router bgp neighbor 172.16.176.101 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.101 type numbered
nv set vrf default router bgp neighbor 172.16.176.102 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.102 type numbered
nv set vrf default router bgp neighbor 172.16.176.103 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.103 type numbered
nv set vrf default router bgp neighbor 172.16.176.104 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.104 type numbered
nv set vrf default router bgp neighbor 172.16.176.105 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.105 type numbered
nv set vrf default router bgp neighbor 172.16.176.106 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.106 type numbered
nv set vrf default router bgp neighbor 172.16.176.107 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.107 type numbered
nv set vrf default router bgp neighbor 172.16.176.108 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.108 type numbered
nv set vrf default router bgp neighbor 172.16.176.109 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.109 type numbered
nv set vrf default router bgp neighbor 172.16.176.110 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.110 type numbered
nv set vrf default router bgp neighbor 172.16.176.111 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.111 type numbered
nv set vrf default router bgp neighbor 172.16.176.112 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.112 type numbered
nv set vrf default router bgp neighbor 172.16.176.113 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.113 type numbered
nv set vrf default router bgp neighbor 172.16.176.114 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.114 type numbered
nv set vrf default router bgp neighbor 172.16.176.115 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.115 type numbered
nv set vrf default router bgp neighbor 172.16.176.116 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.116 type numbered

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
nv set system hostname csl-01
nv set system message pre-login '##############################################################################
#      You are accessing an Information System (IS) that is provided for authorized use only.
##############################################################################'
nv set system message post-login '####################################################################
#       You are successfully logged in to: csl-01 - site: largescale / arch: 2-8-9-400
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
