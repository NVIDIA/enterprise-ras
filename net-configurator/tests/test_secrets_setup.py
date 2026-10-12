# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Tests for scripts/secrets-setup.py (``make secrets``, ERA-131).

The wizard is driven in-process with scripted answers (``ask`` / ``ask_secret``
callables) against a throw-away project tree, so both modes, the existing
plaintext / vault-encrypted detection, prompt-time rejection + re-prompt, and
the real ``ansible-vault`` encrypt/decrypt round-trip are exercised without a
TTY. Vault tests are skipped when ``ansible-vault`` is not on PATH.

Every password literal below is a synthetic test fixture.
"""
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_secrets as cs  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("secrets_setup", SCRIPTS / "secrets-setup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ss = _load()

HAVE_VAULT = shutil.which("ansible-vault") is not None
needs_vault = pytest.mark.skipif(not HAVE_VAULT, reason="ansible-vault not installed")

GOOD = "Sw1tchPa$$word"          # pragma: allowlist secret
GOOD2 = "An0therG00d!pw"         # pragma: allowlist secret
WEAK = "rackaccess2026"          # pragma: allowlist secret  (no upper/special)
VAULT_PW = "unit-test-vault-pw"  # pragma: allowlist secret

EXAMPLE = """---
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
# Template — copy to secrets.yml
switch_ansible_password: "CHANGE_ME"  # pragma: allowlist secret
server_ansible_password: "CHANGE_ME"  # pragma: allowlist secret
ansible_become_password: "CHANGE_ME"  # pragma: allowlist secret
switch_password: "CHANGE_ME"  # pragma: allowlist secret
ldap_admin_password: "CHANGE_ME"  # pragma: allowlist secret
ldap_user_default_password: "CHANGE_ME"  # pragma: allowlist secret
status_page_username: "era"
status_page_password: "CHANGE_ME"  # pragma: allowlist secret
"""


class Script:
    """Scripted answers: a list of (prompt-substring, answer) consumed in order."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.log = []

    def __call__(self, prompt):
        self.log.append(prompt)
        if not self.answers:
            raise AssertionError(f"unexpected extra prompt: {prompt!r}\n" + "\n".join(self.log))
        expect, answer = self.answers.pop(0)
        assert expect in prompt, f"prompt {prompt!r} did not contain {expect!r}"
        return answer

    def done(self):
        assert not self.answers, f"unconsumed answers: {self.answers}"


USE_SAVED = ("Use the vault password from", "y")
SAME_PW = ("same vault password", "y")
ENC_SAVED = [("Encrypt", "y"), USE_SAVED]


def _field_answers(values, keep=()):
    """Answers for the nine field prompts: enter+confirm each, or Enter to keep."""
    out = []
    for key, _label, _gate, hidden in ss.FIELDS:
        if key in keep:
            out.append(("new value", ""))
            continue
        out.append(("new value", values[key]))
        if hidden:
            out.append(("confirm", values[key]))
    return out


ALL_NEW = {
    "switch_ansible_password": GOOD,
    "switch_bootstrap_password": "cumulus",  # pragma: allowlist secret
    "server_ansible_password": "nvidia",  # pragma: allowlist secret
    "ansible_become_password": "nvidia",  # pragma: allowlist secret
    "switch_password": GOOD2,
    "ldap_admin_password": "Ldap@123",  # pragma: allowlist secret
    "ldap_user_default_password": GOOD,
    "status_page_username": "era",
    "status_page_password": "St@tus123",  # pragma: allowlist secret
}


@pytest.fixture
def project(tmp_path):
    (tmp_path / "inventories").mkdir()
    (tmp_path / "inventories" / "secrets.yml.example").write_text(EXAMPLE)
    (tmp_path / "input" / "2-8-5-200" / "default").mkdir(parents=True)
    return tmp_path


def run(project, answers, arch=None, site="default", policy="hardening", environ=None):
    script = Script(answers)

    def ask(prompt):
        # Existing tests exercise the LDAP-enabled path when inventory is unknown.
        if arch is None and "Configure LDAP passwords now?" in prompt:
            return "y"
        return script(prompt)

    rc = ss.run_wizard(project, arch, site, policy, ask=ask, ask_secret=script,
                       environ={} if environ is None else environ)
    return rc, script


def plain(path):
    return yaml.load(path.read_text(), Loader=cs._SecretsLoader)


# ---------------------------------------------------------------- targets

def test_global_mode_targets_shared_template_and_creates_it_from_example(project):
    target = project / "inventories" / "secrets.yml"
    assert not target.exists()
    rc, script = run(project, _field_answers(ALL_NEW) + [("Encrypt", "n")])
    assert rc == 0
    script.done()
    data = plain(target)
    assert data["switch_ansible_password"] == GOOD
    assert data["switch_password"] == GOOD2
    assert data["status_page_username"] == "era"
    assert set(ss.FIELD_KEYS) <= set(data), "every field-table key is written"
    assert "SPDX-License-Identifier" in target.read_text(), "template comments preserved"
    assert (target.stat().st_mode & 0o777) == 0o600


def test_deployment_mode_targets_output_tree_and_creates_dirs(project):
    target = project / "output" / "2-8-5-200" / "cust-a" / "inventory" / "group_vars" / "all" / "secrets.yml"
    assert not target.parent.exists()
    rc, _ = run(project, _field_answers(ALL_NEW) + [("Encrypt", "n")], arch="2-8-5-200", site="cust-a")
    assert rc == 0
    assert target.exists()
    assert not (project / "inventories" / "secrets.yml").exists(), "global template untouched"


