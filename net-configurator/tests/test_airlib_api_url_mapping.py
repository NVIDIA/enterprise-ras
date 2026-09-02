# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Tests for scripts/airlib/api.py::_api() URL rewriting.

NVIDIA Air splits its web UI and API across different hostnames, and the
pattern isn't identical across environments:

- Air-Inside (internal): ``ngc.<env>.nvidia.com`` → ``api.<env>.nvidia.com``
  (mechanical prefix swap).
- Public NGC Air: ``air-ngc.nvidia.com`` and ``dsx-air.nvidia.com`` both
  resolve to the same API host ``api.dsx-air.nvidia.com`` (explicit
  hostname table, not a mechanical rewrite — the web UI domain "air-ngc"
  does NOT reshape to "api-ngc").

This module was originally broken for public Air (users hit 403
"Authentication credentials were not provided" on every call because
requests landed on the UI host, not the API). The fix in commit
1921e54 added explicit hostname mapping for the public case. These
tests pin that behaviour so a future regex tweak can't silently
reintroduce the bug.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from airlib.api import _api, _headers  # noqa: E402


class TestHeadersZstdWorkaround:
    """Regression: every request must pin a non-zstd Accept-Encoding.

    httpx + zstandard has a 'cannot use a decompressobj multiple times' bug
    that corrupts the 2nd+ response on a reused client. It silently broke
    paginated node lookups (page 2 raised DecodingError), so nodes past the
    first page were reported 'not found' and never received their Node
    Instructions — they booted unconfigured and unreachable. Pinning
    Accept-Encoding on every request avoids the zstd code path entirely.
    """

    def test_headers_pin_non_zstd_encoding(self):
        h = _headers("tok")
        assert "Accept-Encoding" in h
        assert "zstd" not in h["Accept-Encoding"].lower()

    def test_headers_still_carry_bearer_token(self):
        assert _headers("tok")["Authorization"] == "Bearer tok"


class TestPublicAirRewrite:
    """Public NGC Air uses an explicit hostname table."""

    def test_air_ngc_maps_to_api_dsx_air(self):
        assert _api("https://air-ngc.nvidia.com") == "https://api.dsx-air.nvidia.com"

    def test_air_ngc_with_trailing_slash_maps(self):
        assert _api("https://air-ngc.nvidia.com/") == "https://api.dsx-air.nvidia.com"

    def test_dsx_air_also_maps_to_api_dsx_air(self):
        """Both public UI hostnames funnel into the same API host."""
        assert _api("https://dsx-air.nvidia.com") == "https://api.dsx-air.nvidia.com"

    def test_public_rewrite_is_case_sensitive_by_design(self):
        # We don't want to match uppercase variants — typos in the Excel
        # deserve a clean "config error" rather than a surprise mapping.
        assert _api("https://AIR-NGC.NVIDIA.COM") == "https://AIR-NGC.NVIDIA.COM"

    def test_http_scheme_also_recognised(self):
        assert _api("http://air-ngc.nvidia.com") == "https://api.dsx-air.nvidia.com"


class TestAirInsideRewrite:
    """Internal Air-Inside: ngc.<env> → api.<env>."""

    def test_ngc_prefix_swaps_to_api(self):
        assert _api("https://ngc.air-inside.nvidia.com") == \
            "https://api.air-inside.nvidia.com"

    def test_ngc_prefix_swap_preserves_trailing_slash(self):
        assert _api("https://ngc.air-inside.nvidia.com/") == \
            "https://api.air-inside.nvidia.com/"

    def test_ngc_prefix_swap_works_for_other_environments(self):
        # The ngc.X.Y pattern is generic — not hardcoded to air-inside.
        assert _api("https://ngc.staging.example.com") == \
            "https://api.staging.example.com"


class TestAlreadyApiPassthrough:
    """If the URL is already an api.* host, don't rewrite."""

    def test_api_dsx_air_unchanged(self):
        assert _api("https://api.dsx-air.nvidia.com") == "https://api.dsx-air.nvidia.com"

    def test_api_air_inside_unchanged(self):
        assert _api("https://api.air-inside.nvidia.com") == \
            "https://api.air-inside.nvidia.com"

    def test_arbitrary_non_matching_host_unchanged(self):
        # Anything not matching either pattern falls through untouched —
        # we don't want to silently rewrite user-typed custom hosts.
        assert _api("https://custom-air.example.com") == "https://custom-air.example.com"


class TestRegressionPinned:
    """Direct regression guards for the bug this rewrite was added to
    fix (1921e54). Each asserts a concrete before/after the fix would
    have been wrong."""

    def test_public_ui_is_NOT_reshaped_as_ngc_prefix_rewrite(self):
        """Pre-fix bug: the old regex ``^(https?://)ngc\\.`` didn't match
        ``air-ngc.nvidia.com`` (the `ngc.` isn't at the start), so the
        URL flowed through unchanged, requests hit the UI host, and
        every API call 403'd. The current mapping must NOT leave
        ``air-ngc.nvidia.com`` unchanged."""
        assert _api("https://air-ngc.nvidia.com") != "https://air-ngc.nvidia.com"

    def test_public_ui_does_not_accidentally_map_to_api_ngc(self):
        """The obvious wrong fix would be to rewrite ``air-ngc`` →
        ``air-api``, which is NOT what the OpenAPI spec says. Make
        sure we don't regress to that."""
        assert _api("https://air-ngc.nvidia.com") != "https://air-api.nvidia.com"

class TestDsxAirHosts:
    """Air moved to dsx-air hostnames (2026-08-04).

    Verified by resolution + unauthenticated probe at the time of the change:
    api.inside.dsx-air.nvidia.com and the previous api.air-inside.nvidia.com
    resolve to the SAME address and both answer 401 on /api/v1/, so the rename
    is the same gateway under a new name. The address is not recorded here —
    infrastructure detail, and it goes stale.
    """

    def test_internal_ui_maps_to_internal_api(self):
        assert _api("https://inside.dsx-air.nvidia.com") == \
            "https://api.inside.dsx-air.nvidia.com"

    def test_internal_ui_trailing_slash(self):
        assert _api("https://inside.dsx-air.nvidia.com/") == \
            "https://api.inside.dsx-air.nvidia.com"

    def test_internal_and_public_do_not_collide(self):
        """Distinct gateways — internal must not funnel into the public API."""
        assert _api("https://inside.dsx-air.nvidia.com") != \
            _api("https://dsx-air.nvidia.com")

    def test_legacy_internal_host_still_maps(self):
        """Existing .era-secrets vaults keep working."""
        assert _api("https://ngc.air-inside.nvidia.com") == \
            "https://api.air-inside.nvidia.com"

    def test_legacy_public_host_still_maps(self):
        assert _api("https://air-ngc.nvidia.com") == "https://api.dsx-air.nvidia.com"
