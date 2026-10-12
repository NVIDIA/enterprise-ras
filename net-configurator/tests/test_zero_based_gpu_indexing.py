# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ADR-0044 zero-based logical GPU indexing vs one-based physical planes.

Workbook GPU plane and rail identifiers are *logical* and zero-based:
`gpu_plane0`, `gpu_rail0`, `gpu_rail0_plane0`, VLAN 900, `192.168.0.0/24`.
Everything physical stays one-based and unchanged — switch hostnames
(`gsl-plane1-*`, `gl-plane2-*`), inventory groups (`gsl_plane1`),
group_vars filenames (`gl_plane1.yml` / `gsl_plane1.yml`) and Wire Map
`Port Side` values. The boundary is therefore:

    logical GPU plane 0 -> physical switch plane 1
    logical GPU plane 1 -> physical switch plane 2

Existing operator-authored one-based workbooks (`gpu_plane1`, `gpu_rail1`,
`gpu_rail1_plane1`) remain readable: a zero marker selects zero-based
parsing, and its absence keeps the legacy one-based reading. Once an origin
is chosen, out-of-range or non-contiguous index sets fail loudly instead of
being reinterpreted with the other origin.

`excel_parser` owns the single detection/translation implementation and
`validate_excel` imports it, so the validator cannot approve a workbook the
parser would read differently.
"""
import ipaddress
import sys
from pathlib import Path

import openpyxl
import pytest
import yaml

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from excel_parser import (  # noqa: E402
    build_devices,
    generate_group_vars,
    generate_host_vars,
    gpu_index_errors,
    gpu_index_origin,
    logical_gpu_plane,
    physical_gpu_plane,
)
from validate_excel import (  # noqa: E402
    ValidationResult,
    validate_gpu_vlan_mode_consistency,
    validate_plane_consistency,
)


# ---------------------------------------------------------------------------
# Fixtures — VLAN rows, Wire Map rows and switch nodes
# ---------------------------------------------------------------------------

# Non-GPU rows every workbook carries. `vni` is required by
# generate_group_vars(), which builds a {vlan_id: vni} map from every row.
BASE_VLANS = [
    {"id": 200, "name": "oob", "subnet": "192.168.200.0/24", "vni": 4200, "vrf": "OOB"},
    {"id": 300, "name": "INBAND", "subnet": "172.16.178.0/24", "vni": 4300, "vrf": "INBAND"},
]

# ADR-0044 aggregate ("single" gpu_vlan_mode) dual-plane rows: zero-based
# names over the unchanged 900/920, /20-at-0/16, 4900/4920 allocations.
AGGREGATE_ZERO_BASED = [
    {"id": 900, "name": "gpu_plane0", "subnet": "192.168.0.0/20",
     "gateway": "192.168.0.1", "vni": 4900, "vrf": "GPU"},
    {"id": 920, "name": "gpu_plane1", "subnet": "192.168.16.0/20",
     "gateway": "192.168.16.1", "vni": 4920, "vrf": "GPU"},
]

# The same fabric as an existing operator wrote it before ADR-0044.
AGGREGATE_ONE_BASED = [
    {"id": 900, "name": "gpu_plane1", "subnet": "192.168.0.0/20",
     "gateway": "192.168.0.1", "vni": 4900, "vrf": "GPU"},
    {"id": 920, "name": "gpu_plane2", "subnet": "192.168.16.0/20",
     "gateway": "192.168.16.1", "vni": 4920, "vrf": "GPU"},
]


def _rail_plane_vlans(index_origin):
    """Two rails x two planes of per-(rail, plane) rows at `index_origin`.

    VLAN/subnet/VNI arithmetic follows the ADR-0044 logical formulas
    (`VLAN = 900 + r + 20*p`) so both origins describe the same fabric and
    only the *names* differ.
    """
    rows = []
    for logical_plane in range(index_origin, index_origin + 2):
        for logical_rail in range(index_origin, index_origin + 2):
            r = logical_rail - index_origin
            p = logical_plane - index_origin
            vlan = 900 + r + 20 * p
            rows.append({
                "id": vlan,
                "name": f"gpu_rail{logical_rail}_plane{logical_plane}",
                "subnet": f"192.168.{vlan - 900}.0/24",
                "gateway": f"192.168.{vlan - 900}.1",
                "vni": vlan + 4000,
                "vrf": "GPU",
            })
    return rows


def _rail_vlans(index_origin, count=2):
    """Single-plane per-rail rows at `index_origin`."""
    return [
        {
            "id": 900 + i,
            "name": f"gpu_rail{index_origin + i}",
            "subnet": f"192.168.{i}.0/24",
            "gateway": f"192.168.{i}.1",
            "vni": 4900 + i,
            "vrf": "GPU",
        }
        for i in range(count)
    ]


def _switch(name, category, index):
    """A switch Nodes-tab row as parse_nodes() would hand it over."""
    return {"name": name, "role": name, "category": category, "index": index,
            "mgmt_ip": "", "status": "Active"}


DUAL_PLANE_LEAVES = [
    _switch("gsl-plane1-01", "gsl-plane1", 1),
    _switch("gsl-plane1-02", "gsl-plane1", 2),
    _switch("gsl-plane2-01", "gsl-plane2", 1),
    _switch("gsl-plane2-02", "gsl-plane2", 2),
]

COMPUTE_NODE = [{"name": "su-01-node-01", "role": "su-01-node-01",
                 "mgmt_ip": "192.168.200.11", "status": "Active"}]


def _wm_row(nic, profile, switch):
    """One Wire Map row in _build_wiremap_row_list() shape."""
    return {"display_in_air": "Yes", "system_role": "gpu",
            "system_name": "su-01-node-01", "nic_port": nic,
            "net_profile": profile, "switch_role": switch.rsplit("-", 1)[0],
            "switch_name": switch, "switch_port": "swp1s0"}


def _host_vars(tmp_path, nodes, vlans, gpu_vlan_mode):
    """Run generate_host_vars() and return {hostname: parsed host_vars}."""
    settings = {"gpu_vlan_mode": gpu_vlan_mode, "architecture": "2-8-9-800"}
    generate_host_vars(nodes, vlans, tmp_path, "2-8-9-800", settings)
    return {
        path.stem: (yaml.safe_load(path.read_text()) or {})
        for path in (tmp_path / "host_vars").glob("*.yml")
    }


def _plane_group_vars(tmp_path, vlans, gpu_vlan_mode="single"):
    """Run generate_group_vars() and return the per-plane group files."""
    nodes = [_switch("core-01", "core", 1)] + DUAL_PLANE_LEAVES
    vrfs = {"GPU": {"name": "GPU", "vlan": 4001, "l3_vni": 104001}}
    settings = {"gpu_vlan_mode": gpu_vlan_mode, "architecture": "2-8-9-800"}
    generate_group_vars(settings, vlans, vrfs, tmp_path, "2-8-9-800", nodes=nodes)
    return {
        path.name: (yaml.safe_load(path.read_text()) or {})
        for path in (tmp_path / "group_vars").glob("*plane*.yml")
    }


def _wire_map_workbook(plane_profiles):
    """A workbook whose Wire Map cables GPU NICs to physical plane switches.

    `plane_profiles` maps a physical plane ordinal to the Network Profile
    values cabled to it, e.g. {1: ["GPU Rail 0 Plane 0"]}.
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("Wire Map")
    ws.append(["Display in Air", "System Role", "System Name", "NIC/Port",
               "Speed", "Description", "Network Profile",
               "Disabled by Neighbor", "Speed2", "Description2",
               "Switch Role", "Switch Name", "Switch Port"])
    for physical_plane, profiles in sorted(plane_profiles.items()):
        for idx, profile in enumerate(profiles, start=1):
            ws.append(["Yes", "gpu", "su-01-node-01", f"eth{idx + 2}",
                       "400G", "", profile, "", "", "",
                       f"gsl-plane{physical_plane}",
                       f"gsl-plane{physical_plane}-01", f"swp{idx}s0"])
    return wb