def test_deployment_mode_seeds_from_shared_template_when_present(project):
    shared = project / "inventories" / "secrets.yml"
    shared.write_text(EXAMPLE + "switch_user: \"admin\"\n# org-specific note\n")
    rc, _ = run(project, _field_answers(ALL_NEW) + [("Encrypt", "n")], arch="2-8-5-200")
    target = ss.target_path(project, "2-8-5-200", "default")[0]
    assert rc == 0
    assert "org-specific note" in target.read_text()
    assert plain(target)["switch_user"] == "admin"


def test_target_path_helper():
    root = Path("/r")
    assert ss.target_path(root, None, "default") == (root / "inventories" / "secrets.yml", "global")
    assert ss.target_path(root, "2-8-9-800", "s1") == (
        root / "output" / "2-8-9-800" / "s1" / "inventory" / "group_vars" / "all" / "secrets.yml",
        "deployment")


# ---------------------------------------------------------------- existing plaintext

def test_existing_plaintext_is_detected_and_unchanged_fields_kept(project, capsys):
    target = project / "inventories" / "secrets.yml"
    target.write_text(EXAMPLE.replace('switch_ansible_password: "CHANGE_ME"',  # pragma: allowlist secret
                                      f'switch_ansible_password: "{GOOD}"')
                      .replace('switch_password: "CHANGE_ME"', f'switch_password: "{GOOD2}"')  # pragma: allowlist secret
                      .replace('ldap_user_default_password: "CHANGE_ME"',  # pragma: allowlist secret
                               f'ldap_user_default_password: "{GOOD}"')
                      .replace('server_ansible_password: "CHANGE_ME"',  # pragma: allowlist secret
                               'server_ansible_password: "keep-me"'))  # pragma: allowlist secret
    # Keep everything except status_page_password.
    keep = set(ss.FIELD_KEYS) - {"status_page_password"}
    answers = _field_answers({"status_page_password": "N3w$tatus"}, keep=keep) + [("Encrypt", "n")]
    rc, script = run(project, answers)
    out = capsys.readouterr().out
    assert rc == 0
    script.done()
    assert "file is plaintext" in out
    data = plain(target)
    assert data["server_ansible_password"] == "keep-me"  # pragma: allowlist secret
    assert data["switch_ansible_password"] == GOOD
    assert data["status_page_password"] == "N3w$tatus"  # pragma: allowlist secret
    assert "keep-me" not in out and GOOD not in out, "secret values are never echoed"


def test_unset_ungated_key_may_stay_unset_but_unset_switch_key_may_not(project, capsys):
    """.example has no switch_bootstrap_password: Enter leaves it out (inventory default
    'cumulus' applies); Enter on an unset switch key is refused."""
    target = project / "inventories" / "secrets.yml"
    target.write_text("---\nstatus_page_username: \"era\"\n")   # nothing else set
    answers = [("new value", ""), ("new value", GOOD), ("confirm", GOOD)]  # switch_ansible: refused, then set
    for key, _l, gate, hidden in ss.FIELDS[1:]:
        if key in ("switch_bootstrap_password", "ldap_admin_password"):
            answers.append(("new value", ""))                    # stays unset
            continue
        answers.append(("new value", ALL_NEW[key]))
        if hidden:
            answers.append(("confirm", ALL_NEW[key]))
    rc, script = run(project, answers + [("Encrypt", "n")])
    assert rc == 0
    script.done()
    data = plain(target)
    assert "switch_bootstrap_password" not in data and "ldap_admin_password" not in data
    assert data["switch_ansible_password"] == GOOD
    assert capsys.readouterr().out.count("A value is required") == 1


def test_existing_placeholder_switch_password_cannot_be_kept(project):
    """Enter on an untouched CHANGE_ME switch password is refused, then a good value is taken."""
    target = project / "inventories" / "secrets.yml"
    target.write_text(EXAMPLE)
    answers = [("new value", ""),            # try to keep CHANGE_ME -> required
               ("new value", GOOD), ("confirm", GOOD)]
    rest = {k: v for k, v in ALL_NEW.items() if k != "switch_ansible_password"}
    for key, _l, _g, hidden in ss.FIELDS[1:]:
        answers.append(("new value", rest[key]))
        if hidden:
            answers.append(("confirm", rest[key]))
    answers.append(("Encrypt", "n"))
    rc, script = run(project, answers)
    assert rc == 0
    script.done()
    assert plain(target)["switch_ansible_password"] == GOOD


# ---------------------------------------------------------------- prompt-time policy

def test_weak_switch_password_is_rejected_and_reprompted(project, capsys):
    answers = [("new value", WEAK), ("confirm", WEAK),      # rejected: no upper / special
               ("new value", "CHANGE_ME"), ("confirm", "CHANGE_ME"),  # rejected: placeholder
               ("new value", GOOD), ("confirm", GOOD)]
    rest = {k: v for k, v in ALL_NEW.items() if k != "switch_ansible_password"}
    for key, _l, _g, hidden in ss.FIELDS[1:]:
        answers.append(("new value", rest[key]))
        if hidden:
            answers.append(("confirm", rest[key]))
    answers.append(("Encrypt", "n"))
    rc, script = run(project, answers)
    out = capsys.readouterr().out
    assert rc == 0
    script.done()
    assert out.count("rejected (ERA switch-password policy") == 2
    assert "has no uppercase letter" in out
    assert "is a known placeholder" in out or "placeholder" in out
    assert plain(project / "inventories" / "secrets.yml")["switch_ansible_password"] == GOOD


