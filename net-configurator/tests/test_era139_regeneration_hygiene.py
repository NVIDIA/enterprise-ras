# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""ERA-139: regeneration / import hygiene findings from the offline review.

F3  Re-generating into the same site left per-node artefacts of renamed or
    disabled nodes on disk (`configs/<old>-config.sh`, `host_vars/<old>.yml`,
    `node-instructions/<old>.sh`). `prune_stale_artifacts.py` now removes a
    per-node file only when its node has left `inventory/hosts` AND the file
    is recorded in the generator-owned `generated-manifest.json`; operator
    files and `secrets.yml` are never touched.
F9  `common.site` in `group_vars/all/main.yml` was the workbook `site_name`
    cell rather than the resolved `SITE` the inventory was generated for.
F10 `make inventory` piped `ansible-inventory` into `head -50`; on inventories
    longer than 50 lines Ansible died on a closed pipe with a
    "[Errno 32] Broken pipe" traceback. The recipe now drains into a temp
    file and keeps the producer's exit status.
F11 `inventory_defaults.yml` emitted legacy single-interface dnsmasq keys
    (`dhcp_range_start/end`, `dhcp_gateway`, `dhcp_lease_time`,
    `dnsmasq_interface`) into every `main.yml`; generated inventories use
    `ztp_interfaces`, so the values were dead and the deploy summary printed
    them instead of the scopes actually rendered.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import openpyxl
import pytest
import yaml

REPO = Path(__file__).parent.parent
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from excel_parser import process_excel_template  # noqa: E402
from inventory_defaults import arch_group_vars  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "prune_stale_artifacts", SCRIPTS / "prune_stale_artifacts.py")
prune_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prune_mod)

ARCH = "2-4-3-200"
WORKBOOK = REPO / "input" / ARCH / "default" / f"{ARCH}.xlsx"
LEGACY_DNSMASQ_KEYS = ("dhcp_range_start", "dhcp_range_end", "dhcp_lease_time",
                       "dhcp_gateway", "dnsmasq_interface")


def _main_yml(out_dir):
    return yaml.safe_load((out_dir / "group_vars" / "all" / "main.yml").read_text())


# ── F9 ────────────────────────────────────────────────────────────────────

def test_common_site_is_the_resolved_site_not_the_workbook_cell(tmp_path):
    """SITE=audit-flat with a workbook whose site_name says `sample`."""
    wb_path = tmp_path / f"{ARCH}.xlsx"
    shutil.copy(WORKBOOK, wb_path)
    wb = openpyxl.load_workbook(wb_path)
    for row in wb["Deployment"].iter_rows(min_row=1):
        if row[0].value == "site_name":
            row[1].value = "sample"
    wb.save(wb_path)

    out = tmp_path / "output" / ARCH / "audit-flat" / "inventory"
    process_excel_template(wb_path, out, site="audit-flat")
    assert _main_yml(out)["common"]["site"] == "audit-flat"


def test_common_site_falls_back_to_workbook_cell_without_a_site(tmp_path):
    out = tmp_path / "inventory"
    process_excel_template(WORKBOOK, out)
    assert _main_yml(out)["common"]["site"] == "default"


def test_cli_passes_resolved_site_through():
    src = (SCRIPTS / "excel_parser.py").read_text()
    assert "process_excel_template(excel_path, output_dir, site=args.site)" in src


# ── F11 ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("arch", sorted(
    p.name for p in (REPO / "input").iterdir()
    if (p / "default" / f"{p.name}.xlsx").exists()))
def test_legacy_dnsmasq_keys_are_not_defaulted_for_any_arch(arch):
    shared = arch_group_vars("all", arch)
    leaked = [k for k in LEGACY_DNSMASQ_KEYS if k in shared]
    assert not leaked, f"{arch}: obsolete top-level dnsmasq keys still defaulted: {leaked}"


