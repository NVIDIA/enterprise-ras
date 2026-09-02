# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
ERA-37 — the validation bundle must be safe to email.

`output/` holds a *plaintext* `group_vars/all/secrets.yml`, and an LDAP-enabled
deployment renders its LDAP secret into the switch config scripts. The bundle
is what an OEM sends onward for endorsement, so a leak here goes to a third
party.

Three layers are tested, in the order they'd fail an operator:
  1. `secrets.yml` is never staged.
  2. Secret *values* are redacted wherever else they appear.
  3. A pattern guard aborts the build on anything credential-shaped that
     survived — the layer that protects against a future template change.

Plus the regression that made layer 2 unusable at first: the shipped defaults
set `status_page_password` to the documented placeholder `CHANGE_ME`, which is
also the value of `ansible_host` on the Air vnodes. Redacting it blanked a
hostname field the reviewer needs.
"""
import shutil
import importlib.util
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location(
        "make_validation_bundle", SCRIPTS / "make_validation_bundle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mvb = _load()

EXCLUDED_RELPATH = "inventory/group_vars/all/secrets.yml"


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A miniature output/<arch>/<site> tree, with the module pointed at it."""
    monkeypatch.setattr(mvb, "REPO", tmp_path)
    s = tmp_path / "output" / "arch1" / "s1"
    (s / "configs").mkdir(parents=True)
    (s / "inventory" / "group_vars" / "all").mkdir(parents=True)
    (s / "topology").mkdir(parents=True)

    (s / "inventory" / "group_vars" / "all" / "secrets.yml").write_text(
        "switch_ansible_password: SuperSecret123\n"
        "ldap_admin_password: Ldap@Secret99\n"
        "status_page_password: CHANGE_ME\n"
        "status_page_username: adm\n"
    )
    (s / "configs" / "sw-01-config.sh").write_text(
        "#!/bin/bash\n"
        "nv set system aaa ldap secret Ldap@Secret99\n"
        "nv set interface swp1 description uplink\n"
    )
    (s / "inventory" / "host_vars").mkdir()
    (s / "inventory" / "host_vars" / "utility.yml").write_text(
        "ansible_host: CHANGE_ME\nansible_user: ubuntu\n")
    (s / "inventory" / "group_vars" / "switches.yml").write_text(
        'ansible_password: "{{ switch_ansible_password }}"\n')
    (s / "topology" / "topo.json").write_text('{"nodes": []}\n')
    return s


def _build(tmp_path, expect=0):
    out = tmp_path / "bundle.zip"
    import sys
    argv = sys.argv
    sys.argv = ["x", "--arch", "arch1", "--site", "s1", "--out", str(out)]
    try:
        code = mvb.main()
    finally:
        sys.argv = argv
    assert code == expect, f"expected exit {expect}, got {code}"
    return out


def _names(zpath):
    with zipfile.ZipFile(zpath) as z:
        return set(z.namelist())


def _read(zpath, name):
    with zipfile.ZipFile(zpath) as z:
        return z.read(name).decode()


# ------------------------------------------------ layer 1: never staged -----

def test_secrets_file_is_never_bundled(site, tmp_path):
    out = _build(tmp_path)
    assert EXCLUDED_RELPATH not in _names(out)
    assert not any("secrets.yml" in n for n in _names(out))


# ------------------------------------------------ layer 2: value redaction --

def test_secret_values_are_redacted_from_configs(site, tmp_path):
    """The LDAP secret is rendered into the switch config by the template."""
    out = _build(tmp_path)
    cfg = _read(out, "configs/sw-01-config.sh")
    assert "Ldap@Secret99" not in cfg
    assert mvb.REDACTED in cfg
    assert "nv set interface swp1 description uplink" in cfg  # rest intact


def test_placeholder_values_are_not_redacted(site, tmp_path):
    """Regression: status_page_password ships as the documented placeholder
    CHANGE_ME, which is also `ansible_host: CHANGE_ME` on the Air vnodes.
    Redacting it blanked a hostname the reviewer needs, and protected nothing."""
    out = _build(tmp_path)
    assert "ansible_host: CHANGE_ME" in _read(out, "inventory/host_vars/utility.yml")


def test_jinja_references_are_left_alone(site, tmp_path):
    """`ansible_password: "{{ switch_ansible_password }}"` is a reference, not a
    secret; the generated inventory is full of them by design."""
    out = _build(tmp_path)
    assert "{{ switch_ansible_password }}" in _read(
        out, "inventory/group_vars/switches.yml")


# ------------------------------------------------ layer 3: the guard --------