def test_rejection_uses_check_secrets_rules_not_a_local_copy(project, monkeypatch):
    """If check_secrets.password_problems accepts a value, the wizard must too."""
    monkeypatch.setattr(cs, "password_problems", lambda value, username=None, policy=None: [])
    values = dict(ALL_NEW, switch_ansible_password=WEAK, switch_password=WEAK,
                  ldap_user_default_password=WEAK)
    rc, script = run(project, _field_answers(values) + [("Encrypt", "n")])
    assert rc == 0
    script.done()


def test_server_side_password_is_not_gated(project):
    """server/sudo/bootstrap/admin/status passwords may be simple (documented default is fine)."""
    values = dict(ALL_NEW, server_ansible_password="nvidia", ansible_become_password="nvidia",  # pragma: allowlist secret
                  switch_bootstrap_password="cumulus", ldap_admin_password="weak",  # pragma: allowlist secret
                  status_page_password="weak")  # pragma: allowlist secret
    rc, script = run(project, _field_answers(values) + [("Encrypt", "n")])
    assert rc == 0
    script.done()


def test_placeholder_policy_relaxes_complexity_but_not_change_me(project, capsys):
    answers = [("new value", "CHANGE_ME"), ("confirm", "CHANGE_ME"),  # still rejected
               ("new value", WEAK), ("confirm", WEAK)]                  # accepted under placeholder
    rest = {k: v for k, v in ALL_NEW.items() if k != "switch_ansible_password"}
    for key, _l, _g, hidden in ss.FIELDS[1:]:
        answers.append(("new value", rest[key]))
        if hidden:
            answers.append(("confirm", rest[key]))
    answers.append(("Encrypt", "n"))
    rc, script = run(project, answers, policy="placeholder")
    assert rc == 0
    script.done()
    assert capsys.readouterr().out.count("rejected") == 1


def test_mismatched_confirmation_reprompts(project, capsys):
    answers = [("new value", GOOD), ("confirm", "typo")]
    answers += _field_answers(ALL_NEW) + [("Encrypt", "n")]
    rc, script = run(project, answers)
    assert rc == 0
    script.done()
    assert "do not match" in capsys.readouterr().out


# ---------------------------------------------------------------- LDAP gating

def _write_main_yml(project, arch, site, enabled):
    all_dir = project / "output" / arch / site / "inventory" / "group_vars" / "all"
    all_dir.mkdir(parents=True, exist_ok=True)
    (all_dir / "main.yml").write_text(f"---\nldap:\n  enabled: {str(enabled).lower()}\n")


def test_ldap_disabled_in_generated_inventory_skips_ldap_user_gate(project):
    _write_main_yml(project, "2-8-5-200", "default", False)
    assert ss.ldap_enabled(project, "2-8-5-200", "default") is False
    assert "ldap_user_default_password" not in ss.gated_keys(False)
    values = {k: v for k, v in ALL_NEW.items() if not k.startswith("ldap_")}
    answers = []
    for key, _, _, hidden in ss.FIELDS:
        if key.startswith("ldap_"):
            continue
        answers.append(("new value", values[key]))
        if hidden:
            answers.append(("confirm", values[key]))
    rc, script = run(project, answers + [("Encrypt", "n")], arch="2-8-5-200")
    assert rc == 0
    script.done()


def test_ldap_enabled_gates_ldap_user_password(project, capsys):
    _write_main_yml(project, "2-8-5-200", "default", True)
    assert ss.ldap_enabled(project, "2-8-5-200", "default") is True
    values = dict(ALL_NEW)
    answers = []
    for key, _l, _g, hidden in ss.FIELDS:
        if key == "ldap_user_default_password":
            answers += [("new value", WEAK), ("confirm", WEAK)]  # rejected
        answers.append(("new value", values[key]))
        if hidden:
            answers.append(("confirm", values[key]))
    rc, script = run(project, answers + [("Encrypt", "n")], arch="2-8-5-200")
    assert rc == 0
    script.done()
    assert "ldap_user_default_password" in capsys.readouterr().out.split("rejected")[0].split("\n")[-1]


def test_ldap_unknown_is_conservative(project):
    """Global mode / no main.yml: LDAP state unknown -> the LDAP user password is checked."""
    assert ss.ldap_enabled(project, None, "default") is None
    assert ss.ldap_enabled(project, "2-8-5-200", "default") is None
    assert "ldap_user_default_password" in ss.gated_keys(None)


# ---------------------------------------------------------------- rendering

def test_render_preserves_comments_appends_missing_and_quotes_specials():
    text = "---\n# keep me\nswitch_password: \"old\"\nother: 1\n"
    out = ss.render_secrets(text, {"switch_password": "a{{b}}#c: d", "new_key": "v"})
    assert "# keep me" in out and "other: 1" in out
    data = yaml.safe_load(out)
    assert data["switch_password"] == "a{{b}}#c: d"  # pragma: allowlist secret
    assert data["new_key"] == "v"
    assert "old" not in out


def test_render_leaves_kept_vault_scalar_untouched():
    text = ("switch_password: !vault |\n"
            "          $ANSIBLE_VAULT;1.1;AES256\n"
            "          6162\n"
            "server_ansible_password: \"x\"\n")
    out = ss.render_secrets(text, {"switch_password": cs.VaultedValue(),
                                   "server_ansible_password": "y"})
    assert "!vault |" in out and "6162" in out
    assert 'server_ansible_password: "y"' in out


