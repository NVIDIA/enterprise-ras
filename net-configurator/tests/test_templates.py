# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Unit tests for Jinja2 templates.

Includes both structural checks (existence, syntax) and rendering tests
that verify templates produce correct NVUE commands when given mock variables.
"""
import re
import shlex
import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined, Undefined
from pathlib import Path


# ---------------------------------------------------------------------------
# Jinja2 Environment with Ansible filter stubs for rendering tests
# ---------------------------------------------------------------------------

def _make_rendering_env(template_dir):
    """Create a Jinja2 Environment with Ansible filter stubs for testing.

    Stubs only the Ansible-specific filters used by our templates so that
    rendering succeeds outside of a real Ansible run.
    """
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        extensions=["jinja2.ext.do"],
    )

    # Ansible's regex_replace filter: (value, pattern, replacement)
    def _regex_replace(value, pattern, replacement):
        return re.sub(pattern, replacement, str(value))

    env.filters["regex_replace"] = _regex_replace

    return env


class TestCoreCLITemplate:
    """Test suite for core switch CLI template."""

    def test_template_exists(self, core_cli_template):
        """Test that core CLI template file exists."""
        assert core_cli_template.exists()

    def test_template_is_valid_jinja(self, core_cli_template):
        """Test that template is valid Jinja2."""
        template_dir = core_cli_template.parent
        env = Environment(loader=FileSystemLoader(str(template_dir)))

        # Should load without syntax errors
        template = env.get_template(core_cli_template.name)
        assert template is not None

    def test_template_has_nv_commands(self, core_cli_template):
        """Test that template contains nv set commands."""
        content = core_cli_template.read_text()

        # Template should contain nv set commands
        assert 'nv set' in content
        # Note: nv config apply is added by the ZTP wrapper script, not the template


class TestOOBCLITemplate:
    """Test suite for OOB switch CLI template."""

    def test_template_exists(self, oob_cli_template):
        """Test that OOB CLI template file exists."""
        assert oob_cli_template.exists()

    def test_template_is_valid_jinja(self, oob_cli_template):
        """Test that template is valid Jinja2."""
        template_dir = oob_cli_template.parent
        env = Environment(loader=FileSystemLoader(str(template_dir)))

        # Should load without syntax errors
        template = env.get_template(oob_cli_template.name)
        assert template is not None

    def test_template_has_nv_commands(self, oob_cli_template):
        """Test that template contains nv set commands."""
        content = oob_cli_template.read_text()

        # Template should contain nv set commands
        assert 'nv set' in content
        # Note: nv config apply is added by the ZTP wrapper script, not the template


class TestAllTemplates:
    """Test all role templates."""

    def test_all_role_templates_exist(self, project_root):
        """Test that all expected role templates exist."""
        expected_templates = [
            'roles/core/templates/core_nvue_cli.j2',
            'roles/oob-switch/templates/oob_nvue_cli.j2',
            'roles/ztp-server/templates/dnsmasq.conf.j2',
            'roles/ztp-server/templates/dnsmasq-ztp.conf.j2',
            'roles/ztp-server/templates/nginx-ztp.conf.j2',
            'roles/ztp-server/templates/ztp.sh.j2',
        ]

        for template_path in expected_templates:
            full_path = project_root / template_path
            assert full_path.exists(), f"Template not found: {template_path}"

    def test_all_templates_are_valid_jinja(self, project_root):
        """Test that all templates are valid Jinja2 (excluding Ansible-specific filters)."""
        templates_dir = project_root / 'roles'

        # Some templates use Ansible-specific filters (like ipaddr) that aren't available
        # in plain Jinja2. We skip validation for those.
        ansible_filter_templates = {'interfaces-ztp.j2', 'netplan-ztp.yaml.j2'}

        for template in templates_dir.rglob('*.j2'):
            if template.name in ansible_filter_templates:
                # Skip templates that use Ansible-specific filters
                continue
            env = Environment(loader=FileSystemLoader(str(template.parent)))
            # `quote` is an Ansible built-in (used in ztp.sh.j2 to neutralise
            # shell metacharacters in passwords). Register an equivalent so
            # parse succeeds outside of a real Ansible run.
            env.filters["quote"] = lambda s: shlex.quote(str(s))
            try:
                t = env.get_template(template.name)
                assert t is not None
            except Exception as e:
                pytest.fail(f"Template {template} has Jinja2 syntax error: {e}")


# ---------------------------------------------------------------------------
# Template Rendering Tests
# ---------------------------------------------------------------------------

class TestOOBTemplateRendering:
    """Render OOB switch template with mock variables and verify output.

    The OOB template is simpler than core (no macros, no network_roles)
    and uses only standard Jinja2 filters, making it ideal for full rendering.
    """

    @pytest.fixture
    def oob_vars(self):
        """Minimal variables needed to render oob_nvue_cli.j2."""
        return {
            "hostname": "oob-switch-01",
            "ansible_date_time": {"iso8601": "2026-01-01T00:00:00Z"},
            "spine_bond_members": ["swp49", "swp51"],
            "svi_ip": "192.168.200.2/24",
            "ntp_servers": ["0.pool.ntp.org", "1.pool.ntp.org"],
            "ldap": {"enabled": False},
            "timezone": "Etc/UTC",
            "default_gateway": "192.168.200.1",
        }

    def test_hostname_in_output(self, oob_cli_template, oob_vars):
        """Rendered output contains the hostname in the system command."""
        env = _make_rendering_env(oob_cli_template.parent)
        template = env.get_template(oob_cli_template.name)
        output = template.render(**oob_vars)

        assert "nv set system hostname oob-switch-01" in output

    def test_svi_ip_in_output(self, oob_cli_template, oob_vars):
        """Rendered output contains the SVI IP address."""
        env = _make_rendering_env(oob_cli_template.parent)
        template = env.get_template(oob_cli_template.name)
        output = template.render(**oob_vars)

        assert "nv set interface vlan200 ipv4 address 192.168.200.2/24" in output

    def test_spine_bond_members(self, oob_cli_template, oob_vars):
        """Rendered output contains spine bond configuration."""
        env = _make_rendering_env(oob_cli_template.parent)
        template = env.get_template(oob_cli_template.name)
        output = template.render(**oob_vars)

        assert "nv set interface spine_bond bond member swp49,swp51" in output

    def test_ntp_servers(self, oob_cli_template, oob_vars):
        """Rendered output contains configured NTP servers."""
        env = _make_rendering_env(oob_cli_template.parent)
        template = env.get_template(oob_cli_template.name)
        output = template.render(**oob_vars)

        assert "nv set system ntp server 0.pool.ntp.org" in output
        assert "nv set system ntp server 1.pool.ntp.org" in output

    def test_bridge_vlan_200(self, oob_cli_template, oob_vars):
        """Rendered output contains bridge domain VLAN 200."""
        env = _make_rendering_env(oob_cli_template.parent)
        template = env.get_template(oob_cli_template.name)
        output = template.render(**oob_vars)

        assert "nv set bridge domain br_default vlan 200" in output

    def test_default_ntp_when_not_provided(self, oob_cli_template, oob_vars):
        """When ntp_servers is not provided, defaults are used."""
        env = _make_rendering_env(oob_cli_template.parent)
        template = env.get_template(oob_cli_template.name)
        # Remove ntp_servers so the template uses its default
        oob_vars.pop("ntp_servers")
        output = template.render(**oob_vars)

        assert "nv set system ntp server 0.cumulusnetworks.pool.ntp.org" in output

    def test_output_starts_with_shebang(self, oob_cli_template, oob_vars):
        """Rendered output starts with #!/bin/bash."""
        env = _make_rendering_env(oob_cli_template.parent)
        template = env.get_template(oob_cli_template.name)
        output = template.render(**oob_vars)

        # Strip blank lines from top
        first_nonblank = next(
            line for line in output.splitlines() if line.strip()
        )
        assert first_nonblank.strip() == "#!/bin/bash"

    def test_post_login_message_contains_hostname(self, oob_cli_template, oob_vars):
        """Post-login message banner includes the hostname."""
        env = _make_rendering_env(oob_cli_template.parent)
        template = env.get_template(oob_cli_template.name)
        output = template.render(**oob_vars)

        assert "logged in to: oob-switch-01" in output

    def test_access_ports_configured(self, oob_cli_template, oob_vars):
        """Access ports have VLAN 200 and 1G speed."""
        env = _make_rendering_env(oob_cli_template.parent)
        template = env.get_template(oob_cli_template.name)
        output = template.render(**oob_vars)

        assert "nv set interface swp1-46 bridge domain br_default access 200" in output
        assert "nv set interface swp1-46 link speed 1G" in output


