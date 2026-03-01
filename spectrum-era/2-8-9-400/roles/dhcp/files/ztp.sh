#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

function error() {
  echo -e "e[0;33mERROR: The Zero Touch Provisioning script failed while running the command $BASH_COMMAND at line $BASH_LINENO.e[0m" >&2
}
trap error ERR

SSH_URL="http://192.168.200.1/authorized_keys"
# Uncomment to setup SSH key authentication for Ansible
mkdir -p /home/cumulus/.ssh
wget -q -O /home/cumulus/.ssh/authorized_keys $SSH_URL

# Uncomment to unexpire and change the default cumulus user password
# passwd -x 99999 cumulus
# echo 'cumulus:Cumu1usLinux!' | chpasswd

# Uncomment to make user cumulus passwordless sudo
echo "cumulus ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/10_cumulus

# NVUE config
nv set system aaa user cumulus password 'Cumu1usLinux!'
nv config apply

exit 0
#CUMULUS-AUTOPROVISIONING
