<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: MIT -->

# net-configurator — Public Changelog

Public releases, newest first. Each section describes what changed for users since the previous public release.

## nc-v8.0.0 — 2026-10-12

### Breaking changes: upgrading from v7 to v8 — required workflow changes

**Convert your v7 workbook and configure secrets before generating a v8 deployment.**
Run these commands from the net-configurator directory.

1. **Legacy workbooks are no longer accepted.** Convert once, review conversion
   warnings and the resulting sheets, then validate the new intake workbook:

   ```bash
   make convert-workbook EXCEL=/path/to/site-v7.xlsx
   make validate-excel EXCEL=/path/to/site-v7.intake.xlsx
   ```

   The converter writes `site-v7.intake.xlsx` beside the original; it does not
   overwrite the v7 workbook. It preserves populated optional override sheets and omits empty ones.
   Use the intake workbook from now on. The transitional converter is scheduled
   for removal in v10.

2. **Use `make secrets` to create or update deployment credentials.** Import
   the converted workbook first so the wizard can read its LDAP settings, then
   configure the matching architecture and site before generation. For example,
   for a `2-8-5-200` workbook and site `customer-a`:

   ```bash
   make import EXCEL=/path/to/site-v7.intake.xlsx SITE=customer-a
   make secrets ARCH=2-8-5-200 SITE=customer-a
   make generate ARCH=2-8-5-200 SITE=customer-a
   ```

   Substitute your workbook's architecture and chosen site. A bare
   `make secrets` edits the shared template, ignores the saved context, and
   does not update existing deployment copies. With `ARCH=… SITE=…`, it edits
   that deployment and offers Vault encryption. Existing valid secrets can be
   retained; you do not have to rotate them solely to upgrade. Disabled LDAP
   skips its password prompts. If you encrypt the file, configure the Vault
   password source before running unattended generation or deployment.

