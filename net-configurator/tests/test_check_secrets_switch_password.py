# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""`check_secrets.py` refuses switch passwords that fail the ERA policy (ERA-129, ADR-0078).

ZTP applies `switch_password` with `nv set system aaa user cumulus password`;
on a switch with password-hardening enabled a value such as the untouched
`CHANGE_ME` placeholder is refused, ZTP finishes with the factory password
still in place, and every later login uses the wrong one. The ERA policy is
the Cumulus password-security rule set regardless of the switch's setting
(`--policy placeholder` relaxes it). Server-side passwords are not gated: the
default `nvidia` is fine there.

The shipped `Cumu1usLinux!` is accepted without a development override.

All values below are synthetic. Nothing here is a real credential.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NC / "scripts"))

import check_secrets as cs  # noqa: E402

GOOD = "Zq9#Synth-Hardened"  # pragma: allowlist secret
SHIPPED = "Cumu1usLinux!"  # the documented default in inventories/secrets.yml


def test_viable_switch_password_passes():
    assert cs.password_problems(GOOD) == []


@pytest.mark.parametrize("value", ["era-status-CHANGE_ME"])
@pytest.mark.parametrize("policy", cs.POLICIES)
def test_status_sentinel_is_a_placeholder_under_every_policy(value, policy):
    assert cs.PLACEHOLDER_PROBLEM in cs.password_problems(value, policy=policy)


@pytest.mark.parametrize("value", ["CHANGE_ME", "change_me", "  CHANGE_ME ", "changeme", "password", ""])
def test_placeholders_are_rejected(value):
    assert cs.password_problems(value)


def test_change_me_names_the_placeholder_rule():
    assert any("placeholder" in p for p in cs.password_problems("CHANGE_ME"))


@pytest.mark.parametrize("value, rule", [
    ("Ab1!", "shorter than 8"),
    ("ABCDEFG1!", "no lowercase"),
    ("abcdefg1!", "no uppercase"),
    ("Abcdefgh!", "no digit"),
    ("Abcdefg1", "no special"),
    ("Cumulus", "equals the username"),
])
def test_each_hardening_rule_is_reported(value, rule):
    assert any(rule in p for p in cs.password_problems(value)), cs.password_problems(value)


@pytest.mark.parametrize("special", list("`~!@#$%^&*()-_+=|[]{};:',<.>/?") + [" "])
def test_every_cumulus_special_character_counts(special):
    assert cs.password_problems(f"Abcdefg1{special}") == []


def test_none_is_not_set():
    assert cs.password_problems(None) == ["is not set"]


def test_only_switch_keys_are_gated():
    secrets = {
        "switch_password": "CHANGE_ME",  # pragma: allowlist secret
        "switch_ansible_password": GOOD,
        "switch_bootstrap_password": "cumulus",  # pragma: allowlist secret
        "server_ansible_password": "nvidia",  # pragma: allowlist secret
        "ansible_become_password": "nvidia",  # pragma: allowlist secret
        "status_page_password": "CHANGE_ME",  # pragma: allowlist secret
        "ldap_user_default_password": "x",
    }
    findings = cs.check_switch_passwords(secrets)
    assert len(findings) == 1
    assert findings[0].startswith("switch_password ")


def test_server_defaults_alone_are_fine():
    assert cs.check_switch_passwords({"switch_ansible_password": GOOD,
                                      "server_ansible_password": "nvidia",  # pragma: allowlist secret
                                      "ansible_become_password": "nvidia",  # pragma: allowlist secret
                                      "switch_bootstrap_password": "cumulus"}) == []  # pragma: allowlist secret


def test_missing_switch_ansible_password_is_a_finding():
    # group_vars/switches.yml has `ansible_password: "{{ switch_ansible_password }}"`
    # with no default, so omitting it breaks every switch login.
    findings = cs.check_switch_passwords({"switch_password": GOOD})
    assert len(findings) == 1 and findings[0].startswith("switch_ansible_password is not set")
    assert "switches.yml" in findings[0]


def test_username_rule_follows_switch_user_from_secrets():
    # ztp.sh.j2 applies the password to `switch_user | default("cumulus")`.
    pw = "Netadmin1!"
    assert cs.check_switch_passwords({"switch_ansible_password": pw}) == []
    findings = cs.check_switch_passwords({"switch_user": "netadmin1!",
                                          "switch_ansible_password": pw})
    assert findings and "equals the username 'netadmin1!'" in findings[0]