def test_generated_main_yml_has_ztp_interfaces_and_no_legacy_keys(tmp_path):
    out = tmp_path / "inventory"
    process_excel_template(WORKBOOK, out)
    main = _main_yml(out)
    leaked = [k for k in LEGACY_DNSMASQ_KEYS if k in main]
    assert not leaked, f"legacy top-level dnsmasq keys in generated main.yml: {leaked}"
    listening = [i for i in main["ztp_interfaces"] if i.get("dnsmasq_listen")]
    assert listening, "generated inventories must carry at least one listening ztp_interfaces entry"
    for iface in listening:
        assert iface["dhcp_range_start"] and iface["dhcp_range_end"] and iface["gateway"]


def _ztp_role_tasks():
    return yaml.safe_load((REPO / "roles" / "ztp-server" / "tasks" / "main.yml").read_text())


def test_deploy_summary_no_longer_prints_top_level_legacy_keys():
    tasks = _ztp_role_tasks()
    summary = next(t for t in tasks if t["name"] == "Display ZTP server information")
    text = "\n".join(summary["debug"]["msg"])
    for key in LEGACY_DNSMASQ_KEYS:
        assert key not in text, f"deploy summary still prints top-level {key}"
    builder = next(t for t in tasks if t["name"] == "Build DHCP scope summary lines")
    assert "ztp_interfaces" in builder["set_fact"]["ztp_dhcp_summary_lines"]


@pytest.mark.skipif(not shutil.which("ansible-playbook"), reason="ansible-playbook required")
def test_deploy_summary_renders_actual_ztp_interface_scopes(tmp_path):
    """Run the summary tasks under real Ansible against a generated main.yml
    (per-interface branch) and against an inventory with no ztp_interfaces
    (legacy branch). Offline: localhost only, nothing is installed."""
    out = tmp_path / "inventory"
    process_excel_template(WORKBOOK, out)
    main = _main_yml(out)
    iface = next(i for i in main["ztp_interfaces"] if i.get("dnsmasq_listen"))

    tasks = _ztp_role_tasks()
    keep = ("Build DHCP scope summary lines",
            'Display configured DHCP scopes as "interface (purpose) range  gateway"')
    subset = [t for t in tasks if t["name"] in keep]
    assert len(subset) == 2
    (tmp_path / "summary.yml").write_text(yaml.safe_dump(subset, sort_keys=False))
    play = [
        {"hosts": "localhost", "gather_facts": False,
         "vars_files": [str(out / "group_vars" / "all" / "main.yml")],
         "tasks": [{"include_tasks": str(tmp_path / "summary.yml")}]},
        {"hosts": "localhost", "gather_facts": False,
         "vars": {"dnsmasq_interface": "ens9", "dhcp_range_start": "10.9.9.50",
                  "dhcp_range_end": "10.9.9.60", "dhcp_gateway": "10.9.9.1"},
         "tasks": [{"include_tasks": str(tmp_path / "summary.yml")}]},
    ]
    (tmp_path / "play.yml").write_text(yaml.safe_dump(play, sort_keys=False))
    env = {**os.environ, "ANSIBLE_LOCALHOST_WARNING": "false",
           "ANSIBLE_STDOUT_CALLBACK": "default"}
    env.pop("ANSIBLE_CONFIG", None)
    res = subprocess.run(["ansible-playbook", "-i", "localhost,", str(tmp_path / "play.yml")],
                         capture_output=True, text=True, env=env, cwd=tmp_path, timeout=300)
    assert res.returncode == 0, res.stdout + res.stderr
    expected = (f"{iface['name']} ({iface['purpose']}): {iface['dhcp_range_start']} - "
                f"{iface['dhcp_range_end']}  gateway {iface['gateway']}")
    assert expected in res.stdout, res.stdout
    assert "ens9 (legacy): 10.9.9.50 - 10.9.9.60  gateway 10.9.9.1" in res.stdout, res.stdout
    assert "192.168.200.100" not in res.stdout.split("PLAY [localhost]")[1], \
        "per-interface branch must not fall back to the legacy defaults"


