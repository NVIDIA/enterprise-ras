#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# Local-test customer-edge eBGP peer for the cores' EXIT-VRF uplinks (cust-net-edge-02).
nv set system hostname cust-net-edge-02
nv set interface eth0 type eth
nv set interface eth0 vrf mgmt
nv set interface lo type loopback
nv set interface lo ipv4 address 10.255.255.2/32
nv set interface swp51,swp52,swp53,swp54 type swp
nv set router bgp autonomous-system 4260000000
nv set router bgp router-id 10.255.255.2
nv set router bgp state enabled
nv set vrf default router bgp state enabled
nv set vrf default router bgp address-family ipv4-unicast state enabled
nv set vrf default router bgp address-family ipv4-unicast redistribute connected state enabled
nv set vrf default router bgp peer-group external remote-as external
nv set vrf default router bgp peer-group external address-family ipv4-unicast state enabled
nv set vrf default router bgp neighbor swp51 peer-group external
nv set vrf default router bgp neighbor swp51 type unnumbered
nv set vrf default router bgp neighbor swp52 peer-group external
nv set vrf default router bgp neighbor swp52 type unnumbered
nv set vrf default router bgp neighbor swp53 peer-group external
nv set vrf default router bgp neighbor swp53 type unnumbered
nv set vrf default router bgp neighbor swp54 peer-group external
nv set vrf default router bgp neighbor swp54 type unnumbered
