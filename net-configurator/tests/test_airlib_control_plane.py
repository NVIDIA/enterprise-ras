# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""F14 (review #4): the Air control plane against a scripted API.

`airlib/api.py` drives every simulation create/start/poll/destroy, and was at
19% coverage. These tests run the real functions over an `httpx.MockTransport`
that records each request, so they check what is sent (method, path, bearer,
body) and how each response — paginated, failing, malformed — is handled.
`air-destroy.py` is exercised end to end the same way.
"""
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from airlib import api  # noqa: E402
from airlib.budget import format_budget_row  # noqa: E402
from airlib.errors import EXIT_API, EXIT_CONFIG, AirAPIError  # noqa: E402
from airlib.models import SimState  # noqa: E402

BASE = "https://air.example.test"
TOKEN = "tok-123"
UUID1 = "11111111-2222-3333-4444-555555555555"
UUID2 = "66666666-7777-8888-9999-000000000000"


class FakeAir:
    """Routes (method, path) to canned responses; records every request."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        key = (request.method, request.url.path)
        handler = self.routes.get(key)
        if handler is None:
            return httpx.Response(599, text=f"unrouted {key}")
        if callable(handler):
            return handler(request)
        if isinstance(handler, list):
            return handler.pop(0) if len(handler) > 1 else handler[0]
        return handler

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self))


def _sims(*rows, next_url=None):
    return httpx.Response(200, json={"results": list(rows), "next": next_url})


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(api.time, "sleep", lambda s: None)
    api.set_ngc_org(None)


# --- listing + pagination --------------------------------------------------

def test_list_simulations_follows_relative_next_and_maps_states():
    pages = {
        None: _sims({"id": UUID1, "name": "a", "state": "ACTIVE"},
                    next_url="/api/v3/simulations/?page=2"),
        "2": _sims({"id": UUID2, "name": "b", "state": "INACTIVE"}),
    }
    air = FakeAir({("GET", "/api/v3/simulations/"):
                   lambda r: pages[r.url.params.get("page")]})
    sims = api.list_simulations(air.client(), BASE, TOKEN)
    assert [(s.title, s.state) for s in sims] == [("a", SimState.LOADED), ("b", SimState.STORED)]
    assert len(air.requests) == 2
    assert all(r.headers["Authorization"] == f"Bearer {TOKEN}" for r in air.requests)


@pytest.mark.parametrize("nxt,want", [
    ("/api/v3/simulations/?page=2", "https://air.example.test/api/v3/simulations/?page=2"),
    ("?page=2", "https://air.example.test/api/v3/simulations/?page=2"),
    ("page2/", "https://air.example.test/api/v3/simulations/page2/"),
    (f"{BASE}/api/v3/simulations/?page=2", f"{BASE}/api/v3/simulations/?page=2"),
])
def test_relative_next_resolves_against_the_page_that_returned_it(nxt, want):
    assert api._checked_next(BASE, nxt, f"{BASE}/api/v3/simulations/") == want


def test_list_simulations_follows_query_only_next():
    pages = {
        None: _sims({"id": UUID1, "name": "a", "state": "ACTIVE"}, next_url="?page=2"),
        "2": _sims({"id": UUID2, "name": "b", "state": "INACTIVE"}),
    }
    air = FakeAir({("GET", "/api/v3/simulations/"):
                   lambda r: pages[r.url.params.get("page")]})
    assert [s.title for s in api.list_simulations(air.client(), BASE, TOKEN)] == ["a", "b"]
    assert [r.url.path for r in air.requests] == ["/api/v3/simulations/"] * 2


def test_list_simulations_refuses_off_origin_next():
    air = FakeAir({("GET", "/api/v3/simulations/"):
                   _sims({"id": UUID1, "name": "a", "state": "ACTIVE"},
                         next_url="https://evil.example/steal")})
    with pytest.raises(AirAPIError, match="off-origin"):
        api.list_simulations(air.client(), BASE, TOKEN)
    assert {r.url.host for r in air.requests} == {"air.example.test"}