def _parsed(vlans):
    """Add the `network` object validate_vlans() attaches to each row."""
    return [
        dict(v, network=ipaddress.ip_network(v["subnet"], strict=False))
        for v in vlans
    ]


# ---------------------------------------------------------------------------
# Shared origin detection and logical -> physical translation
# ---------------------------------------------------------------------------

def test_zero_based_plane_maps_to_one_based_physical_plane():
    assert gpu_index_origin(["gpu_rail0_plane0"]) == 0
    assert physical_gpu_plane(0, index_origin=0) == 1
    assert physical_gpu_plane(1, index_origin=0) == 2


def test_legacy_one_based_plane_mapping_is_preserved():
    assert gpu_index_origin(["gpu_rail1_plane1"]) == 1
    assert physical_gpu_plane(1, index_origin=1) == 1
    assert physical_gpu_plane(2, index_origin=1) == 2


@pytest.mark.parametrize("names", [
    ["gpu_plane0", "gpu_plane1"],
    ["gpu_rail0", "gpu_rail1"],
    ["gpu_rail0_plane0", "gpu_rail1_plane0"],
    ["gpu_rail0_plane1"],
    ["gpu_rail3_plane0"],
    ["GPU_Rail0_Plane0", "  gpu_rail1_plane1  "],
])
def test_any_zero_marker_selects_origin_zero(names):
    """A zero index anywhere in a plane, rail or rail-plane name is the marker."""
    assert gpu_index_origin(names) == 0


