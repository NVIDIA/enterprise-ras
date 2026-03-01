<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# ERA switch automation using NVIDIA NVUE Collection
![release](https://img.shields.io/badge/release-v3.0.0-blue)
![architecture](https://img.shields.io/badge/architecture-2--8--5--200-green)

This repository contains the files to setup ERA configuration on the core switches. You can change the values in the inventory files to customize the variables.

2-8-5-200 Release v3.0.0

## Deploying the setup on Air

Once you login to Nvidia Air, click on the `Create Simulation` button. Upload the `ERA-285-topology.json` to setup this topology on Air.

### Enable SSH services (optional)

Enable the SSH service for both `oob-server-01` and `dhcp-oob` by clicking on `+ New Service` under the `Services` option on NVIDIA air. Ensure you select `Service Type` as `SSH`. You can use the generated endpoint to SSH directly into these systems from your preferred SSH client like PuTTY, etc.

## Preparing the Out-of-band management setup

### oob-switch-01 and oob-switch-02

Launch the terminal of `oob-switch-01` and login using the default credentials:

```
username: cumulus
password: cumulus
```

You will be prompted to reset the default password.

```
cumulus login: cumulus
Password: 
You are required to change your password immediately (administrator enforced).
Changing password for cumulus.
Current password: 
New password: 
Retype new password:
```

Once you login, run the following commands to setup the out-of-band management network. Use the files correspondign to each file in the `oob-switch-config` directory.

```
cumulus@cumulus:~$ vi nvue.yaml
<paste the contents of oob-switch-01.yaml>
cumulus@cumulus:~$ nv config patch nvue.yaml
cumulus@cumulus:~$ nv config apply -y
```

Repeat these steps on `oob-switch-02` and `oob-switch-03` as well. Use the `oob-switch-02.yaml` and `oob-switch-03.yaml` configuration files respectively.

### oob-server-01

Login to the `oob-server-01` using the default credentials:

```
username: ubuntu
password: nvidia
```

Run the below commands to disable IPv6 and enable routing:

```
ubuntu@ubuntu:~$ sudo nano /etc/sysctl.conf
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1

ubuntu@ubuntu:~$ sudo sysctl -p
```

Setup static IP address:

```
ubuntu@ubuntu:~$ sudo nano /etc/netplan/01-config.yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth1:
      dhcp4: no
      addresses:
        - 192.168.200.1/24
    eth2:
      dhcp4: no
      addresses:
        - 192.168.210.1/24
    eth3:
      dhcp4: no
      addresses:
        - 192.168.220.1/24
ubuntu@ubuntu:~$ sudo netplan apply
```

### dhcp-oob

Login to the `dhcp-oob` using the default credentials:

```
username: ubuntu
password: nvidia
```

Run the below commands to disable IPv6:

```
ubuntu@ubuntu:~$ sudo nano /etc/sysctl.conf
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1

ubuntu@ubuntu:~$ sudo sysctl -p
```

Setup static IP address:

```
ubuntu@ubuntu:~$ sudo nano /etc/netplan/01-config.yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth1:
      dhcp4: no
      addresses:
        - 192.168.200.252/24
    eth2:
      dhcp4: no
      addresses:
        - 192.168.210.252/24
    eth3:
      dhcp4: no
      addresses:
        - 192.168.220.252/24
ubuntu@ubuntu:~$ sudo netplan apply
```

Run the update command:

```
ubuntu@ubuntu:~$ sudo apt-get update -y
```

## Setting up the configuration using Ansible on oob-server-01

Install Ansible:

```
ubuntu@ubuntu:~$ python3 -m pip install ansible paramiko
ubuntu@ubuntu:~$ PATH=$PATH:/home/ubuntu/.local/bin
```

Ensure that you have the NVIDIA NVUE Ansible collection installed on the OOB server running Ansible:

```
ubuntu@ubuntu:~$ ansible-galaxy collection install nvidia.nvue
```

Pull this git repo to use it for configuring the setup:

```
ubuntu@ubuntu:~$ git clone https://github.com/NVIDIA/enterprise-ras.git
ubuntu@ubuntu:~$ git checkout sp-2-8-5-200-v3.0.0
ubuntu@ubuntu:~$ cd spectrum-era/2-8-5-200
```

To configure the switches and the nodes, run the playbook as shown below:

```
ubuntu@ubuntu:~$ ansible-playbook playbooks/era-config.yml -i inventories/hosts
```

## Setting up the configuration using configuration files

You can use `nv config replace` to setup the switch configuration on each of the switches. The corresponding files can be found in the `exported-configurations` directory.

```
core-01:$ nv config replace core-01.yaml
core-01:$ nv config apply -y
```