def test_http_error_names_method_url_and_status():
    air = FakeAir({("GET", "/api/v3/simulations/"):
                   httpx.Response(403, json={"detail": "nope"})})
    with pytest.raises(AirAPIError, match=r"GET .*/api/v3/simulations/ -> 403\n\{'detail': 'nope'\}"):
        api.list_simulations(air.client(), BASE, TOKEN)


def test_non_json_success_is_an_api_error():
    air = FakeAir({("GET", f"/api/v3/simulations/{UUID1}/"):
                   httpx.Response(200, text="<html>gateway</html>")})
    with pytest.raises(AirAPIError, match="Non-JSON response"):
        api.get_simulation_detail(air.client(), BASE, TOKEN, UUID1)


# --- resolving a simulation ------------------------------------------------

def _listing(*rows):
    return FakeAir({("GET", "/api/v3/simulations/"): _sims(*rows)})


def test_resolve_by_uuid_and_by_title():
    rows = ({"id": UUID1, "name": "ERA-default-2-4-3-200", "state": "ACTIVE"},
            {"id": UUID2, "name": "other", "state": "INACTIVE"})
    assert api.resolve_simulation(_listing(*rows).client(), BASE, TOKEN, UUID2).title == "other"
    assert api.resolve_simulation(_listing(*rows).client(), BASE, TOKEN,
                                  "ERA-default-2-4-3-200").id == UUID1


def test_resolve_missing_and_ambiguous_titles_raise():
    with pytest.raises(AirAPIError, match="No simulation found with ID"):
        api.resolve_simulation(_listing().client(), BASE, TOKEN, UUID1)
    with pytest.raises(AirAPIError, match="No simulation found with title"):
        api.resolve_simulation(_listing().client(), BASE, TOKEN, "x")
    dup = ({"id": UUID1, "name": "x", "state": "ACTIVE"},
           {"id": UUID2, "name": "x", "state": "INACTIVE"})
    with pytest.raises(AirAPIError, match="Multiple simulations match") as e:
        api.resolve_simulation(_listing(*dup).client(), BASE, TOKEN, "x")
    assert UUID1 in str(e.value) and UUID2 in str(e.value)


def test_find_loaded_simulation_needs_exactly_one():
    up = {"id": UUID1, "name": "a", "state": "ACTIVE"}
    down = {"id": UUID2, "name": "b", "state": "INACTIVE"}
    assert api.find_loaded_simulation(_listing(up, down).client(), BASE, TOKEN).id == UUID1
    with pytest.raises(AirAPIError, match="No running"):
        api.find_loaded_simulation(_listing(down).client(), BASE, TOKEN)
    with pytest.raises(AirAPIError, match="Multiple running"):
        api.find_loaded_simulation(_listing(up, {**up, "id": UUID2}).client(), BASE, TOKEN)


# --- budget ----------------------------------------------------------------

def test_resource_budget_reads_v3_usage_and_rejects_empty():
    air = FakeAir({("GET", "/api/v3/resource-budgets/"): httpx.Response(200, json={"results": [
        {"id": "b1", "cpu": 100, "memory": 2048, "disk_storage": 500, "simulations": 5,
         "userconfigs": 1000, "image_uploads": 2,
         "usage": {"cpu": 40, "memory": 1024, "disk_storage": 100, "simulations": 1,
                   "userconfigs": 250, "image_uploads": 0}}]})})
    b = api.get_resource_budget(air.client(), BASE, TOKEN)
    assert (b.cpu, b.cpu_used, b.storage, b.storage_used, b.userconfigs_available) == (100, 40, 500, 100, 750)
    empty = FakeAir({("GET", "/api/v3/resource-budgets/"): httpx.Response(200, json={"results": []})})
    with pytest.raises(AirAPIError, match="No resource budget"):
        api.get_resource_budget(empty.client(), BASE, TOKEN)