def test_zero_based_set_containing_index_one_is_still_zero_based():
    """rail1/plane1 are legal *members* of a zero-based set, not legacy markers.

    Treating every non-zero index as one-based would misread the second rail
    and the second plane of every ADR-0044 workbook.
    """
    names = [v["name"] for v in _rail_plane_vlans(0)]
    assert "gpu_rail1_plane1" in names
    assert gpu_index_origin(names) == 0


@pytest.mark.parametrize("names", [
    ["gpu_plane1", "gpu_plane2"],
    ["gpu_rail1", "gpu_rail2"],
    ["gpu_rail1_plane1", "gpu_rail16_plane2"],
    ["oob", "INBAND"],
    [],
    [None, ""],
])
def test_absent_zero_marker_keeps_legacy_origin_one(names):
    assert gpu_index_origin(names) == 1


@pytest.mark.parametrize("origin", [0, 1])
@pytest.mark.parametrize("logical", [0, 1, 2])
def test_logical_gpu_plane_inverts_physical_gpu_plane(origin, logical):
    physical = physical_gpu_plane(logical, index_origin=origin)
    assert logical_gpu_plane(physical, index_origin=origin) == logical


# ---------------------------------------------------------------------------
# Parser: logical GPU data must land on the matching physical switch plane
# ---------------------------------------------------------------------------

def test_zero_based_bare_rail_vlan_becomes_rail0_key():
    """`gpu_rail0` keeps its raw workbook key — rails are never renumbered."""
    devices = build_devices(
        COMPUTE_NODE, BASE_VLANS + _rail_vlans(0),
        wiremap_rows=[_wm_row("eth3", "GPU Rail 0", "gsl-plane1-01"),
                      _wm_row("eth4", "GPU Rail 1", "gsl-plane1-01")],
        gpu_vlan_mode="per_rail")
    ifaces = devices["su-01-node-01"]["gpu_interfaces"]
    assert [i["plane"] for i in ifaces] == ["rail0", "rail1"]
    # Per-rail tables are the rail's own VLAN id — no plane offset applies.
    assert [i["table"] for i in ifaces] == [900, 901]
    assert ifaces[0]["ip"] == "192.168.0.50/24"