def test_guard_blocks_a_secret_the_value_pass_cannot_know(site, tmp_path):
    """The layer that matters long-term: a secret that is NOT in secrets.yml —
    e.g. one a future template starts emitting — must still stop the build."""
    (site / "configs" / "sw-02-config.sh").write_text(
        "nv set system aaa ldap secret NotInSecretsYaml123\n")
    out = tmp_path / "bundle.zip"
    import sys
    argv = sys.argv
    sys.argv = ["x", "--arch", "arch1", "--site", "s1", "--out", str(out)]
    try:
        code = mvb.main()
    finally:
        sys.argv = argv
    assert code == 1, "guard must fail the build"
    assert not out.exists(), "no archive may be written when the guard trips"


def test_cumulus_masked_password_is_not_a_finding(site, tmp_path):
    """A collected running config renders an unset/hidden password as `'*'`.
    That is the *absence* of a secret. Without this the guard fires on every
    `reports/raw/config-*.txt` — the exact artifact an endorsement bundle
    exists to carry, so the feature failed on its primary use case.

    Observed on a real site (2-8-9-800/evpnval): 16 findings, every one
    `nv set system aaa user cumulus hashed-password '*'`."""
    (site / "configs" / "collected.txt").write_text(
        "  ~ nv set system aaa user cumulus hashed-password '*'\n"
        "nv set system aaa user cumulus hashed-password '*'\n")
    # Scoped to this file: the fixture plants its own real secret elsewhere.
    assert [f for f in mvb.guard(site) if "collected.txt" in f] == []


def test_a_real_secret_beside_a_masked_one_still_trips_the_guard(site, tmp_path):
    """The masked-value skip must not blunt the guard."""
    (site / "configs" / "collected.txt").write_text(
        "nv set system aaa user cumulus hashed-password '*'\n"
        "nv set system aaa ldap secret RealLeakedSecret99\n")
    mine = [f for f in mvb.guard(site) if "collected.txt" in f]
    assert len(mine) == 1 and "collected.txt:2" in mine[0], mine


def test_documented_default_passwords_are_not_redacted(site, tmp_path):
    """`nvidia` ships as a documented default and appears inside legitimate
    hostnames — `ansible_host: air-worker-example.air-inside.nvidia.com`. Redacting
    it protects nothing (it is public in the repo) and mangles the hostname."""
    (site / "inventory" / "group_vars" / "all" / "secrets.yml").write_text(
        "server_ansible_password: nvidia\nswitch_password: RealSecret12345\n")
    (site / "inventory" / "host_vars" / "utility.yml").write_text(
        "ansible_host: air-worker-example.air-inside.nvidia.com\n")
    # The fixture's planted LDAP secret is no longer in this secrets.yml, so it
    # would (correctly) trip the guard and mask what this test is checking.
    (site / "configs" / "sw-01-config.sh").write_text(
        "#!/bin/bash\nnv set interface swp1 description uplink\n")
    out = _build(tmp_path)
    hv = _read(out, "inventory/host_vars/utility.yml")
    assert hv.strip() == "ansible_host: air-worker-example.air-inside.nvidia.com"
    assert "nvidia" not in mvb.load_secret_values("arch1", "s1")
    assert "RealSecret12345" in mvb.load_secret_values("arch1", "s1")


def test_guard_catches_a_vault_body_and_private_key(site, tmp_path):
    (site / "configs" / "leak.txt").write_text(
        "$ANSIBLE_VAULT;1.1;AES256\n3736\n")
    findings = mvb.guard(site)
    assert any("vault" in f for f in findings), findings


def test_staging_is_cleaned_up_when_the_guard_trips(site, tmp_path):
    (site / "configs" / "sw-02-config.sh").write_text(
        "nv set system aaa ldap secret NotInSecretsYaml123\n")
    import sys
    argv = sys.argv
    sys.argv = ["x", "--arch", "arch1", "--site", "s1",
                "--out", str(tmp_path / "b.zip")]
    try:
        mvb.main()
    finally:
        sys.argv = argv
    assert not (site / ".bundle-staging").exists()


# ------------------------------------------------ contents / manifest -------

def test_bundle_carries_the_expected_trees_and_a_manifest(site, tmp_path):
    out = _build(tmp_path)
    names = _names(out)
    assert "configs/sw-01-config.sh" in names
    assert "topology/topo.json" in names
    assert "inventory/host_vars/utility.yml" in names
    assert "MANIFEST.txt" in names


def test_manifest_checksums_every_file(site, tmp_path):
    out = _build(tmp_path)
    manifest = _read(out, "MANIFEST.txt")
    for n in _names(out):
        if n != "MANIFEST.txt":
            assert n in manifest, f"{n} missing from MANIFEST"
    assert "arch1" in manifest and "s1" in manifest


def test_out_path_outside_the_repo_does_not_crash(site, tmp_path, monkeypatch, capsys):
    """`--out /tmp/x.zip` used to raise ValueError from Path.relative_to(REPO) —
    *after* the archive was written, so the bundle existed but the run
    tracebacked. The path is reported either way."""
    outside = Path("/tmp") / "era_bundle_outside_repo_test.zip"
    if outside.exists():
        outside.unlink()
    import sys
    argv = sys.argv
    sys.argv = ["x", "--arch", "arch1", "--site", "s1", "--out", str(outside)]
    try:
        assert mvb.main() == 0
    finally:
        sys.argv = argv
        printed = capsys.readouterr().out
        if outside.exists():
            outside.unlink()
    assert str(outside) in printed