def test_malformed_yaml_reports_location_not_source_line(tmp_path):
    leak = "Zq9#LeakProbe"
    f = tmp_path / "secrets.yml"
    f.write_text(f"switch_password: {GOOD}\nswitch_ansible_password: [{leak}\n")
    findings, note = cs.check_secrets_file(f)
    assert note is None and len(findings) == 1
    assert "is not valid YAML (line" in findings[0]
    assert leak not in findings[0] and GOOD not in findings[0]


def test_findings_never_contain_the_value():
    bad = "Zq9#SyntheticLeakProbe"  # would pass the policy; make it fail via username
    findings = cs.check_switch_passwords({"switch_password": "CHANGE_ME",  # pragma: allowlist secret
                                          "switch_ansible_password": bad.lower()[:5]})
    joined = " ".join(findings)
    assert "CHANGE_ME" not in joined and bad.lower()[:5] not in joined


@pytest.mark.parametrize("policy", cs.POLICIES)
def test_shipped_default_passes_without_override(policy):
    assert cs.password_problems(SHIPPED, policy=policy) == []
    findings, note = cs.check_secrets_file(NC / "inventories" / "secrets.yml", policy=policy)
    assert findings == [] and note is None


def test_dev_opt_in_waives_only_the_placeholder_rule():
    waived = []
    findings, _ = cs.classify_switch_passwords(
        {"switch_password": "CHANGE_ME", "switch_ansible_password": GOOD},  # pragma: allowlist secret
        policy="placeholder", waived=waived)
    assert findings == [] and waived == ["switch_password"]
    waived = []
    findings, _ = cs.classify_switch_passwords(
        {"switch_password": "CHANGE_ME", "switch_ansible_password": GOOD}, waived=waived)  # pragma: allowlist secret
    assert waived == [] and len(findings) == 1 and findings[0].startswith("switch_password ")


def test_missing_switch_password_falls_back_to_ztp_template_default():
    assert cs.check_switch_passwords({"switch_ansible_password": GOOD}) == []


@pytest.mark.parametrize("value, expected", [("1", True), (" 1 ", True), ("", False),
                                             ("0", False), ("yes", False), ("true", False)])
def test_dev_opt_in_requires_exactly_one(value, expected):
    assert cs.dev_opt_in_enabled({cs.DEV_OPT_IN_ENV: value}) is expected
    assert cs.dev_opt_in_enabled({}) is False


def test_unedited_example_is_exactly_the_case_that_must_stop():
    """`secrets.yml.example` ships every switch password as CHANGE_ME. An
    operator who copies it and forgets to edit it is the reported failure."""
    findings, note = cs.check_secrets_file(NC / "inventories" / "secrets.yml.example")
    assert note is None
    assert sorted(f.split()[0] for f in findings) == ["switch_ansible_password", "switch_password"]
    assert all("placeholder" in f for f in findings)


def test_vault_encrypted_file_is_skipped_with_note(tmp_path):
    p = tmp_path / "secrets.yml"
    p.write_text("$ANSIBLE_VAULT;1.1;AES256\n3030\n")
    findings, note = cs.check_secrets_file(p)
    assert findings == [] and "vault-encrypted" in note


def test_missing_file_is_a_note_not_a_failure(tmp_path):
    findings, note = cs.check_secrets_file(tmp_path / "nope.yml")
    assert findings == [] and "built-in defaults" in note


def test_resolve_prefers_generated_copy(tmp_path):
    gen = tmp_path / "output/a/s/inventory/group_vars/all/secrets.yml"
    gen.parent.mkdir(parents=True)
    gen.write_text("switch_password: x\n")
    (tmp_path / "inventories").mkdir()
    (tmp_path / "inventories/secrets.yml").write_text("switch_password: y\n")
    assert cs.resolve_secrets_file(tmp_path, "a", "s") == gen
    assert cs.resolve_secrets_file(tmp_path, "a", "other") == tmp_path / "inventories/secrets.yml"


def _cli(*args, opt_in=False):
    env = {k: v for k, v in os.environ.items() if k != cs.DEV_OPT_IN_ENV}
    if opt_in:
        env[cs.DEV_OPT_IN_ENV] = "1"
    return subprocess.run([sys.executable, str(NC / "scripts" / "check_secrets.py"), *args],
                          capture_output=True, text=True, env=env)


def test_cli_accepts_shipped_default_without_override(tmp_path):
    p = tmp_path / "secrets.yml"
    p.write_text(f'switch_password: "{SHIPPED}"\nswitch_ansible_password: "{SHIPPED}"\n')
    r = _cli("--file", str(p))
    assert r.returncode == 0, r.stdout
    assert "WARNING" not in r.stdout and SHIPPED not in r.stdout