See the [upgrade instructions](README.md#upgrading-from-v7-to-v8--required-workflow-changes)
and [workbook guide](docs/EXCEL_CONFIGURATION_GUIDE.md#migrating-a-legacy-workbook).

### New: Architecture support

- Added support for 2-8-5-400 (2 CPU / 8 GPU / 5 NIC / 400 Gbps per GPU), the eighth supported architecture, from SU 1 to SU 8, with default and largescale reference examples.
- ZTP is now supported on physical switches (deploy_in_air = No), not only in NVIDIA Air.

### New: Intake-form workbook

- The intake form is now the only input format. Every shipped workbook has been converted to the seven-sheet intake form. A workbook in the previous layout is refused by make generate, with a pointer to make convert-workbook, which converts it.
- The five optional override sheets (Prefix lists, Route policy, Community lists, ACLs, Custom_Config) are omitted from the standard workbooks and read only if present. A populated
  [optional-sheet sample](docs/optional-overrides.xlsx) is available for copying
  and adapting; it is not a standalone deployment workbook.
- Validation findings now name the intake-form sheet and cell to fix.
- Host Data: an IP you fill in on a data-plane row is now applied as written; blank cells are still allocated automatically.
- Wire Map Port Side and Cable Split now identify the breakout cage and lane of each switch sub-port, instead of NA / 1.0 everywhere.
- GPU rails and planes in generated workbooks are now numbered from 0, matching GPU numbering. Hostnames, inventory groups and physical port labels still count from 1.

### New: Switch configuration

- BGP graceful restart is enabled on every switch role.
- Service VRFs use BGP multipath; spines allow up to 128 paths in the default VRF.
- Host-facing N/S bonds are STP edge ports with BPDU guard.
- Generated switch configuration scripts now carry an SPDX license header.
- Cumulus Linux moves from 5.18.0 to 5.18.3 on every switch role and architecture.

### New: Tooling

- make secrets creates, edits and vault-encrypts secrets.yml, either the shared template or a per-deployment copy.
- make secrets for a deployment skips the LDAP password prompts when the workbook or generated inventory disables LDAP and neither enables it; if the setting can't be read, the prompts still run. For the shared template, it asks whether to set LDAP passwords and defaults to no.
- A vault-encrypted secrets.yml now works with every make target that runs a playbook.
- Regenerating into an existing site now removes per-node files left over from an earlier generation. Only files the generator wrote are removed.
- The ZTP server user is configurable (ztp_server_user).
- make air-deploy checks that every image the topology uses exists on the Air instance before importing, instead of failing later with an INVALID simulation and a misleading resource error.
- A warning, with an offered fix, when every GPU/CPU link in an SU is set to Display in Air = No.
- air-destroy --cleanup-only now removes only the UserConfigs that belong to the given site and architecture.

### Structural changes

- The 2-4-3-200 default example moved from SU 8 to SU 5, so the default and largescale examples now cover different scales.
- Architecture names follow one rule with no exceptions: {CPUs}-{GPUs}-{NICs}-{Gbps per GPU}. Documentation that described "200" as a per-NIC link speed was corrected.

### Fixed

Excel-driven generation & validation:

- Air infrastructure addresses are now allocated inside the declared OOB / air-mgmt subnet. Previously a fixed offset could fall outside a smaller subnet such as a /26, leaving every server unreachable.
- External storage hosts are now placed correctly on a custom air-mgmt subnet.
- A Wire Map switch whose role can't be recognised now stops validation and generation, instead of being configured as the wrong role.
- Loopback uniqueness is checked before any file is written, so a collision no longer leaves a half-written inventory.
- A switch role with no resolvable Cumulus image is now an error. Previously it silently fell back to an unpinned 5.16.0 image.
- An invalid oob_uplink_mode value (for example LAYER3) is now handled the same way by every component, instead of producing an L2 inventory with an L3-labelled topology.
- The public OOB switch-count check now covers every architecture and SU, including the shipped largescale workbooks.
- 2-4-5-800 with L2 OOB: the core-side BGP seed now peers only over the ISL, fixing a BGP health failure.
- validate-topology no longer warns about external storage nodes on the default sites.
- The BGP/EVPN report now covers GPU leaf and spine switches.

Air / deployment tooling:

- Full-scale ping validation (for example 2-4-5-800 at SU 8) failed for compute hosts because the generated script exceeded the Linux argument-length limit; scripts are now streamed over SSH stdin.
- validate-ping-matrix now fails when a server's results can't be collected, instead of passing.
- make validate-ztp-direct now returns the playbook's exit status.
- LDAP is configured on every switch role, and restart-ldap covers every switch.
- A SITE= passed on the command line is now used by every step of make deploy, and by site directory matching. A lower-case ARCH= is normalised.
- ZTP downloads use wget -q, the documented workaround for a Cumulus ZTP decode error.

Documentation:

- Documentation names the intake-form sheets, says which OOB mode each oob-server-01 / dhcp-oob reference applies to, and states that validate-* playbooks run on the jump host.

### Security

- Workbook text is treated as data: cells containing template markers ({{, {%, {#) are rejected.
- Custom_Config entries are checked against a stricter command grammar.
- Several steps now read passwords from stdin instead of taking them on the command line. Some steps still expose passwords in the process table; see Known limitations.
- NVIDIA Air URLs must use https, since the NGC API key is sent with every Air call. SSH agent forwarding is no longer enabled by default.
- Switch passwords are checked against the Cumulus password policy before generate and deploy. CHANGE_ME, empty values, passwords that match the username and weak passwords are rejected. The documented example password Cumu1usLinux! is accepted, but unique production passwords are still recommended.
- Every shipped workbook sets status_page_enabled: No. When the status page is enabled, a placeholder, empty or reused-switch password for it is refused.

### Dependencies

- Bumped ansible to >=14.3.1,<15 and ansible-core to >=2.21.4,<2.22 (CVE-2026-16493, CVE-2026-11332).
- NOTICE now also lists test dependencies and certifi.

### Testing

- The public tree now passes its own test suite with no skipped tests.
- tests/ is now linted as part of make lint.
- Validated in NVIDIA Air: all eight architectures passed at both shipped scales (default and largescale) in NOZTP, DHCP ZTP and switches-only modes. This does not cover every optional feature combination. Physical switches were not tested for this release.

### Known limitations

- Don't run the tool on a multi-user host. The Air ProxyCommand (which server deployment through the jump host also uses), restart-ldap-switches, push-switch-configs and make fix-ext-storage still expose passwords in the process table (ps auxww) while they run. See SECURITY.md.
- Regenerating the tracked default or largescale sites with real passwords in the workbook changes their tracked secrets.yml. Use a site name of your own for real deployments.
- Not tested on physical switches. On physical hardware, most validate-* targets run through the jump group, which is filled only from Air nodes, so they check almost nothing; validate-ztp-direct is the only validation that connects to switches directly.
- L2 storage is supported but no shipped workbook, reference output or Air test uses it.
- Loopback addresses can collide beyond the shipped scales: at the 21st OOB switch, or at 11 N/S leaves when Loopbacks cells are left blank. No shipped site has a duplicate.
- Every OOB switch puts all 48 host ports in the VLAN 200 access bridge; the range can't be narrowed per switch.
- Some fabric shapes can't be expressed: SVIs in the default VRF, per-switch GPU VLANs, two subnets on one SVI, and fabrics with no GPU network.
- 2-4-5-800 creates 12 generic support-NN servers, not the role-specific Mission Control layout.
- make air-destroy can delete UserConfigs whose names share the first 40 characters of the simulation title. air-destroy --cleanup-only matches only its own site and architecture.
- The image check before an Air import proves an image name exists, not that your account can use it.
- No CI ships with the public repository.
- Cumulus Linux bug 5079383 (BGP assertion crash with EVPN symmetric IRB and VRF route leaking) matches this design and is not fixed in 5.18.3.

## nc-v7.0.0 — 2026-09-02

### New: Architecture support

- Added support for 2-4-5-400 — a depopulated variant of 2-8-5-200 (2 CPU / 4 GPU / 5 NIC / 400 Gbps, same fabric, half the GPU count and half the external uplink capacity).
- 2-4-5-400 ships a default and a largescale reference example (input workbook + generated output), like every other supported architecture.

### New: Increased Excel field support

- Custom_Config sheet — inject switch configuration the tool doesn't generate (login banner, SNMP target, local user, etc.), targeted by architecture role or hostname. Restricted to safe nv set/nv unset/nv show commands; your entries are applied last and take priority over generated settings.
- ACLs sheet — add, override, or remove the inbound control-plane ACL rules applied to every switch.
- Prefix lists / Route policy / Community lists sheets — add, override, or remove BGP prefix-lists, route-maps, and community-lists beyond what the tool computes by default.
- All of the above are optional and off by default — an empty or absent sheet produces identical output to previous versions.
- Loopbacks sheet: added a per-node BGP ASN column — ASNs can now be set per node instead of only at the fabric level.
- Nodes sheet: added an OOB VLAN column, allowing OOB switches to serve distinct management subnets.
- Versions sheet: added csl and gsl rows alongside the existing core/oob rows.
- Added support for deploying with deploy_in_air = No against real hardware using static management IPs, instead of only NVIDIA Air simulations.
- ntp_servers entries can now specify an NTP association type (server, pool, peer) per server.
- Port Profile Speed and link auto-negotiate are now honored by the generator instead of being ignored.

### New: Tooling

- Cumulus Linux moves from 5.16.1 to 5.18.0 on every switch role.
- Validation now checks fabric ISLs both by faceplate (physical transceivers at both ends) and by bandwidth.
- make ip-report — generates a read-only report of every IP address assigned in a deployment.
- make validation-bundle — packages a completed deployment for review/endorsement, with credential values automatically redacted.
- Command-line variables passed to make (ARCH=, SITE=, etc.) are now accepted in any letter case.

### Structural changes

- Reference inventory files are now fully generated per deployment (output/<arch>/<site>/) instead of being maintained as static, hand-edited per-architecture templates — reduces drift between what's checked in and what a deployment actually produces.
- VLAN/VRF/VNI numbering and prefix-list conventions are now consistent across every supported architecture model.
- Every architecture now includes a dedicated STORAGE VRF.
- BFD profile and OOB route-map naming standardized across switch roles.
- BGP peer-group naming unified to a single convention.
- Node naming refreshed for scale-up units and collapsed spine-leaf roles.

### Fixed

Excel-driven generation & validation:

- Server data-plane IP auto-assignment now respects the declared subnet instead of using a hardcoded stride.
- Storage server ports are no longer dropped from switch configs when an L3 storage uplink/VRF is defined.
- Fixed inventory IP selection when deploy_in_air = No.
- Fixed a case where an overridden loopback address wasn't picked up by the GPU-plane overlay neighbor, resulting in a dead EVPN session.
- Node-facing core switch ports are now correctly generated as sub-ports — previously a bare server link on certain port types was silently dropped from the config.
- OOB switch templates now correctly bring up their access-port links.
- Per-switch OOB VLAN assignment now reaches the access ports, not just the SVI.
- Fixed data-plane host IP collisions with core switch SVIs on non-/24 VLANs.
- Fixed a validation gap where an out-of-band subnet duplicate-IP check could silently pass without actually checking anything.
- Fixed a Wire Map port that could pass validation and then be silently dropped from the generated topology.
- Fixed incorrect ISL (inter-switch link) count detection on certain workbook formats, including a case where north/south ISLs were double-cabled on largescale workbooks.
- The interface breakout profile governing inter-switch links now applies consistently across all switch roles.
- Switch role is now determined from the authoritative Nodes-sheet field rather than inferred from hostname naming — previously a non-standard hostname could silently receive no configuration while validation still reported success.
- Added hard-fail validation when a management/OOB subnet is too small for its assigned node count.
- Added hard-fail validation for switch name/role consistency and incomplete config generation.
- Added validation for storage/exit uplink bandwidth floors.

Air / deployment tooling:

- Fixed an issue where clearing an optional Air setup field (e.g. NGC Org, Air username) back to blank would silently keep the old value instead, which could cause Air API calls to fail with a 403 error. Clearing now prompts for confirmation and then actually clears the field. (#14)
- Fixed the Air SSH connectivity check incorrectly reporting a password failure when password authentication was in fact working.
- At SU 32, the cust-net-edge node in Air no longer exceeds the 64-port platform limit.
- push-switch-configs keeps SSH authentication working through the NVUE apply, and no longer reports a network failure as a wrong password.
- A boot race in Air could lose the configuration-apply step; it now retries.
- External storage hosts reserve eth0 for management and use ethN (not swpN) ports in the Wire Map; air-deploy was broken on every architecture without this.
- A shipped 8x breakout on an even port broke its own ISL; fixed in the generator and the shipped examples.
- Shipped workbooks no longer carry a stale Cumulus version in the Versions sheet "Default Value" column.
- Generated workbooks no longer trigger an Excel repair prompt (duplicate ACLs-sheet relationship id).
- Fixed missing sshpass and SSH key injection issues on the Air out-of-band jump node that could cause dropped sessions.
- Fixed a case where the management subnet setting wasn't consistently honored between the config generator and the provisioning scripts.
- Fixed an issue where a malformed SITE= value passed on the command line could be misinterpreted by make.
- Documentation no longer references a jump-host name that doesn't exist in any shipped inventory.

Other:

- Fixed several previously-suppressed linter warnings that had been masking minor logic issues in validation code.
- Removed an outdated hardcoded example password from the ZTP documentation.

### Security

- Updated the vulnerability reporting process: security issues should now be reported privately via psirt@nvidia.com or GitHub's private vulnerability reporting feature rather than a public issue.
- Added a factory-password bootstrap step for first-time switch provisioning.
- Hardened make command-line variable handling against malformed input.

### Dependencies

- Bumped ansible-core to >=2.20.7,<2.21.
- Bumped jinja2 to >=3.1.6,<4.
- Added pexpect>=4.9.0,<5 (used for the new password bootstrap step).

### Testing

- Substantially expanded automated test coverage across configuration validation, IP/ASN/loopback allocation, and workbook parsing.

## nc-v6.0.0 — 2026-07-07

### New: Architecture support

- Added support for 2-4-5-800 and 2-8-9-400-SP (the single-plane 2-8-9-400 variant, with its switch roles strictly enforced).
- Multi-tier (largescale) fabrics are supported for every architecture, including two-tier N/S EVPN with per-bond ESIs and the cs-spine overlay.
- Every supported architecture now ships a largescale reference example (input workbook + generated output) alongside the default example.

### New: Tooling

- A switches-only, no-ZTP deploy path, with a switch-health check and faster parallel validate-all.
- Long validation steps show live progress instead of looking hung.
- Optional nv-ngc-org header for NVIDIA Air API calls, read from configuration and off by default.
- The site name is taken from the input folder when it and the workbook disagree, and failed Air simulations are cleaned up on a best-effort basis.
- Friendlier errors for unreadable .xlsx files.

### Structural changes

- "maxscale" is renamed "largescale".
- Default and sample server names follow the su-XX-node-YY convention.
- The OOB server inventory group is renamed oob_server everywhere.
- Removed duplicate per-architecture inventory files.

### Fixed

- Storage EVPN multihoming ARP flux.
- Storage VLAN tagging and SVI/VRR subnet correctness.
- A dead OOB_LOCAL_IF rule and a missing WEIGHTED_ECMP outbound policy on core/csl switches.
- A custom air_mgmt_subnet is now honored by the validation gate.
- A hard preflight gate for duplicate or reserved management-IP collisions.
- An OOB-to-csl BGP gate, a STORAGE warning, an external-storage fix and a server eth0 netplan fix.
- The Air setup vault write is atomic, and deploy-switches-only honors the imported site.
- The public validator accepts the shipped largescale workbooks.
- Node Instructions hostnames are quoted.

### Security

- Workbook values can no longer reach a root shell through the rendered configuration, and the input layer rejects unsafe hostnames, prefix-list entries and wiring.
- Secrets are kept out of ZTP logs and the status page.
- Status-page basic auth no longer defaults to the switch password.
- Added SECURITY.md and the canonical LICENSE; removed personal data from shipped workbooks.

### Dependencies

- Removed the unused paramiko dependency.
- Test dependencies moved to pytest 9 and pytest-cov 7.

### Testing

- All six architectures validated in NVIDIA Air at default and largescale, including ZTP, NOZTP and controller-from-node deploy modes.

## nc-v5.0.0 — 2026-05-29

### New: Architecture support

- Added support for 2-8-9-800 (HGX B300), dual-plane.
- External storage nodes (Ubuntu + FRR) peer with the fabric over eBGP in the STORAGE VRF.

### New: Increased Excel field support

- STORAGE VRF is first-class: validated, parsed and rendered from the workbook, and shipped in the 2-8-9-800 default.
- L2 or L3 OOB uplink mode is selected in the workbook.
- Loopbacks sheet: per-switch and per-VRF loopback overrides.
- VRF-aware DHCP relay, including inter-VRF relay through the EXIT VRF, with dnsmasq configured automatically.
- Per-rail GPU VLANs and a per_rail_per_plane gpu_vlan_mode (one VLAN per rail and plane); the Wire Map Allowed VLANs and L3 VNI columns are honored.
- Custom server roles from arbitrary Port Profile names.
- Operator-configurable pre- and post-login SSH banners.
- Named BFD profiles (default and overlay).
- Nodes sheet: Type, Notes, Enabled = Air and Cable Split (A)/(B) columns, with dropdowns.
- Per-bond descriptions name the connected node.
- Wire Map Network Profile names are validated; unused port-settings columns were removed.

### New: Tooling

- NOZTP=1, the fastest way to deploy to NVIDIA Air.
- End-to-end L3 OOB support, including the status page and per-NIC policy-based routing.
- A richer report when BGP sessions are down.
- push-switch-configs, validate-ztp-direct and restart-ldap-switches-direct work with every switch group name.
- validate-servers no longer gets stuck on poisoned ARP entries, and its reports are split per check.
- Reference output is shipped alongside the reference workbooks.

### Structural changes

- The static route in L3 OOB was removed.
- Removed the legacy input and template directories.

### Fixed

- The workbook validator is much stricter, across the Wire Map (phantom hosts, self-loops, port bounds), VLAN/VRF (types, uniqueness, reserved IPs), DHCP relay, Settings (duplicates, bounds, overlaps, MAC sanity), Loopbacks and Nodes sheets, with RFC 1123 hostname checks, reserved hostnames and cross-sheet checks. generate stops when validation fails.
- Server netplan eth numbering matches the topology.
- Enabled = No is honored for Wire Map rows and topology nodes.
- ERA_PREFIXES lists narrow VLAN subnets explicitly.
- Core switches no longer set update-source on unnumbered peers, and route distinguishers are derived automatically.
- The 8x breakout odd-port convention is validated.
- push-switch-configs matches generated file names and confirms the apply.

### Security

- NVUE values are shell-quoted in ZTP and LDAP scripts, the ZTP web server is restricted to the OOB network, and the LDAP password is kept off command lines.
- Shell metacharacters in Settings values are rejected.
- Fixed a password leak in shell trace output.

### Documentation

- Architecture names: B is the per-GPU bandwidth; added a feature support matrix.
- OEM deployment and Excel guide gaps closed; documented 2-8-9-800 / HGX B300 and LDAP prefill in NVIDIA Air.

## nc-v4.0.0 — 2026-05-01

First public release of net-configurator: fill in an Excel workbook describing a deployment, and the tool generates the Ansible inventory, NVUE switch configurations and an NVIDIA Air topology, then deploys them with Zero Touch Provisioning.

### Architecture support

- 2-4-3-200, 2-8-5-200 and 2-8-9-400, each with a sample workbook.

### Features

- make deploy EXCEL=... runs the whole pipeline.
- ZTP: switches configure themselves on first boot over DHCP.
- Optional NVIDIA Air integration, with automated simulation creation and SSH setup.
- Multiple sites per architecture.
- Optional LDAP authentication, detected from the workbook.
- Secrets encrypted at rest with Ansible Vault.

### Fixed

- .era-context no longer races when several deployments run in parallel.

### Structural changes

- Removed the legacy topology/ and templates/ directories.
- Added CONTRIBUTING.md and SPDX license headers.

### Dependencies

- ansible >=13.5.0,<14, ansible-core >=2.20.4,<2.21, httpx, openpyxl, pyyaml, rich, paramiko and jinja2.

## Earlier releases: spectrum-era (deprecated)

Before net-configurator, ERA switch automation shipped as separate Ansible projects for each architecture, in the [spectrum-era/](https://github.com/NVIDIA/enterprise-ras/tree/main/spectrum-era) folder of this repository. Their tags are named sp-<architecture>-v<version>. Each project was configured by editing its inventory files by hand; there was no workbook. The folder is deprecated and kept for reference only. Use net-configurator for new deployments. All spectrum-era releases were published on GitHub on 2026-03-01, except sp-2-8-5-200-v2.0.0 (2026-03-02).

### sp-2-4-3-200-v3.0.0, sp-2-8-5-200-v3.0.0, sp-2-8-9-400-v3.0.0 — 2026-03-01

- LDAP: an OpenLDAP server with example users is set up on the dhcp-oob host, and the core switches are configured to use it.
- Telemetry is enabled on the core switches, both system-wide and per interface.
- The edge VRF is renamed from COMMON to EXIT, along with its route map and prefix list.
- Unused core switch ports are disabled.
- 2-4-3-200: VLANs and VNIs are renumbered (OOB 200, CPU 300, support 400, storage 500, GPU 900), and the separate BCM VLAN is removed.
- 2-8-5-200: storage bond segment IDs are renumbered.
- Refreshed exported NVUE configurations. CLI scripts are added for the OOB switches (and for core-02 on 2-8-9-400).

### sp-2-8-5-200-v2.0.0 — 2026-03-02

- An intermediate 2-8-5-200 release that adds LDAP on the dhcp-oob host and updates the topology file, diagram and core switch configurations. Superseded by sp-2-8-5-200-v3.0.0.

### sp-2-4-3-200-v1.0.0, sp-2-8-5-200-v1.0.0, sp-2-8-9-400-v1.0.0 — 2026-03-01

- First releases for 2-4-3-200, 2-8-5-200 and 2-8-9-400. Each is a set of Ansible playbooks built on the NVIDIA NVUE collection that configures:
  - the core switches;
  - the OOB switches;
  - DHCP and DNS on the OOB server;
  - LLDP;
  - server, storage and support interfaces.

  Each release also includes exported NVUE configurations, a topology file and a wiring diagram.
