#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# NVUE CLI Configuration for cl-01
# Generated: 2026-09-02T02:45:19Z
# Format: NVUE CLI commands (Simplified with Pure Jinja2)

#============================================================================
# Bridge and VLANs
#============================================================================
nv set bridge domain br_default type vlan-aware
nv set bridge domain br_default vlan 200 vni 4200
nv set bridge domain br_default vlan 300 vni 4300
nv set bridge domain br_default vlan 400 vni 4400

#============================================================================
# EVPN
#============================================================================
nv set evpn state enabled
nv set evpn multihoming state enabled

#============================================================================
# Breakout Configuration
#============================================================================
nv set interface swp59,swp60,swp61,swp62,swp63,swp64 link breakout 4x lanes-per-port 2
nv set interface swp1,swp2,swp3,swp4,swp5,swp6,swp7,swp8,swp9,swp10,swp11,swp12,swp13,swp14,swp15,swp16,swp17,swp19,swp20,swp21,swp22,swp23,swp24,swp25,swp26,swp27,swp28,swp29,swp30,swp31,swp32,swp33,swp34,swp35,swp36,swp37,swp38,swp39,swp40,swp41,swp42,swp43,swp44,swp45,swp46,swp47,swp48,swp49,swp50 link breakout 2x lanes-per-port 4
nv set interface swp57 link breakout 8x lanes-per-port 1
nv set interface swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5 link speed 100G
nv set interface swp61s0,swp61s1,swp61s2,swp61s3,swp62s0,swp62s1,swp62s2,swp62s3,swp63s0,swp63s1,swp63s2,swp63s3,swp64s0,swp64s1,swp64s2,swp64s3,swp59s0,swp59s1,swp59s2,swp59s3,swp60s0,swp60s1,swp60s2,swp60s3 link speed 200G
nv set interface swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1 link speed 400G

nv set interface swp58 link breakout disabled

#============================================================================
# Bond Interfaces - Auto-Generated from Network Roles
#============================================================================

nv set interface bond1s0 bond member swp1s0
nv set interface bond1s0 evpn multihoming segment local-id 1001
nv set interface bond1s0 description su-01-node-01
nv set interface bond1s1 bond member swp1s1
nv set interface bond1s1 evpn multihoming segment local-id 2001
nv set interface bond1s1 description su-02-node-01

nv set interface bond2s0 bond member swp2s0
nv set interface bond2s0 evpn multihoming segment local-id 3001
nv set interface bond2s0 description su-03-node-01
nv set interface bond2s1 bond member swp2s1
nv set interface bond2s1 evpn multihoming segment local-id 4001
nv set interface bond2s1 description su-04-node-01

nv set interface bond3s0 bond member swp3s0
nv set interface bond3s0 evpn multihoming segment local-id 5001
nv set interface bond3s0 description su-05-node-01
nv set interface bond3s1 bond member swp3s1
nv set interface bond3s1 evpn multihoming segment local-id 6001
nv set interface bond3s1 description su-06-node-01

nv set interface bond4s0 bond member swp4s0
nv set interface bond4s0 evpn multihoming segment local-id 7001
nv set interface bond4s0 description su-07-node-01
nv set interface bond4s1 bond member swp4s1
nv set interface bond4s1 evpn multihoming segment local-id 8001
nv set interface bond4s1 description su-08-node-01

nv set interface bond5s0 bond member swp5s0
nv set interface bond5s0 evpn multihoming segment local-id 9001
nv set interface bond5s0 description su-09-node-01
nv set interface bond5s1 bond member swp5s1
nv set interface bond5s1 evpn multihoming segment local-id 10001
nv set interface bond5s1 description su-10-node-01

nv set interface bond6s0 bond member swp6s0
nv set interface bond6s0 evpn multihoming segment local-id 11001
nv set interface bond6s0 description su-11-node-01
nv set interface bond6s1 bond member swp6s1
nv set interface bond6s1 evpn multihoming segment local-id 12001
nv set interface bond6s1 description su-12-node-01

nv set interface bond7s0 bond member swp7s0
nv set interface bond7s0 evpn multihoming segment local-id 13001
nv set interface bond7s0 description su-13-node-01
nv set interface bond7s1 bond member swp7s1
nv set interface bond7s1 evpn multihoming segment local-id 14001
nv set interface bond7s1 description su-14-node-01

nv set interface bond8s0 bond member swp8s0
nv set interface bond8s0 evpn multihoming segment local-id 15001
nv set interface bond8s0 description su-15-node-01
nv set interface bond8s1 bond member swp8s1
nv set interface bond8s1 evpn multihoming segment local-id 16001
nv set interface bond8s1 description su-16-node-01