# ── F10 ───────────────────────────────────────────────────────────────────

def _inventory_recipe():
    mk = (REPO / "Makefile").read_text()
    start = mk.index("\ninventory:")
    end = mk.index("\nstatus:", start)
    return mk[start:end]


def test_make_inventory_does_not_pipe_ansible_inventory_into_head():
    recipe = _inventory_recipe()
    assert "--yaml | head" not in recipe
    assert "2>/dev/null" not in recipe, "producer stderr must not be suppressed"
    assert "exit $$rc" in recipe.rstrip().splitlines()[-1]


@pytest.mark.skipif(not shutil.which("bash"), reason="bash required")
@pytest.mark.parametrize(("lines", "producer_rc"), [(400, 0), (400, 3), (10, 0)])
def test_make_inventory_recipe_drains_output_and_keeps_exit_status(tmp_path, lines, producer_rc):
    """Execute the recipe body under bash with a stub ansible-inventory that
    writes `lines` lines to stdout, a marker to stderr, and exits producer_rc."""
    recipe = _inventory_recipe()
    body = []
    for raw in recipe.splitlines():
        if raw.startswith("\t@") and not raw.startswith("\t@#") and "echo \"📋" not in raw \
                and raw.strip() != '@echo ""' and "check_arch" not in raw:
            body.append(raw[2:])
        elif raw.startswith("\t\t"):
            body.append(raw[2:])
    script = "\n".join(body).replace("$$", "$").replace("$(INVENTORY_DIR)", "inv")

    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "ansible-inventory"
    stub.write_text("#!/bin/bash\n"
                    f"for i in $(seq 1 {lines}); do echo \"line $i\"; done\n"
                    "echo 'STDERR-MARKER' >&2\n"
                    f"exit {producer_rc}\n")
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "TMPDIR": str(tmp_path)}
    res = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                         env=env, cwd=tmp_path, timeout=60)

    assert res.returncode == producer_rc, res.stderr
    assert "Broken pipe" not in res.stdout + res.stderr
    assert "STDERR-MARKER" in res.stderr, "producer stderr must reach the operator"
    shown = [l for l in res.stdout.splitlines() if l.startswith("line ")]
    assert len(shown) == min(lines, 50)
    if lines > 50:
        assert f"{lines - 50} more lines" in res.stdout
    else:
        assert "more lines" not in res.stdout
    assert not [p for p in tmp_path.iterdir() if p.name.startswith("tmp.")], \
        "temp file must be removed"


# ── F3 ────────────────────────────────────────────────────────────────────

def test_generate_runs_pruner_as_its_last_step():
    mk = (REPO / "Makefile").read_text()
    start = mk.index("\ngenerate:")
    end = mk.index("\ntopology:", start)
    recipe = mk[start:end]
    assert "scripts/prune_stale_artifacts.py --arch $(ARCH) --site $(SITE) --mark-start" in recipe
    assert "scripts/prune_stale_artifacts.py --arch $(ARCH) --site $(SITE)\n" in recipe
    assert recipe.index("--mark-start") < recipe.index("excel_parser.py"), \
        "the start marker must be dropped before the first generator writes anything"
    assert recipe.rindex("prune_stale_artifacts.py") > recipe.index("generate-node-instructions.py")


def test_help_generate_documents_the_pruning_step():
    mk = (REPO / "Makefile").read_text()
    start = mk.index("\nhelp-generate:")
    end = mk.index("\nhelp-ztp-setup:", start)
    text = mk[start:end]
    assert "6. Prune" in text and "DELETES" in text and "generated-manifest.json" in text
    assert "--dry-run" in text
    assert "prune" in (REPO / "README.md").read_text().lower()