def test_zero_based_rail_plane_svis_reach_only_their_physical_plane(tmp_path):
    """Logical plane 0 rails belong to physical plane 1 leaves, and only those."""
    hosts = _host_vars(tmp_path, DUAL_PLANE_LEAVES, BASE_VLANS + _rail_plane_vlans(0),
                       "per_rail_per_plane")
    for leaf in ("gsl-plane1-01", "gsl-plane1-02"):
        assert sorted(hosts[leaf]["gpu_rail_planes"]) == ["rail0_plane0", "rail1_plane0"]
        assert hosts[leaf]["gpu_rail_planes"]["rail0_plane0"]["vlan_id"] == 900
    for leaf in ("gsl-plane2-01", "gsl-plane2-02"):
        assert sorted(hosts[leaf]["gpu_rail_planes"]) == ["rail0_plane1", "rail1_plane1"]
        assert hosts[leaf]["gpu_rail_planes"]["rail0_plane1"]["vlan_id"] == 920


def test_legacy_one_based_rail_plane_svis_keep_their_physical_plane(tmp_path):
    """The pre-ADR-0044 workbook still maps plane1 -> plane1, plane2 -> plane2."""
    hosts = _host_vars(tmp_path, DUAL_PLANE_LEAVES, BASE_VLANS + _rail_plane_vlans(1),
                       "per_rail_per_plane")
    assert sorted(hosts["gsl-plane1-01"]["gpu_rail_planes"]) == [
        "rail1_plane1", "rail2_plane1"]
    assert hosts["gsl-plane1-01"]["gpu_rail_planes"]["rail1_plane1"]["vlan_id"] == 900
    assert sorted(hosts["gsl-plane2-01"]["gpu_rail_planes"]) == [
        "rail1_plane2", "rail2_plane2"]
    assert hosts["gsl-plane2-01"]["gpu_rail_planes"]["rail1_plane2"]["vlan_id"] == 920


def test_zero_based_aggregate_planes_pick_physical_plane_group_vars(tmp_path):
    """`gpu_plane0` configures `gsl_plane1.yml`; `gpu_plane1` configures plane 2.

    Output filenames stay one-based because they must match the inventory
    groups the leaves land in.
    """
    groups = _plane_group_vars(tmp_path, BASE_VLANS + AGGREGATE_ZERO_BASED)
    assert set(groups) == {"gsl_plane1.yml", "gsl_plane2.yml"}
    assert groups["gsl_plane1.yml"]["gpu_vlan"] == 900
    assert groups["gsl_plane1.yml"]["gpu_vni"] == 4900
    assert groups["gsl_plane1.yml"]["gpu_subnet"] == "192.168.0.0/20"
    assert groups["gsl_plane1.yml"]["vlan900_vrr"] == "192.168.0.1/20"
    assert groups["gsl_plane2.yml"]["gpu_vlan"] == 920
    assert groups["gsl_plane2.yml"]["gpu_vni"] == 4920
    assert groups["gsl_plane2.yml"]["gpu_subnet"] == "192.168.16.0/20"
    assert groups["gsl_plane2.yml"]["vlan900_vrr"] == "192.168.16.1/20"


def test_legacy_aggregate_planes_pick_physical_plane_group_vars(tmp_path):
    groups = _plane_group_vars(tmp_path, BASE_VLANS + AGGREGATE_ONE_BASED)
    assert set(groups) == {"gsl_plane1.yml", "gsl_plane2.yml"}
    assert groups["gsl_plane1.yml"]["gpu_vlan"] == 900
    assert groups["gsl_plane1.yml"]["gpu_subnet"] == "192.168.0.0/20"
    assert groups["gsl_plane2.yml"]["gpu_vlan"] == 920
    assert groups["gsl_plane2.yml"]["gpu_subnet"] == "192.168.16.0/20"