def test_render_replacing_vault_scalar_drops_ciphertext_block_and_stays_valid_yaml():
    """Overwriting a `!vault |` value must remove its indented ciphertext lines, or the
    result is not YAML (review finding on !297)."""
    text = ("---\n"
            "switch_password: !vault |\n"
            "          $ANSIBLE_VAULT;1.1;AES256\n"
            "          6162\n"
            "\n"
            "          6364\n"
            "# trailing comment\n"
            "server_ansible_password: \"x\"\n")
    out = ss.render_secrets(text, {"switch_password": GOOD2})
    data = yaml.load(out, Loader=cs._SecretsLoader)
    assert data["switch_password"] == GOOD2
    assert data["server_ansible_password"] == "x"
    assert "6162" not in out and "6364" not in out and "ANSIBLE_VAULT" not in out
    assert "# trailing comment" in out


def test_render_replacing_last_vault_scalar_in_file():
    text = ("a: 1\n"
            "switch_password: !vault |\n"
            "          $ANSIBLE_VAULT;1.1;AES256\n"
            "          6162\n")
    out = ss.render_secrets(text, {"switch_password": GOOD2, "status_page_username": "u"})
    data = yaml.safe_load(out)
    assert data == {"a": 1, "switch_password": GOOD2, "status_page_username": "u"}


def test_wizard_replaces_vault_scalar_end_to_end(project):
    target = project / "inventories" / "secrets.yml"
    target.write_text(EXAMPLE
                      .replace('switch_password: "CHANGE_ME"',  # pragma: allowlist secret
                               "switch_password: !vault |\n"
                               "          $ANSIBLE_VAULT;1.1;AES256\n"
                               "          6162636465\n")
                      .replace('switch_ansible_password: "CHANGE_ME"',  # pragma: allowlist secret
                               f'switch_ansible_password: "{GOOD}"')
                      .replace('ldap_user_default_password: "CHANGE_ME"',  # pragma: allowlist secret
                               f'ldap_user_default_password: "{GOOD}"'))
    keep = [k for k, *_ in ss.FIELDS if k != "switch_password"]
    answers = _field_answers({"switch_password": GOOD2}, keep=keep) + [("Encrypt", "n")]
    rc, script = run(project, answers)
    assert rc == 0
    data = yaml.safe_load(target.read_text())
    assert data["switch_password"] == GOOD2
    assert "ANSIBLE_VAULT" not in target.read_text()


def test_describe_never_reveals_value():
    assert GOOD not in ss.describe(GOOD)
    assert ss.describe("CHANGE_ME").startswith("(PLACEHOLDER")
    assert ss.describe(cs.VaultedValue()) == "(set, !vault)"
    assert ss.describe("{{ x }}") == "(set, Jinja template)"
    assert ss.describe(GOOD) == "(set)"


# ---------------------------------------------------------------- vault precedence

def test_vault_password_file_precedence(tmp_path):
    env_file = tmp_path / "envpass"
    env_file.write_text("a\n")
    saved_dir = tmp_path / ".era-secrets"
    saved_dir.mkdir()
    saved = saved_dir / "vault-pass"
    saved.write_text("b\n")
    assert ss.vault_password_file(tmp_path, {"ANSIBLE_VAULT_PASSWORD_FILE": str(env_file)}) == env_file
    assert ss.vault_password_file(tmp_path, {}) == saved
    assert ss.vault_password_file(tmp_path, {"ANSIBLE_VAULT_PASSWORD_FILE": "/nonexistent"}) == saved
    saved.unlink()
    assert ss.vault_password_file(tmp_path, {}) is None


# ---------------------------------------------------------------- ansible-vault round trip

@needs_vault
def test_encrypt_with_saved_vault_pass_produces_vault_file(project):
    (project / ".era-secrets").mkdir()
    (project / ".era-secrets" / "vault-pass").write_text(VAULT_PW + "\n")
    rc, script = run(project, _field_answers(ALL_NEW) + ENC_SAVED)
    assert rc == 0
    script.done()
    target = project / "inventories" / "secrets.yml"
    assert cs.is_vault_encrypted(target)
    assert GOOD not in target.read_text()
    assert (target.stat().st_mode & 0o777) == 0o600
    decrypted = ss.decrypt_text(target, VAULT_PW)
    assert yaml.safe_load(decrypted)["switch_password"] == GOOD2
    assert [p for p in target.parent.iterdir() if p.name != "secrets.yml"] == \
        [project / "inventories" / "secrets.yml.example"], "no temp files left"


@needs_vault
def test_encrypt_prompts_and_saves_vault_pass_when_no_file(project):
    answers = _field_answers(ALL_NEW) + [("Encrypt", "y"),
                                         ("Vault password", VAULT_PW), ("Confirm", VAULT_PW),
                                         ("Save it", "y")]
    rc, script = run(project, answers)
    assert rc == 0
    script.done()
    saved = project / ".era-secrets" / "vault-pass"
    assert saved.read_text().strip() == VAULT_PW
    assert (saved.stat().st_mode & 0o777) == 0o600
    assert cs.is_vault_encrypted(project / "inventories" / "secrets.yml")


@needs_vault
def test_rerun_on_encrypted_file_decrypts_edits_and_reencrypts(project, capsys):
    (project / ".era-secrets").mkdir()
    (project / ".era-secrets" / "vault-pass").write_text(VAULT_PW + "\n")
    rc, _ = run(project, _field_answers(ALL_NEW) + ENC_SAVED)
    assert rc == 0
    target = project / "inventories" / "secrets.yml"
    first = target.read_text()

    keep = set(ss.FIELD_KEYS) - {"switch_password"}
    rc, script = run(project, [USE_SAVED] + _field_answers({"switch_password": "Rot@ted9pw"}, keep=keep)
                     + [SAME_PW])
    out = capsys.readouterr().out
    assert rc == 0
    script.done()  # no "Encrypt?" question: re-encrypt is automatic (only "same password?")
    assert "vault-encrypted ($ANSIBLE_VAULT header)" in out
    assert cs.is_vault_encrypted(target)
    assert target.read_text() != first
    data = yaml.safe_load(ss.decrypt_text(target, VAULT_PW))
    assert data["switch_password"] == "Rot@ted9pw"  # pragma: allowlist secret
    assert data["switch_ansible_password"] == GOOD, "untouched field survived the round trip"