def _site(tmp_path, hosts, files, manifest=None):
    site = tmp_path / "output" / ARCH / "audit-prune"
    (site / "inventory" / "host_vars").mkdir(parents=True)
    (site / "inventory" / "group_vars" / "all").mkdir(parents=True)
    (site / "configs").mkdir()
    (site / "topology" / "node-instructions").mkdir(parents=True)
    (site / "inventory" / "hosts").write_text(
        "# generated\n[switches]\n" + "\n".join(hosts) + "\n\n[switches:vars]\nansible_user=cumulus\n")
    (site / "inventory" / "group_vars" / "all" / "secrets.yml").write_text("switch_password: keep\n")
    for rel in files:
        (site / rel).write_text(f"# {rel}\n")
    if manifest is not None:
        (site / prune_mod.MANIFEST_NAME).write_text(json.dumps({"schema": 1, "files": manifest}))
    return site


def test_prunes_only_manifest_owned_files_of_departed_nodes(tmp_path):
    current = ["inventory/host_vars/core-01.yml", "configs/core-01-config.sh",
               "topology/node-instructions/core-01.sh"]
    stale = ["inventory/host_vars/core-99.yml", "configs/core-99-config.sh",
             "topology/node-instructions/core-99.sh"]
    operator = ["configs/operator-notes-config.sh", "inventory/host_vars/hand-made.yml"]
    site = _site(tmp_path, ["core-01"], current + stale + operator, manifest=current + stale)

    result = prune_mod.prune(site, ARCH, "audit-prune")

    assert result["pruned"] == stale
    assert sorted(result["unmanaged"]) == sorted(operator)
    for rel in stale:
        assert not (site / rel).exists()
    for rel in current + operator:
        assert (site / rel).exists()
    assert (site / "inventory" / "group_vars" / "all" / "secrets.yml").read_text() == "switch_password: keep\n"
    manifest = json.loads((site / prune_mod.MANIFEST_NAME).read_text())
    assert manifest["files"] == sorted(current)
    assert manifest["arch"] == ARCH and manifest["site"] == "audit-prune"


def test_unwritten_file_of_a_current_host_is_never_adopted_nor_pruned(tmp_path):
    """An operator's configs/support-01-config.sh (the CLI generator only
    writes switches) must not become generator-owned just because support-01
    is a current host — otherwise removing support-01 later would delete it."""
    generated = ["inventory/host_vars/support-01.yml", "inventory/host_vars/core-01.yml"]
    operator = "configs/support-01-config.sh"
    site = _site(tmp_path, ["core-01", "support-01"], generated + [operator])
    old = time.time() - 3600
    os.utime(site / operator, (old, old))
    since = prune_mod.mark_start(site).stat().st_mtime - 1
    for rel in generated:
        (site / rel).write_text("# rewritten by this run\n")

    first = prune_mod.prune(site, ARCH, "audit-prune", since=since)
    assert first["skipped"] == [operator]
    assert sorted(first["current"]) == sorted(generated)
    assert operator not in json.loads((site / prune_mod.MANIFEST_NAME).read_text())["files"]

    hosts = site / "inventory" / "hosts"
    hosts.write_text(hosts.read_text().replace("\nsupport-01\n", "\n"))
    (site / generated[0]).unlink()  # the generator no longer writes it
    second = prune_mod.prune(site, ARCH, "audit-prune", since=time.time() - 1)
    assert second["pruned"] == []
    assert second["unmanaged"] == [operator]
    assert (site / operator).exists()


def test_cli_refuses_to_adopt_without_a_start_marker(tmp_path, capsys):
    files = ["inventory/host_vars/core-01.yml"]
    _site(tmp_path, ["core-01"], files)
    args = ["--arch", ARCH, "--site", "audit-prune", "--base-dir", str(tmp_path)]
    assert prune_mod.main(args) == 1
    assert "--mark-start" in capsys.readouterr().out
    assert prune_mod.main(args + ["--adopt-all"]) == 0
    site = tmp_path / "output" / ARCH / "audit-prune"
    assert json.loads((site / prune_mod.MANIFEST_NAME).read_text())["files"] == files
    assert prune_mod.main(args + ["--mark-start"]) == 0
    assert (site / prune_mod.START_MARKER).exists()
    assert prune_mod.main(args) == 0
    assert not (site / prune_mod.START_MARKER).exists(), "marker is consumed by the run"