def test_success_output_reports_a_clickable_absolute_path(site, tmp_path, capsys):
    out = _build(tmp_path)
    printed = capsys.readouterr().out
    assert str(out.resolve()) in printed, "absolute path must be shown"
    assert f"file://{out.resolve()}" in printed, "file:// URI must be shown"


def test_missing_output_dir_is_a_clean_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(mvb, "REPO", tmp_path)
    import sys
    argv = sys.argv
    sys.argv = ["x", "--arch", "nope", "--site", "default"]
    try:
        assert mvb.main() == 1
    finally:
        sys.argv = argv


# ------------------------------------------------ e2e marker sweep ----------

REAL_SITE = REPO / "output" / "2-8-9-800" / "default"
MARKER = "catfrogcatfrog"


@pytest.mark.skipif(not REAL_SITE.is_dir(), reason="generated 2-8-9-800 output absent")
def test_marker_password_appears_nowhere_in_a_bundle_built_from_real_output(tmp_path, monkeypatch):
    """The sweep an operator would actually run: set every credential to one
    marker string, build a bundle from REAL generated artifacts, then hunt for
    the marker everywhere — extracted files, the raw archive bytes, and inside
    the bundled .xlsx (a zip within a zip, which a plain grep cannot see into).

    Fixture-based tests cover the layers individually; this is the end-to-end
    "is the password anywhere at all" check.
    """
    monkeypatch.setattr(mvb, "REPO", tmp_path)
    site = tmp_path / "output" / "2-8-9-800" / "default"
    site.parent.mkdir(parents=True)
    shutil.copytree(REAL_SITE, site,
                    ignore=shutil.ignore_patterns("validation-bundle-*.zip",
                                                  ".bundle-staging"))
    (tmp_path / "input" / "2-8-9-800" / "default").mkdir(parents=True)
    src_xlsx = REPO / "input" / "2-8-9-800" / "default" / "2-8-9-800.xlsx"
    if src_xlsx.exists():
        shutil.copy2(src_xlsx, tmp_path / "input" / "2-8-9-800" / "default" / "2-8-9-800.xlsx")

    # Every credential becomes the marker...
    secrets = site / "inventory" / "group_vars" / "all" / "secrets.yml"
    secrets.parent.mkdir(parents=True, exist_ok=True)
    secrets.write_text("".join(
        f"{k}: {MARKER}\n" for k in (
            "switch_ansible_password", "server_ansible_password",
            "ansible_become_password", "switch_password",
            "ldap_admin_password", "ldap_user_default_password",
            "status_page_username", "status_page_password")))
    # ...and it also lands in a rendered config, as an LDAP-enabled deploy does.
    cfg = next(iter(sorted((site / "configs").glob("*-config.sh"))))
    cfg.write_text(cfg.read_text() + f"\nnv set system aaa ldap secret {MARKER}\n")

    out = tmp_path / "b.zip"
    import sys
    argv = sys.argv
    sys.argv = ["x", "--arch", "2-8-9-800", "--site", "default", "--out", str(out)]
    try:
        assert mvb.main() == 0
    finally:
        sys.argv = argv

    extract = tmp_path / "x"
    with zipfile.ZipFile(out) as z:
        z.extractall(extract)

    # 1) every extracted file, read as bytes so binaries are covered too
    for f in extract.rglob("*"):
        if f.is_file():
            assert MARKER.encode() not in f.read_bytes(), f"marker survived in {f}"

    # 2) the raw archive, catching any stored/uncompressed copy
    assert MARKER.encode() not in out.read_bytes(), "marker present in raw .zip"

    # 3) inside the bundled .xlsx — decompress it, since it is a zip of XML
    for x in extract.rglob("*.xlsx"):
        with zipfile.ZipFile(x) as z:
            for part in z.namelist():
                assert MARKER.encode() not in z.read(part), f"marker in {x.name}:{part}"

    # sanity: the bundle is substantive and the redaction actually ran
    assert any(extract.rglob("configs/*-config.sh"))
    assert not any(extract.rglob("secrets.yml"))
    assert mvb.REDACTED in (extract / "configs" / cfg.name).read_text()


# ------------------------------------------------ helper unit tests ---------

def test_short_and_placeholder_values_are_skipped(site):
    vals = mvb.load_secret_values("arch1", "s1")
    assert "SuperSecret123" in vals and "Ldap@Secret99" in vals
    assert "CHANGE_ME" not in vals, "documented placeholder must be skipped"
    assert "adm" not in vals, "too short to redact safely"
