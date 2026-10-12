# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""air-deploy checks every topology image exists before it imports anything.

Air accepts a topology that names an unknown image with HTTP 200, then moves
the simulation to INVALID with no nodes and no reason, and air-deploy blamed
`minimum_resources`. These tests drive `check_topology_images()` and
`air-deploy.py main()` against a scripted Air API.
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

from airlib.api import check_topology_images, topology_images  # noqa: E402
from airlib.errors import (  # noqa: E402
    EXIT_API, EXIT_CONFIG, AirAPIError, AirAuthError, AirConfigError,
)

BASE = "https://api.dsx-air.nvidia.com"
TOKEN = "tok"
IMAGES = "/api/v3/images/"
IMPORT = "/api/v3/simulations/import/"

CUMULUS = "cumulus-vx-5.18.3"
UBUNTU = "generic/ubuntu2204"
INTERNAL_5183 = "cumulus-linux-vx-amd64-5.18.3.0001.qcow2"


def _node(image):
    return {"cpu": 2, "memory": 4096, "storage": 20, "os": image,
            "features": {"uefi": False, "tpm": False}}


def _topology(**nodes):
    return {"format": "JSON", "title": "ERA-default-2-4-3-200",
            "content": {"nodes": {n: _node(i) for n, i in nodes.items()}, "links": []}}


MIXED = _topology(**{"leaf-01": CUMULUS, "leaf-02": CUMULUS, "spine-01": CUMULUS,
                     "gpu-01": UBUNTU, "gpu-02": UBUNTU})


class FakeAir:
    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        key = (request.method, request.url.path, request.url.params.get("page"))
        handler = self.routes.get(key) or self.routes.get(key[:2])
        if handler is None:
            return httpx.Response(599, text=f"unrouted {key}")
        if isinstance(handler, Exception):
            raise handler
        return handler


def _catalog(*names, next_url=None):
    return httpx.Response(200, json={
        "next": next_url,
        "results": [{"id": f"id-{i}", "name": n, "version": "x"} for i, n in enumerate(names)]})


def _check(routes, topology=MIXED):
    air = FakeAir(routes)
    with httpx.Client(transport=httpx.MockTransport(air)) as client:
        return check_topology_images(client, BASE, TOKEN, topology), air


def test_all_images_present_mixed_cumulus_and_generic():
    images, air = _check({("GET", IMAGES): _catalog(UBUNTU, CUMULUS, "cumulus-vx-5.18.0")})
    assert images == [CUMULUS, UBUNTU]
    assert [r.url.path for r in air.requests] == [IMAGES]


def test_duplicate_references_are_looked_up_and_reported_once():
    assert topology_images(MIXED) == {
        CUMULUS: ["leaf-01", "leaf-02", "spine-01"], UBUNTU: ["gpu-01", "gpu-02"]}
    with pytest.raises(AirConfigError) as exc:
        _check({("GET", IMAGES): _catalog(UBUNTU)})
    msg = str(exc.value)
    assert msg.count(repr(CUMULUS)) == 1
    assert "3 node(s): leaf-01, leaf-02, spine-01" in msg


def test_missing_cumulus_image_is_named_with_same_version_hint():
    with pytest.raises(AirConfigError) as exc:
        _check({("GET", IMAGES): _catalog(UBUNTU, INTERNAL_5183, "cumulus-vx-5.18.1")})
    msg = str(exc.value)
    assert msg.startswith(f"1 image(s) in the topology do not exist on {BASE}")
    assert repr(CUMULUS) in msg
    assert f"same version on this instance: {INTERNAL_5183}" in msg
    assert "cumulus-vx-5.18.1" not in msg
    assert repr(UBUNTU) not in msg
    assert exc.value.exit_code == EXIT_CONFIG


def test_same_version_hint_is_digit_bounded_and_names_only():
    catalog = httpx.Response(200, json={"next": None, "results": [
        {"id": "5.18.3", "name": "uuid-like-id-is-not-a-hint"},
        {"id": "a", "name": "cumulus-vx-5.18.30"},
        {"id": "b", "name": "vendor-15.18.3"},
        {"id": "c", "name": "cumulus-vx-5.18.3x"},
        {"id": "d", "name": INTERNAL_5183},
        {"id": "e", "name": UBUNTU},
    ]})
    with pytest.raises(AirConfigError) as exc:
        _check({("GET", IMAGES): catalog})
    hint = [ln for ln in str(exc.value).splitlines() if "same version" in ln]
    assert hint == [f"      same version on this instance: {INTERNAL_5183}"]


def test_missing_generic_and_cumulus_both_reported():
    with pytest.raises(AirConfigError) as exc:
        _check({("GET", IMAGES): _catalog("cumulus-vx-5.18.0")})
    msg = str(exc.value)
    assert msg.startswith("2 image(s)")
    assert repr(CUMULUS) in msg and repr(UBUNTU) in msg


def test_catalog_is_read_across_pages():
    images, air = _check({
        ("GET", IMAGES, None): _catalog(UBUNTU, next_url=f"{BASE}{IMAGES}?page=2"),
        ("GET", IMAGES, "2"): _catalog(CUMULUS),
    })
    assert images == [CUMULUS, UBUNTU]
    assert len(air.requests) == 2


