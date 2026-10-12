# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""YAML dump/load for the generated Ansible inventory (ADR-0090).

Ansible templates every inventory string that contains a Jinja marker
(``{{``, ``{%``, ``{#``) when the variable is used. Workbook text therefore must
never reach the inventory as a plain string: a banner cell holding
``{{ lookup('pipe', ...) }}`` would run a command on the controller at
``make generate``.

The rule is default-deny. On dump, every string containing a marker is tagged
``!unsafe`` (Ansible keeps it literal) unless the tool itself authored it as an
expression, which it marks by wrapping the value in :class:`AnsibleExpr`
(e.g. ``AnsibleExpr('{{ ldap_admin_password }}')``). Strings without a marker
cannot be templated and are written unchanged, so ordinary output is identical.

Usage:
    import inventory_yaml
    inventory_yaml.dump(data, fh)          # instead of yaml.dump(...)
    data = inventory_yaml.load(fh)         # reads generated files back
    data = inventory_yaml.load_tool_yaml(text)  # repo-authored YAML (defaults)
"""

import re

import yaml

JINJA_MARKER_RE = re.compile(r"\{\{|\{%|\{#")
UNSAFE_TAG = "!unsafe"


class AnsibleExpr(str):
    """A tool-authored Jinja expression that Ansible must evaluate."""


class UnsafeText(str):
    """Text read back from an ``!unsafe`` scalar; stays ``!unsafe`` on re-dump."""


def has_jinja_marker(text):
    return bool(JINJA_MARKER_RE.search(text))


class InventoryDumper(yaml.Dumper):
    """yaml.Dumper that tags marker-bearing strings ``!unsafe`` (see module doc)."""


def _represent_str(dumper, data):
    if has_jinja_marker(data):
        return dumper.represent_scalar(UNSAFE_TAG, str(data))
    return dumper.represent_str(str(data))


def _represent_expr(dumper, data):
    return dumper.represent_str(str(data))


InventoryDumper.add_representer(str, _represent_str)
InventoryDumper.add_representer(UnsafeText, _represent_str)
InventoryDumper.add_representer(AnsibleExpr, _represent_expr)


def dump(data, stream=None, **kwargs):
    kwargs.setdefault("default_flow_style", False)
    kwargs.setdefault("sort_keys", False)
    return yaml.dump(data, stream, Dumper=InventoryDumper, **kwargs)


class InventoryLoader(yaml.SafeLoader):
    """SafeLoader for generated inventory: ``!unsafe`` -> UnsafeText; an untagged
    marker string was written by the tool, so it round-trips as AnsibleExpr."""


def _construct_unsafe(loader, node):
    return UnsafeText(loader.construct_scalar(node))


def _construct_tool_str(loader, node):
    value = loader.construct_scalar(node)
    return AnsibleExpr(value) if has_jinja_marker(value) else value


InventoryLoader.add_constructor(UNSAFE_TAG, _construct_unsafe)
InventoryLoader.add_constructor("tag:yaml.org,2002:str", _construct_tool_str)


def load(stream):
    return yaml.load(stream, Loader=InventoryLoader)


class ToolYamlLoader(yaml.SafeLoader):
    """SafeLoader for repo-authored YAML: marker strings are tool expressions."""


ToolYamlLoader.add_constructor("tag:yaml.org,2002:str", _construct_tool_str)


def load_tool_yaml(stream):
    return yaml.load(stream, Loader=ToolYamlLoader)