nv set interface bond9s0 bond member swp9s0
nv set interface bond9s0 evpn multihoming segment local-id 17001
nv set interface bond9s0 description su-17-node-01
nv set interface bond9s1 bond member swp9s1
nv set interface bond9s1 evpn multihoming segment local-id 18001
nv set interface bond9s1 description su-18-node-01

nv set interface bond10s0 bond member swp10s0
nv set interface bond10s0 evpn multihoming segment local-id 19001
nv set interface bond10s0 description su-19-node-01
nv set interface bond10s1 bond member swp10s1
nv set interface bond10s1 evpn multihoming segment local-id 20001
nv set interface bond10s1 description su-20-node-01

nv set interface bond11s0 bond member swp11s0
nv set interface bond11s0 evpn multihoming segment local-id 21001
nv set interface bond11s0 description su-21-node-01
nv set interface bond11s1 bond member swp11s1
nv set interface bond11s1 evpn multihoming segment local-id 22001
nv set interface bond11s1 description su-22-node-01

nv set interface bond12s0 bond member swp12s0
nv set interface bond12s0 evpn multihoming segment local-id 23001
nv set interface bond12s0 description su-23-node-01
nv set interface bond12s1 bond member swp12s1
nv set interface bond12s1 evpn multihoming segment local-id 24001
nv set interface bond12s1 description su-24-node-01

nv set interface bond13s0 bond member swp13s0
nv set interface bond13s0 evpn multihoming segment local-id 25001
nv set interface bond13s0 description su-25-node-01
nv set interface bond13s1 bond member swp13s1
nv set interface bond13s1 evpn multihoming segment local-id 26001
nv set interface bond13s1 description su-26-node-01

nv set interface bond14s0 bond member swp14s0
nv set interface bond14s0 evpn multihoming segment local-id 27001
nv set interface bond14s0 description su-27-node-01
nv set interface bond14s1 bond member swp14s1
nv set interface bond14s1 evpn multihoming segment local-id 28001
nv set interface bond14s1 description su-28-node-01

nv set interface bond15s0 bond member swp15s0
nv set interface bond15s0 evpn multihoming segment local-id 29001
nv set interface bond15s0 description su-29-node-01
nv set interface bond15s1 bond member swp15s1
nv set interface bond15s1 evpn multihoming segment local-id 30001
nv set interface bond15s1 description su-30-node-01

nv set interface bond16s0 bond member swp16s0
nv set interface bond16s0 evpn multihoming segment local-id 31001
nv set interface bond16s0 description su-31-node-01
nv set interface bond16s1 bond member swp16s1
nv set interface bond16s1 evpn multihoming segment local-id 32001
nv set interface bond16s1 description su-32-node-01

# CPU role - 16 ports, 32 bonds
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1,bond5s0,bond5s1,bond6s0,bond6s1,bond7s0,bond7s1,bond8s0,bond8s1,bond9s0,bond9s1,bond10s0,bond10s1,bond11s0,bond11s1,bond12s0,bond12s1,bond13s0,bond13s1,bond14s0,bond14s1,bond15s0,bond15s1,bond16s0,bond16s1 evpn multihoming segment state enabled
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1,bond5s0,bond5s1,bond6s0,bond6s1,bond7s0,bond7s1,bond8s0,bond8s1,bond9s0,bond9s1,bond10s0,bond10s1,bond11s0,bond11s1,bond12s0,bond12s1,bond13s0,bond13s1,bond14s0,bond14s1,bond15s0,bond15s1,bond16s0,bond16s1 evpn multihoming segment mac-address 44:38:39:FF:00:AA
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1,bond5s0,bond5s1,bond6s0,bond6s1,bond7s0,bond7s1,bond8s0,bond8s1,bond9s0,bond9s1,bond10s0,bond10s1,bond11s0,bond11s1,bond12s0,bond12s1,bond13s0,bond13s1,bond14s0,bond14s1,bond15s0,bond15s1,bond16s0,bond16s1 type bond
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1,bond5s0,bond5s1,bond6s0,bond6s1,bond7s0,bond7s1,bond8s0,bond8s1,bond9s0,bond9s1,bond10s0,bond10s1,bond11s0,bond11s1,bond12s0,bond12s1,bond13s0,bond13s1,bond14s0,bond14s1,bond15s0,bond15s1,bond16s0,bond16s1 bridge domain br_default vlan 300,400
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1,bond5s0,bond5s1,bond6s0,bond6s1,bond7s0,bond7s1,bond8s0,bond8s1,bond9s0,bond9s1,bond10s0,bond10s1,bond11s0,bond11s1,bond12s0,bond12s1,bond13s0,bond13s1,bond14s0,bond14s1,bond15s0,bond15s1,bond16s0,bond16s1 bridge domain br_default untagged 300
nv set interface bond1s0,bond1s1,bond2s0,bond2s1,bond3s0,bond3s1,bond4s0,bond4s1,bond5s0,bond5s1,bond6s0,bond6s1,bond7s0,bond7s1,bond8s0,bond8s1,bond9s0,bond9s1,bond10s0,bond10s1,bond11s0,bond11s1,bond12s0,bond12s1,bond13s0,bond13s1,bond14s0,bond14s1,bond15s0,bond15s1,bond16s0,bond16s1 bond lacp-bypass enabled