def test_image_may_be_referenced_by_id():
    topo = _topology(**{"leaf-01": "id-1", "gpu-01": UBUNTU})
    images, _ = _check({("GET", IMAGES): _catalog(UBUNTU, CUMULUS)}, topo)
    assert images == [UBUNTU, "id-1"]


@pytest.mark.parametrize("status", [401, 403])
def test_unauthorized_is_an_auth_error_not_a_missing_image(status):
    with pytest.raises(AirAuthError) as exc:
        _check({("GET", IMAGES): httpx.Response(status, json={"detail": "nope"})})
    assert f"HTTP {status}" in str(exc.value)
    assert "refused the API key" in str(exc.value)
    assert "do not exist" not in str(exc.value)
    assert exc.value.exit_code == EXIT_API


@pytest.mark.parametrize("response", [
    httpx.Response(500, text="boom"),
    httpx.Response(200, text="<html>not json</html>"),
    httpx.Response(200, json={"detail": "no results key"}),
    httpx.Response(200, json={"next": None, "results": [None]}),
    httpx.Response(200, json={"next": None, "results": ["cumulus-vx-5.18.3"]}),
    httpx.Response(200, json={"next": None, "results": [{"id": "x"}]}),
])
def test_catalog_failure_is_an_api_error(response):
    with pytest.raises(AirAPIError) as exc:
        _check({("GET", IMAGES): response})
    assert not isinstance(exc.value, AirAuthError)
    assert "do not exist" not in str(exc.value)
    assert exc.value.exit_code == EXIT_API


@pytest.mark.parametrize("exc", [
    httpx.ConnectTimeout("timed out"),
    httpx.ReadTimeout("timed out"),
    httpx.ConnectError("connection refused"),
    httpx.RemoteProtocolError("server disconnected"),
])
def test_transport_failure_is_an_api_error(exc):
    def handler(request):
        raise exc
    with pytest.raises(AirAPIError) as err:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            check_topology_images(client, BASE, TOKEN, MIXED)
    assert not isinstance(err.value, AirAuthError)
    assert type(exc).__name__ in str(err.value)
    assert err.value.exit_code == EXIT_API


def test_topology_without_images_skips_the_catalog():
    images, air = _check({}, {"content": {"nodes": {}}})
    assert images == [] and air.requests == []


# --- air-deploy.py main(): the check runs before the first import ----------

def _load_air_deploy():
    spec = importlib.util.spec_from_file_location("air_deploy_preflight", SCRIPTS / "air-deploy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def deploy(monkeypatch, tmp_path):
    mod = _load_air_deploy()
    arch, site = "2-4-3-200", "default"
    topo = tmp_path / "output" / arch / site / "topology" / f"{arch}-topology.json"
    topo.parent.mkdir(parents=True)
    topo.write_text(json.dumps(MIXED))
    (tmp_path / "output" / arch / site / "inventory").mkdir(parents=True)
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "scripts" / "air-deploy.py"))
    monkeypatch.setattr(mod, "load_air_config",
                        lambda *a: {"base_url": BASE, "api_key": "k", "username": "u"})
    monkeypatch.setattr(mod, "get_key_fingerprint", lambda p: "SHA256:test")
    monkeypatch.setattr(mod, "authenticate", lambda *a: TOKEN)

    def run(routes):
        air = FakeAir(routes)
        real_client = httpx.Client
        monkeypatch.setattr(mod.httpx, "Client",
                            lambda **kw: real_client(transport=httpx.MockTransport(air)))
        monkeypatch.setattr(sys, "argv", ["air-deploy.py", "--arch", arch, "--site", site,
                                          "--skip-budget-check"])
        return mod.main(), air
    return run


def _imports(air):
    return [r for r in air.requests if r.method == "POST" and r.url.path == IMPORT]


def test_main_missing_image_stops_before_import(deploy):
    rc, air = deploy({("GET", IMAGES): _catalog(UBUNTU, INTERNAL_5183),
                      ("POST", IMPORT): httpx.Response(200, json={"id": "sim"})})
    assert rc == EXIT_CONFIG
    assert _imports(air) == []


def test_main_unauthorized_catalog_stops_before_import(deploy):
    rc, air = deploy({("GET", IMAGES): httpx.Response(401, text="bad key"),
                      ("POST", IMPORT): httpx.Response(200, json={"id": "sim"})})
    assert rc == EXIT_API
    assert _imports(air) == []


def test_main_catalog_timeout_exits_api_without_import(deploy):
    rc, air = deploy({("GET", IMAGES): httpx.ReadTimeout("timed out"),
                      ("POST", IMPORT): httpx.Response(200, json={"id": "sim"})})
    assert rc == EXIT_API
    assert _imports(air) == []


def test_main_present_images_proceed_to_import(deploy):
    rc, air = deploy({("GET", IMAGES): _catalog(UBUNTU, CUMULUS),
                      ("POST", IMPORT): httpx.Response(500, text="stop here")})
    assert rc == EXIT_API
    assert len(_imports(air)) == 1
    paths = [r.url.path for r in air.requests]
    assert paths.index(IMAGES) < paths.index(IMPORT)