@pytest.mark.parametrize("used,total,expected", [
    (0, 0, "(no quota)"),
    (3, 0, "3/0 vCPU  (OVER QUOTA)"),
    (40, 100, "40/100 vCPU  (40%)  60 available"),
    (120, 100, "120/100 vCPU  (120%)  0 available"),
])
def test_format_budget_row(used, total, expected):
    assert expected in format_budget_row("CPU", used, total, "vCPU")


# --- lifecycle -------------------------------------------------------------

def test_import_topology_posts_the_document_and_returns_its_id():
    air = FakeAir({("POST", "/api/v3/simulations/import/"):
                   httpx.Response(201, json={"id": UUID1, "name": "t"})})
    body = json.dumps({"title": "t"}).encode()
    assert api.import_topology(air.client(), BASE, TOKEN, body)["id"] == UUID1
    req = air.requests[0]
    assert req.content == body and req.headers["Content-Type"] == "application/json"


@pytest.mark.parametrize("resp,match", [
    (httpx.Response(400, json={"nodes": ["bad"]}), r"Import failed: 400\n\{'nodes': \['bad'\]\}"),
    (httpx.Response(201, json={"name": "t"}), "Import returned no simulation ID"),
])
def test_import_topology_failures(resp, match):
    air = FakeAir({("POST", "/api/v3/simulations/import/"): resp})
    with pytest.raises(AirAPIError, match=match):
        api.import_topology(air.client(), BASE, TOKEN, b"{}")


def test_start_waits_for_inactive_then_patches_start():
    detail = [httpx.Response(200, json={"state": "IMPORTING"}),
              httpx.Response(200, json={"state": "INACTIVE"})]
    air = FakeAir({
        ("GET", f"/api/v3/simulations/{UUID1}/"): detail,
        ("PATCH", f"/api/v3/simulations/{UUID1}/start/"): httpx.Response(200, json={}),
    })
    api.start_simulation(air.client(), BASE, TOKEN, UUID1)
    assert [(r.method, r.url.path) for r in air.requests] == [
        ("GET", f"/api/v3/simulations/{UUID1}/"),
        ("GET", f"/api/v3/simulations/{UUID1}/"),
        ("PATCH", f"/api/v3/simulations/{UUID1}/start/"),
    ]
    assert air.requests[-1].content == b"{}"


def test_wait_for_inactive_gives_up_with_the_last_state():
    air = FakeAir({("GET", f"/api/v3/simulations/{UUID1}/"):
                   httpx.Response(200, json={"state": "importing"})})
    assert api.wait_for_inactive(air.client(), BASE, TOKEN, UUID1, max_wait=9) == "IMPORTING"
    assert len(air.requests) == 3


def test_poll_until_loaded_walks_the_transitional_states():
    states = [httpx.Response(200, json={"state": s})
              for s in ("INACTIVE", "REQUESTING", "BOOTING", "ACTIVE")]
    air = FakeAir({("GET", f"/api/v3/simulations/{UUID1}/"): states})
    seen = []
    final = api.poll_until_loaded(air.client(), BASE, TOKEN, UUID1, interval=0,
                                  status_callback=lambda s, t: seen.append(s))
    assert final == SimState.LOADED
    assert seen == ["STORED (INACTIVE)", "NEW (REQUESTING)", "LOADING (BOOTING)", "LOADED (ACTIVE)"]


def test_poll_until_loaded_stops_on_error_and_reports_the_node():
    air = FakeAir({
        ("GET", f"/api/v3/simulations/{UUID1}/"): httpx.Response(200, json={"state": "ERROR"}),
        ("GET", "/api/v3/simulations/nodes/"): httpx.Response(200, json={"results": [
            {"name": "leaf-01", "state": "RUNNING", "status_from_worker": ""},
            {"name": "gpu-07", "state": "RUNNING", "status_from_worker": "Error: no capacity"}]}),
    })
    errors = []
    assert api.poll_until_loaded(air.client(), BASE, TOKEN, UUID1, interval=0,
                                 error_callback=errors.append) == "ERROR"
    assert errors == ["gpu-07: Error: no capacity"]