nv set interface bond17s0 bond member swp17s0
nv set interface bond17s0 evpn multihoming segment local-id 800001
nv set interface bond17s0 description support-01
nv set interface bond17s1 bond member swp17s1
nv set interface bond17s1 evpn multihoming segment local-id 800005
nv set interface bond17s1 description support-05

# SUPPORT role - 1 ports, 2 bonds
nv set interface bond17s0,bond17s1 evpn multihoming segment state enabled
nv set interface bond17s0,bond17s1 evpn multihoming segment mac-address 44:38:39:FF:00:AA
nv set interface bond17s0,bond17s1 type bond
nv set interface bond17s0,bond17s1 bridge domain br_default vlan 200,300,400
nv set interface bond17s0,bond17s1 bridge domain br_default untagged 300
nv set interface bond17s0,bond17s1 bond lacp-bypass enabled

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
nv set interface swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1 description isl_to_peer_core_switch
nv set interface swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1 evpn multihoming uplink enabled

# EDGE role - direct interfaces
nv set interface swp61s0,swp61s1,swp61s2,swp61s3,swp62s0,swp62s1,swp62s2,swp62s3,swp63s0,swp63s1,swp63s2,swp63s3,swp64s0,swp64s1,swp64s2,swp64s3 description edge_uplink
nv set interface swp61s0,swp61s1,swp61s2,swp61s3,swp62s0,swp62s1,swp62s2,swp62s3,swp63s0,swp63s1,swp63s2,swp63s3,swp64s0,swp64s1,swp64s2,swp64s3 vrf EXIT

# OOB role - direct L3 uplinks
nv set interface swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5 description oob_uplink

# STORAGE role - L3 external uplinks
nv set interface swp59s0,swp59s1,swp59s2,swp59s3,swp60s0,swp60s1,swp60s2,swp60s3 description external_uplink_storage_vrf
nv set interface swp59s0,swp59s1,swp59s2,swp59s3,swp60s0,swp60s1,swp60s2,swp60s3 vrf STORAGE

#============================================================================
# Disabled Interfaces / Link State Down
#============================================================================

#============================================================================
# All Switch Ports Type and Telemetry
#============================================================================

nv set interface swp18,swp51,swp52,swp53,swp54,swp55,swp56,swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp61s0,swp61s1,swp61s2,swp61s3,swp62s0,swp62s1,swp62s2,swp62s3,swp63s0,swp63s1,swp63s2,swp63s3,swp64s0,swp64s1,swp64s2,swp64s3 type swp

nv set interface swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp61s0,swp61s1,swp61s2,swp61s3,swp62s0,swp62s1,swp62s2,swp62s3,swp63s0,swp63s1,swp63s2,swp63s3,swp64s0,swp64s1,swp64s2,swp64s3 telemetry histogram counter counter-type rx-packet
nv set interface swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp61s0,swp61s1,swp61s2,swp61s3,swp62s0,swp62s1,swp62s2,swp62s3,swp63s0,swp63s1,swp63s2,swp63s3,swp64s0,swp64s1,swp64s2,swp64s3 telemetry histogram counter counter-type tx-packet
nv set interface swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp61s0,swp61s1,swp61s2,swp61s3,swp62s0,swp62s1,swp62s2,swp62s3,swp63s0,swp63s1,swp63s2,swp63s3,swp64s0,swp64s1,swp64s2,swp64s3 telemetry histogram egress-buffer traffic-class 0
nv set interface swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp61s0,swp61s1,swp61s2,swp61s3,swp62s0,swp62s1,swp62s2,swp62s3,swp63s0,swp63s1,swp63s2,swp63s3,swp64s0,swp64s1,swp64s2,swp64s3 telemetry histogram ingress-buffer priority-group 0
nv set interface swp1s0,swp1s1,swp2s0,swp2s1,swp3s0,swp3s1,swp4s0,swp4s1,swp5s0,swp5s1,swp6s0,swp6s1,swp7s0,swp7s1,swp8s0,swp8s1,swp9s0,swp9s1,swp10s0,swp10s1,swp11s0,swp11s1,swp12s0,swp12s1,swp13s0,swp13s1,swp14s0,swp14s1,swp15s0,swp15s1,swp16s0,swp16s1,swp17s0,swp17s1,swp19s0,swp19s1,swp20s0,swp20s1,swp21s0,swp21s1,swp22s0,swp22s1,swp23s0,swp23s1,swp24s0,swp24s1,swp25s0,swp25s1,swp26s0,swp26s1,swp27s0,swp27s1,swp28s0,swp28s1,swp29s0,swp29s1,swp30s0,swp30s1,swp31s0,swp31s1,swp32s0,swp32s1,swp33s0,swp33s1,swp34s0,swp34s1,swp35s0,swp35s1,swp36s0,swp36s1,swp37s0,swp37s1,swp38s0,swp38s1,swp39s0,swp39s1,swp40s0,swp40s1,swp41s0,swp41s1,swp42s0,swp42s1,swp43s0,swp43s1,swp44s0,swp44s1,swp45s0,swp45s1,swp46s0,swp46s1,swp47s0,swp47s1,swp48s0,swp48s1,swp49s0,swp49s1,swp50s0,swp50s1,swp57s0,swp57s1,swp57s2,swp57s3,swp57s4,swp57s5,swp61s0,swp61s1,swp61s2,swp61s3,swp62s0,swp62s1,swp62s2,swp62s3,swp63s0,swp63s1,swp63s2,swp63s3,swp64s0,swp64s1,swp64s2,swp64s3 telemetry histogram ingress-buffer priority-group 1

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
nv set router bgp autonomous-system 4260395189
nv set router bgp router-id 172.16.176.11

