#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Extract architecture requirements from ERA deployment guide PDFs.

Reads a PDF from architectural_docs/ and generates a structured YAML
requirements file in docs/requirements/.

Usage:
    python3 scripts/extract_requirements.py architectural_docs/ERA-00016*.pdf
    python3 scripts/extract_requirements.py --all   # process all PDFs in architectural_docs/
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber required. Install with: pip install pdfplumber")
    sys.exit(1)


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_full_text(pdf_path):
    """Extract all text from a PDF."""
    with pdfplumber.open(pdf_path) as pdf:
        pages = []
        for page in pdf.pages:
            pages.append(page.extract_text() or '')
    return pages


def find_arch(pages):
    """Detect the architecture name (e.g., 2-8-5-200) from the PDF."""
    for page_text in pages[:5]:
        m = re.search(r'(\d-\d+-\d+-\d+)\s+node\s+architecture', page_text, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r'ERA\s+(\d-\d+-\d+-\d+)', page_text)
        if m:
            return m.group(1)
    return None


def find_doc_id(pages):
    """Extract document ID (e.g., ERA-00016-001) and version."""
    for page_text in pages[:5]:
        m = re.search(r'(ERA-\d{5}-\d{3})\s+[Vv](\d+)', page_text)
        if m:
            return m.group(1), m.group(2)
    return None, None


def find_doc_date(pages):
    """Extract document date."""
    for page_text in pages[:5]:
        # Pattern: "25th November 2025" or "November 2025" or "2025 November"
        m = re.search(r'(\d{4})\s+(January|February|March|April|May|June|July|August|September|October|November|December)', page_text, re.IGNORECASE)
        if m:
            return f"{m.group(2)} {m.group(1)}"
        m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', page_text, re.IGNORECASE)
        if m:
            return f"{m.group(1)} {m.group(2)}"
    return None


# ---------------------------------------------------------------------------
# Port assignment extraction
# ---------------------------------------------------------------------------

def extract_port_table(pages):
    """Extract the SN5610 port assignment table from the PDF.

    Returns a dict of role -> {start_port, end_port, breakout, lanes, ...}
    """
    full_text = '\n'.join(pages)
    roles = {}

    # Patterns found in ERA PDFs (text is noisy from OCR):
    # "CPU/INBAND (N/S) swp1s0 swp5s3 Breakout port to 4x 200G ports with 2 lanes"
    # "GPU (E/W) swp6s0 swp25s1 Breakout port to 2x 400G ports with 4 lanes"

    # Clean up common OCR artifacts
    text = full_text.replace('\n', ' ')

    # Match port role lines
    # Regex patterns for port role lines. OCR text is noisy, so patterns
    # are lenient on whitespace and stray characters between swp numbers.
    # Each pattern captures: (start_port, end_port, breakout_multiplier, lanes)
    role_patterns = [
        (r'CPU/INBAND\s*\(N/S\)\s*swp(\d+)s\d+\s+.*?swp(\d+)s\d+.*?(\d+)x\s*\d+G.*?(\d+)\s*lane', 'cpu'),
        (r'GPU\s*\(E/W\)\s*swp(\d+)s\d+\s+.*?swp(\d+)s\d+.*?(\d+)x\s*\d+G.*?(\d+)\s*lane', 'gpu'),
        (r'ISL\s*\(Interlink\)\s*swp(\d+)s\d+\s+.*?swp(\d+)s\d+.*?(\d+)x\s*\d+G.*?(\d+)\s*lane', 'isl'),
        (r'SUPPORT\s+swp(\d+)s?\d*\s+.*?swp(\d+)\D.*?(\d+)x\s*\d+G.*?(\d+)\s*lane', 'support'),
        (r'STORAGE\s+swp.{0,5}(\d+)\s*s?\s*\d*\s+.*?swp.{0,5}(\d+)s?\d*.*?(\d+)x\s*\d+G.*?(\d+)\s*lane', 'storage'),
        (r'OOB\s+swp.{0,3}(\d+)s\d+.*?swp.{0,3}(\d+)s\d+.*?(\d+)x\s*\d+G.*?(\d+)\s*lane', 'oob_uplink'),
        (r'(?:COMMON/)?EXIT\s+swp(\d+)s\d+\s+.*?swp(\d+)s\d+.*?(\d+)x\s*\d+G.*?(\d+)\s*lane', 'edge'),
    ]

    for pattern, role_name in role_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            roles[role_name] = {
                'start_port': int(m.group(1)),
                'end_port': int(m.group(2)),
                'breakout': int(m.group(3)),
                'lanes': int(m.group(4)),
            }

    # Extract disabled ports
    disabled_match = re.search(r'swp(\d+(?:,\s*swp\d+)*)\s+are\s+disabled', text, re.IGNORECASE)
    if disabled_match:
        disabled_text = disabled_match.group(0)
        disabled_ports = [int(x) for x in re.findall(r'swp(\d+)', disabled_text)]
        roles['disabled'] = disabled_ports

    return roles


