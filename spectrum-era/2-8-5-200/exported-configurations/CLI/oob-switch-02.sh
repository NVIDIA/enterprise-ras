# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
nv set bridge domain br_default vlan 200
nv set interface eth0 ip address dhcp
nv set interface eth0 ip vrf mgmt
nv set interface eth0 type eth
nv set interface spine_bond bond member swp49-52
nv set interface spine_bond type bond
nv set interface spine_bond,swp1-5,10-15,28-40,49-57,60-61 link state up
nv set interface spine_bond,swp1-5,10-15,28-40,53-57,60-61 bridge domain br_default access 200
nv set interface swp1-5,10-15,28-40,49-57,60-61 type swp
nv set interface vlan200 ip address 192.168.210.2/24
nv set interface vlan200 type svi
nv set interface vlan200 vlan 200
nv set service ntp mgmt server 0.cumulusnetworks.pool.ntp.org
nv set service ntp mgmt server 1.cumulusnetworks.pool.ntp.org
nv set service ntp mgmt server 2.cumulusnetworks.pool.ntp.org
nv set service ntp mgmt server 3.cumulusnetworks.pool.ntp.org
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
nv set system aaa user cumulus hashed-password '*'
nv set system aaa user cumulus role system-admin
nv set system api state enabled
nv set system config auto-save state enabled
nv set system control-plane acl acl-default-dos inbound
nv set system control-plane acl acl-default-whitelist inbound
nv set system hostname oob-switch-02
nv set system message post-login '#####################################################################################
#                     You are successfully logged in to: oob-switch-02              #
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
nv set system timezone Etc/Zulu
nv set system wjh channel forwarding trigger l2
nv set system wjh channel forwarding trigger l3
nv set system wjh channel forwarding trigger tunnel
nv set system wjh enable on
nv set vrf default router static 0.0.0.0/0 address-family ipv4-unicast
nv set vrf default router static 0.0.0.0/0 via 192.168.210.1 type ipv4-address