nv set router bfd state enabled
nv set router bfd profile underlay detect-multiplier 3
nv set router bfd profile underlay min-rx-interval 300
nv set router bfd profile underlay min-tx-interval 300
nv set router bfd profile overlay detect-multiplier 3
nv set router bfd profile overlay min-rx-interval 1000
nv set router bfd profile overlay min-tx-interval 1000
nv set router bfd profile storage detect-multiplier 3
nv set router bfd profile storage min-rx-interval 300
nv set router bfd profile storage min-tx-interval 300
nv set router bfd offload enabled

nv set vrf default router bgp path-selection multipath aspath-ignore enabled
nv set vrf default router bgp address-family ipv4-unicast multipaths ebgp 128

nv set router policy prefix-list ALL_PREFIXES rule 10 action permit
nv set router policy prefix-list ALL_PREFIXES rule 10 match 0.0.0.0/0 max-prefix-len 32
nv set router policy prefix-list EXIT_LOCAL_IF rule 10 action permit
nv set router policy prefix-list EXIT_LOCAL_IF rule 10 match 172.16.176.183/32 max-prefix-len 32
nv set router policy prefix-list INBAND_LOCAL_IF rule 10 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 10 match 172.16.176.167/32 max-prefix-len 32
nv set router policy prefix-list INBAND_LOCAL_IF rule 20 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 20 match 172.16.178.2/32 max-prefix-len 32
nv set router policy prefix-list INBAND_LOCAL_IF rule 30 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 30 match 172.16.179.2/32 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 10 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 10 match 172.16.178.0/24 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 20 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 20 match 172.16.179.0/24 max-prefix-len 32
nv set router policy prefix-list INBAND_PREFIXES rule 30 action permit
nv set router policy prefix-list INBAND_PREFIXES rule 30 match 172.16.176.167/32 max-prefix-len 32
nv set router policy prefix-list ERA_PREFIXES rule 10 action permit
nv set router policy prefix-list ERA_PREFIXES rule 10 match 172.16.176.0/21 max-prefix-len 24
nv set router policy prefix-list ERA_PREFIXES rule 20 action permit
nv set router policy prefix-list ERA_PREFIXES rule 20 match 172.16.176.0/24 max-prefix-len 32
nv set router policy prefix-list ERA_PREFIXES rule 30 action permit
nv set router policy prefix-list ERA_PREFIXES rule 30 match 192.168.200.0/24 max-prefix-len 32
nv set router policy prefix-list OOB_HOSTS rule 10 action permit
nv set router policy prefix-list OOB_HOSTS rule 10 match 192.168.200.0/24 max-prefix-len 32
nv set router policy prefix-list LOCAL_OOB_LOOPBACK rule 10 action permit
nv set router policy prefix-list LOCAL_OOB_LOOPBACK rule 10 match 172.16.176.151/32 max-prefix-len 32
nv set router policy prefix-list OOB_LOCAL_IF rule 10 action permit
nv set router policy prefix-list OOB_LOCAL_IF rule 10 match 172.16.176.151/32 max-prefix-len 32
nv set router policy prefix-list OOB_PREFIXES rule 10 action permit
nv set router policy prefix-list OOB_PREFIXES rule 10 match 192.168.200.0/24 max-prefix-len 32
nv set router policy prefix-list OOB_PREFIXES rule 20 action permit
nv set router policy prefix-list OOB_PREFIXES rule 20 match 172.16.176.151/32 max-prefix-len 32
nv set router policy prefix-list VTEP_PREFIXES rule 5 action permit
nv set router policy prefix-list VTEP_PREFIXES rule 5 match 172.16.176.8/29 max-prefix-len 32