def test_l2_infra_and_topology_node_instructions_are_current_not_unmanaged(tmp_path):
    """generate-node-instructions.py writes air-oob-switch.sh / dhcp-oob.sh /
    oob-server-01.sh (L2) and one script per Air topology node; none of
    those names need be a host in inventory/hosts. The L2 names count only
    while the topology records L2 mode (an old topology without the field
    is L2 by definition, see utils.topology_oob_uplink_mode)."""
    ni = ["topology/node-instructions/air-oob-switch.sh",
          "topology/node-instructions/dhcp-oob.sh",
          "topology/node-instructions/oob-server-01.sh",
          "topology/node-instructions/cust-net-edge-01.sh",
          "topology/node-instructions/core-01.sh"]
    stale_ni = "topology/node-instructions/gsl-plane2-02.sh"
    site = _site(tmp_path, ["core-01"], ni + [stale_ni, "configs/cust-net-edge-01-config.sh"],
                 manifest=[stale_ni])
    (site / "topology" / f"{ARCH}-topology.json").write_text(json.dumps(
        {"content": {"nodes": {"core-01": {}, "cust-net-edge-01": {}}, "links": []}}))

    result = prune_mod.prune(site, ARCH, "audit-prune")
    assert sorted(result["current"]) == sorted(ni)
    assert result["pruned"] == [stale_ni]
    # topology nodes only widen the node-instructions class, not configs/
    assert result["unmanaged"] == ["configs/cust-net-edge-01-config.sh"]


def test_switching_site_from_l2_to_l3_prunes_the_recorded_l2_infra_scripts(tmp_path):
    """After oob_uplink_mode flips to L3 the generator no longer writes
    air-oob-switch.sh / dhcp-oob.sh / oob-server-01.sh; the copies the L2 run
    recorded must leave disk and the manifest like any other departed node,
    while a genuine L2 site keeps them without warnings."""
    l2 = ["topology/node-instructions/air-oob-switch.sh",
          "topology/node-instructions/dhcp-oob.sh",
          "topology/node-instructions/oob-server-01.sh"]
    keep = ["topology/node-instructions/core-01.sh"]
    site = _site(tmp_path, ["core-01"], l2 + keep)
    topo = site / "topology" / f"{ARCH}-topology.json"
    topo.write_text(json.dumps(
        {"_oob_uplink_mode": "l2", "content": {"nodes": {"core-01": {}}, "links": []}}))
    first = prune_mod.prune(site, ARCH, "audit-prune")
    assert sorted(first["current"]) == sorted(l2 + keep)
    assert first["pruned"] == [] and first["unmanaged"] == []

    topo.write_text(json.dumps(
        {"_oob_uplink_mode": "l3", "content": {"nodes": {"core-01": {}}, "links": []}}))
    second = prune_mod.prune(site, ARCH, "audit-prune", since=time.time() - 1)
    assert sorted(second["pruned"]) == sorted(l2)
    assert second["unmanaged"] == []
    for rel in l2:
        assert not (site / rel).exists(), rel
    manifest = json.loads((site / prune_mod.MANIFEST_NAME).read_text())["files"]
    assert manifest == keep

    # a later run (e.g. a host disabled) must not resurrect them either
    third = prune_mod.prune(site, ARCH, "audit-prune", since=time.time() - 1)
    assert third["pruned"] == [] and third["unmanaged"] == []
    assert json.loads((site / prune_mod.MANIFEST_NAME).read_text())["files"] == keep


