# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
ERA-50 / public issue NVIDIA/enterprise-ras#14 — an OPTIONAL Air field must be
clearable once set.

The old prompts did `if not val and current is not None: return current`, so a
set NGC Org ID was permanently sticky: blank input re-applied the previous
value. The stale org kept riding on every Air API call as the `nv-ngc-org`
header, which the gateway answered with 403.

Blank now means blank, but clearing an existing value asks for confirmation
first, so Enter-ing through the wizard on a re-run cannot silently discard a
working setting. These tests pin both halves — the clear, and the guard against
accidentally clearing.
"""
import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_air_setup():
    spec = importlib.util.spec_from_file_location("air_setup", SCRIPTS / "air-setup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


air_setup = _load_air_setup()

PROMPTS = pytest.mark.parametrize("fn_name", ["prompt_ngc_org", "prompt_username"])


def _feed(monkeypatch, *answers):
    """Feed successive input() responses; record what was asked."""
    asked = []
    it = iter(answers)

    def fake_input(prompt=""):
        asked.append(prompt)
        try:
            return next(it)
        except StopIteration:  # pragma: no cover - a test fed too few answers
            raise AssertionError(f"prompt asked for more input than fed: {prompt!r}")

    monkeypatch.setattr("builtins.input", fake_input)
    return asked


# ------------------------------------------------------- the reported bug ---

@PROMPTS
def test_blank_plus_confirm_clears_a_set_value(monkeypatch, fn_name):
    """The #14 repro: a set value must be clearable. Pre-fix this returned the
    old value, so the stale nv-ngc-org header kept causing 403s."""
    _feed(monkeypatch, "", "y")
    assert getattr(air_setup, fn_name)("myorg") == ""


@PROMPTS
def test_declining_the_confirmation_keeps_the_value(monkeypatch, fn_name):
    """Enter-ing through a re-run must not silently discard a working setting."""
    _feed(monkeypatch, "", "n")
    assert getattr(air_setup, fn_name)("myorg") == "myorg"


@PROMPTS
def test_bare_enter_at_the_confirmation_keeps_the_value(monkeypatch, fn_name):
    """The confirmation defaults to No — anything that isn't 'y' preserves."""
    _feed(monkeypatch, "", "")
    assert getattr(air_setup, fn_name)("myorg") == "myorg"


# ------------------------------------------------------- unchanged paths ----

@PROMPTS
def test_a_new_value_replaces_without_confirmation(monkeypatch, fn_name):
    asked = _feed(monkeypatch, "neworg")
    assert getattr(air_setup, fn_name)("myorg") == "neworg"
    assert len(asked) == 1, "replacing a value must not ask to confirm"


@PROMPTS
@pytest.mark.parametrize("current", [None, ""])
def test_blank_with_nothing_set_is_simply_none(monkeypatch, fn_name, current):
    """No existing value ⇒ blank is 'none', with no confirmation prompt."""
    asked = _feed(monkeypatch, "")
    assert getattr(air_setup, fn_name)(current) == ""
    assert len(asked) == 1, "should not confirm when there is nothing to clear"


@PROMPTS
def test_whitespace_only_is_treated_as_blank(monkeypatch, fn_name):
    _feed(monkeypatch, "   ", "y")
    assert getattr(air_setup, fn_name)("myorg") == ""


# ------------------------------------------------------- robustness ---------

@PROMPTS
def test_eof_at_the_confirmation_preserves_the_value(monkeypatch, fn_name):
    """Piped/non-interactive input must not destroy a setting by accident."""
    it = iter([""])

    def fake_input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)
    assert getattr(air_setup, fn_name)("myorg") == "myorg"


# ------------------------------------------- selective-update menu (ERA-50) --