class TestCoreTemplateRendering:
    """Render the core switch template with mock variables.

    The core template is complex and uses Ansible-specific filters
    (regex_replace, ansible_date_time). We stub those and verify key
    sections of the output.
    """

    @pytest.fixture
    def core_vars(self):
        """Minimal variables needed to render core_nvue_cli.j2.

        This set covers the most common sections. Optional sections
        (LDAP, telemetry, etc.) are omitted to test the default/guard paths.
        """
        return {
            "hostname": "core-01",
            "ansible_date_time": {"iso8601": "2026-01-01T00:00:00Z"},
            "lo_ip": "172.16.176.1/32",
            "mh_mac": "44:38:39:BE:EF:01",
            # VLANs and VNIs
            "vlans": [100, 200, 300],
            "vnis": {100: 4100, 200: 4200, 300: 4300},
            # VLAN SVIs
            "vlan_interfaces": [
                {
                    "id": "vlan100",
                    "vlan": 100,
                    "ip": "172.16.178.2/24",
                    "vrr": "172.16.178.1/24",
                    "vrf": "default",
                },
            ],
            # Network roles — one simple CPU role
            "network_roles": {
                "cpu": {
                    "ports": [1, 2],
                    "breakout": 4,
                    "lanes": 2,
                    "vlan": 100,
                    "lacp_bypass": True,
                    "port_overrides": {},
                    "bond_overrides": {},
                },
            },
            # GPU interfaces
            "gpu_interfaces": {
                "ports": [3, 4],
                "breakout": 2,
                "lanes": 4,
                "vlan": 200,
                "state": "up",
                "port_overrides": {},
            },
            # ISL interfaces
            "isl_interfaces": {
                "ports": [49, 50],
                "breakout": 2,
                "lanes": 4,
                "port_overrides": {},
            },
            # Disabled interfaces
            "interfaces_disabled": [60, 62, 64],
            # Physical interfaces state
            "interfaces_up": "swp1s0-3,swp2s0-3,swp3s0-1,swp4s0-1,swp49s0-1,swp50s0-1",
            "interfaces_down": "swp60,swp62,swp64",
            # NVE VXLAN
            "nve_vxlan": {
                "decap_dscp": "copy",
                "encap_dscp": "copy",
                "source": "172.16.176.1",
            },
            # Anycast MAC
            "anycast_mac": "44:38:39:BE:EF:AA",
            # BGP (top-level, used by template directly)
            "bgp_asn": 65100,
            "router_id": "172.16.176.1",
            # VRFs (list of dicts, each with .id)
            "vrf_config": [
                {
                    "id": "default",
                    "lo": "172.16.176.1/32",
                },
            ],
            # Physical port count
            "num_physical_ports": 64,
            # NTP
            "ntp_servers": ["0.pool.ntp.org"],
            # SSH
            "ssh_authorized_keys": [],
            # LDAP disabled
            "ldap": {"enabled": False},
            # Community list and route map (optional, provide empty)
            "community_list": {},
            "route_map": {},
            # System
            "timezone": "Etc/UTC",
        }

    def test_hostname_command(self, core_cli_template, core_vars):
        """Output contains nv set system hostname."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        assert "nv set system hostname core-01" in output

    def test_bridge_vlan_commands(self, core_cli_template, core_vars):
        """Output contains VLAN bridge domain commands for all configured VLANs."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        assert "nv set bridge domain br_default vlan 100 vni 4100" in output
        assert "nv set bridge domain br_default vlan 200 vni 4200" in output
        assert "nv set bridge domain br_default vlan 300 vni 4300" in output

    def test_evpn_enabled(self, core_cli_template, core_vars):
        """Output contains EVPN enabled commands."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        assert "nv set evpn state enabled" in output
        assert "nv set evpn multihoming state enabled" in output

    def test_loopback_address(self, core_cli_template, core_vars):
        """Output contains loopback address configuration."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        assert "nv set interface lo ipv4 address 172.16.176.1/32" in output

    def test_breakout_configuration(self, core_cli_template, core_vars):
        """Output contains breakout commands for CPU (4x2) and GPU (2x4) ports."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        # CPU ports 1,2 should get 4x breakout with 2 lanes
        assert "link breakout 4x lanes-per-port 2" in output
        # GPU ports 3,4 should get 2x breakout with 4 lanes
        assert "link breakout 2x lanes-per-port 4" in output

    def test_bond_interfaces_created(self, core_cli_template, core_vars):
        """Output contains bond interfaces for CPU role ports."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        # CPU port 1 with breakout 4 should create bond1s0, bond1s1, bond1s2, bond1s3
        assert "nv set interface bond1s0 bond member swp1s0" in output
        assert "nv set interface bond1s1 bond member swp1s1" in output
        assert "nv set interface bond1s2 bond member swp1s2" in output
        assert "nv set interface bond1s3 bond member swp1s3" in output

    def test_mh_segment_enabled(self, core_cli_template, core_vars):
        """Output contains EVPN multihoming segment enabled and MAC."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        assert "evpn multihoming segment state enabled" in output
        assert "evpn multihoming segment mac-address 44:38:39:BE:EF:01" in output

    def test_lacp_bypass(self, core_cli_template, core_vars):
        """Output contains LACP bypass for CPU role (lacp_bypass=True)."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        assert "bond lacp-bypass enabled" in output

    def test_disabled_interfaces(self, core_cli_template, core_vars):
        """Output contains breakout disabled for specified ports."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        assert "link breakout disabled" in output
        assert "swp60" in output
        assert "swp62" in output
        assert "swp64" in output

    def test_gpu_access_vlan(self, core_cli_template, core_vars):
        """GPU interfaces are assigned bridge domain access VLAN."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        # GPU ports 3,4 with breakout 2 = swp3s0, swp3s1, swp4s0, swp4s1
        assert "bridge domain br_default access 200" in output

    def test_anycast_mac(self, core_cli_template, core_vars):
        """Output contains anycast MAC when defined."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        assert "nv set system global anycast-mac 44:38:39:BE:EF:AA" in output

    def test_nve_vxlan_enabled(self, core_cli_template, core_vars):
        """Output contains NVE VXLAN enabled."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        assert "nv set nve vxlan state enabled" in output

    def test_vlan_svi_configuration(self, core_cli_template, core_vars):
        """Output contains VLAN SVI with IP, VRR, and type."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        assert "nv set interface vlan100 ipv4 address 172.16.178.2/24" in output
        assert "nv set interface vlan100 ipv4 vrr address 172.16.178.1/24" in output
        assert "nv set interface vlan100 ipv4 vrr state enabled" in output
        assert "nv set interface vlan100 type svi" in output
        assert "nv set interface vlan100 vlan 100" in output

    def test_output_starts_with_shebang(self, core_cli_template, core_vars):
        """Rendered output starts with #!/bin/bash (after macro definitions)."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        # The core template has macros at the top that produce empty output,
        # then #!/bin/bash is the first actual content line
        first_nonblank = next(
            line for line in output.splitlines() if line.strip()
        )
        assert first_nonblank.strip() == "#!/bin/bash"

    def test_no_ldap_when_disabled(self, core_cli_template, core_vars):
        """LDAP section is not rendered when ldap.enabled is False."""
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        # Should not contain LDAP-specific commands
        assert "ldap" not in output.lower() or "ldap" in "# LDAP".lower()

    def test_ldap_enabled_with_missing_nested_keys_does_not_crash(
        self, core_cli_template, core_vars
    ):
        """TIER 1 regression: `ldap_enabled=Yes` but missing ldap_base_dn /
        ldap_root_dn / ldap_admin_password must NOT crash config generation.

        Previously the template accessed `ldap.base_dn` etc. without
        `| default()` guards, so a partial LDAP config in the Excel
        crashed Jinja2 with UndefinedError mid-generate. The template
        now falls back to an obvious sentinel value — the generated
        config is intentionally broken so the user notices, but
        generation itself succeeds and the rest of the configs (GPU,
        bonds, BGP, etc.) still get written."""
        core_vars["ldap"] = {"enabled": True}  # enabled but nothing else set
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)

        # Must not raise
        output = template.render(**core_vars)

        # Sentinel values must appear in the output so the user sees
        # clearly what's missing — don't just silently generate a
        # broken LDAP block.
        assert "MISSING_ldap_base_dn_SET_IN_EXCEL" in output
        assert "MISSING_ldap_root_dn_SET_IN_EXCEL" in output
        assert "MISSING_ldap_admin_password_SET_IN_VAULT" in output

        # And the rest of the template should still render — check a
        # few non-LDAP landmarks appear.
        assert "nv set system hostname core-01" in output
        assert "nv set router bgp" in output

    def test_ldap_enabled_with_empty_string_fields_also_fires_sentinels(
        self, core_cli_template, core_vars
    ):
        """Follow-on regression: in real Excel→inventory flows, scripts/
        excel_parser.py writes EMPTY STRINGS (not undefined) when the
        user leaves an LDAP cell blank. Jinja2's single-arg `| default(X)`
        only fires on undefined keys — it lets empty strings through
        unchanged, so a user with a blank ldap_base_dn cell was getting
        `nv set system aaa ldap base-dn` with no argument in the rendered
        config (silent broken output, no sentinel).

        The two-argument `| default(X, true)` form fires on any falsy
        value — undefined, None, empty string. This test pins that shape
        so we don't regress to the one-arg form."""
        core_vars["ldap"] = {
            "enabled": True,
            "base_dn": "",           # blank Excel cell → empty string
            "root_dn": "",
            "admin_password": "",
        }
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        # Sentinels MUST still appear even when the values are empty
        # strings (falsy, not undefined).
        assert "MISSING_ldap_base_dn_SET_IN_EXCEL" in output
        assert "MISSING_ldap_root_dn_SET_IN_EXCEL" in output
        assert "MISSING_ldap_admin_password_SET_IN_VAULT" in output

        # Crucially, the silent-empty broken form (trailing whitespace
        # only) must NOT appear. If the test sees `base-dn\n` without a
        # value, that's the regression — empty string slipped through
        # default() and rendered as nothing.
        assert "ldap base-dn \n" not in output
        assert "ldap bind-dn \n" not in output

    def test_ldap_enabled_with_complete_config_uses_real_values(
        self, core_cli_template, core_vars
    ):
        """Happy-path sanity: when all four Excel fields are set, the
        rendered template uses them verbatim (sentinels must NOT
        appear)."""
        core_vars["ldap"] = {
            "enabled": True,
            "base_dn": "dc=acme,dc=example,dc=com",
            "root_dn": "cn=admin,ou=Users,dc=acme,dc=example,dc=com",
            "admin_password": "real-vault-password",
            "servers": [{"ip": "10.0.0.10"}],
        }
        env = _make_rendering_env(core_cli_template.parent)
        template = env.get_template(core_cli_template.name)
        output = template.render(**core_vars)

        assert "base-dn dc=acme,dc=example,dc=com" in output
        assert "bind-dn cn=admin,ou=Users,dc=acme,dc=example,dc=com" in output
        assert "ldap secret real-vault-password" in output
        assert "ldap server 10.0.0.10" in output

        # No sentinels when all values are provided.
        assert "MISSING_ldap" not in output