nv set router policy community-list 11 rule 100 action permit
nv set router policy community-list 11 rule 100 community 11:11

nv set router policy route-map BLOCK_VTEPS rule 10 action deny
nv set router policy route-map BLOCK_VTEPS rule 10 description deny_vtep_loopback_prefixes
nv set router policy route-map BLOCK_VTEPS rule 10 match ip-prefix-list VTEP_PREFIXES
nv set router policy route-map BLOCK_VTEPS rule 10 match type ipv4
nv set router policy route-map BLOCK_VTEPS rule 20 action permit
nv set router policy route-map BLOCK_VTEPS rule 20 description permit_all_other_ipv4
nv set router policy route-map BLOCK_VTEPS rule 20 match ip-prefix-list ALL_PREFIXES
nv set router policy route-map BLOCK_VTEPS rule 20 match type ipv4
nv set router policy route-map EVPN_OOB_OUT rule 10 action permit
nv set router policy route-map EVPN_OOB_OUT rule 10 description permit_macip_of_real_oob_hosts
nv set router policy route-map EVPN_OOB_OUT rule 10 match type ipv4
nv set router policy route-map EVPN_OOB_OUT rule 10 match evpn-route-type macip
nv set router policy route-map EVPN_OOB_OUT rule 10 match ip-prefix-list OOB_HOSTS
nv set router policy route-map EVPN_OOB_OUT rule 20 action deny
nv set router policy route-map EVPN_OOB_OUT rule 20 description deny_macip_outside_oob_hosts
nv set router policy route-map EVPN_OOB_OUT rule 20 match type ipv4
nv set router policy route-map EVPN_OOB_OUT rule 20 match evpn-route-type macip
nv set router policy route-map EVPN_OOB_OUT rule 100 action permit
nv set router policy route-map EVPN_OOB_OUT rule 100 description permit_all_other_evpn_routes
nv set router policy route-map EXIT_FILTER rule 10 action deny
nv set router policy route-map EXIT_FILTER rule 10 description deny_exit_vrf_local_interfaces
nv set router policy route-map EXIT_FILTER rule 10 match ip-prefix-list EXIT_LOCAL_IF
nv set router policy route-map EXIT_FILTER rule 10 match type ipv4
nv set router policy route-map EXIT_FILTER rule 20 action permit
nv set router policy route-map EXIT_FILTER rule 20 description tag_exit_learned_routes
nv set router policy route-map EXIT_FILTER rule 20 set community 11:11
nv set router policy route-map INBAND_FILTER rule 5 action deny
nv set router policy route-map INBAND_FILTER rule 5 description deny_exit_tagged_routes
nv set router policy route-map INBAND_FILTER rule 5 match community-list 11
nv set router policy route-map INBAND_FILTER rule 10 action deny
nv set router policy route-map INBAND_FILTER rule 10 description deny_oob_vrf_prefixes
nv set router policy route-map INBAND_FILTER rule 10 match ip-prefix-list OOB_PREFIXES
nv set router policy route-map INBAND_FILTER rule 10 match type ipv4
nv set router policy route-map INBAND_FILTER rule 15 action deny
nv set router policy route-map INBAND_FILTER rule 15 description deny_inband_vrf_local_interfaces
nv set router policy route-map INBAND_FILTER rule 15 match ip-prefix-list INBAND_LOCAL_IF
nv set router policy route-map INBAND_FILTER rule 15 match type ipv4
nv set router policy route-map INBAND_FILTER rule 20 action permit
nv set router policy route-map INBAND_FILTER rule 20 description permit_all_other_ipv4
nv set router policy route-map INBAND_FILTER rule 20 match ip-prefix-list ALL_PREFIXES
nv set router policy route-map INBAND_FILTER rule 20 match type ipv4
nv set router policy route-map OOB_FILTER rule 5 action deny
nv set router policy route-map OOB_FILTER rule 5 description deny_exit_tagged_routes
nv set router policy route-map OOB_FILTER rule 5 match community-list 11
nv set router policy route-map OOB_FILTER rule 10 action deny
nv set router policy route-map OOB_FILTER rule 10 description deny_inband_vrf_prefixes
nv set router policy route-map OOB_FILTER rule 10 match ip-prefix-list INBAND_PREFIXES
nv set router policy route-map OOB_FILTER rule 10 match type ipv4
nv set router policy route-map OOB_FILTER rule 15 action deny
nv set router policy route-map OOB_FILTER rule 15 description deny_oob_vrf_local_interfaces
nv set router policy route-map OOB_FILTER rule 15 match ip-prefix-list OOB_LOCAL_IF
nv set router policy route-map OOB_FILTER rule 15 match type ipv4
nv set router policy route-map OOB_FILTER rule 20 action permit
nv set router policy route-map OOB_FILTER rule 20 description permit_all_other_ipv4
nv set router policy route-map OOB_FILTER rule 20 match ip-prefix-list ALL_PREFIXES
nv set router policy route-map OOB_FILTER rule 20 match type ipv4
nv set router policy route-map OUTBOUND_ERA_PREFIXES rule 10 action permit
nv set router policy route-map OUTBOUND_ERA_PREFIXES rule 10 description permit_era_owned_prefixes_outbound
nv set router policy route-map OUTBOUND_ERA_PREFIXES rule 10 match ip-prefix-list ERA_PREFIXES
nv set router policy route-map OUTBOUND_ERA_PREFIXES rule 10 match type ipv4
nv set router policy route-map WEIGHTED_ECMP rule 10 action permit
nv set router policy route-map WEIGHTED_ECMP rule 10 description enable_w_ecmp_adjustment
nv set router policy route-map WEIGHTED_ECMP rule 10 set ext-community-bw multipaths

