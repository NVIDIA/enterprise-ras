# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-136: every registered arch must carry Air virtual-node host_vars defaults.

``inventory_defaults.yml`` had no ``host_vars`` block for ``2-4-5-800``, and
the parser's merge loop skipped a ``None`` lookup silently, so a 2-4-5-800 site
generated with no ``dhcp-oob.yml`` / ``oob-server-01.yml`` (and therefore no
``oob_server_interfaces``) while ``make import`` reported success.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _valid_archs import VALID_ARCHS  # noqa: E402
from excel_parser import AIR_VIRTUAL_NODES  # noqa: E402
from inventory_defaults import air_vnode_host_vars  # noqa: E402

# Everything process_excel_template can put in air_virtual_nodes: the Air_Only
# rows plus the mode-derived L2 pair / L3 trio.
ALL_VNODES = sorted(AIR_VIRTUAL_NODES | {"dhcp-oob", "oob-server-01",
                                         "external-conn", "external-dhcp", "utility"})


@pytest.mark.parametrize("arch", VALID_ARCHS)
@pytest.mark.parametrize("vnode", ALL_VNODES)
def test_every_registered_arch_has_defaults_for_every_vnode(arch, vnode):
    hv = air_vnode_host_vars(arch, vnode)
    assert hv is not None, f"{arch} has no host_vars defaults for {vnode}"
    assert hv.get("hostname") == vnode
    assert hv.get("ansible_host") == "CHANGE_ME"


def test_missing_vnode_defaults_are_a_hard_error(tmp_path, monkeypatch):
    """A registered arch with no block must stop the import, not skip the node."""
    import excel_parser

    monkeypatch.setattr(excel_parser, "air_vnode_host_vars", lambda arch, vnode: None)
    with pytest.raises(SystemExit, match="inventory_defaults.yml"):
        excel_parser.require_air_vnode_host_vars("9-9-9-999", "dhcp-oob")