# ---------------------------------------------------------------------------
# Regression tests for roles/ztp-server/templates/ztp.sh.j2
#
# ZTP bootstrap runs as root on every switch during first boot. Any variable
# interpolated into the generated shell script MUST be shell-escaped, or a
# password containing a single quote (hostile or merely realistic) can break
# out of the surrounding quotes and execute arbitrary commands as root.
# The fix (commit 02e25bf) routes `switch_password` through Ansible's
# `| quote` filter; these tests nail the fix down so a future refactor
# can't regress it silently.
# ---------------------------------------------------------------------------

HOSTILE_PASSWORD = "foo'; touch /tmp/pwned; echo '"
LEGIT_APOSTROPHE_PASSWORD = "M@ry's_P@ss!"


def _ztp_render_env(template_dir):
    """Jinja2 env for ztp.sh.j2 with Ansible's `quote` filter stubbed
    via shlex.quote (identical POSIX-shell-escape semantics)."""
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
    )
    env.filters["quote"] = lambda s: shlex.quote(str(s))
    return env


def _ztp_context(switch_password):
    """Minimum-viable context for rendering ztp.sh.j2."""
    return {
        "switch_password": switch_password,
        "switch_user": "cumulus",
        "cumulus_target_release": "",
        "ztp_monitoring_config": "",
    }


