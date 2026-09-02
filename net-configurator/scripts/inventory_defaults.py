# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Single home for invariant group_vars content that was previously
copied/merged from the per-arch seed inventory. The parser sources these instead
of reading inventories/<arch>/group_vars/*, so the seed files can be deleted.

Two forms:
- Uniform-across-archs files (switches/servers) → the string constants below.
- Per-arch content (all, oob, core/csl …) → a single consolidated data file,
  inventory_defaults.yml, keyed by section -> arch, so every arch's variant of a
  section sits side-by-side (an update can't miss one). Loaded via
  arch_group_vars().

Guarded by tests/test_seedless_generation.py."""

import copy
from pathlib import Path

import yaml

_DEFAULTS_YML = Path(__file__).resolve().parent / "inventory_defaults.yml"
_DEFAULTS = yaml.safe_load(_DEFAULTS_YML.read_text()) or {}


def arch_group_vars(section, arch):
    """Invariant group_vars dict for (section, arch), a deep copy so callers may
    mutate freely.

    'all' is special: the infra defaults are a single arch-independent
    shared block (`all_shared`), plus two per-arch bits assembled here —
      * `devices`: the server node inventory (per-arch, inserted at its original
        position after host_dhcp); absent for archs that carry none.
      * `ztp_server_host`: derived from the OOB uplink mode (l3 -> external-dhcp,
        else dhcp-oob), overriding the placeholder in all_shared in place.
    Other sections (oob, core) are keyed by arch directly.
    """
    if section == "all":
        dev = (_DEFAULTS.get("devices") or {}).get(arch)
        out = {}
        for k, v in (_DEFAULTS.get("all_shared") or {}).items():
            out[k] = copy.deepcopy(v)
            if k == "host_dhcp" and dev is not None:
                out["devices"] = copy.deepcopy(dev)
        oob_mode = ((_DEFAULTS.get("oob") or {}).get(arch) or {}).get("oob_uplink_mode")
        out["ztp_server_host"] = "external-dhcp" if oob_mode == "l3" else "dhcp-oob"
        return out
    return copy.deepcopy((_DEFAULTS.get(section) or {}).get(arch) or {})


def air_vnode_host_vars(arch, vnode):
    """Air virtual-node host_vars for (arch, vnode) from inventory_defaults.yml,
    or None if that arch/vnode carries none (replaces the per-arch seed
    inventories/<arch>/host_vars/). Deep-copied so callers may mutate freely."""
    v = ((_DEFAULTS.get("host_vars") or {}).get(arch) or {}).get(vnode)
    return copy.deepcopy(v) if v is not None else None


SWITCHES_GROUP_VARS = '# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.\n# SPDX-License-Identifier: MIT\n\n# ============================================================================\n# Switches Group Variables\n# ============================================================================\n# Connection settings for all switches (core + oob)\n\nansible_password: "{{ switch_ansible_password }}"\n\n'

SERVERS_GROUP_VARS = '# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.\n# SPDX-License-Identifier: MIT\n\n# ============================================================================\n# Servers Group Variables\n# ============================================================================\n# Connection settings for all servers\n\nansible_password: "{{ server_ansible_password }}"\n\n'