@needs_vault
def test_wrong_vault_password_fails_closed_without_touching_file(project, capsys):
    (project / ".era-secrets").mkdir()
    (project / ".era-secrets" / "vault-pass").write_text(VAULT_PW + "\n")
    rc, _ = run(project, _field_answers(ALL_NEW) + ENC_SAVED)
    assert rc == 0
    target = project / "inventories" / "secrets.yml"
    before = target.read_text()
    (project / ".era-secrets" / "vault-pass").write_text("wrong\n")
    rc, script = run(project, [USE_SAVED])
    assert rc == 1
    script.done()
    assert target.read_text() == before
    assert "ansible-vault edit" in capsys.readouterr().out


def test_failed_encrypt_leaves_existing_file_and_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / "secrets.yml"
    target.write_text("$ANSIBLE_VAULT;1.1;AES256\nabc\n")

    def boom(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "simulated failure")

    monkeypatch.setattr(ss.subprocess, "run", boom)
    with pytest.raises(ss.VaultError):
        ss.write_encrypted(target, "switch_password: \"new\"\n", "pw")
    assert target.read_text() == "$ANSIBLE_VAULT;1.1;AES256\nabc\n", "ciphertext never downgraded to plaintext"
    assert [p.name for p in tmp_path.iterdir()] == ["secrets.yml"], "no plaintext temp file left behind"


@needs_vault
def test_encrypt_works_with_ansible_vault_password_file_env_set(project, monkeypatch):
    """ANSIBLE_VAULT_PASSWORD_FILE + --vault-password-file = two 'default' vault-ids -> encrypt refuses."""
    pw_file = project / "vault-pass"
    pw_file.write_text(VAULT_PW + "\n")
    monkeypatch.setenv("ANSIBLE_VAULT_PASSWORD_FILE", str(pw_file))
    rc, script = run(project, _field_answers(ALL_NEW) + ENC_SAVED,
                     environ={"ANSIBLE_VAULT_PASSWORD_FILE": str(pw_file)})
    assert rc == 0
    script.done()
    target = project / "inventories" / "secrets.yml"
    assert cs.is_vault_encrypted(target)
    assert yaml.safe_load(ss.decrypt_text(target, VAULT_PW))["switch_password"] == GOOD2


@needs_vault
def test_rerun_on_encrypted_file_never_writes_plaintext_to_destination(project, monkeypatch):
    (project / ".era-secrets").mkdir()
    (project / ".era-secrets" / "vault-pass").write_text(VAULT_PW + "\n")
    rc, _ = run(project, _field_answers(ALL_NEW) + ENC_SAVED)
    assert rc == 0
    target = project / "inventories" / "secrets.yml"
    seen = []
    real_replace = ss.os.replace

    def spy(src, dst):
        if Path(dst) == target:
            seen.append(Path(src).read_text()[:15])
        return real_replace(src, dst)

    monkeypatch.setattr(ss.os, "replace", spy)
    keep = set(ss.FIELD_KEYS) - {"switch_password"}
    rc, _ = run(project, [USE_SAVED] + _field_answers({"switch_password": "Rot@ted9pw"}, keep=keep)
                + [SAME_PW])
    assert rc == 0
    assert seen and all(s.startswith("$ANSIBLE_VAULT") for s in seen), seen


def test_declined_encrypt_leaves_plaintext_with_reminder(project, capsys):
    rc, _ = run(project, _field_answers(ALL_NEW) + [("Encrypt", "n")])
    assert rc == 0
    assert "ansible-vault encrypt inventories/secrets.yml" in capsys.readouterr().out
    assert not cs.is_vault_encrypted(project / "inventories" / "secrets.yml")


# ---------------------------------------------------------------- CLI / Makefile

def test_cli_site_without_arch_is_an_error():
    with pytest.raises(SystemExit) as exc:
        ss.main(["--site", "x"])
    assert exc.value.code == 2


def test_makefile_has_secrets_targets_and_optional_arch():
    mk = (SCRIPTS.parent / "Makefile").read_text()
    assert "\nsecrets:  ## " in mk
    assert "\nhelp-secrets:  ## " in mk
    # Command-line ARCH is detected via _ARCH_ON_CLI (captured before the
    # case-normalising `override ARCH :=`, which would change $(origin ARCH)).
    assert "_ARCH_ON_CLI := $(filter command line,$(origin ARCH))" in mk
    assert "ifneq ($(_ARCH_ON_CLI),)" in mk
    assert "$(origin arch)" in mk  # lowercase arch= is rejected, not silently ignored
    assert "scripts/secrets-setup.py --arch $(ARCH) --site $(_SECRETS_SITE)" in mk
    assert "ifneq ($(_SITE_ON_CLI),)\n_SECRETS_SITE := $(SITE)" in mk


@pytest.mark.parametrize("site", ["cust-b", None])
def test_explicit_arch_does_not_inherit_context_site(tmp_path, site):
    """`make secrets ARCH=x` targets x/default even with a saved .era-context site (review)."""
    work = tmp_path / "nc"
    shutil.copytree(SCRIPTS.parent, work, ignore=shutil.ignore_patterns(
        "output", "tests", "__pycache__", ".venv", "archive", ".era-context"))
    (work / ".era-context").write_text("_ARCH=2-8-9-800\n_SITE=customer-b\n")  # pragma: allowlist secret
    cmd = ["make", "-n", "secrets", "ARCH=2-8-5-200"] + ([f"SITE={site}"] if site else [])
    res = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    want = f"--arch 2-8-5-200 --site {site or 'default'}"
    assert want in res.stdout
    assert "customer-b" not in res.stdout