def test_rail_plane_group_vars_never_cross_planes(tmp_path):
    """No aggregate row: each physical plane takes a rail row of *its own* plane.

    A per-(rail, plane) workbook has no `gpu_plane{N}` row at all, so the
    plane-group files fall back to picking a rail row. Indexing that rail list
    by the physical plane ordinal reads `gpu_rail1_plane0` for physical plane 2
    and writes logical plane 0's rail data into `gsl_plane2.yml`. The row must
    instead be chosen by the plane it *belongs to*: physical plane 2 is logical
    plane 1, whose first rail is VLAN 920 on `192.168.20.0/24`, VNI 4920.
    """
    groups = _plane_group_vars(
        tmp_path, BASE_VLANS + _rail_plane_vlans(0), "per_rail_per_plane")
    assert set(groups) == {"gsl_plane1.yml", "gsl_plane2.yml"}
    assert groups["gsl_plane1.yml"]["gpu_vlan"] == 900
    assert groups["gsl_plane1.yml"]["gpu_vni"] == 4900
    assert groups["gsl_plane1.yml"]["gpu_subnet"] == "192.168.0.0/24"
    assert groups["gsl_plane1.yml"]["vlan900_vrr"] == "192.168.0.1/24"
    assert groups["gsl_plane2.yml"]["gpu_vlan"] == 920
    assert groups["gsl_plane2.yml"]["gpu_vni"] == 4920
    assert groups["gsl_plane2.yml"]["gpu_subnet"] == "192.168.20.0/24"
    assert groups["gsl_plane2.yml"]["vlan900_vrr"] == "192.168.20.1/24"


def test_legacy_rail_plane_group_vars_keep_their_physical_plane(tmp_path):
    """The same selection on a pre-ADR-0044 sheet: plane1 -> 900, plane2 -> 920."""
    groups = _plane_group_vars(
        tmp_path, BASE_VLANS + _rail_plane_vlans(1), "per_rail_per_plane")
    assert groups["gsl_plane1.yml"]["gpu_vlan"] == 900
    assert groups["gsl_plane1.yml"]["gpu_subnet"] == "192.168.0.0/24"
    assert groups["gsl_plane2.yml"]["gpu_vlan"] == 920
    assert groups["gsl_plane2.yml"]["gpu_subnet"] == "192.168.20.0/24"


@pytest.mark.parametrize("origin", [0, 1])
def test_single_plane_rail_rows_only_configure_physical_plane1(tmp_path, origin):
    """Bare `gpu_railN` rows carry no plane, so only plane 1 may claim them.

    Guessing a value for a plane no row belongs to is what crossed the planes
    in the first place: plane 2 emits no GPU VLAN rather than a plane-1 one.
    """
    groups = _plane_group_vars(
        tmp_path, BASE_VLANS + _rail_vlans(origin), "per_rail")
    assert groups["gsl_plane1.yml"]["gpu_vlan"] == 900
    assert groups["gsl_plane1.yml"]["gpu_subnet"] == "192.168.0.0/24"
    assert "gpu_vlan" not in groups["gsl_plane2.yml"]
    assert "gpu_vni" not in groups["gsl_plane2.yml"]


def test_zero_based_aggregate_pbr_table_bases_are_900_and_1020():
    """Plane offsets are physical: plane 1 adds 0, plane 2 adds 100."""
    devices = build_devices(
        COMPUTE_NODE, BASE_VLANS + AGGREGATE_ZERO_BASED,
        wiremap_rows=[_wm_row("eth3", "GPU Network", "gsl-plane1-01"),
                      _wm_row("eth4", "GPU Network", "gsl-plane2-01")],
        gpu_vlan_mode="single")
    ifaces = devices["su-01-node-01"]["gpu_interfaces"]
    # Physical plane keys — this path derives the plane from the switch it is
    # cabled to, not from the VLAN name.
    assert [i["plane"] for i in ifaces] == ["plane1", "plane2"]
    assert [i["table"] for i in ifaces] == [900, 1020]
    assert [i["ip"] for i in ifaces] == ["192.168.0.50/20", "192.168.16.50/20"]