def extract_vlan_table(pages):
    """Extract VLAN/VNI mappings from the PDF."""
    full_text = '\n'.join(pages)
    vlans = {}

    # Pattern: "OOB 200 4200 172.16.177.0/24" etc.
    vlan_patterns = [
        (r'OOB\s+200\s+4200\s+([\d./]+)', 200, 4200, 'OOB'),
        (r'INBAND\s+300\s+4300\s+([\d./]+)', 300, 4300, 'INBAND'),
        (r'INBAND\s+400\s+4400\s+([\d./]+)', 400, 4400, 'INBAND'),
        (r'INBAND\s+500\s+4500\s+([\d./]+)', 500, 4500, 'INBAND'),
        (r'GPU\s+900\s+4900\s+([\d./]+)', 900, 4900, 'GPU'),
    ]

    for pattern, vlan_id, vni, vrf in vlan_patterns:
        m = re.search(pattern, full_text, re.IGNORECASE)
        subnet = m.group(1).strip() if m else None
        vlans[vlan_id] = {
            'vni': vni,
            'vrf': vrf,
            'subnet': subnet,
        }

    return vlans


def extract_oob_switch_count(pages):
    """Determine number of OOB switches from the PDF."""
    full_text = '\n'.join(pages)

    # Look for patterns like "3x SN2201" or "2 OOB" or table with SN2201 count
    m = re.search(r'(\d+)\s*x?\s*SN2201', full_text)
    if m:
        return int(m.group(1))

    # Fallback: check for 17-24 nodes -> 3 switches, 8-16 -> 2
    m = re.search(r'17.*24.*3\s*(?:x\s*)?SN2201', full_text, re.DOTALL)
    if m:
        return 3

    return None


def extract_node_spec(pages, arch):
    """Extract node hardware spec from architecture name and PDF."""
    parts = arch.split('-')
    if len(parts) == 4:
        return {
            'cpus_per_node': int(parts[0]),
            'gpus_per_node': int(parts[1]),
            'nics_per_node': int(parts[2]),
            'nic_speed': f"{parts[3]}G",
            'nodes_per_su': 4,  # standard across all ERAs
        }
    return {}


# ---------------------------------------------------------------------------
# YAML generation
# ---------------------------------------------------------------------------

def build_requirements(arch, doc_id, doc_version, doc_date, port_roles, vlans, oob_count, node_spec, pdf_name):
    """Build the requirements dict for YAML output."""
    req = {
        'source_document': f"{doc_id}_v{doc_version}" if doc_id else "unknown",
        'source_file': pdf_name,
        'extracted_date': datetime.now().strftime('%Y-%m-%d'),
        'architecture': arch,
    }

    if node_spec:
        req['node_spec'] = node_spec

    if oob_count:
        req['oob_switches'] = oob_count

    # Build core_ports section
    core_ports = {}

    role_config = {
        'cpu': {
            'bond': True, 'lacp_bypass': True, 'vlan': 300,
            'description': 'CPU/INBAND North-South converged network',
        },
        'gpu': {
            'bond': False, 'vlan': 900, 'pfc_watchdog': True,
            'description': 'GPU East-West compute fabric',
        },
        'support': {
            'bond': True, 'lacp_bypass': True, 'vlan': 400, 'vlan_untagged': 300,
            'description': 'Support servers (bcme, k8s)',
        },
        'isl': {
            'bond': False, 'evpn_mh_uplink': True,
            'description': 'Inter-Switch Links (core-01 to core-02)',
        },
        'oob_uplink': {
            'bond': True, 'vlan': 200,
            'description': 'Uplinks to OOB management switches (SN2201)',
        },
        'storage': {
            'bond': True, 'lacp_bypass': True, 'vlan': 500,
            'description': 'Storage fabric uplinks',
        },
        'edge': {
            'bond': False, 'vrf': 'EXIT',
            'description': 'Customer edge / EXIT uplinks',
        },
    }

    for role_name, port_info in port_roles.items():
        if role_name == 'disabled':
            core_ports['disabled'] = {
                'ports': sorted(port_info),
                'reason': 'Adjacent port disabled when neighbor uses 8-lane breakout',
            }
            continue

        start = port_info['start_port']
        end = port_info['end_port']
        ports = list(range(start, end + 1))

        speed_map = {(2, 4): '400G', (4, 2): '200G', (8, 1): '100G'}
        speed = speed_map.get((port_info['breakout'], port_info['lanes']), 'unknown')

        entry = {
            'ports': ports,
            'breakout': port_info['breakout'],
            'lanes': port_info['lanes'],
            'speed_per_link': speed,
        }

        # Merge role-specific config
        if role_name in role_config:
            entry.update(role_config[role_name])

        core_ports[role_name] = entry

    if core_ports:
        req['core_ports'] = core_ports

    return req


