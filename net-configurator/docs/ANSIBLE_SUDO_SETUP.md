<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# Ansible Sudo Configuration

This guide explains how to configure sudo access for Ansible deployments.

## The Issue

When running Ansible playbooks that need sudo/root access, you may see:
```
sudo: a password is required
```

This happens because Ansible tries to run commands with `become: true` (sudo) but doesn't have the password.

## Solutions

### Option 1: Interactive Password Prompt (Quick Fix)

The Makefile commands now include `--ask-become-pass` which prompts for the sudo password:

```bash
make ztp-setup         # Will prompt for password
make deploy-servers    # Will prompt for password
```

When prompted:
```
BECOME password:
```
Enter the sudo password for the target server.

**Pros**: Simple, works immediately
**Cons**: Must enter password each time

---

### Option 2: Passwordless Sudo (Recommended for Labs)

Set up passwordless sudo on the target server(s).

#### On the Target Server (dhcp-oob, etc.)

```bash
# SSH to the server
ssh dhcp-oob

# Edit sudoers file
sudo visudo
```

Add this line at the end (replace `username` with your actual username):
```
username ALL=(ALL) NOPASSWD:ALL
```

Or for a specific group:
```
%admin ALL=(ALL) NOPASSWD:ALL
```

Save and exit (Ctrl+X, then Y, then Enter).

#### Test It
```bash
# Should work without password
sudo ls /root
```

#### Remove --ask-become-pass from Makefile

If you've set up passwordless sudo, you can optionally remove the `--ask-become-pass` flag from the Makefile:

```make
ztp-setup:
	@ansible-playbook playbooks/setup-ztp-server.yml -i output/<arch>/<site>/inventory/hosts
```

**Pros**: No password prompts, faster workflows
**Cons**: Less secure (acceptable for lab environments)

---

### Option 3: Ansible Configuration File

Create a permanent configuration for Ansible.

#### Create/Edit ansible.cfg

In the project root:
```bash
cd /path/to/net-configurator
vim ansible.cfg
```

Add:
```ini
[defaults]
ask_become_pass = True
inventory = output/<arch>/<site>/inventory/hosts
host_key_checking = False

[privilege_escalation]
become = True
become_method = sudo
become_ask_pass = True
```

Now ALL Ansible commands will automatically prompt for the sudo password.

**Pros**: Centralized configuration, works for all playbooks
**Cons**: Still need to enter password each time

---

### Option 4: Ansible Vault (Most Secure)

Store the sudo password in an encrypted Ansible vault.

#### Create Vault File
```bash
ansible-vault create output/<arch>/<site>/inventory/group_vars/all/vault.yml
```

Enter vault password when prompted, then add:
```yaml
---
ansible_become_pass: your-sudo-password-here
```

#### Use Vault
```bash
# Run with vault password
ansible-playbook playbooks/setup-ztp-server.yml -i output/<arch>/<site>/inventory/hosts --ask-vault-pass

# Or with vault password file
echo "your-vault-password" > ~/.vault_pass.txt
chmod 600 ~/.vault_pass.txt

ansible-playbook playbooks/setup-ztp-server.yml -i output/<arch>/<site>/inventory/hosts \
  --vault-password-file ~/.vault_pass.txt
```

#### Update Makefile (Optional)
```make
ztp-setup:
	@ansible-playbook playbooks/setup-ztp-server.yml -i output/<arch>/<site>/inventory/hosts --ask-vault-pass
```

**Pros**: Secure, password encrypted in repo
**Cons**: More complex setup

---

### Option 5: SSH Key + Passwordless Sudo (Production)

Best practice for production environments.

#### Step 1: Set up SSH key authentication
```bash
# Generate SSH key if you don't have one
ssh-keygen -t ed25519 -C "ansible@automation"

# Copy to target server
ssh-copy-id username@dhcp-oob
```

#### Step 2: Configure passwordless sudo
Follow Option 2 above.

#### Step 3: Update inventory
```yaml
# output/<arch>/<site>/inventory/host_vars/dhcp-oob.yml
ansible_user: username
ansible_ssh_private_key_file: ~/.ssh/id_ed25519
```

#### Step 4: Test
```bash
# Should connect without any passwords
ansible dhcp-oob -i output/<arch>/<site>/inventory/hosts -m ping
```

**Pros**: Most secure, no passwords in playbooks, fast
**Cons**: Requires key management

---

## Current Setup

The repository is currently configured with **Option 1** (Interactive Password Prompt):

- `make ztp-setup` → prompts for password
- `make deploy-servers` → prompts for password

This is the safest default but requires manual password entry each time.

## Recommended Setup

### For Lab/Development
Use **Option 2** (Passwordless Sudo):
- Fast, convenient
- No security concerns in isolated lab
- Can commit Makefile changes to remove `--ask-become-pass`

### For Production
Use **Option 5** (SSH Key + Passwordless Sudo):
- Secure
- Auditable
- Scalable

### For Shared Environments
Use **Option 4** (Ansible Vault):
- Secure
- Works with team workflows
- Password encrypted in repo

---

## Troubleshooting

### Error: "sudo: a password is required"
**Solution**: Use `--ask-become-pass` flag or set up passwordless sudo

### Error: "SSH permission denied"
**Solution**: Check SSH keys, try `ssh-copy-id`

### Error: "username is not in the sudoers file"
**Solution**: Add user to sudoers or admin group
```bash
sudo usermod -aG sudo username
```

### Ansible still asks for password
**Solution**: Verify passwordless sudo works:
```bash
ssh dhcp-oob
sudo ls /root  # Should not prompt
```

### Different password for different servers
**Solution**: Use host_vars or group_vars with vault:
```yaml
# output/<arch>/<site>/inventory/host_vars/dhcp-oob/vault.yml
ansible_become_pass: server1-password

# output/<arch>/<site>/inventory/host_vars/other-server/vault.yml
ansible_become_pass: server2-password
```

---

## Quick Reference

| Method | Security | Convenience | Use Case |
|--------|----------|-------------|----------|
| Interactive Prompt | ⭐⭐⭐ | ⭐ | Quick tests |
| Passwordless Sudo | ⭐ | ⭐⭐⭐ | Lab/Dev |
| ansible.cfg | ⭐⭐ | ⭐⭐ | Shared defaults |
| Ansible Vault | ⭐⭐⭐ | ⭐⭐ | Team/Production |
| SSH Key + No-Pass Sudo | ⭐⭐⭐⭐ | ⭐⭐⭐ | Production |

---

## See Also

- [Ansible Privilege Escalation](https://docs.ansible.com/ansible/latest/user_guide/become.html)
- [Ansible Vault](https://docs.ansible.com/ansible/latest/user_guide/vault.html)
- [SSH Key Authentication](https://www.ssh.com/academy/ssh/copy-id)

