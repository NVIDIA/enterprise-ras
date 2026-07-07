#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# Local-test customer-edge eBGP peer for the cores' EXIT-VRF uplinks (cust-net-edge-01).
nv set system hostname cust-net-edge-01
nv set interface eth0 type eth
nv set interface eth0 vrf mgmt
nv set interface lo type loopback
nv set interface lo ipv4 address 10.255.255.1/32
nv set interface swp1,swp2,swp3,swp4 type swp
nv set router bgp autonomous-system 4260000000
nv set router bgp router-id 10.255.255.1
nv set router bgp state enabled
nv set vrf default router bgp state enabled
nv set vrf default router bgp address-family ipv4-unicast state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf default router bgp peer-group external remote-as external
nv set vrf default router bgp peer-group external address-family ipv4-unicast state enabled
nv set vrf default router bgp neighbor swp1 peer-group external
nv set vrf default router bgp neighbor swp1 type unnumbered
nv set vrf default router bgp neighbor swp2 peer-group external
nv set vrf default router bgp neighbor swp2 type unnumbered
nv set vrf default router bgp neighbor swp3 peer-group external
nv set vrf default router bgp neighbor swp3 type unnumbered
nv set vrf default router bgp neighbor swp4 peer-group external
nv set vrf default router bgp neighbor swp4 type unnumbered