def test_check_node_errors_tolerates_api_failure():
    air = FakeAir({("GET", "/api/v3/simulations/nodes/"): httpx.Response(500, text="boom")})
    assert api.check_node_errors(air.client(), BASE, TOKEN, UUID1) is None


def test_delete_simulation_reports_status():
    ok = FakeAir({("DELETE", f"/api/v3/simulations/{UUID1}/"): httpx.Response(204)})
    api.delete_simulation(ok.client(), BASE, TOKEN, UUID1)
    gone = FakeAir({("DELETE", f"/api/v3/simulations/{UUID1}/"): httpx.Response(404)})
    with pytest.raises(AirAPIError, match=f"Failed to delete simulation {UUID1}: 404"):
        api.delete_simulation(gone.client(), BASE, TOKEN, UUID1)


# --- userconfigs -----------------------------------------------------------

def test_create_userconfig_truncates_name_to_air_limit():
    air = FakeAir({("POST", "/api/v3/userconfigs/"):
                   lambda r: httpx.Response(201, json={"id": "uc1", **json.loads(r.content)})})
    uc = api.create_userconfig(air.client(), BASE, TOKEN, "n" * 80, "#cloud-config\n")
    assert uc.id == "uc1" and len(uc.name) == 64
    sent = json.loads(air.requests[0].content)
    assert sent == {"name": "n" * 64, "kind": "cloud-init-user-data", "content": "#cloud-config\n"}


def test_assign_userconfigs_rejects_unknown_slot_before_any_request():
    air = FakeAir({})
    with pytest.raises(ValueError, match="slot"):
        api.assign_node_userconfigs(air.client(), BASE, TOKEN, UUID1, {"n": "uc"}, slot="vendor")
    assert air.requests == []


# --- air-destroy.py end to end ---------------------------------------------

def _load_air_destroy():
    spec = importlib.util.spec_from_file_location("air_destroy_mod", SCRIPTS / "air-destroy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def destroy(monkeypatch):
    mod = _load_air_destroy()
    air = FakeAir({
        ("GET", "/api/v3/simulations/"): _sims(
            {"id": UUID1, "name": "ERA-default-2-4-3-200", "state": "ACTIVE"}),
        ("DELETE", f"/api/v3/simulations/{UUID1}/"): httpx.Response(204),
        ("GET", "/api/v3/userconfigs/"): httpx.Response(200, json={"results": [
            {"id": "u1", "name": "ERA-default-2-4-3-200-gpu-01", "kind": "cloud-init-user-data"},
            {"id": "u2", "name": "someone-else", "kind": "cloud-init-user-data"}]}),
        ("DELETE", "/api/v3/userconfigs/u1/"): httpx.Response(204),
    })
    real_client = httpx.Client
    monkeypatch.setattr(mod.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(air)))
    monkeypatch.setattr(mod, "load_air_config",
                        lambda *a: {"base_url": BASE, "api_key": "k", "username": "u"})
    monkeypatch.setattr(mod, "authenticate", lambda *a: TOKEN)

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["air-destroy.py", "--arch", "2-4-3-200", *argv])
        return mod.main()
    return run, air


def _deletes(air):
    return [r.url.path for r in air.requests if r.method == "DELETE"]


def test_air_destroy_force_deletes_sim_and_only_its_userconfigs(destroy):
    run, air = destroy
    assert run("--force") == 0
    assert _deletes(air) == [f"/api/v3/simulations/{UUID1}/", "/api/v3/userconfigs/u1/"]


