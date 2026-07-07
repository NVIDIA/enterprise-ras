# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
#26: when a sim is created but fails to start, air-deploy should attempt a
best-effort delete so orphaned STORED sims don't accumulate. If the delete also
fails (e.g. the same 403 permission issue), it must not raise — just report.
"""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_air_deploy():
    spec = importlib.util.spec_from_file_location("air_deploy", SCRIPTS / "air-deploy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


air_deploy = _load_air_deploy()


def test_cleanup_calls_delete_and_returns_true(monkeypatch):
    calls = {}

    def fake_delete(client, base_url, token, sim_id):
        calls["args"] = (sim_id,)

    monkeypatch.setattr(air_deploy, "delete_simulation", fake_delete)
    ok = air_deploy.cleanup_failed_sim("client", "url", "tok", "sim-123", "2-4-3-200")
    assert ok is True
    assert calls["args"] == ("sim-123",)


def test_cleanup_swallows_delete_error_and_returns_false(monkeypatch):
    def fake_delete(*a, **k):
        raise air_deploy.AirError("403 Forbidden")

    monkeypatch.setattr(air_deploy, "delete_simulation", fake_delete)
    # Must NOT raise even though delete failed (same 403 that blocked start).
    ok = air_deploy.cleanup_failed_sim("client", "url", "tok", "sim-123", "2-4-3-200")
    assert ok is False