# ---------------------------------------------------------------- review round 3

@pytest.mark.parametrize("arch,site", [
    ("..", "default"), (".", "default"), ("2-8-5-200", ".."), ("2-8-5-200", "../x"),
    ("2-8-5-200", "a/b"), ("2-8-5-200", ".hidden"), ("input/..", "default"), ("2-8-5-200", ""),
])
def test_traversal_components_are_rejected(project, arch, site):
    with pytest.raises(ValueError):
        ss.target_path(project, arch, site)
    rc, script = run(project, [], arch=arch, site=site)
    assert rc == 2
    script.done()
    assert not (project / "output").exists()
    assert not (project / "inventories" / "secrets.yml").exists()
    assert not (project / "inventory").exists()


def test_ordinary_components_are_accepted():
    ss.target_path(Path("/r"), "2-8-9-400-SP", "cust_1.east")


def test_requested_encryption_never_falls_back_to_plaintext(project, monkeypatch, capsys):
    """Yes to 'Encrypt?' with no ansible-vault must abort, not silently write plaintext (review)."""
    monkeypatch.setattr(ss.shutil, "which", lambda name: None)
    target = project / "inventories" / "secrets.yml"
    rc, script = run(project, _field_answers(ALL_NEW) + [("Encrypt", "y")])
    assert rc == 2
    script.done()
    assert not target.exists()
    assert "nothing written" in capsys.readouterr().err
    # an explicit 'n' still writes plaintext
    rc, _ = run(project, _field_answers(ALL_NEW) + [("Encrypt", "n")])
    assert rc == 0 and target.exists()


@needs_vault
def test_new_deployment_can_seed_from_encrypted_template(project, capsys):
    """Global `make secrets` + encrypt, then `make secrets ARCH=…` before generate (review)."""
    (project / ".era-secrets").mkdir()
    (project / ".era-secrets" / "vault-pass").write_text(VAULT_PW + "\n")
    shared = project / "inventories" / "secrets.yml"
    shared.write_text(EXAMPLE + "# org-specific note\n")
    rc, _ = run(project, _field_answers(ALL_NEW) + ENC_SAVED)
    assert rc == 0 and cs.is_vault_encrypted(shared)
    before = shared.read_text()

    keep = set(ss.FIELD_KEYS) - {"switch_password"}
    rc, script = run(project, [USE_SAVED] + _field_answers({"switch_password": "Rot@ted9pw"}, keep=keep)
                     + [("Encrypt", "y"), SAME_PW], arch="2-8-5-200")
    out = capsys.readouterr().out
    assert rc == 0, out
    script.done()
    assert "inventories/secrets.yml is vault-encrypted" in out
    assert "not valid YAML" not in out
    target = ss.target_path(project, "2-8-5-200", "default")[0]
    assert cs.is_vault_encrypted(target)
    data = yaml.safe_load(ss.decrypt_text(target, VAULT_PW))
    assert data["switch_password"] == "Rot@ted9pw"  # pragma: allowlist secret
    assert data["switch_ansible_password"] == GOOD, "seeded from the decrypted template"
    assert "# org-specific note" in ss.decrypt_text(target, VAULT_PW)
    assert shared.read_text() == before, "template itself untouched"


@needs_vault
def test_encrypted_seed_still_lets_operator_decline_encryption(project):
    (project / ".era-secrets").mkdir()
    (project / ".era-secrets" / "vault-pass").write_text(VAULT_PW + "\n")
    rc, _ = run(project, _field_answers(ALL_NEW) + ENC_SAVED)
    assert rc == 0
    keep = set(ss.FIELD_KEYS)
    rc, script = run(project, [USE_SAVED] + _field_answers({}, keep=keep) + [("Encrypt", "n")],
                     arch="2-8-5-200")
    assert rc == 0
    script.done()
    target = ss.target_path(project, "2-8-5-200", "default")[0]
    assert not cs.is_vault_encrypted(target)
    assert plain(target)["switch_password"] == GOOD2


# ---------------------------------------------------------------- vault password choice / rekey

NEW_VAULT_PW = "a-second-vault-pw"  # pragma: allowlist secret


def _saved(project, pw=VAULT_PW):
    (project / ".era-secrets").mkdir(exist_ok=True)
    (project / ".era-secrets" / "vault-pass").write_text(pw + "\n")
    return project / ".era-secrets" / "vault-pass"


@needs_vault
def test_saved_air_vault_password_is_offered_not_assumed(project, capsys):
    """The saved password is the Air one — the wizard says so and asks before using it."""
    _saved(project)
    rc, script = run(project, _field_answers(ALL_NEW) + ENC_SAVED)
    out = capsys.readouterr().out
    assert rc == 0
    script.done()
    assert "make air-setup" in out and "air-secrets.yml" in out
    assert "Use the vault password from vault-pass?" in "".join(script.log)