def write_requirements(req, output_path):
    """Write requirements dict to YAML file."""

    class FlowListDumper(yaml.SafeDumper):
        """Custom dumper that uses flow style for port lists."""
        pass

    def represent_list(dumper, data):
        # Use flow style for lists of ints (port lists) to keep them compact
        if data and all(isinstance(x, int) for x in data):
            return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)
        return dumper.represent_sequence('tag:yaml.org,2002:seq', data)

    FlowListDumper.add_representer(list, represent_list)

    header = (
        "# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.\n"
        "# SPDX-License-Identifier: MIT\n"
        "#\n"
        f"# Architecture requirements for ERA {req['architecture']}\n"
        f"# Extracted from: {req.get('source_document', 'unknown')}\n"
        f"# Extraction date: {req.get('extracted_date', 'unknown')}\n"
        "#\n"
        "# AUTO-GENERATED by scripts/extract_requirements.py\n"
        "# Review and adjust before using for validation.\n"
        "\n"
    )

    with open(output_path, 'w') as f:
        f.write(header)
        f.write("---\n")
        yaml.dump(req, f, Dumper=FlowListDumper, default_flow_style=False, sort_keys=False)

    print(f"  Written to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_pdf(pdf_path, output_dir):
    """Process a single PDF and generate requirements YAML."""
    pdf_path = Path(pdf_path)
    print(f"\nProcessing: {pdf_path.name}")

    pages = extract_full_text(pdf_path)
    print(f"  Pages: {len(pages)}")

    arch = find_arch(pages)
    if not arch:
        print(f"  ERROR: Could not detect architecture from PDF")
        return False
    print(f"  Architecture: {arch}")

    doc_id, doc_version = find_doc_id(pages)
    doc_date = find_doc_date(pages)
    print(f"  Document: {doc_id} v{doc_version} ({doc_date})")

    port_roles = extract_port_table(pages)
    print(f"  Port roles found: {list(port_roles.keys())}")

    vlans = extract_vlan_table(pages)
    print(f"  VLANs found: {list(vlans.keys())}")

    oob_count = extract_oob_switch_count(pages)
    print(f"  OOB switches: {oob_count}")

    node_spec = extract_node_spec(pages, arch)

    req = build_requirements(
        arch, doc_id, doc_version, doc_date,
        port_roles, vlans, oob_count, node_spec,
        pdf_path.name,
    )

    # Write to output
    output_path = Path(output_dir) / f'{arch}.yml'
    write_requirements(req, output_path)

    # Print summary of extracted ports for review
    print(f"\n  Port assignment summary:")
    for role, info in req.get('core_ports', {}).items():
        if role == 'disabled':
            print(f"    {role:15s} ports={info['ports']}")
        else:
            ports = info.get('ports', [])
            bo = info.get('breakout', '?')
            lanes = info.get('lanes', '?')
            spd = info.get('speed_per_link', '?')
            if ports:
                print(f"    {role:15s} swp{ports[0]}-swp{ports[-1]} ({len(ports)} ports) {bo}x {spd} ({lanes} lanes)")
            else:
                print(f"    {role:15s} NO PORTS EXTRACTED — needs manual review")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Extract architecture requirements from ERA PDF deployment guides'
    )
    parser.add_argument('pdf', nargs='*', help='PDF file(s) to process')
    parser.add_argument('--all', action='store_true', help='Process all PDFs in architectural_docs/')
    parser.add_argument('--output-dir', default='docs/requirements',
                        help='Output directory for YAML files (default: docs/requirements)')
    parser.add_argument('--draft', action='store_true',
                        help='Write to docs/requirements/drafts/ instead of overwriting')
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    if args.all:
        pdf_dir = project_root / 'architectural_docs'
        pdf_files = sorted(pdf_dir.glob('*.pdf'))
    elif args.pdf:
        pdf_files = [Path(p) for p in args.pdf]
    else:
        parser.print_help()
        sys.exit(1)

    if not pdf_files:
        print("No PDF files found")
        sys.exit(1)

    output_dir = project_root / args.output_dir
    if args.draft:
        output_dir = output_dir / 'drafts'
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output directory: {output_dir}")

    success = 0
    for pdf_path in pdf_files:
        if process_pdf(pdf_path, output_dir):
            success += 1

    print(f"\n{'=' * 60}")
    print(f"Processed {success}/{len(pdf_files)} PDFs")
    if args.draft:
        print(f"Drafts written to {output_dir}/")
        print(f"Review and copy to docs/requirements/ when ready")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