def test_cli_dev_opt_in_passes_with_a_warning(tmp_path):
    p = tmp_path / "secrets.yml"
    p.write_text('switch_password: "CHANGE_ME"\nswitch_ansible_password: "CHANGE_ME"\n')  # pragma: allowlist secret
    r = _cli("--file", str(p), "--policy", "placeholder", opt_in=True)
    assert r.returncode == 0, r.stdout
    assert "WARNING" in r.stdout and "development only" in r.stdout
    assert "switch_password, switch_ansible_password" in r.stdout and "CHANGE_ME" not in r.stdout


def test_dev_opt_in_is_recorded_and_cleared(tmp_path):
    record = cs.record_dev_opt_in(tmp_path, "2-4-3-200", "s", ["switch_password"])
    assert record == tmp_path / "output" / "2-4-3-200" / "s" / cs.DEV_OPT_IN_RECORD
    text = record.read_text()
    assert "DEVELOPMENT ONLY" in text and "switch_password" in text and "CHANGE_ME" not in text and SHIPPED not in text
    assert cs.record_dev_opt_in(tmp_path, "2-4-3-200", "s", []) is None
    assert not record.exists()


def test_cli_fails_closed_on_change_me_without_leaking(tmp_path):
    p = tmp_path / "secrets.yml"
    p.write_text('switch_password: "CHANGE_ME"\nserver_ansible_password: "nvidia"\n')  # pragma: allowlist secret
    r = _cli("--file", str(p))
    assert r.returncode == 1
    assert "switch_password" in r.stdout and "placeholder" in r.stdout
    assert "CHANGE_ME" not in r.stdout and "nvidia" not in r.stdout
    assert "server_ansible_password" not in r.stdout


def test_cli_passes_on_viable_password(tmp_path):
    p = tmp_path / "secrets.yml"
    p.write_text(f'switch_password: "{GOOD}"\nswitch_ansible_password: "{GOOD}"\n')
    r = _cli("--file", str(p))
    assert r.returncode == 0 and "pass the ERA switch-password policy" in r.stdout
    assert GOOD not in r.stdout and "WARNING" not in r.stdout


# --- per-variable vault, Jinja aliases / lookups, policy selection -----------

VAULT_SCALAR = (
    "!vault |\n"
    "          $ANSIBLE_VAULT;1.1;AES256\n"
    "          66386439653236336462626566653063336164663966303231363934653561363964363833313662\n"
    "          6431626536303530376336343832656537303632313433360a626438346336353331386135323734\n"
)


def test_vault_scalar_on_unrelated_key_does_not_block(tmp_path):
    p = tmp_path / "secrets.yml"
    p.write_text(f'switch_password: "{GOOD}"\nswitch_ansible_password: "{GOOD}"\n'
                 f"ldap_admin_password: {VAULT_SCALAR}")
    findings, note = cs.check_secrets_file(p)
    assert findings == [] and note is None
    assert _cli("--file", str(p)).returncode == 0


def test_vault_scalar_on_switch_key_is_reported_not_asserted_viable(tmp_path):
    p = tmp_path / "secrets.yml"
    p.write_text(f'switch_password: "{GOOD}"\nswitch_ansible_password: {VAULT_SCALAR}')
    findings, note = cs.check_secrets_file(p)
    assert findings == []
    assert note and "switch_ansible_password is !vault-encrypted" in note
    r = _cli("--file", str(p))
    assert r.returncode == 0 and "!vault-encrypted" in r.stdout and "pass the ERA" not in r.stdout


def test_alias_to_valid_key_resolves_and_passes():
    secrets = {"switch_ansible_password": GOOD,
               "switch_password": "{{ switch_ansible_password }}"}
    assert cs.classify_switch_passwords(secrets) == ([], [])


def test_alias_to_placeholder_fails_on_the_aliasing_key():
    secrets = {"switch_ansible_password": "CHANGE_ME",  # pragma: allowlist secret
               "switch_password": "{{ switch_ansible_password }}"}
    findings = cs.check_switch_passwords(secrets)
    assert len(findings) == 2
    assert any(f.startswith("switch_password is a placeholder") for f in findings)


def test_dangling_or_looping_alias_is_a_finding():
    assert cs.check_switch_passwords({"switch_ansible_password": "{{ nope }}"}) == [
        "switch_ansible_password aliases 'nope', which is not set in this file"]
    loop = {"switch_ansible_password": "{{ switch_password }}",
            "switch_password": "{{ switch_ansible_password }}"}
    assert all("alias loop" in f for f in cs.check_switch_passwords(loop))