def test_legacy_aggregate_pbr_table_bases_are_unchanged():
    devices = build_devices(
        COMPUTE_NODE, BASE_VLANS + AGGREGATE_ONE_BASED,
        wiremap_rows=[_wm_row("eth3", "GPU Network", "gsl-plane1-01"),
                      _wm_row("eth4", "GPU Network", "gsl-plane2-01")],
        gpu_vlan_mode="single")
    ifaces = devices["su-01-node-01"]["gpu_interfaces"]
    assert [i["table"] for i in ifaces] == [900, 1020]
    assert [i["ip"] for i in ifaces] == ["192.168.0.50/20", "192.168.16.50/20"]


def test_zero_based_rail_plane_pbr_table_bases_are_900_and_1020():
    """Logical plane 0 must not shift its table down by a plane stride."""
    devices = build_devices(
        COMPUTE_NODE, BASE_VLANS + _rail_plane_vlans(0),
        wiremap_rows=[_wm_row("eth3", "GPU Rail 0 Plane 0", "gsl-plane1-01"),
                      _wm_row("eth4", "GPU Rail 0 Plane 1", "gsl-plane2-01")],
        gpu_vlan_mode="per_rail_per_plane")
    ifaces = devices["su-01-node-01"]["gpu_interfaces"]
    assert [i["plane"] for i in ifaces] == ["rail0_plane0", "rail0_plane1"]
    assert [i["table"] for i in ifaces] == [900, 1020]
    assert [i["ip"] for i in ifaces] == ["192.168.0.50/24", "192.168.20.50/24"]


def test_legacy_rail_plane_pbr_table_bases_are_unchanged():
    devices = build_devices(
        COMPUTE_NODE, BASE_VLANS + _rail_plane_vlans(1),
        wiremap_rows=[_wm_row("eth3", "GPU Rail 1 Plane 1", "gsl-plane1-01"),
                      _wm_row("eth4", "GPU Rail 1 Plane 2", "gsl-plane2-01")],
        gpu_vlan_mode="per_rail_per_plane")
    ifaces = devices["su-01-node-01"]["gpu_interfaces"]
    assert [i["plane"] for i in ifaces] == ["rail1_plane1", "rail1_plane2"]
    assert [i["table"] for i in ifaces] == [900, 1020]


# ---------------------------------------------------------------------------
# Validator: same interpretation as the parser
# ---------------------------------------------------------------------------

def test_zero_based_dual_plane_workbook_passes_plane_consistency():
    """`gpu_plane0`/`gpu_plane1` satisfy `gsl-plane1-*`/`gsl-plane2-*` cabling."""
    wb = _wire_map_workbook({1: ["GPU Network"], 2: ["GPU Network"]})
    result = ValidationResult()
    validate_plane_consistency(wb, _parsed(AGGREGATE_ZERO_BASED), result)
    assert result.errors == []
    assert result.warnings == []


def test_legacy_dual_plane_workbook_passes_plane_consistency():
    wb = _wire_map_workbook({1: ["GPU Network"], 2: ["GPU Network"]})
    result = ValidationResult()
    validate_plane_consistency(wb, _parsed(AGGREGATE_ONE_BASED), result)
    assert result.errors == []
    assert result.warnings == []


@pytest.mark.parametrize("origin", [0, 1])
def test_rail_plane_workbook_passes_plane_consistency_at_either_origin(origin):
    wb = _wire_map_workbook({
        1: [f"GPU Rail {origin} Plane {origin}", f"GPU Rail {origin + 1} Plane {origin}"],
        2: [f"GPU Rail {origin} Plane {origin + 1}",
            f"GPU Rail {origin + 1} Plane {origin + 1}"],
    })
    result = ValidationResult()
    validate_plane_consistency(wb, _parsed(_rail_plane_vlans(origin)), result)
    assert result.errors == []
    assert result.warnings == []


def test_zero_based_plane_missing_from_vlans_is_still_reported():
    """The fix must not make the missing-plane check unreachable."""
    wb = _wire_map_workbook({1: ["GPU Network"], 2: ["GPU Network"]})
    result = ValidationResult()
    validate_plane_consistency(wb, _parsed(AGGREGATE_ZERO_BASED[:1]), result)
    assert any("plane2" in e for e in result.errors), result.errors