def test_air_destroy_without_tty_cancels_and_deletes_nothing(destroy, monkeypatch):
    run, air = destroy

    def _eof(prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", _eof)
    assert run() == 0
    assert _deletes(air) == []


def test_air_destroy_declined_prompt_deletes_nothing(destroy, monkeypatch):
    run, air = destroy
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert run() == 0
    assert _deletes(air) == []


# --- air-destroy.py --cleanup-only: this site's UserConfigs, nobody else's ---

CLEANUP_NAMES = {
    "u-title": "ERA-default-2-4-3-200",
    "u-target": "ERA-default-2-4-3-200-gpu-01",
    "u-lab": "ERA-lab-2-4-3-200-gpu-01",
    "u-other-arch": "ERA-default-2-8-9-800-gpu-01",
    "u-site-ext": "ERA-default-2-4-3-200-x-2-8-9-800-gpu-01",
    "u-legacy": "ERA-2-4-3-200-gpu-01",
    "u-sp": "ERA-lab-2-8-9-400-SP-gpu-01",
    "u-400": "ERA-lab-2-8-9-400-gpu-01",
    "u-other": "someone-else",
    # site `default-2-4-3-200-xxx…`, arch 2-8-9-800, cut to Air's 64 chars
    "u-cut": ("ERA-default-2-4-3-200-" + "x" * 60 + "-2-8-9-800-gpu-01")[:64],
}


@pytest.fixture
def cleanup(monkeypatch):
    mod = _load_air_destroy()
    routes = {
        ("GET", "/api/v3/userconfigs/"): httpx.Response(200, json={"results": [
            {"id": i, "name": n, "kind": "cloud-init-user-data"}
            for i, n in CLEANUP_NAMES.items()]}),
    }
    routes.update({("DELETE", f"/api/v3/userconfigs/{i}/"): httpx.Response(204)
                   for i in CLEANUP_NAMES})
    air = FakeAir(routes)
    real_client = httpx.Client
    monkeypatch.setattr(mod.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(air)))
    monkeypatch.setattr(mod, "load_air_config",
                        lambda *a: {"base_url": BASE, "api_key": "k", "username": "u"})
    monkeypatch.setattr(mod, "authenticate", lambda *a: TOKEN)

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["air-destroy.py", "--cleanup-only", *argv])
        return mod.main()
    return run, air, mod


def _deleted_ids(air):
    return sorted(r.url.path.split("/")[-2] for r in air.requests if r.method == "DELETE")


def _touched_sims(air):
    return [r for r in air.requests if r.url.path.startswith("/api/v3/simulations")]


def test_cleanup_only_deletes_only_the_default_sites_userconfigs(cleanup):
    run, air, _ = cleanup
    assert run("--arch", "2-4-3-200", "--force") == 0
    assert _deleted_ids(air) == ["u-target", "u-title"]
    assert _touched_sims(air) == []


def test_cleanup_only_respects_site(cleanup):
    run, air, _ = cleanup
    assert run("--arch", "2-4-3-200", "--site", "lab", "--force") == 0
    assert _deleted_ids(air) == ["u-lab"]
    assert _touched_sims(air) == []


def test_cleanup_only_arch_is_not_a_prefix_of_a_longer_arch(cleanup):
    run, air, _ = cleanup
    assert run("--arch", "2-8-9-400", "--site", "lab", "--force") == 0
    assert _deleted_ids(air) == ["u-400"]
    assert run("--arch", "2-8-9-400-SP", "--site", "lab", "--force") == 0
    assert _deleted_ids(air) == ["u-400", "u-sp"]


@pytest.mark.parametrize("argv", [
    ("--arch", "2-4-3"),
    ("--arch", "2-4-3-200", "--site", "../x"),
    ("--arch", "2-4-3-200", "--site", "a b"),
    ("--arch", "2-4-3-200", "--site", ""),
])
def test_cleanup_only_refuses_unknown_arch_or_bad_site(cleanup, argv):
    run, air, _ = cleanup
    assert run(*argv) == EXIT_CONFIG
    assert air.requests == []


@pytest.mark.parametrize("answer", ["n", "", "yes please", EOFError])
def test_cleanup_only_without_force_deletes_nothing_unless_confirmed(
        cleanup, monkeypatch, capsys, answer):
    run, air, _ = cleanup

    def reply(prompt=""):
        if answer is EOFError:
            raise EOFError
        return answer
    monkeypatch.setattr("builtins.input", reply)
    assert run("--arch", "2-4-3-200") == 0
    assert _deleted_ids(air) == []
    out = capsys.readouterr().out
    assert "Matched: ERA-default-2-4-3-200-gpu-01" in out
    assert "Matched: ERA-lab" not in out