def test_lookup_expression_is_unchecked_not_viable(monkeypatch):
    monkeypatch.setenv("SWITCH_PASS1", "CHANGE_ME")
    secrets = {"switch_ansible_password": "{{ lookup('env', 'SWITCH_PASS1') }}"}
    findings, unchecked = cs.classify_switch_passwords(secrets)
    assert findings == []
    assert len(unchecked) == 1 and unchecked[0].startswith("switch_ansible_password is a Jinja template")
    assert "CHANGE_ME" not in unchecked[0]


def test_jinja_comment_cannot_make_a_weak_password_pass(tmp_path):
    # Ansible renders this to "abc": the comment must not supply the classes.
    secrets = {"switch_ansible_password": "abc{# DEF1! #}"}  # pragma: allowlist secret
    findings, unchecked = cs.classify_switch_passwords(secrets)
    assert findings == []
    assert len(unchecked) == 1 and "not checked" in unchecked[0]
    assert "DEF1" not in unchecked[0]
    p = tmp_path / "secrets.yml"
    p.write_text('switch_ansible_password: "abc{# DEF1! #}"\n')  # pragma: allowlist secret
    r = _cli("--file", str(p))
    assert r.returncode == 0 and "pass the ERA" not in r.stdout and "not checked" in r.stdout


@pytest.mark.parametrize("raw", ["{{ other_key }} ", " {{ other_key }}", "{{ other_key }}\n",
                                 "x{{ other_key }}", "{{ other_key }}!"])
def test_alias_with_literal_whitespace_is_not_falsely_rejected(raw):
    # Ansible keeps the surrounding text as part of the password; we neither
    # drop it (false reject of a 7+1-char value) nor guess at it.
    secrets = {"other_key": "Abcdef1", "switch_ansible_password": raw}  # pragma: allowlist secret
    findings, unchecked = cs.classify_switch_passwords(secrets)
    assert findings == []
    assert len(unchecked) == 1 and "not checked" in unchecked[0]
    assert "Abcdef1" not in unchecked[0]


def test_bare_alias_with_inner_spacing_still_resolves():
    secrets = {"other_key": GOOD, "switch_ansible_password": "{{other_key}}"}
    assert cs.classify_switch_passwords(secrets) == ([], [])
    secrets["switch_ansible_password"] = "{{   other_key   }}"
    assert cs.classify_switch_passwords(secrets) == ([], [])


def test_switch_user_alias_is_followed():
    secrets = {"admin": "netops", "switch_user": "{{ admin }}",
               "switch_ansible_password": "netops"}  # pragma: allowlist secret
    assert "equals the username 'netops'" in cs.check_switch_passwords(secrets)[0]


def test_placeholder_policy_relaxes_complexity_but_not_placeholders():
    weak = "rackaccess2026"
    assert cs.password_problems(weak) != []
    assert cs.password_problems(weak, policy="placeholder") == []
    assert cs.password_problems("CHANGE_ME", policy="placeholder") == [  # pragma: allowlist secret
        "is a placeholder value (edit secrets.yml)"]
    assert cs.password_problems("cumulus", policy="placeholder") == ["equals the username 'cumulus'"]
    with pytest.raises(ValueError):
        cs.password_problems(weak, policy="lax")


def test_cli_policy_flag_and_env(tmp_path, monkeypatch):
    p = tmp_path / "secrets.yml"
    p.write_text('switch_ansible_password: "rackaccess2026"\n')  # pragma: allowlist secret
    assert _cli("--file", str(p)).returncode == 1
    assert _cli("--file", str(p), "--policy", "placeholder").returncode == 0
    monkeypatch.setenv(cs.POLICY_ENV, "placeholder")
    assert _cli("--file", str(p)).returncode == 0


def test_makefile_passes_policy_variable():
    mk = (NC / "Makefile").read_text()
    assert "SECRETS_PASSWORD_POLICY ?= hardening" in mk
    macro = mk.split("define check_secrets", 1)[1].split("endef", 1)[0]
    assert "--policy $(SECRETS_PASSWORD_POLICY)" in macro


def test_makefile_gates_generate_and_deploy_targets():
    mk = (NC / "Makefile").read_text()
    assert "define check_secrets" in mk
    for target in ("generate:", "push-switch-configs:", "air-deploy:",
                   "air-deploy-retry:", "air-deploy-switches-only:",
                   "switch-ztp-deploy:", "ztp-setup:", "ztp-update:"):
        body = mk.split("\n" + target, 1)[1].split("\n\n", 1)[0]
        assert "check_secrets" in body, target


def test_makefile_gate_honours_both_skip_variables():
    mk = (NC / "Makefile").read_text()
    macro = mk.split("define check_secrets", 1)[1].split("endef", 1)[0]
    assert "$(GENERATE_SKIP_VALIDATE)" in macro and "$(DEPLOY_SKIP_VALIDATE)" in macro
