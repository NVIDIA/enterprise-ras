#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Normalize NVUE config lines for comparison.

Reads nv set/unset lines from stdin, normalizes interface range notation
and numeric ranges (e.g., priority-group 0-1), expands grouped items into
individual lines, and outputs sorted unique lines.

This allows comparing generated configs (which may use compact notation like
'swp1,swp2,swp3' or 'swp1-3') against running configs from 'nv config show -o commands'
(which may expand or compact differently).

Usage:
    cat config.sh | python3 normalize_nvue.py
    nv config show -o commands | python3 normalize_nvue.py
"""
import re
import sys


def _natural_key(s):
    """Sort key that handles embedded numbers naturally."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]


def _expand_iface_token(token):
    """Expand a NVUE comma+range interface spec to sorted individual interfaces.

    Examples:
      'swp1-3'           -> ['swp1', 'swp2', 'swp3']
      'swp1,swp2,swp3'  -> ['swp1', 'swp2', 'swp3']
      'bond1s0-3'        -> ['bond1s0', 'bond1s1', 'bond1s2', 'bond1s3']
    """
    parts = token.split(',')
    expanded = []
    last_alpha_prefix = None
    for part in parts:
        m = re.match(r'^(.*[a-zA-Z])(\d+)(?:-(\d+))?$', part)
        if m:
            raw_prefix = m.group(1)
            start = int(m.group(2))
            end = int(m.group(3)) if m.group(3) else start
            last_alpha_prefix = raw_prefix
            for i in range(start, end + 1):
                expanded.append(f'{raw_prefix}{i}')
        else:
            m2 = re.match(r'^(\d+)(?:-(\d+))?$', part)
            if m2 and last_alpha_prefix is not None:
                start = int(m2.group(1))
                end = int(m2.group(2)) if m2.group(2) else start
                for i in range(start, end + 1):
                    expanded.append(f'{last_alpha_prefix}{i}')
            else:
                expanded.append(part)
                last_alpha_prefix = None
    expanded.sort(key=_natural_key)
    return expanded


def _is_iface_spec(tok):
    """Check if a token looks like an interface spec (contains letter+digit with range or comma)."""
    return bool(
        re.search(r'[a-zA-Z]\d+-\d', tok)
        or (',' in tok and re.search(r'[a-zA-Z]', tok) and re.search(r'\d', tok))
    )


def _expand_trailing_numeric_range(tokens):
    """Expand a bare numeric range at the end of a line into individual lines.

    Handles patterns like:
      'nv set interface swp10s0 telemetry histogram ingress-buffer priority-group 0-1'
    becomes:
      ['... priority-group 0', '... priority-group 1']

    Also handles comma-separated: '0,1,2' -> individual lines.
    """
    if len(tokens) < 2:
        return [' '.join(tokens)]

    last = tokens[-1]
    # Match pure numeric range: '0-1', '0-3', '100-200'
    m = re.match(r'^(\d+)-(\d+)$', last)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        prefix = tokens[:-1]
        return [' '.join(prefix + [str(i)]) for i in range(start, end + 1)]

    # Match comma-separated numbers: '0,1,2'
    if re.match(r'^\d+(?:,\d+)+$', last):
        prefix = tokens[:-1]
        return [' '.join(prefix + [n]) for n in last.split(',')]

    return [' '.join(tokens)]


def _normalize_syntax(line):
    """Normalize NVUE syntax variations between written and reported forms.

    NVUE 5.15 reports some settings differently than how they are written:
      'enable on'    -> 'state enabled'     (and vice versa)
      'enable off'   -> 'state disabled'
      'ip vrr'       -> 'ipv4 vrr'          (interface-level VRR)

    We normalize everything to the written form (enable on/off, ip vrr)
    so both generated and running configs compare cleanly.
    """
    # state enabled/disabled -> enable on/off
    line = re.sub(r'\bstate enabled\b', 'enable on', line)
    line = re.sub(r'\bstate disabled\b', 'enable off', line)

    # ipv4 vrr -> ip vrr (interface-level VRR only)
    line = re.sub(r'(nv set interface \S+ )ipv4 vrr\b', r'\1ip vrr', line)

    return line