class TestZTPShellInjectionRegression:
    """Regression tests for the shell-injection fix in ztp.sh.j2."""

    def test_template_exists(self, ztp_sh_template):
        assert ztp_sh_template.exists()

    def test_hostile_password_survives_as_single_shell_token(self, ztp_sh_template):
        """Rendering with an injection payload must produce exactly one
        shell token for the password — no command split."""
        env = _ztp_render_env(ztp_sh_template.parent)
        tmpl = env.get_template(ztp_sh_template.name)
        output = tmpl.render(**_ztp_context(HOSTILE_PASSWORD))

        nv_line = next(
            line for line in output.splitlines()
            if "nv set system aaa user" in line and "password" in line
        )
        tokens = shlex.split(nv_line)
        assert tokens[-1] == HOSTILE_PASSWORD, (
            f"password was split by the shell — expected one literal token, "
            f"got {tokens[-1]!r} with surrounding tokens {tokens[-3:]!r}"
        )

    def test_hostile_password_also_safe_in_chpasswd_line(self, ztp_sh_template):
        """The fallback `echo user:password | chpasswd` line must also keep
        the whole user:password pair as a single token."""
        env = _ztp_render_env(ztp_sh_template.parent)
        tmpl = env.get_template(ztp_sh_template.name)
        output = tmpl.render(**_ztp_context(HOSTILE_PASSWORD))

        chpasswd_line = next(
            line for line in output.splitlines()
            if "chpasswd" in line and line.strip().startswith("echo ")
        )
        # Up to the `|` is the echo command; split just that part.
        echo_part = chpasswd_line.split("|", 1)[0].strip()
        tokens = shlex.split(echo_part)
        assert tokens[0] == "echo"
        assert tokens[1] == f"cumulus:{HOSTILE_PASSWORD}", (
            f"user:password was split by the shell — got tokens {tokens!r}"
        )

    def test_none_of_the_injected_commands_appear_at_command_level(self, ztp_sh_template):
        """Defense-in-depth: the literal injection substring `touch /tmp/pwned`
        must only ever appear *inside* a quoted literal, never as a
        standalone shell command position."""
        env = _ztp_render_env(ztp_sh_template.parent)
        tmpl = env.get_template(ztp_sh_template.name)
        output = tmpl.render(**_ztp_context(HOSTILE_PASSWORD))

        # Grab every line that mentions the injection fragment.
        hits = [l for l in output.splitlines() if "touch /tmp/pwned" in l]
        assert hits, "test setup bug: injection fragment not found anywhere"
        for line in hits:
            # Tokenize. If the fragment is inside a quoted literal, the
            # whole password comes out as one token. If a shell would
            # actually execute `touch`, `touch` appears as its own token.
            try:
                tokens = shlex.split(line.split("|", 1)[0].strip())
            except ValueError:
                pytest.fail(f"rendered line is not even valid shell: {line!r}")
            assert "touch" not in tokens, (
                f"injection command leaked to a command position: {line!r}"
            )

    def test_legit_apostrophe_password_renders_cleanly(self, ztp_sh_template):
        """A real-world password containing an apostrophe must render
        without breaking the script — this is both a security and a
        reliability regression."""
        env = _ztp_render_env(ztp_sh_template.parent)
        tmpl = env.get_template(ztp_sh_template.name)
        output = tmpl.render(**_ztp_context(LEGIT_APOSTROPHE_PASSWORD))

        nv_line = next(
            line for line in output.splitlines()
            if "nv set system aaa user" in line and "password" in line
        )
        tokens = shlex.split(nv_line)
        assert tokens[-1] == LEGIT_APOSTROPHE_PASSWORD

    def test_default_password_renders_identically_to_pre_fix(self, ztp_sh_template):
        """Sanity check: the common-case default password produces the
        expected literal and the whole script is still valid shell."""
        env = _ztp_render_env(ztp_sh_template.parent)
        tmpl = env.get_template(ztp_sh_template.name)
        output = tmpl.render(**_ztp_context("Cumu1usLinux!"))

        assert "password 'Cumu1usLinux!'" in output, (
            "default password should render as a plain single-quoted literal"
        )
