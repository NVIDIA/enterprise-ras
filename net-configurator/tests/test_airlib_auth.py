# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Tests for scripts/airlib/auth.py::authenticate().

authenticate() used to silently accept any non-401 response as success
(it only raised on 401). That let 402 "PAYMENT_REQUIRED" and 403
"Authentication credentials were not provided" sail through as if the
key were valid, and every downstream API call then failed with the
same underlying error — far from where it originated.

Commit d277792 hardened the function to require a 2xx response and
raise distinct, actionable errors for each of the common failure
modes. These tests pin that behaviour and each error-message branch.
"""
import json
import sys
from pathlib import Path

import httpx
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from airlib.auth import authenticate  # noqa: E402
from airlib.errors import AirAPIError  # noqa: E402


def _make_client(status_code: int, body: dict | str = "") -> httpx.Client:
    """Build an httpx.Client whose validation GET returns the given response."""
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(body, dict):
            return httpx.Response(status_code, json=body)
        return httpx.Response(status_code, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


BASE_URL = "https://air-ngc.nvidia.com"
API_KEY = "nvapi-test-key-longer-than-20-chars"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_2xx_response_returns_api_key_unchanged():
    with _make_client(200, {"count": 0, "results": []}) as client:
        token = authenticate(client, BASE_URL, username="", api_key=API_KEY)
    assert token == API_KEY


def test_204_no_content_also_counts_as_success():
    """Any 2xx is accepted — belt-and-braces for future API changes."""
    with _make_client(204) as client:
        token = authenticate(client, BASE_URL, username="", api_key=API_KEY)
    assert token == API_KEY


# ---------------------------------------------------------------------------
# Missing key
# ---------------------------------------------------------------------------

def test_empty_api_key_raises_with_setup_hint():
    # No HTTP call should even be attempted.
    def handler(request):
        pytest.fail("authenticate() should not send any request when api_key is empty")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AirAPIError) as exc:
            authenticate(client, BASE_URL, username="", api_key="")
    msg = str(exc.value)
    assert "No API key" in msg
    assert "make air-setup" in msg


# ---------------------------------------------------------------------------
# Error branches — each status code gets a distinct, actionable message
# ---------------------------------------------------------------------------

def test_401_raises_invalid_key_with_rotation_hint():
    with _make_client(401, {"detail": "Invalid token"}) as client:
        with pytest.raises(AirAPIError) as exc:
            authenticate(client, BASE_URL, username="", api_key=API_KEY)
    msg = str(exc.value)
    assert "401" in msg
    # User-actionable guidance.
    assert "invalid or expired" in msg.lower()
    assert "make air-setup" in msg


def test_402_payment_required_mentions_subscription():
    body = {
        "requestStatus": {
            "statusCode": "PAYMENT_REQUIRED",
            "statusDescription": "No active subscription for the product found.",
        }
    }
    with _make_client(402, body) as client:
        with pytest.raises(AirAPIError) as exc:
            authenticate(client, BASE_URL, username="", api_key=API_KEY)
    msg = str(exc.value)
    assert "402" in msg
    # The message should steer the user toward the real problem (no
    # Air subscription on this NGC org), not a generic HTTP error.
    assert "subscription" in msg.lower()


def test_403_credentials_not_provided_lists_common_causes():
    """Air's DRF-style 403 with "Authentication credentials were not
    provided" is its confusing shape for "we don't recognise this
    token" — the error message must name the three typical causes
    so the user can self-diagnose."""
    body = {"detail": "Authentication credentials were not provided."}
    with _make_client(403, body) as client:
        with pytest.raises(AirAPIError) as exc:
            authenticate(client, BASE_URL, username="", api_key=API_KEY)
    msg = str(exc.value)
    assert "403" in msg
    # Mentions each of the three common causes from the hint block.
    assert "NGC instance" in msg            # wrong-portal key
    assert "air_url" in msg                 # wrong host
    assert "proxy" in msg.lower() or "WAF" in msg  # stripped header


def test_403_without_credentials_message_falls_to_generic_branch():
    """A 403 that is NOT the DRF-style "credentials were not provided"
    shape should land on the generic HTTP-error branch, not the
    three-causes-hint block — otherwise we'd mis-lead users."""
    body = {"detail": "You do not have permission to perform this action."}
    with _make_client(403, body) as client:
        with pytest.raises(AirAPIError) as exc:
            authenticate(client, BASE_URL, username="", api_key=API_KEY)
    msg = str(exc.value)
    assert "403" in msg
    # Generic branch does NOT mention the three-causes hint keywords.
    assert "NGC instance" not in msg
    assert "air_url" not in msg


def test_500_raises_with_generic_message():
    with _make_client(500, {"detail": "internal server error"}) as client:
        with pytest.raises(AirAPIError) as exc:
            authenticate(client, BASE_URL, username="", api_key=API_KEY)
    msg = str(exc.value)
    assert "500" in msg
    assert "Unexpected" in msg


# ---------------------------------------------------------------------------
# Validation endpoint routing
# ---------------------------------------------------------------------------

def test_validation_uses_the_mapped_api_host_not_the_ui_host():
    """The GET issued by authenticate() must go to the API host (the
    result of ``_api(base_url)``), not the raw UI host. This is the
    exact bug the 2xx-validation fix was built to catch — if the
    rewrite were accidentally removed, auth would happily succeed
    against the UI host while real API calls 403'd."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["host"] = request.url.host
        captured["path"] = request.url.path
        return httpx.Response(200, json={"count": 0, "results": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        authenticate(client, "https://air-ngc.nvidia.com", "", API_KEY)

    assert captured["host"] == "api.dsx-air.nvidia.com"
    assert captured["path"].startswith("/api/v3/simulations/")


def test_authorization_header_is_sent_as_bearer():
    captured_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        authenticate(client, BASE_URL, "", API_KEY)

    assert captured_headers.get("authorization") == f"Bearer {API_KEY}"