@needs_vault
def test_declining_saved_password_uses_a_typed_one_and_keeps_air_file_unless_replaced(project, capsys):
    saved = _saved(project)
    answers = _field_answers(ALL_NEW) + [("Encrypt", "y"), ("Use the vault password from", "n"),
                                         ("Vault password", NEW_VAULT_PW), ("Confirm", NEW_VAULT_PW),
                                         ("Replace the saved password", "n")]
    rc, script = run(project, answers)
    out = capsys.readouterr().out
    assert rc == 0
    script.done()
    assert "ansible-vault rekey" in out, "warned that replacing would break the Air vault"
    assert saved.read_text().strip() == VAULT_PW, "Air password file untouched"
    target = project / "inventories" / "secrets.yml"
    assert yaml.safe_load(ss.decrypt_text(target, NEW_VAULT_PW))["switch_password"] == GOOD2
    with pytest.raises(ss.VaultError):
        ss.decrypt_text(target, VAULT_PW)


@needs_vault
def test_typed_password_can_replace_saved_file_on_explicit_consent(project):
    saved = _saved(project)
    answers = _field_answers(ALL_NEW) + [("Encrypt", "y"), ("Use the vault password from", "n"),
                                         ("Vault password", NEW_VAULT_PW), ("Confirm", NEW_VAULT_PW),
                                         ("Replace the saved password", "y")]
    rc, script = run(project, answers)
    assert rc == 0
    script.done()
    assert saved.read_text().strip() == NEW_VAULT_PW
    assert (saved.stat().st_mode & 0o777) == 0o600


@needs_vault
def test_rerun_can_change_the_vault_password(project, capsys):
    """Re-running on an encrypted file offers a new vault password (rekey)."""
    saved = _saved(project)
    rc, _ = run(project, _field_answers(ALL_NEW) + ENC_SAVED)
    assert rc == 0
    target = project / "inventories" / "secrets.yml"
    keep = set(ss.FIELD_KEYS)
    answers = [USE_SAVED] + _field_answers({}, keep=keep) + [
        ("same vault password", "n"), ("Vault password", NEW_VAULT_PW), ("Confirm", NEW_VAULT_PW),
        ("Replace the saved password", "y")]
    rc, script = run(project, answers)
    out = capsys.readouterr().out
    assert rc == 0, out
    script.done()
    assert "rekeying" in out
    assert cs.is_vault_encrypted(target)
    assert yaml.safe_load(ss.decrypt_text(target, NEW_VAULT_PW))["switch_password"] == GOOD2
    with pytest.raises(ss.VaultError):
        ss.decrypt_text(target, VAULT_PW)
    assert saved.read_text().strip() == NEW_VAULT_PW

    # third run: the replaced file now opens it again without typing anything
    rc, script = run(project, [USE_SAVED] + _field_answers({}, keep=keep) + [SAME_PW])
    assert rc == 0
    script.done()


@needs_vault
def test_declined_saved_password_that_is_wrong_for_decrypt_fails_closed(project):
    _saved(project)
    rc, _ = run(project, _field_answers(ALL_NEW) + ENC_SAVED)
    assert rc == 0
    target = project / "inventories" / "secrets.yml"
    before = target.read_text()
    rc, script = run(project, [("Use the vault password from", "n"), ("Vault password", "nope")])
    assert rc == 1
    script.done()  # no "Replace the saved password?" — an unproven password is never offered for saving
    assert target.read_text() == before


def test_offer_save_skips_prompt_when_saved_password_is_identical(project):
    _saved(project)
    script = Script([])
    assert ss.offer_save_vault_password(project, VAULT_PW, ask=script) is False
    script.done()


def test_env_password_file_is_labelled_not_called_air(project, capsys):
    pw_file = project / "my-pass"
    pw_file.write_text(VAULT_PW + "\n")
    script = Script([("Use the vault password from", "y")])
    pw, typed = ss.choose_vault_password(project, {"ANSIBLE_VAULT_PASSWORD_FILE": str(pw_file)},
                                         ask=script, ask_secret=script)
    assert (pw, typed) == (VAULT_PW, False)
    out = capsys.readouterr().out
    assert "ANSIBLE_VAULT_PASSWORD_FILE" in out and "make air-setup" not in out


# REUSE-IgnoreStart
INDENTED = ("---\n"
            "  # SPDX-License-Identifier: MIT\n"
            "  switch_user: netops\n"
            f'  switch_ansible_password: "{GOOD}"\n'
            "  switch_password: !vault |\n"
            "          $ANSIBLE_VAULT;1.1;AES256\n"
            "          6162\n"
            "  custom_var: keep-me\n"
            f'  ldap_user_default_password: "{GOOD}"\n')
# REUSE-IgnoreEnd


def test_render_indented_root_mapping_preserves_siblings_and_indent():
    out = ss.render_secrets(INDENTED, {"switch_password": GOOD2, "status_page_username": "u"})
    data = yaml.safe_load(out)
    assert data["switch_user"] == "netops"
    assert data["custom_var"] == "keep-me"
    assert data["switch_password"] == GOOD2
    assert data["status_page_username"] == "u"
    assert "6162" not in out
    assert "\n  switch_password: " in out and "\n  status_page_username: " in out


def test_indented_top_level_mapping_preserves_switch_user(project, capsys):
    target = project / "inventories" / "secrets.yml"
    target.write_text(INDENTED)
    keep = set(ss.FIELD_KEYS) - {"switch_password"}
    rc, _ = run(project, _field_answers({"switch_password": GOOD2}, keep=keep) + [("Encrypt", "n")])
    assert rc == 0, capsys.readouterr().out
    data = plain(target)
    assert data["switch_user"] == "netops"
    assert data["custom_var"] == "keep-me"
    assert data["switch_password"] == GOOD2
    assert list(data).count("switch_ansible_password") == 1