def test_cleanup_only_confirmed_deletes_only_matched(cleanup, monkeypatch):
    run, air, _ = cleanup
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "y")
    assert run("--arch", "2-4-3-200") == 0
    assert _deleted_ids(air) == ["u-target", "u-title"]
    assert prompts == ["  Delete these 2 UserConfig(s)? [y/N]: "]


def test_cleanup_only_no_match_does_not_prompt(cleanup, monkeypatch):
    run, air, _ = cleanup
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("prompted"))
    assert run("--arch", "2-4-5-800") == 0
    assert _deleted_ids(air) == []


def test_cleanup_only_list_failure_deletes_nothing(cleanup):
    run, air, _ = cleanup
    air.routes[("GET", "/api/v3/userconfigs/")] = httpx.Response(500, text="boom")
    assert run("--arch", "2-4-3-200", "--force") == EXIT_API
    assert _deleted_ids(air) == []


ADVERSARIAL_SITES = [
    "default", "lab", "lab-2", "a.b", "default-2-4-3-200", "default-2-4-3-200-x",
    "x-2-8-9-400", "ci-71915206-2-8-9-400-SP-noztp", "ci-71915206-2-8-9-400-noztp",
]


def test_owned_by_never_claims_another_site_or_arch():
    """Every (site, arch) pair against every other: no cross-ownership."""
    mod = _load_air_destroy()
    pairs = [(s, a) for s in ADVERSARIAL_SITES for a in mod.VALID_ARCHS]
    for site, arch in pairs:
        title = mod.era_title(site, arch)
        assert mod.owned_by(title, site, arch)
        assert mod.owned_by(f"{title}-gpu-01", site, arch)
        for other_site, other_arch in pairs:
            if (other_site, other_arch) == (site, arch):
                continue
            other = mod.era_title(other_site, other_arch)
            for name in (other, f"{other}-gpu-01", f"{other}-leaf-01"):
                assert not mod.owned_by(name, site, arch), (name, site, arch)


def test_owned_by_refuses_every_name_at_the_64_char_cap():
    """Air keeps name[:64]; the cut can hide whose name it was."""
    mod = _load_air_destroy()
    cap = mod.USERCONFIG_NAME_MAX
    # The whole foreign arch is cut off, leaving plain site-name text.
    cut = ("ERA-default-2-4-3-200-" + "x" * 60 + "-2-8-9-800-gpu-01")[:cap]
    assert len(cut) == cap
    assert not mod.owned_by(cut, "default", "2-4-3-200")
    # A longer foreign title cut to exactly the requested 64-char title.
    site = "s" * 50
    title = mod.era_title(site, "2-4-3-200")
    assert len(title) == cap
    foreign = mod.era_title(site + "-2-4-3-200-x", "2-8-9-800")[:cap]
    assert foreign == title
    assert not mod.owned_by(title, site, "2-4-3-200")
    # A cut-off partial arch, for every arch.
    site, arch = "s" * 40, "2-4-3-200"
    for other_arch in mod.VALID_ARCHS:
        name = f"{mod.era_title(f'{site}-{arch}-x', other_arch)}-gpu-01"[:cap]
        assert len(name) == cap
        assert not mod.owned_by(name, site, arch), name
    # One char under the cap is still decided by the ordinary rules.
    short = f"{mod.era_title(site, arch)}-gpu-".ljust(cap - 1, "g")
    assert len(short) == cap - 1 and mod.owned_by(short, site, arch)


def test_cleanup_only_keeps_and_names_a_name_at_the_cap(cleanup, capsys):
    run, air, _ = cleanup
    assert run("--arch", "2-4-3-200", "--force") == 0
    assert "u-cut" not in _deleted_ids(air)
    out = capsys.readouterr().out
    assert "Kept:" in out and CLEANUP_NAMES["u-cut"] in out
