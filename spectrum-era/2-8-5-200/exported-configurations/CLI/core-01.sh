# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
nv set bridge domain br_default type vlan-aware
nv set bridge domain br_default vlan 200 vni 4200
nv set bridge domain br_default vlan 300 vni 4300
nv set bridge domain br_default vlan 400 vni 4400
nv set bridge domain br_default vlan 500 vni 4500
nv set bridge domain br_default vlan 900 vni 4900
nv set evpn enable on
nv set evpn multihoming enable on
nv set interface bond1s0 bond member swp1s0
nv set interface bond1s0 evpn multihoming segment local-id 10
nv set interface bond1s0-3,bond2s0-3,bond3s0-3,bond4s0-3,bond5s0-3 bridge domain br_default access 300
nv set interface bond1s0-3,bond2s0-3,bond3s0-3,bond4s0-3,bond5s0-3,bond26s0-3,bond27s0-3,bond49s0-7,bond51s0-7 evpn multihoming segment enable on
nv set interface bond1s0-3,bond2s0-3,bond3s0-3,bond4s0-3,bond5s0-3,bond26s0-3,bond27s0-3,bond49s0-7,bond51s0-7 evpn multihoming segment mac-address 44:38:39:FF:00:AA
nv set interface bond1s0-3,bond2s0-3,bond3s0-3,bond4s0-3,bond5s0-3,bond26s0-3,bond27s0-3,bond49s0-7,bond51s0-7 type bond
nv set interface bond1s0-3,bond2s0-3,bond3s0-3,bond4s0-3,bond5s0-3,bond26s0-3,bond27s0-3,bond49s6-7,bond51s0-7 bond lacp-bypass on
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
nv set interface bond4s0 bond member swp4s0
nv set interface bond4s0 evpn multihoming segment local-id 40
nv set interface bond4s1 bond member swp4s1
nv set interface bond4s1 evpn multihoming segment local-id 41
nv set interface bond4s2 bond member swp4s2
nv set interface bond4s2 evpn multihoming segment local-id 42
nv set interface bond4s3 bond member swp4s3
nv set interface bond4s3 evpn multihoming segment local-id 43
nv set interface bond5s0 bond member swp5s0
nv set interface bond5s0 evpn multihoming segment local-id 50
nv set interface bond5s1 bond member swp5s1
nv set interface bond5s1 evpn multihoming segment local-id 51
nv set interface bond5s2 bond member swp5s2
nv set interface bond5s2 evpn multihoming segment local-id 52
nv set interface bond5s3 bond member swp5s3
nv set interface bond5s3 evpn multihoming segment local-id 53
nv set interface bond26s0 bond member swp26s0
nv set interface bond26s0 evpn multihoming segment local-id 260
nv set interface bond26s0-3,bond27s0-3 bridge domain br_default vlan 400
nv set interface bond26s0-3,bond27s0-3,bond49s6-7,bond51s0-7 bridge domain br_default untagged 300
nv set interface bond26s1 bond member swp26s1
nv set interface bond26s1 evpn multihoming segment local-id 261
nv set interface bond26s2 bond member swp26s2
nv set interface bond26s2 evpn multihoming segment local-id 262
nv set interface bond26s3 bond member swp26s3
nv set interface bond26s3 evpn multihoming segment local-id 263
nv set interface bond27s0 bond member swp27s0
nv set interface bond27s0 evpn multihoming segment local-id 270
nv set interface bond27s1 bond member swp27s1
nv set interface bond27s1 evpn multihoming segment local-id 271
nv set interface bond27s2 bond member swp27s2
nv set interface bond27s2 evpn multihoming segment local-id 272
nv set interface bond27s3 bond member swp27s3
nv set interface bond27s3 evpn multihoming segment local-id 273
nv set interface bond49s0 bond member swp49s0
nv set interface bond49s0 evpn multihoming segment local-id 490
nv set interface bond49s0-5 bridge domain br_default access 200
nv set interface bond49s1 bond member swp49s1
nv set interface bond49s1 evpn multihoming segment local-id 491
nv set interface bond49s2 bond member swp49s2
nv set interface bond49s2 evpn multihoming segment local-id 492
nv set interface bond49s3 bond member swp49s3
nv set interface bond49s3 evpn multihoming segment local-id 493
nv set interface bond49s4 bond member swp49s4
nv set interface bond49s4 evpn multihoming segment local-id 494
nv set interface bond49s5 bond member swp49s5
nv set interface bond49s5 evpn multihoming segment local-id 495
nv set interface bond49s6 bond member swp49s6
nv set interface bond49s6 evpn multihoming segment local-id 496
nv set interface bond49s6-7,bond51s0-7 bridge domain br_default vlan 500
nv set interface bond49s7 bond member swp49s7
nv set interface bond49s7 evpn multihoming segment local-id 497
nv set interface bond51s0 bond member swp51s0
nv set interface bond51s0 evpn multihoming segment local-id 510
nv set interface bond51s1 bond member swp51s1
nv set interface bond51s1 evpn multihoming segment local-id 511
nv set interface bond51s2 bond member swp51s2
nv set interface bond51s2 evpn multihoming segment local-id 512
nv set interface bond51s3 bond member swp51s3
nv set interface bond51s3 evpn multihoming segment local-id 513
nv set interface bond51s4 bond member swp51s4
nv set interface bond51s4 evpn multihoming segment local-id 514
nv set interface bond51s5 bond member swp51s5
nv set interface bond51s5 evpn multihoming segment local-id 515
nv set interface bond51s6 bond member swp51s6
nv set interface bond51s6 evpn multihoming segment local-id 516
nv set interface bond51s7 bond member swp51s7
nv set interface bond51s7 evpn multihoming segment local-id 517
nv set interface eth0 ip address dhcp
nv set interface eth0 ip vrf mgmt
nv set interface eth0 type eth
nv set interface lo ip address 172.16.176.11/32
nv set interface lo type loopback
nv set interface swp1,6-9,26-47,49,51,59,61,63 link state up
nv set interface swp1-5,26-27 link breakout 4x lanes-per-port 2
nv set interface swp1-64,swp1s0-3,swp2s0-3,swp3s0-3,swp4s0-3,swp5s0-3,swp6s0-1,swp7s0-1,swp8s0-1,swp9s0-1,swp10s0-1,swp11s0-1,swp12s0-1,swp13s0-1,swp14s0-1,swp15s0-1,swp16s0-1,swp17s0-1,swp18s0-1,swp19s0-1,swp20s0-1,swp21s0-1,swp22s0-1,swp23s0-1,swp24s0-1,swp25s0-1,swp26s0-3,swp27s0-3,swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1,swp49s0-7,swp51s0-7,swp59s0-5,swp61s0-5,swp63s0-5 type swp
nv set interface swp1s0-3,swp2s0-3,swp3s0-3,swp4s0-3,swp5s0-3,swp6s0-1,swp7s0-1,swp8s0-1,swp9s0-1,swp10s0-1,swp11s0-1,swp12s0-1,swp13s0-1,swp14s0-1,swp15s0-1,swp16s0-1,swp17s0-1,swp18s0-1,swp19s0-1,swp20s0-1,swp21s0-1,swp22s0-1,swp23s0-1,swp24s0-1,swp25s0-1,swp26s0-3,swp27s0-3,swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1,swp49s0-7,swp51s0-7,swp59s0-5,swp61s0-5,swp63s0-5 telemetry histogram counter counter-type rx-packet
nv set interface swp1s0-3,swp2s0-3,swp3s0-3,swp4s0-3,swp5s0-3,swp6s0-1,swp7s0-1,swp8s0-1,swp9s0-1,swp10s0-1,swp11s0-1,swp12s0-1,swp13s0-1,swp14s0-1,swp15s0-1,swp16s0-1,swp17s0-1,swp18s0-1,swp19s0-1,swp20s0-1,swp21s0-1,swp22s0-1,swp23s0-1,swp24s0-1,swp25s0-1,swp26s0-3,swp27s0-3,swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1,swp49s0-7,swp51s0-7,swp59s0-5,swp61s0-5,swp63s0-5 telemetry histogram counter counter-type tx-packet
nv set interface swp1s0-3,swp2s0-3,swp3s0-3,swp4s0-3,swp5s0-3,swp6s0-1,swp7s0-1,swp8s0-1,swp9s0-1,swp10s0-1,swp11s0-1,swp12s0-1,swp13s0-1,swp14s0-1,swp15s0-1,swp16s0-1,swp17s0-1,swp18s0-1,swp19s0-1,swp20s0-1,swp21s0-1,swp22s0-1,swp23s0-1,swp24s0-1,swp25s0-1,swp26s0-3,swp27s0-3,swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1,swp49s0-7,swp51s0-7,swp59s0-5,swp61s0-5,swp63s0-5 telemetry histogram egress-buffer traffic-class 0
nv set interface swp1s0-3,swp2s0-3,swp3s0-3,swp4s0-3,swp5s0-3,swp6s0-1,swp7s0-1,swp8s0-1,swp9s0-1,swp10s0-1,swp11s0-1,swp12s0-1,swp13s0-1,swp14s0-1,swp15s0-1,swp16s0-1,swp17s0-1,swp18s0-1,swp19s0-1,swp20s0-1,swp21s0-1,swp22s0-1,swp23s0-1,swp24s0-1,swp25s0-1,swp26s0-3,swp27s0-3,swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1,swp49s0-7,swp51s0-7,swp59s0-5,swp61s0-5,swp63s0-5 telemetry histogram ingress-buffer priority-group 0
nv set interface swp1s0-3,swp2s0-3,swp3s0-3,swp4s0-3,swp5s0-3,swp6s0-1,swp7s0-1,swp8s0-1,swp9s0-1,swp10s0-1,swp11s0-1,swp12s0-1,swp13s0-1,swp14s0-1,swp15s0-1,swp16s0-1,swp17s0-1,swp18s0-1,swp19s0-1,swp20s0-1,swp21s0-1,swp22s0-1,swp23s0-1,swp24s0-1,swp25s0-1,swp26s0-3,swp27s0-3,swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1,swp49s0-7,swp51s0-7,swp59s0-5,swp61s0-5,swp63s0-5 telemetry histogram ingress-buffer priority-group 1
nv set interface swp2-5,10-25,48,50,52-58,60,62 link state down
nv set interface swp6-9,28-47 link breakout 2x lanes-per-port 4
nv set interface swp6s0-1,swp7s0-1,swp8s0-1,swp9s0-1,swp10s0-1,swp11s0-1,swp12s0-1,swp13s0-1,swp14s0-1,swp15s0-1,swp16s0-1,swp17s0-1,swp18s0-1,swp19s0-1,swp20s0-1,swp21s0-1,swp22s0-1,swp23s0-1,swp24s0-1,swp25s0-1 bridge domain br_default access 900
nv set interface swp6s0-1,swp7s0-1,swp8s0-1,swp9s0-1,swp10s0-1,swp11s0-1,swp12s0-1,swp13s0-1,swp14s0-1,swp15s0-1,swp16s0-1,swp17s0-1,swp18s0-1,swp19s0-1,swp20s0-1,swp21s0-1,swp22s0-1,swp23s0-1,swp24s0-1,swp25s0-1 qos pfc-watchdog state enable
nv set interface swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1 description 'ISL to other core switch'
nv set interface swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1 evpn multihoming uplink on
nv set interface swp49,51,59,61,63 link breakout 8x lanes-per-port 1
nv set interface swp50,52,60,62,64 link breakout disabled
nv set interface swp59s0-5,swp61s0-5,swp63s0-5 description 'Edge uplinks'
nv set interface swp59s0-5,swp61s0-5,swp63s0-5 ip vrf EXIT
nv set interface vlan200 ip address 172.16.177.2/24
nv set interface vlan200 ip vrf OOB
nv set interface vlan200 ip vrr address 172.16.177.1/24
nv set interface vlan200 vlan 200
nv set interface vlan200,300,400,500,900 ip vrr enable on
nv set interface vlan200,300,400,500,900 ip vrr state up
nv set interface vlan200,300,400,500,900 type svi
nv set interface vlan300 ip address 172.16.178.2/24
nv set interface vlan300 ip vrr address 172.16.178.1/24
nv set interface vlan300 vlan 300
nv set interface vlan300,400,500 ip vrf INBAND
nv set interface vlan400 ip address 172.16.179.2/24
nv set interface vlan400 ip vrr address 172.16.179.1/24
nv set interface vlan400 vlan 400
nv set interface vlan500 ip address 172.16.180.2/24
nv set interface vlan500 ip vrr address 172.16.180.1/24
nv set interface vlan500 vlan 500
nv set interface vlan900 ip address 192.168.110.2/24
nv set interface vlan900 ip vrf GPU
nv set interface vlan900 ip vrr address 192.168.110.1/24
nv set interface vlan900 vlan 900
nv set nve vxlan decapsulation dscp action preserve
nv set nve vxlan enable on
nv set nve vxlan encapsulation dscp action copy
nv set nve vxlan flooding enable on
nv set nve vxlan flooding head-end-replication evpn
nv set nve vxlan source address 172.16.176.11
nv set qos roce enable on
nv set qos roce mode lossless
nv set qos traffic-pool default-lossy memory-percent 10
nv set qos traffic-pool roce-lossless memory-percent 90
nv set router bgp autonomous-system 4260394788
nv set router bgp enable on
nv set router bgp router-id 172.16.176.11
nv set router policy community-list 11 rule 100 action permit
nv set router policy community-list 11 rule 100 community 11:11
nv set router policy prefix-list ALL_PREFIXES rule 10 action permit
nv set router policy prefix-list ALL_PREFIXES rule 10 match 0.0.0.0/0 max-prefix-len 32
nv set router policy prefix-list ERA_PREFIXES rule 10 action permit
nv set router policy prefix-list ERA_PREFIXES rule 10 match 172.16.176.0/21 max-prefix-len 24
nv set router policy prefix-list ERA_PREFIXES rule 20 action permit
nv set router policy prefix-list ERA_PREFIXES rule 20 match 172.16.176.0/24 max-prefix-len 32
nv set router policy prefix-list EXIT_LOCAL_IF rule 10 action permit
nv set router policy prefix-list EXIT_LOCAL_IF rule 10 match 172.16.176.5/32 max-prefix-len 32
nv set router policy prefix-list INBAND_LOCAL_IF rule 10 action permit
nv set router policy prefix-list INBAND_LOCAL_IF rule 10 match 172.16.176.3/32 max-prefix-len 32
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
nv set router policy prefix-list INBAND_PREFIXES rule 40 match 172.16.176.3/32 max-prefix-len 32
nv set router policy prefix-list LOCAL_OOB_LOOPBACK rule 10 action permit
nv set router policy prefix-list LOCAL_OOB_LOOPBACK rule 10 match 172.16.176.1/32 max-prefix-len 32
nv set router policy prefix-list OOB_LOCAL_IF rule 10 action permit
nv set router policy prefix-list OOB_LOCAL_IF rule 10 match 172.16.176.1/32 max-prefix-len 32
nv set router policy prefix-list OOB_LOCAL_IF rule 20 action permit
nv set router policy prefix-list OOB_LOCAL_IF rule 20 match 172.16.177.2/32 max-prefix-len 32
nv set router policy prefix-list OOB_PREFIXES rule 10 action permit
nv set router policy prefix-list OOB_PREFIXES rule 10 match 172.16.177.0/24 max-prefix-len 32
nv set router policy prefix-list OOB_PREFIXES rule 20 action permit
nv set router policy prefix-list OOB_PREFIXES rule 20 match 172.16.176.1/32 max-prefix-len 32
nv set router policy prefix-list VTEP_PREFIXES rule 5 action permit
nv set router policy prefix-list VTEP_PREFIXES rule 5 match 172.16.176.8/29 max-prefix-len 32
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
nv set router vrr enable on
nv set service dhcp-relay EXIT interface swp59s0
nv set service dhcp-relay EXIT interface swp59s1
nv set service dhcp-relay EXIT interface swp59s2
nv set service dhcp-relay EXIT interface swp59s3
nv set service dhcp-relay EXIT interface swp59s4
nv set service dhcp-relay EXIT interface swp59s5
nv set service dhcp-relay EXIT interface swp61s0
nv set service dhcp-relay EXIT interface swp61s1
nv set service dhcp-relay EXIT interface swp61s2
nv set service dhcp-relay EXIT interface swp61s3
nv set service dhcp-relay EXIT interface swp61s4
nv set service dhcp-relay EXIT interface swp61s5
nv set service dhcp-relay EXIT interface swp63s0
nv set service dhcp-relay EXIT interface swp63s1
nv set service dhcp-relay EXIT interface swp63s2
nv set service dhcp-relay EXIT interface swp63s3
nv set service dhcp-relay EXIT interface swp63s4
nv set service dhcp-relay EXIT interface swp63s5
nv set service dhcp-relay EXIT interface vlan3004_l3
nv set service dhcp-relay EXIT server 192.168.210.41
nv set service dhcp-relay EXIT server 192.168.220.42
nv set service dhcp-relay OOB interface vlan200
nv set service dhcp-relay OOB interface vlan3001_l3
nv set service dhcp-relay OOB server 192.168.200.2
nv set service dhcp-relay OOB server 192.168.210.2
nv set service dhcp-relay OOB server 192.168.220.2
nv set service ntp mgmt server 0.cumulusnetworks.pool.ntp.org
nv set service ntp mgmt server 1.cumulusnetworks.pool.ntp.org
nv set service ntp mgmt server 2.cumulusnetworks.pool.ntp.org
nv set service ntp mgmt server 3.cumulusnetworks.pool.ntp.org
nv set system aaa authentication-order 1 local
nv set system aaa authentication-order 2 ldap
nv set system aaa class nvapply action allow
nv set system aaa class nvapply command-path / permission all
nv set system aaa class nvshow action allow
nv set system aaa class nvshow command-path / permission ro
nv set system aaa class sudo action allow
nv set system aaa class sudo command-path / permission all
nv set system aaa ldap base-dn dc=example,dc=com
nv set system aaa ldap bind-dn cn=admin,ou=Users,dc=example,dc=com
nv set system aaa ldap secret '$nvsec$04176b6cfafbbc04ca27fc8fa12b52fa'
nv set system aaa ldap server 192.168.200.252
nv set system aaa ldap server 192.168.210.252 priority 2
nv set system aaa role nvue-admin class nvapply
nv set system aaa role nvue-monitor class nvshow
nv set system aaa role system-admin class nvapply
nv set system aaa role system-admin class sudo
nv set system aaa user cumulus full-name cumulus,,,
nv set system aaa user cumulus hashed-password '*'
nv set system aaa user cumulus role system-admin
nv set system api state enabled
nv set system config auto-save state enabled
nv set system control-plane acl acl-default-dos inbound
nv set system control-plane acl acl-default-whitelist inbound
nv set system global anycast-mac 44:38:39:ff:00:ff
nv set system hostname core-01
nv set system message post-login '#####################################################################################
#                     You are successfully logged in to: core-01                    #
#####################################################################################
'
nv set system message pre-login '#####################################################################################
#  Welcome to NVIDIA Cumulus VX (TM)                                                #
#  NVIDIA Cumulus VX (TM) is a community supported virtual appliance designed       #
#  for experiencing, testing and prototyping NVIDIA Cumulus'"'"'"'"'"'"'"'"' latest technology. #
#  For any questions or technical support, visit our community site at:             #
#  https://www.nvidia.com/en-us/support                                             #
#####################################################################################
'
nv set system reboot mode cold
nv set system ssh-server state enabled
nv set system telemetry enable on
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
nv set system timezone Etc/Zulu
nv set system wjh channel forwarding trigger l2
nv set system wjh channel forwarding trigger l3
nv set system wjh channel forwarding trigger tunnel
nv set system wjh enable on
nv set vrf EXIT evpn enable on
nv set vrf EXIT evpn vlan 3004
nv set vrf EXIT evpn vni 5004
nv set vrf EXIT loopback ip address 172.16.176.5/32
nv set vrf EXIT router bgp address-family ipv4-unicast enable on
nv set vrf EXIT router bgp address-family ipv4-unicast redistribute connected enable on
nv set vrf EXIT router bgp address-family ipv4-unicast route-export to-evpn enable on
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf enable on
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf list INBAND
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf list OOB
nv set vrf EXIT router bgp address-family ipv4-unicast route-import from-vrf route-map EXIT_FILTER
nv set vrf EXIT router bgp address-family l2vpn-evpn enable on
nv set vrf EXIT router bgp autonomous-system 4260394788
nv set vrf EXIT router bgp enable on
nv set vrf EXIT router bgp neighbor swp59s0-5,swp61s0-5,swp63s0-5 peer-group underlay-esl-external
nv set vrf EXIT router bgp neighbor swp59s0-5,swp61s0-5,swp63s0-5 type unnumbered
nv set vrf EXIT router bgp neighbor swp59s0-5,swp61s0-5,swp63s0-5 update-source 172.16.176.11
nv set vrf EXIT router bgp peer-group underlay-esl-external address-family ipv4-unicast enable on
nv set vrf EXIT router bgp peer-group underlay-esl-external address-family ipv4-unicast policy outbound route-map OUTBOUND_ERA_PREFIXES
nv set vrf EXIT router bgp peer-group underlay-esl-external remote-as external
nv set vrf EXIT router bgp rd 172.16.176.11:5004
nv set vrf EXIT router bgp route-export
nv set vrf EXIT router bgp router-id 172.16.176.11
nv set vrf GPU evpn enable on
nv set vrf GPU evpn vlan 3003
nv set vrf GPU evpn vni 5003
nv set vrf GPU loopback ip address 192.168.110.5/32
nv set vrf GPU router bgp address-family ipv4-unicast enable on
nv set vrf GPU router bgp address-family ipv4-unicast redistribute connected enable on
nv set vrf GPU router bgp address-family ipv4-unicast route-export to-evpn enable on
nv set vrf GPU router bgp address-family l2vpn-evpn enable on
nv set vrf GPU router bgp autonomous-system 4260394788
nv set vrf GPU router bgp enable on
nv set vrf GPU router bgp rd 172.16.176.11:5003
nv set vrf GPU router bgp router-id 172.16.176.11
nv set vrf INBAND evpn enable on
nv set vrf INBAND evpn vlan 3002
nv set vrf INBAND evpn vni 5002
nv set vrf INBAND loopback ip address 172.16.176.3/32
nv set vrf INBAND router bgp address-family ipv4-unicast enable on
nv set vrf INBAND router bgp address-family ipv4-unicast redistribute connected enable on
nv set vrf INBAND router bgp address-family ipv4-unicast route-export to-evpn enable on
nv set vrf INBAND router bgp address-family ipv4-unicast route-import from-vrf enable on
nv set vrf INBAND router bgp address-family ipv4-unicast route-import from-vrf list EXIT
nv set vrf INBAND router bgp address-family ipv4-unicast route-import from-vrf route-map INBAND_FILTER
nv set vrf INBAND router bgp address-family l2vpn-evpn enable on
nv set vrf INBAND router bgp autonomous-system 4260394788
nv set vrf INBAND router bgp enable on
nv set vrf INBAND router bgp rd 172.16.176.11:5002
nv set vrf INBAND router bgp route-export
nv set vrf INBAND router bgp route-import
nv set vrf INBAND router bgp router-id 172.16.176.11
nv set vrf OOB evpn enable on
nv set vrf OOB evpn vlan 3001
nv set vrf OOB evpn vni 5001
nv set vrf OOB loopback ip address 172.16.176.1/32
nv set vrf OOB router bgp address-family ipv4-unicast enable on
nv set vrf OOB router bgp address-family ipv4-unicast redistribute connected enable on
nv set vrf OOB router bgp address-family ipv4-unicast route-export to-evpn enable on
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf enable on
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf list EXIT
nv set vrf OOB router bgp address-family ipv4-unicast route-import from-vrf route-map OOB_FILTER
nv set vrf OOB router bgp address-family l2vpn-evpn enable on
nv set vrf OOB router bgp autonomous-system 4260394788
nv set vrf OOB router bgp enable on
nv set vrf OOB router bgp rd 172.16.176.11:5001
nv set vrf OOB router bgp router-id 172.16.176.11
nv set vrf default router bgp address-family ipv4-unicast enable on
nv set vrf default router bgp address-family ipv4-unicast redistribute connected enable on
nv set vrf default router bgp address-family l2vpn-evpn enable on
nv set vrf default router bgp enable on
nv set vrf default router bgp neighbor swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1 peer-group underlay
nv set vrf default router bgp neighbor swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1 ttl-security hops 1
nv set vrf default router bgp neighbor swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1 type unnumbered
nv set vrf default router bgp neighbor swp28s0-1,swp29s0-1,swp30s0-1,swp31s0-1,swp32s0-1,swp33s0-1,swp34s0-1,swp35s0-1,swp36s0-1,swp37s0-1,swp38s0-1,swp39s0-1,swp40s0-1,swp41s0-1,swp42s0-1,swp43s0-1,swp44s0-1,swp45s0-1,swp46s0-1,swp47s0-1 update-source 172.16.176.11
nv set vrf default router bgp peer-group underlay address-family l2vpn-evpn enable on
nv set vrf default router bgp peer-group underlay bfd enable on
nv set vrf default router bgp peer-group underlay remote-as internal
nv set vrf default router bgp peer-group underlay-esl-external address-family ipv4-unicast enable on
nv set vrf default router bgp peer-group underlay-esl-external address-family ipv4-unicast policy outbound route-map OUTBOUND_ERA_PREFIXES
nv set vrf default router bgp peer-group underlay-esl-external bfd enable on
nv set vrf default router bgp peer-group underlay-esl-external remote-as external