@pytest.mark.parametrize("key", ["switch_ansible_password", "switch_password", "ldap_user_default_password"])
@pytest.mark.parametrize("keep", [False, True])
def test_shipped_default_can_be_entered_or_kept(key, keep, capsys):
    value = "Cumu1usLinux!"  # pragma: allowlist secret
    answers = Script([("new value", "")] if keep else
                     [("new value", value), ("confirm", value)])
    result = ss.prompt_field(key, "test field", value if keep else "CHANGE_ME",
                             True, "hardening", "cumulus", True,
                             ask_secret=answers)
    answers.done()
    assert result == value
    output = capsys.readouterr().out
    assert "rejected" not in output and value not in output


@pytest.mark.parametrize("answer", ["", "n"])
def test_shared_template_ldap_can_be_skipped_without_changing_existing_values(project, answer):
    arch = None
    answers = [("Configure LDAP passwords now?", answer)]
    for key, _, _, hidden in ss.FIELDS:
        if key.startswith("ldap_"):
            continue
        answers.append(("new value", ALL_NEW[key]))
        if hidden:
            answers.append(("confirm", ALL_NEW[key]))
    answers.append(("Encrypt", "n"))
    script = Script(answers)
    assert ss.run_wizard(project, arch, "default", "hardening",
                         ask=script, ask_secret=script, environ={}) == 0
    script.done()
    path, _ = ss.target_path(project, arch, "default")
    data = plain(path)
    assert data["ldap_admin_password"] == "CHANGE_ME"  # pragma: allowlist secret
    assert data["ldap_user_default_password"] == "CHANGE_ME"  # pragma: allowlist secret


@pytest.mark.parametrize("value, expected", [(True, True), (False, False), ("Yes", True),
                                             ("No", False), ("false", False), ("invalid", None)])
def test_inventory_ldap_boolean_values(project, value, expected):
    path = project / "output/2-8-5-200/default/inventory/group_vars/all/main.yml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump({"ldap": {"enabled": value}, "unrelated": "test"}))
    assert ss.ldap_enabled(project, "2-8-5-200", "default") is expected


def _write_ldap_workbook(project, value, site="default"):
    path = project / "input" / "2-8-5-200" / site / "2-8-5-200.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = cs.openpyxl.Workbook()
    wb.active.title = "Deployment"
    wb.active.append(["ldap_enabled", value])
    wb.save(path)
    wb.close()


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("source", ["workbook", "inventory"])
def test_known_ldap_never_asks_permission_to_skip(project, enabled, source):
    if source == "workbook":
        _write_ldap_workbook(project, "Yes" if enabled else "No")
    else:
        _write_main_yml(project, "2-8-5-200", "default", enabled)
    answers = []
    for key, _, _, hidden in ss.FIELDS:
        if key.startswith("ldap_") and not enabled:
            continue
        answers.append(("new value", ALL_NEW[key]))
        if hidden:
            answers.append(("confirm", ALL_NEW[key]))
    answers.append(("Encrypt", "n"))
    script = Script(answers)
    assert ss.run_wizard(project, "2-8-5-200", "default", "hardening",
                         ask=script, ask_secret=script, environ={}) == 0
    script.done()
    assert not any("Configure LDAP" in p for p in script.log)


@pytest.mark.parametrize("workbook, inventory", [("Yes", False), ("No", True)])
def test_ldap_enabled_in_either_source_wins(project, workbook, inventory):
    _write_ldap_workbook(project, workbook)
    _write_main_yml(project, "2-8-5-200", "default", inventory)
    assert ss.ldap_enabled(project, "2-8-5-200", "default") is True


@pytest.mark.parametrize("source", ["workbook", "missing", "corrupt", "missing-setting"])
def test_pre_generate_ldap_cannot_keep_weak_password(project, source, capsys):
    if source == "workbook":
        _write_ldap_workbook(project, "Yes")
    elif source == "corrupt":
        (project / "input/2-8-5-200/default/2-8-5-200.xlsx").write_bytes(b"not a workbook")
    elif source == "missing-setting":
        _write_ldap_workbook(project, None)
    answers = []
    for key, _, _, hidden in ss.FIELDS:
        if key == "ldap_user_default_password":
            answers += [("new value", ""), ("new value", WEAK), ("confirm", WEAK)]
        answers.append(("new value", ALL_NEW[key]))
        if hidden:
            answers.append(("confirm", ALL_NEW[key]))
    answers.append(("Encrypt", "n"))
    script = Script(answers)
    assert ss.run_wizard(project, "2-8-5-200", "default", "hardening",
                         ask=script, ask_secret=script, environ={}) == 0
    script.done()
    out = capsys.readouterr().out
    assert "required" in out and "rejected" in out
    assert plain(ss.target_path(project, "2-8-5-200", "default")[0])["ldap_user_default_password"] == GOOD


def test_workbook_ldap_uses_requested_site(project):
    _write_ldap_workbook(project, "No")
    _write_ldap_workbook(project, "Yes", site="ldap-site")
    assert ss.ldap_enabled(project, "2-8-5-200", "ldap-site") is True
    assert ss.ldap_enabled(project, "2-8-5-200", "default") is False


@pytest.mark.parametrize("keep", [False, True])
def test_status_page_published_default_is_described_as_placeholder(keep, capsys):
    value = "Cumu1usLinux!"  # pragma: allowlist secret
    assert ss.describe(value, key="status_page_password").startswith("(PLACEHOLDER")
    assert ss.describe(value, key="switch_password") == "(set)"
    script = Script([("new value", "")] if keep else
                    [("new value", value), ("confirm", value)])
    assert ss.prompt_field("status_page_password", "page", value, None, "hardening", "era", True,
                           ask_secret=script) == value
    script.done()
    out = capsys.readouterr().out
    assert "PLACEHOLDER" in out and value not in out
    if not keep:
        assert "looks like a placeholder" in out