def test_first_run_without_manifest_prunes_nothing(tmp_path):
    files = ["inventory/host_vars/core-01.yml", "inventory/host_vars/core-99.yml"]
    site = _site(tmp_path, ["core-01"], files)
    result = prune_mod.prune(site, ARCH, "audit-prune")
    assert result["pruned"] == []
    assert result["unmanaged"] == ["inventory/host_vars/core-99.yml"]
    assert (site / "inventory" / "host_vars" / "core-99.yml").exists()
    assert json.loads((site / prune_mod.MANIFEST_NAME).read_text())["files"] == \
        ["inventory/host_vars/core-01.yml"]


def test_dry_run_reports_but_removes_nothing(tmp_path):
    files = ["configs/core-99-config.sh"]
    site = _site(tmp_path, ["core-01"], files, manifest=files)
    result = prune_mod.prune(site, ARCH, "audit-prune", dry_run=True)
    assert result["pruned"] == files
    assert (site / files[0]).exists()
    manifest = json.loads((site / prune_mod.MANIFEST_NAME).read_text())
    assert manifest["files"] == files, "dry-run must not rewrite the manifest"


def test_parse_hosts_skips_children_and_vars_sections(tmp_path):
    hosts = tmp_path / "hosts"
    hosts.write_text("[a]\nx-1 ansible_host=1.2.3.4\n[b:children]\na\n[b:vars]\nfoo=bar\n[c]\n# c\ny-1\n")
    assert prune_mod.parse_hosts(hosts) == {"x-1", "y-1"}


def test_missing_inventory_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        prune_mod.prune(tmp_path / "nope", ARCH, "audit-prune")
    assert prune_mod.main(["--arch", ARCH, "--site", "audit-prune",
                           "--base-dir", str(tmp_path)]) == 1


def test_renamed_node_on_a_real_inventory_is_pruned_but_connection_state_survives(tmp_path):
    """Generate 2-4-3-200, record the manifest, then simulate the workbook
    renaming support-01 (its host line disappears, support-01x appears)."""
    site = tmp_path / "output" / ARCH / "audit-prune"
    inv = site / "inventory"
    process_excel_template(WORKBOOK, inv, site="audit-prune")
    # Air connection details written by air-deploy.py into a *current* host.
    oob = yaml.safe_load((inv / "host_vars" / "oob-server-01.yml").read_text()) \
        if (inv / "host_vars" / "oob-server-01.yml").exists() else None
    conn_file = "oob-server-01.yml" if oob is not None else "core-01.yml"
    conn = yaml.safe_load((inv / "host_vars" / conn_file).read_text())
    conn.update({"ansible_host": "air.example", "ansible_port": 24001, "ansible_user": "ubuntu"})
    (inv / "host_vars" / conn_file).write_text(yaml.safe_dump(conn))
    secrets_before = (inv / "group_vars" / "all" / "secrets.yml").read_text()

    first = prune_mod.prune(site, ARCH, "audit-prune")
    assert first["pruned"] == [] and "inventory/host_vars/support-01.yml" in first["current"]

    hosts = inv / "hosts"
    hosts.write_text(hosts.read_text().replace("\nsupport-01\n", "\nsupport-01x\n"))
    (inv / "host_vars" / "support-01x.yml").write_text("hostname: support-01x\n")

    second = prune_mod.prune(site, ARCH, "audit-prune")
    assert second["pruned"] == ["inventory/host_vars/support-01.yml"]
    assert not (inv / "host_vars" / "support-01.yml").exists()
    assert (inv / "host_vars" / "support-01x.yml").exists()
    kept = yaml.safe_load((inv / "host_vars" / conn_file).read_text())
    assert (kept["ansible_host"], kept["ansible_port"], kept["ansible_user"]) == \
        ("air.example", 24001, "ubuntu")
    assert (inv / "group_vars" / "all" / "secrets.yml").read_text() == secrets_before
    manifest = json.loads((site / prune_mod.MANIFEST_NAME).read_text())
    assert "inventory/host_vars/support-01x.yml" in manifest["files"]
    assert "inventory/host_vars/support-01.yml" not in manifest["files"]
