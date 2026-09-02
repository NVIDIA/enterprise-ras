# net-configurator — Public Changelog

## nc-v7.0.0

### New: Architecture support

- Added support for 2-4-5-400 — a depopulated variant of 2-8-5-200 (2 CPU / 4 GPU / 5 NIC / 400 Gbps, same fabric, half the GPU count and half the external uplink capacity).
- Every supported architecture now ships an additional largescale reference example (input workbook + generated output), alongside the existing default example.

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