nv set router vrr state enabled

#============================================================================
# VRFs
#============================================================================
nv set vrf EXIT evpn state enabled
nv set vrf EXIT evpn vlan 3004
nv set vrf EXIT evpn vni 5004

nv set vrf EXIT loopback ip address 172.16.176.183/32

nv set vrf EXIT router bgp address-family ipv4-unicast state enabled
nv set vrf EXIT router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf EXIT router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf state enabled
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf list INBAND
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf list OOB
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf route-map EXIT_FILTER
nv set vrf EXIT router bgp address-family l2vpn-evpn state enabled

nv set vrf EXIT router bgp autonomous-system 4260395189
nv set vrf EXIT router bgp state enabled

nv set vrf EXIT router bgp neighbor swp61s0 peer-group exit
nv set vrf EXIT router bgp neighbor swp61s0 type unnumbered
nv set vrf EXIT router bgp neighbor swp61s1 peer-group exit
nv set vrf EXIT router bgp neighbor swp61s1 type unnumbered
nv set vrf EXIT router bgp neighbor swp61s2 peer-group exit
nv set vrf EXIT router bgp neighbor swp61s2 type unnumbered
nv set vrf EXIT router bgp neighbor swp61s3 peer-group exit
nv set vrf EXIT router bgp neighbor swp61s3 type unnumbered
nv set vrf EXIT router bgp neighbor swp62s0 peer-group exit
nv set vrf EXIT router bgp neighbor swp62s0 type unnumbered
nv set vrf EXIT router bgp neighbor swp62s1 peer-group exit
nv set vrf EXIT router bgp neighbor swp62s1 type unnumbered
nv set vrf EXIT router bgp neighbor swp62s2 peer-group exit
nv set vrf EXIT router bgp neighbor swp62s2 type unnumbered
nv set vrf EXIT router bgp neighbor swp62s3 peer-group exit
nv set vrf EXIT router bgp neighbor swp62s3 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s0 peer-group exit
nv set vrf EXIT router bgp neighbor swp63s0 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s1 peer-group exit
nv set vrf EXIT router bgp neighbor swp63s1 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s2 peer-group exit
nv set vrf EXIT router bgp neighbor swp63s2 type unnumbered
nv set vrf EXIT router bgp neighbor swp63s3 peer-group exit
nv set vrf EXIT router bgp neighbor swp63s3 type unnumbered
nv set vrf EXIT router bgp neighbor swp64s0 peer-group exit
nv set vrf EXIT router bgp neighbor swp64s0 type unnumbered
nv set vrf EXIT router bgp neighbor swp64s1 peer-group exit
nv set vrf EXIT router bgp neighbor swp64s1 type unnumbered
nv set vrf EXIT router bgp neighbor swp64s2 peer-group exit
nv set vrf EXIT router bgp neighbor swp64s2 type unnumbered
nv set vrf EXIT router bgp neighbor swp64s3 peer-group exit
nv set vrf EXIT router bgp neighbor swp64s3 type unnumbered

nv set vrf EXIT router bgp peer-group exit address-family ipv4-unicast state enabled
nv set vrf EXIT router bgp peer-group exit address-family ipv4-unicast policy outbound route-map OUTBOUND_ERA_PREFIXES
nv set vrf EXIT router bgp peer-group exit remote-as external

nv set vrf EXIT router bgp route-export
nv set vrf EXIT router bgp router-id 172.16.176.183

nv set vrf INBAND evpn state enabled
nv set vrf INBAND evpn vlan 3002
nv set vrf INBAND evpn vni 5002

nv set vrf INBAND loopback ip address 172.16.176.167/32