def normalize_and_expand(line):
    """Normalize an nv set/unset line and expand grouped items into individual lines.

    Handles:
    1. Syntax variations (enable on/state enabled, ip vrr/ipv4 vrr)
    2. Interface range/comma specs (swp1-3, swp1,swp2,swp3)
    3. Trailing numeric ranges (priority-group 0-1)

    Returns a list of normalized lines.
    """
    line = ' '.join(line.split())  # normalize whitespace

    # Normalize NVUE syntax variations
    line = _normalize_syntax(line)

    # Strip NVUE default suffixes that the running config adds automatically
    # e.g., 'nv set system ntp server X association-type server' -> 'nv set system ntp server X'
    line = re.sub(r'(\s)association-type server$', '', line)

    tokens = line.split()
    if len(tokens) < 4:
        return [line]

    # Step 1: Expand interface spec (comma-separated or range interfaces)
    iface_idx = None
    for i, tok in enumerate(tokens):
        if _is_iface_spec(tok):
            iface_idx = i
            break

    if iface_idx is not None:
        ifaces = _expand_iface_token(tokens[iface_idx])
        if len(ifaces) > 1:
            results = []
            for iface in ifaces:
                new_tokens = tokens[:iface_idx] + [iface] + tokens[iface_idx + 1:]
                # Also expand trailing numeric ranges on each expanded line
                results.extend(_expand_trailing_numeric_range(new_tokens))
            return results

    # Step 2: Expand trailing numeric ranges (e.g., priority-group 0-1)
    return _expand_trailing_numeric_range(tokens)


# Lines that NVUE 5.15 treats as implicit defaults and does not report
# in 'nv config show -o commands'.  These cause false-positive "missing"
# results when comparing generated configs against running configs.
_IMPLICIT_PATTERNS = [
    # Bridge VLAN membership — reported as part of interface access config
    r'^nv set bridge domain br_default vlan \d+$',
    # EVPN multihoming — implicit when EVPN is enabled
    r'^nv set evpn multihoming enable on$',
    # NVE arp-nd-suppress — implicit when NVE is enabled
    r'^nv set nve vxlan arp-nd-suppress on$',
    # VRF interface assignment — reported differently
    r'^nv set interface \S+ ip vrf \S+$',
    # VRR state up — implicit when VRR is enabled
    r'^nv set interface \S+ ip vrr state up$',
    # VRF-level enable on — implicit defaults on 5.15
    r'^nv set vrf \S+ evpn enable on$',
    r'^nv set vrf \S+ router bgp address-family \S+ enable on$',
    r'^nv set vrf \S+ router bgp address-family \S+ redistribute connected enable on$',
    r'^nv set vrf \S+ router bgp address-family \S+ route-export to-evpn enable on$',
    r'^nv set vrf \S+ router bgp address-family \S+ route-import from-vrf enable on$',
    # BGP path-selection, peer-group details — implicit/default on 5.15
    r'^nv set vrf \S+ router bgp path-selection multipath aspath-ignore on$',
    r'^nv set vrf \S+ router bgp peer-group \S+ address-family \S+ enable (on|off)$',
    r'^nv set vrf \S+ router bgp peer-group \S+ bfd .*$',
]
_IMPLICIT_RE = [re.compile(p) for p in _IMPLICIT_PATTERNS]


def _is_implicit(line):
    """Check if a line matches a known NVUE 5.15 implicit default."""
    return any(r.match(line) for r in _IMPLICIT_RE)


def main():
    lines = set()
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line.startswith('nv '):
            continue
        for expanded in normalize_and_expand(line):
            if not _is_implicit(expanded):
                lines.add(expanded)

    for line in sorted(lines):
        print(line)


if __name__ == '__main__':
    main()