# No `air_api_key` key on purpose. These tests assert only on the returned field
# list, never on the masked banner, and choose_fields_to_update() already handles
# a missing key (`existing.get('air_api_key','')` -> mask() -> "(empty)").
# Including a realistic-looking value trips the CI `security:secrets` scan's
# Secret-Keyword plugin — a false positive, but one better avoided than
# baselined, since every baseline entry weakens the guard a little.
EXISTING = {
    "air_url": "https://x", "air_username": "",
    "air_ssh_key_path": "~/.ssh/id_ed25519", "air_org": "myorg",
}


def _choose(monkeypatch, choice, _tries=3):
    """Answer the menu with `choice`, but fail fast instead of hanging.

    choose_fields_to_update() re-prompts on an unrecognised choice, so a build
    where the entry is missing would loop forever on a constant answer. Cap the
    attempts and raise, so a missing menu entry surfaces as a test failure
    rather than a wedged run."""
    calls = {"n": 0}

    def fake_input(prompt=""):
        calls["n"] += 1
        if calls["n"] > _tries:
            raise AssertionError(
                f"menu rejected choice {choice!r} {_tries}x — entry missing?")
        return choice

    monkeypatch.setattr("builtins.input", fake_input)
    return air_setup.choose_fields_to_update(dict(EXISTING))


def test_ngc_org_is_selectable_on_its_own(monkeypatch):
    """`air_org` was shown under 'Current values' but had no menu entry, so the
    only route to it was [1] All — which re-prompts for the API key."""
    assert _choose(monkeypatch, "6") == ["ngc_org"]


def test_all_includes_ngc_org(monkeypatch):
    assert "ngc_org" in _choose(monkeypatch, "1")


def test_exit_moved_to_seven_and_selects_nothing(monkeypatch):
    assert _choose(monkeypatch, "7") == []


def test_partial_update_does_not_select_ngc_org(monkeypatch):
    for choice in ("2", "3", "4", "5"):
        assert "ngc_org" not in _choose(monkeypatch, choice), f"choice {choice}"


def test_org_prompt_is_gated_on_the_selection():
    """Regression guard for the real defect.

    The org prompt used to run *unconditionally*, relying on 'blank preserves'
    to be a no-op on partial updates. Now that blank offers to clear, an ungated
    prompt asks 'Clear the existing NGC org?' during an unrelated ssh_key-only
    update. The mapping alone doesn't express this — the call site must be
    guarded, so assert on the call site."""
    src = (SCRIPTS / "air-setup.py").read_text()
    call = src.index("prompt_ngc_org(existing_data")
    preceding = src[:call]
    guard = preceding.rindex('if "ngc_org" in fields_to_update:')
    banner = preceding.rindex("banner(")
    assert guard < banner < call, (
        "prompt_ngc_org must sit inside `if \"ngc_org\" in fields_to_update:` — "
        "an ungated prompt fires the clear-confirmation on unrelated updates"
    )


def test_first_run_default_collects_ngc_org():
    """A fresh setup (no existing vault) must still ask for the org — gating it
    on the menu must not drop it from the no-vault path.

    The default lives in a local inside run_interactive(), so read it from the
    source. Matched by shape rather than an exact line so reformatting the
    literal doesn't fail the test; only dropping ngc_org does."""
    src = (SCRIPTS / "air-setup.py").read_text()
    m = re.search(r"fields_to_update\s*:\s*list\[str\]\s*=\s*\[(.*?)\]", src, re.S)
    assert m, "could not locate the first-run fields_to_update default"
    assert "ngc_org" in m.group(1), f"first-run default omits ngc_org: {m.group(1)!r}"


@PROMPTS
def test_prompt_advertises_clear_only_when_something_is_set(monkeypatch, fn_name):
    """The prompt must not promise 'blank = clear' when there is nothing to clear."""
    asked = _feed(monkeypatch, "", "y")
    getattr(air_setup, fn_name)("myorg")
    assert "blank = clear" in asked[0], asked[0]

    asked = _feed(monkeypatch, "")
    getattr(air_setup, fn_name)(None)
    assert "blank = clear" not in asked[0], asked[0]