nv set vrf INBAND router bgp address-family ipv4-unicast state enabled
nv set vrf INBAND router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf INBAND router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf INBAND router bgp address-family ipv4-unicast route-import from-vrf state enabled
nv set vrf INBAND router bgp address-family ipv4-unicast route-import from-vrf list EXIT
nv set vrf INBAND router bgp address-family ipv4-unicast route-import from-vrf route-map INBAND_FILTER
nv set vrf INBAND router bgp address-family l2vpn-evpn state enabled

nv set vrf INBAND router bgp autonomous-system 4260395189
nv set vrf INBAND router bgp state enabled

nv set vrf INBAND router bgp route-export
nv set vrf INBAND router bgp route-import
nv set vrf INBAND router bgp router-id 172.16.176.167

nv set vrf OOB evpn state enabled
nv set vrf OOB evpn vlan 3001
nv set vrf OOB evpn vni 5001

nv set vrf OOB loopback ip address 172.16.176.151/32

nv set vrf OOB router bgp address-family ipv4-unicast state enabled
nv set vrf OOB router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf OOB router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf state enabled
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf list EXIT
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf route-map OOB_FILTER
nv set vrf OOB router bgp address-family l2vpn-evpn state enabled

nv set vrf OOB router bgp autonomous-system 4260395189
nv set vrf OOB router bgp state enabled

nv set vrf OOB router bgp router-id 172.16.176.151

nv set vrf STORAGE evpn state enabled
nv set vrf STORAGE evpn vlan 3005
nv set vrf STORAGE evpn vni 5005

nv set vrf STORAGE loopback ip address 172.16.176.199/32

nv set vrf STORAGE router bgp address-family ipv4-unicast state enabled
nv set vrf STORAGE router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf STORAGE router bgp address-family ipv4-unicast route-export to-evpn state enabled
nv set vrf STORAGE router bgp address-family l2vpn-evpn state enabled

nv set vrf STORAGE router bgp autonomous-system 4260395189
nv set vrf STORAGE router bgp state enabled

nv set vrf STORAGE router bgp neighbor swp59s0 peer-group storage
nv set vrf STORAGE router bgp neighbor swp59s0 type unnumbered
nv set vrf STORAGE router bgp neighbor swp59s1 peer-group storage
nv set vrf STORAGE router bgp neighbor swp59s1 type unnumbered
nv set vrf STORAGE router bgp neighbor swp59s2 peer-group storage
nv set vrf STORAGE router bgp neighbor swp59s2 type unnumbered
nv set vrf STORAGE router bgp neighbor swp59s3 peer-group storage
nv set vrf STORAGE router bgp neighbor swp59s3 type unnumbered
nv set vrf STORAGE router bgp neighbor swp60s0 peer-group storage
nv set vrf STORAGE router bgp neighbor swp60s0 type unnumbered
nv set vrf STORAGE router bgp neighbor swp60s1 peer-group storage
nv set vrf STORAGE router bgp neighbor swp60s1 type unnumbered
nv set vrf STORAGE router bgp neighbor swp60s2 peer-group storage
nv set vrf STORAGE router bgp neighbor swp60s2 type unnumbered
nv set vrf STORAGE router bgp neighbor swp60s3 peer-group storage
nv set vrf STORAGE router bgp neighbor swp60s3 type unnumbered

nv set vrf STORAGE router bgp peer-group storage address-family ipv4-unicast state enabled
nv set vrf STORAGE router bgp peer-group storage address-family l2vpn-evpn state enabled
nv set vrf STORAGE router bgp peer-group storage bfd profile storage
nv set vrf STORAGE router bgp peer-group storage remote-as external

nv set vrf STORAGE router bgp route-export
nv set vrf STORAGE router bgp router-id 172.16.176.199

nv set vrf STORAGE table auto

#============================================================================
# Default VRF BGP (ISL Underlay)
#============================================================================
nv set vrf default router bgp address-family ipv4-unicast state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf default router bgp address-family l2vpn-evpn state enabled

nv set vrf default router bgp state enabled

