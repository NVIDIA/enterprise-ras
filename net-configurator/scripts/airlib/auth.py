# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Air API authentication — NGC Air 2.0 (v3).

NGC API keys (format: nvapi-...) are used directly as Bearer tokens.
No login endpoint is needed.
"""

import httpx


def authenticate(
    client: httpx.Client,
    base_url: str,
    username: str,
    api_key: str,
) -> str:
    """Return the bearer token for Air API calls.

    NGC Air 2.0: The API key IS the bearer token (no login endpoint).
    The username parameter is accepted for interface compatibility but ignored.
    Validates the token with a lightweight API call and requires a 2xx
    response — anything else is a real problem (wrong URL, missing
    subscription, bad key, etc.) that should fail loudly now rather than
    surface as mysterious 402/403s on every downstream call.
    """
    from airlib.api import _api
    from airlib.errors import AirAPIError

    if not api_key:
        raise AirAPIError(
            "No API key provided.\n"
            "Run `make air-setup` to create the shared Air vault, or export AIR_API_KEY."
        )

    # Use the same URL rewrite the real API calls use so the validation
    # actually exercises the path the rest of the script will take.
    api = _api(base_url).rstrip("/")
    url = f"{api}/api/v3/simulations/?limit=1"
    resp = client.get(url, headers={"Authorization": f"Bearer {api_key}"})

    if 200 <= resp.status_code < 300:
        return api_key

    body = ""
    try:
        body = str(resp.json())
    except ValueError:
        body = resp.text[:400]

    if resp.status_code == 401:
        raise AirAPIError(
            f"401 Unauthorized at {url}\n"
            f"{body}\n"
            f"The API key is invalid or expired.\n"
            f"Re-run `make air-setup` to update the key, or export a fresh AIR_API_KEY."
        )

    if resp.status_code == 402 and (
        "PAYMENT_REQUIRED" in body or "subscription" in body.lower()
    ):
        raise AirAPIError(
            f"402 Payment Required at {url}\n"
            f"{body}\n"
            f"Your NGC org does not have an active NVIDIA Air subscription.\n"
            f"The API key authenticates but deployments will fail until a\n"
            f"subscription is attached to this account.\n"
            f"Action: request Air access for your NGC org, or switch to an\n"
            f"        org that already has it."
        )

    if resp.status_code == 403 and "credentials were not provided" in body.lower():
        raise AirAPIError(
            f"403 Forbidden at {url}\n"
            f"{body}\n"
            f"Air did not recognize the Authorization header. Common causes:\n"
            f"  1. The API key was issued for a different NGC instance\n"
            f"     (e.g., an air-inside key will not authenticate against the\n"
            f"     public Air API and vice versa). Regenerate the key from the\n"
            f"     NGC portal that matches `air_url` and re-run `make air-setup`.\n"
            f"  2. The `air_url` in the Excel Settings tab points at the wrong\n"
            f"     host — the API endpoint may differ from the web UI URL.\n"
            f"  3. A corporate proxy/WAF between you and Air is stripping the\n"
            f"     Authorization header.\n"
            f"Try:  curl -i -H 'Authorization: Bearer <key>' '{url}'"
        )

    raise AirAPIError(
        f"Unexpected HTTP {resp.status_code} during authentication at {url}\n"
        f"{body}"
    )