def test_zero_based_seventeenth_rail_fails_validation():
    """ADR-0044 caps a plane at 16 rails: rail0..rail15. rail16 is out of range."""
    vlans = _rail_vlans(0, count=16) + [
        {"id": 916, "name": "gpu_rail16", "subnet": "192.168.16.0/24",
         "gateway": "192.168.16.1", "vni": 4916, "vrf": "GPU"},
    ]
    errors = gpu_index_errors([v["name"] for v in vlans])
    assert errors, "17th zero-based rail must be rejected"
    assert any("gpu_rail16" in e for e in errors), errors
    assert any("0" in e for e in errors), errors

    result = ValidationResult()
    validate_gpu_vlan_mode_consistency({"gpu_vlan_mode": "per_rail"}, vlans, result)
    assert any("gpu_rail16" in e for e in result.errors), result.errors


def test_out_of_range_logical_plane_fails_validation():
    """A two-plane fabric has logical planes 0 and 1; plane2 is out of range."""
    vlans = _rail_plane_vlans(0) + [
        {"id": 940, "name": "gpu_rail0_plane2", "subnet": "192.168.40.0/24",
         "gateway": "192.168.40.1", "vni": 4940, "vrf": "GPU"},
    ]
    errors = gpu_index_errors([v["name"] for v in vlans])
    assert any("gpu_rail0_plane2" in e for e in errors), errors

    result = ValidationResult()
    validate_gpu_vlan_mode_consistency(
        {"gpu_vlan_mode": "per_rail_per_plane"}, vlans, result)
    assert any("gpu_rail0_plane2" in e for e in result.errors), result.errors


def test_noncontiguous_zero_based_rails_fail_validation():
    """A gap in the declared rails means one of them is mis-indexed."""
    names = ["gpu_rail0", "gpu_rail1", "gpu_rail3"]
    errors = gpu_index_errors(names)
    assert any("contiguous" in e for e in errors), errors


def test_legacy_and_zero_based_workbooks_report_no_index_errors():
    """Both accepted origins are clean — the check only rejects mixtures."""
    assert gpu_index_errors([v["name"] for v in _rail_plane_vlans(0)]) == []
    assert gpu_index_errors([v["name"] for v in _rail_plane_vlans(1)]) == []
    assert gpu_index_errors([v["name"] for v in _rail_vlans(0, count=16)]) == []
    assert gpu_index_errors([v["name"] for v in _rail_vlans(1, count=16)]) == []
    assert gpu_index_errors([v["name"] for v in AGGREGATE_ZERO_BASED]) == []
    assert gpu_index_errors([v["name"] for v in AGGREGATE_ONE_BASED]) == []
    assert gpu_index_errors([v["name"] for v in BASE_VLANS]) == []


def test_mixed_origin_workbook_is_rejected_not_silently_remapped():
    """`gpu_plane0` + `gpu_plane2` cannot both be right under one origin."""
    errors = gpu_index_errors(["gpu_plane0", "gpu_plane2"])
    assert errors
    assert any("gpu_plane2" in e for e in errors), errors


def test_validator_and_parser_share_one_origin_implementation():
    """The validator must not carry its own copy of the detection rule."""
    import excel_parser
    import validate_excel

    assert validate_excel.gpu_index_origin is excel_parser.gpu_index_origin
    assert validate_excel.physical_gpu_plane is excel_parser.physical_gpu_plane


def test_gpu_vlan_mode_diagnostics_lead_with_zero_based_examples():
    """Operators copy the example names out of the error text."""
    result = ValidationResult()
    validate_gpu_vlan_mode_consistency({"gpu_vlan_mode": "per_rail"}, [], result)
    joined = " ".join(result.errors)
    assert "gpu_rail0" in joined
    assert "gpu_rail1," in joined or "gpu_rail1 " in joined

    result = ValidationResult()
    validate_gpu_vlan_mode_consistency(
        {"gpu_vlan_mode": "per_rail_per_plane"}, [], result)
    assert any("gpu_rail0_plane0" in e for e in result.errors), result.errors