nv set vrf default router bgp neighbor swp19s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp19s0 type unnumbered
nv set vrf default router bgp neighbor swp19s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp19s1 type unnumbered
nv set vrf default router bgp neighbor swp20s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp20s0 type unnumbered
nv set vrf default router bgp neighbor swp20s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp20s1 type unnumbered
nv set vrf default router bgp neighbor swp21s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp21s0 type unnumbered
nv set vrf default router bgp neighbor swp21s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp21s1 type unnumbered
nv set vrf default router bgp neighbor swp22s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp22s0 type unnumbered
nv set vrf default router bgp neighbor swp22s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp22s1 type unnumbered
nv set vrf default router bgp neighbor swp23s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp23s0 type unnumbered
nv set vrf default router bgp neighbor swp23s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp23s1 type unnumbered
nv set vrf default router bgp neighbor swp24s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp24s0 type unnumbered
nv set vrf default router bgp neighbor swp24s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp24s1 type unnumbered
nv set vrf default router bgp neighbor swp25s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp25s0 type unnumbered
nv set vrf default router bgp neighbor swp25s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp25s1 type unnumbered
nv set vrf default router bgp neighbor swp26s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp26s0 type unnumbered
nv set vrf default router bgp neighbor swp26s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp26s1 type unnumbered
nv set vrf default router bgp neighbor swp27s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp27s0 type unnumbered
nv set vrf default router bgp neighbor swp27s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp27s1 type unnumbered
nv set vrf default router bgp neighbor swp28s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp28s0 type unnumbered
nv set vrf default router bgp neighbor swp28s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp28s1 type unnumbered
nv set vrf default router bgp neighbor swp29s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp29s0 type unnumbered
nv set vrf default router bgp neighbor swp29s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp29s1 type unnumbered
nv set vrf default router bgp neighbor swp30s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp30s0 type unnumbered
nv set vrf default router bgp neighbor swp30s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp30s1 type unnumbered
nv set vrf default router bgp neighbor swp31s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp31s0 type unnumbered
nv set vrf default router bgp neighbor swp31s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp31s1 type unnumbered
nv set vrf default router bgp neighbor swp32s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp32s0 type unnumbered
nv set vrf default router bgp neighbor swp32s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp32s1 type unnumbered
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
nv set vrf default router bgp neighbor swp49s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp49s0 type unnumbered
nv set vrf default router bgp neighbor swp49s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp49s1 type unnumbered
nv set vrf default router bgp neighbor swp50s0 peer-group internal_isl
nv set vrf default router bgp neighbor swp50s0 type unnumbered
nv set vrf default router bgp neighbor swp50s1 peer-group internal_isl
nv set vrf default router bgp neighbor swp50s1 type unnumbered
nv set vrf default router bgp neighbor swp57s0 peer-group underlay
nv set vrf default router bgp neighbor swp57s0 type unnumbered
nv set vrf default router bgp neighbor swp57s1 peer-group underlay
nv set vrf default router bgp neighbor swp57s1 type unnumbered
nv set vrf default router bgp neighbor swp57s2 peer-group underlay
nv set vrf default router bgp neighbor swp57s2 type unnumbered
nv set vrf default router bgp neighbor swp57s3 peer-group underlay
nv set vrf default router bgp neighbor swp57s3 type unnumbered
nv set vrf default router bgp neighbor swp57s4 peer-group underlay
nv set vrf default router bgp neighbor swp57s4 type unnumbered
nv set vrf default router bgp neighbor swp57s5 peer-group underlay
nv set vrf default router bgp neighbor swp57s5 type unnumbered
nv set vrf default router bgp neighbor 172.16.176.61 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.61 type numbered
nv set vrf default router bgp neighbor 172.16.176.62 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.62 type numbered
nv set vrf default router bgp neighbor 172.16.176.63 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.63 type numbered
nv set vrf default router bgp neighbor 172.16.176.64 peer-group overlay
nv set vrf default router bgp neighbor 172.16.176.64 type numbered

nv set vrf default router bgp peer-group internal_isl address-family ipv4-unicast state enabled
nv set vrf default router bgp peer-group internal_isl address-family ipv4-unicast policy outbound route-map WEIGHTED_ECMP
nv set vrf default router bgp peer-group internal_isl address-family l2vpn-evpn state enabled
nv set vrf default router bgp peer-group internal_isl bfd profile underlay
nv set vrf default router bgp peer-group internal_isl description internal_isl_interconnect
nv set vrf default router bgp peer-group internal_isl remote-as external
nv set vrf default router bgp peer-group underlay address-family ipv4-unicast state enabled
nv set vrf default router bgp peer-group underlay address-family ipv4-unicast policy outbound route-map WEIGHTED_ECMP
nv set vrf default router bgp peer-group underlay bfd profile underlay
nv set vrf default router bgp peer-group underlay description oob_underlay_interconnect
nv set vrf default router bgp peer-group underlay remote-as external
nv set vrf default router bgp peer-group overlay address-family ipv4-unicast state disabled
nv set vrf default router bgp peer-group overlay address-family l2vpn-evpn state enabled
nv set vrf default router bgp peer-group overlay address-family l2vpn-evpn policy outbound route-map EVPN_OOB_OUT
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
nv set system ntp server 0.cumulusnetworks.pool.ntp.org association-type server
nv set system ntp server 1.cumulusnetworks.pool.ntp.org association-type server
nv set system ntp server 2.cumulusnetworks.pool.ntp.org association-type server
nv set system ntp server 3.cumulusnetworks.pool.ntp.org association-type server

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
nv set system hostname cl-01
nv set system message pre-login '##############################################################################
#      You are accessing an Information System (IS) that is provided for authorized use only.
##############################################################################'
nv set system message post-login '####################################################################
#       You are successfully logged in to: cl-01 - site: largescale / arch: 2-8-9-800
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
