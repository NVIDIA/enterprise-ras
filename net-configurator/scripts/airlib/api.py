# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Air API helper functions — NGC Air 2.0 (v3).

All functions raise AirAPIError on failure instead of calling sys.exit().
Adapted from ric-flair's v3 airlib for ERA's custom OOB architecture.

NGC v3 uses a mix of API versions:
  - v3: simulations, resource-budgets, SSH services (query)
  - v2: SSH service creation, topology export, userconfigs, ZTP
  - v1: simulation-node, simulation-interface, sshkey
"""

import json
import re
import time
from dataclasses import dataclass

import httpx

from airlib.errors import AirAPIError
from airlib.models import Node, ResourceBudget, SSHService, SimState, Simulation


# ---------------------------------------------------------------------------
# URL rewriting: NGC frontend URL → API URL
# ---------------------------------------------------------------------------

_PUBLIC_AIR_UI_HOSTS = ("air-ngc.nvidia.com", "dsx-air.nvidia.com")
_PUBLIC_AIR_API = "https://api.dsx-air.nvidia.com"


def _api(base_url: str) -> str:
    """Rewrite a web UI URL to the matching API URL.

    Air serves the web UI and API on different hostnames:

    - Air-Inside: ``ngc.<env>.nvidia.com`` → ``api.<env>.nvidia.com``
      (e.g., ``ngc.air-inside.nvidia.com`` → ``api.air-inside.nvidia.com``)
    - Public Air: ``air-ngc.nvidia.com`` or ``dsx-air.nvidia.com`` →
      ``api.dsx-air.nvidia.com`` (all public web UI hosts funnel into the
      same API hostname — this is not a mechanical rewrite)

    If ``base_url`` is already an API hostname (e.g., ``api.dsx-air.nvidia.com``),
    it is returned unchanged.
    """
    stripped = base_url.rstrip("/")
    # Public Air: explicit hostname mapping.
    for host in _PUBLIC_AIR_UI_HOSTS:
        if re.match(rf"^https?://{re.escape(host)}(/|$)", stripped):
            return _PUBLIC_AIR_API
    # Air-Inside: ngc.<env> → api.<env>.
    return re.sub(r"^(https?://)ngc\.", r"\1api.", base_url)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@dataclass
class AirSSHKey:
    """SSH key registered in user's Air account."""
    id: str
    name: str
    fingerprint: str

    @classmethod
    def from_api(cls, data: dict) -> "AirSSHKey":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            fingerprint=data.get("fingerprint", ""),
        )


@dataclass
class UserConfig:
    """User configuration (cloud-init script) in Air."""
    id: str
    name: str
    kind: str
    content: str = ""

    @classmethod
    def from_api(cls, data: dict) -> "UserConfig":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            kind=data.get("kind", ""),
            content=data.get("content", ""),
        )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _checked_json(resp: httpx.Response) -> dict | list:
    """Call raise_for_status() then parse JSON, raising AirAPIError on failure."""
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = f"\n{exc.response.json()}"
        except (ValueError, json.JSONDecodeError):
            detail = f"\n{exc.response.text[:500]}"
        raise AirAPIError(
            f"{exc.request.method} {exc.request.url} -> {exc.response.status_code}{detail}"
        ) from exc
    try:
        return resp.json()
    except ValueError as exc:
        raise AirAPIError(
            f"Non-JSON response from {resp.request.url}: {resp.text[:500]}"
        ) from exc


# ---------------------------------------------------------------------------
# Simulation CRUD (v3)
# ---------------------------------------------------------------------------

def list_simulations(
    client: httpx.Client, base_url: str, token: str,
) -> list[Simulation]:
    """GET /api/v3/simulations/ — return all simulations (paginated)."""
    url = f"{_api(base_url)}/api/v3/simulations/"
    results = []
    while url:
        resp = client.get(url, headers=_headers(token))
        data = _checked_json(resp)
        results.extend(Simulation.from_api(s) for s in data.get("results", []))
        url = data.get("next")
    return results


def resolve_simulation(
    client: httpx.Client, base_url: str, token: str, name_or_id: str,
) -> Simulation:
    """Resolve a simulation by UUID or title.

    Raises AirAPIError if no match or multiple matches by title.
    """
    sims = list_simulations(client, base_url, token)

    # UUID detection
    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
                name_or_id, re.IGNORECASE):
        match = [s for s in sims if s.id == name_or_id]
        if not match:
            raise AirAPIError(f"No simulation found with ID: {name_or_id}")
        return match[0]

    # Search by title
    matches = [s for s in sims if s.title == name_or_id]
    if not matches:
        raise AirAPIError(f"No simulation found with title: {name_or_id}")
    if len(matches) > 1:
        lines = [f"  [{s.state}] {s.title}  {s.id}" for s in matches]
        raise AirAPIError(
            f"Multiple simulations match title '{name_or_id}'. Specify by ID:\n"
            + "\n".join(lines)
        )
    return matches[0]


def find_loaded_simulation(
    client: httpx.Client, base_url: str, token: str,
) -> Simulation:
    """Auto-detect the single LOADED simulation."""
    sims = list_simulations(client, base_url, token)
    loaded = [s for s in sims if s.is_loaded]

    if not loaded:
        raise AirAPIError(
            "No running (LOADED) simulations found.\n"
            "Start a simulation first: make air-deploy ARCH=..."
        )
    if len(loaded) > 1:
        lines = [f"  {s.title}  {s.id}" for s in loaded]
        raise AirAPIError(
            "Multiple running simulations found. Specify one:\n"
            + "\n".join(lines)
        )
    return loaded[0]


# ---------------------------------------------------------------------------
# Resource budget (v3)
# ---------------------------------------------------------------------------

def get_resource_budget(
    client: httpx.Client, base_url: str, token: str,
) -> ResourceBudget:
    """GET /api/v3/resource-budgets/ — return the user's resource budget."""
    resp = client.get(f"{_api(base_url)}/api/v3/resource-budgets/", headers=_headers(token))
    data = _checked_json(resp)
    results = data.get("results", [])
    if not results:
        raise AirAPIError("No resource budget found for this account")
    return ResourceBudget.from_api(results[0])


# ---------------------------------------------------------------------------
# Topology import + simulation lifecycle
# ---------------------------------------------------------------------------

def import_topology(
    client: httpx.Client, base_url: str, token: str, topology_data: bytes,
) -> dict:
    """POST /api/v3/simulations/import/ with topology JSON."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = client.post(
        f"{_api(base_url)}/api/v3/simulations/import/",
        headers=headers,
        content=topology_data,
        timeout=120,
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = f"\n{exc.response.json()}"
        except (ValueError, json.JSONDecodeError):
            detail = f"\n{exc.response.text[:500]}"
        raise AirAPIError(
            f"Import failed: {exc.response.status_code}{detail}"
        ) from exc
    result = resp.json()
    if not result.get("id"):
        raise AirAPIError(f"Import returned no simulation ID: {result}")
    return result


def wait_for_inactive(
    client: httpx.Client, base_url: str, token: str, sim_id: str,
    *, max_wait: int = 120,
) -> str:
    """Wait for the simulation to reach INACTIVE state after import.

    After import_topology(), the simulation transitions through CREATING →
    IMPORTING → INACTIVE.  Nodes are only queryable once INACTIVE is reached.
    Returns the final raw state string.
    """
    raw_state = "unknown"
    for _ in range(max_wait // 3):
        data = get_simulation_detail(client, base_url, token, sim_id)
        raw_state = data.get("state", "").upper()
        if raw_state in ("INACTIVE", "ACTIVE", "INVALID"):
            return raw_state
        time.sleep(3)
    return raw_state


def start_simulation(
    client: httpx.Client, base_url: str, token: str, sim_id: str,
    *, max_wait: int = 60,
) -> None:
    """PATCH /api/v3/simulations/{id}/start/ to start the simulation.

    Caller should ensure the simulation is INACTIVE first (via
    wait_for_inactive).  NGC v3 requires a JSON body for PATCH requests.
    """
    api = _api(base_url)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Safety wait — in case caller didn't wait explicitly
    wait_for_inactive(client, base_url, token, sim_id, max_wait=max_wait)

    resp = client.patch(
        f"{api}/api/v3/simulations/{sim_id}/start/",
        headers=headers,
        json={},
        timeout=60,
    )
    _checked_json(resp)


def stop_simulation(
    client: httpx.Client, base_url: str, token: str, sim_id: str,
) -> None:
    """PATCH /api/v3/simulations/{id}/shutdown/ to stop the simulation."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = client.patch(
        f"{_api(base_url)}/api/v3/simulations/{sim_id}/shutdown/",
        headers=headers,
        json={},
        timeout=60,
    )
    _checked_json(resp)


def delete_simulation(
    client: httpx.Client, base_url: str, token: str, sim_id: str,
) -> None:
    """DELETE /api/v3/simulations/{id}/ — works in any state (no store needed)."""
    resp = client.delete(
        f"{_api(base_url)}/api/v3/simulations/{sim_id}/",
        headers=_headers(token),
        timeout=60,
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AirAPIError(
            f"Failed to delete simulation {sim_id}: {exc.response.status_code}"
        ) from exc


def list_userconfigs(
    client: httpx.Client, base_url: str, token: str,
) -> list[UserConfig]:
    """GET /api/v3/userconfigs/ — return all user configurations (paginated)."""
    url = f"{_api(base_url)}/api/v3/userconfigs/"
    results = []
    while url:
        resp = client.get(url, headers=_headers(token))
        data = _checked_json(resp)
        results.extend(UserConfig.from_api(c) for c in data.get("results", []))
        url = data.get("next")
    return results


def delete_userconfig(
    client: httpx.Client, base_url: str, token: str, config_id: str,
) -> None:
    """DELETE /api/v3/userconfigs/{id}/."""
    resp = client.delete(
        f"{_api(base_url)}/api/v3/userconfigs/{config_id}/",
        headers=_headers(token),
        timeout=60,
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AirAPIError(
            f"Failed to delete userconfig {config_id}: {exc.response.status_code}"
        ) from exc


def get_simulation_detail(
    client: httpx.Client, base_url: str, token: str, sim_id: str,
) -> dict:
    """GET /api/v3/simulations/{id}/ and return the full response dict."""
    resp = client.get(
        f"{_api(base_url)}/api/v3/simulations/{sim_id}/",
        headers=_headers(token),
    )
    return _checked_json(resp)


def get_simulation_state(
    client: httpx.Client, base_url: str, token: str, sim_id: str,
) -> str:
    """GET /api/v3/simulations/{id}/ and return the mapped state string."""
    data = get_simulation_detail(client, base_url, token, sim_id)
    return Simulation.from_api(data).state


def check_node_errors(
    client: httpx.Client, base_url: str, token: str, sim_id: str,
) -> str | None:
    """Check if any nodes have error status messages.

    NGC Air reports platform errors (capacity, provisioning failures) in the
    node-level status_from_worker field. Returns the first error found, or None.
    """
    try:
        url = f"{_api(base_url)}/api/v3/simulations/nodes/?simulation={sim_id}&limit=100"
        resp = client.get(url, headers=_headers(token))
        data = _checked_json(resp)
        for node in data.get("results", []):
            status = node.get("status_from_worker", "")
            state = node.get("state", "")
            if state == "ERROR" or (status and "error" in status.lower()):
                return f"{node.get('name', '?')}: {status or state}"
    except AirAPIError:
        pass
    return None


def poll_until_loaded(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    *,
    max_polls: int = 60,
    interval: int = 10,
    status_callback=None,
    error_callback=None,
) -> str:
    """Poll simulation state until LOADED. Returns final state.

    NGC v3 state flow: INACTIVE(STORED) -> REQUESTING(NEW) -> PROVISIONING(NEW)
    -> BOOTING(LOADING) -> ACTIVE(LOADED). We wait through all transitional states.

    Periodically checks node-level errors for early detection of platform
    issues (capacity, provisioning failures).

    Args:
        status_callback: Optional callable(state, elapsed_seconds) for progress.
        error_callback: Optional callable(error_message) when node error detected.
    """
    # States that mean "still starting up, keep waiting"
    _WAIT_STATES = {
        SimState.NEW,       # REQUESTING, PROVISIONING, CREATING, IMPORTING
        SimState.LOADING,   # PREPARE_BOOT, BOOTING, PREPARE_REBUILD, REBUILDING
        SimState.STORED,    # INACTIVE — initial state before start takes effect
        SimState.STORING,   # SHUTTING_DOWN, SAVING — transitional
        "",                 # Unknown / transient error
    }
    state = ""
    start_time = time.time()
    for i in range(max_polls):
        try:
            data = get_simulation_detail(client, base_url, token, sim_id)
            sim = Simulation.from_api(data)
            state = sim.state
            raw_state = data.get("state", "")
        except AirAPIError:
            state = ""
            raw_state = ""

        if status_callback:
            # Show the raw NGC state for more detail
            display = f"{state} ({raw_state})" if raw_state and raw_state != state else state
            status_callback(display, int(time.time() - start_time))

        if state == SimState.LOADED:
            return state

        if state not in _WAIT_STATES:
            # Check nodes for specific error messages
            node_error = check_node_errors(client, base_url, token, sim_id)
            if node_error and error_callback:
                error_callback(node_error)
            return state  # ERROR or DELETED — stop waiting

        # Periodically check for node-level errors (every 30s)
        if i > 0 and i % 3 == 0:
            node_error = check_node_errors(client, base_url, token, sim_id)
            if node_error:
                if error_callback:
                    error_callback(node_error)
                return "ERROR"

        time.sleep(interval)

    return state


# ---------------------------------------------------------------------------
# SSH service management (generalized for ERA's custom OOB)
# ---------------------------------------------------------------------------

def get_ssh_services(
    client: httpx.Client, base_url: str, token: str, sim_id: str,
) -> list[SSHService]:
    """Find all SSH services for a simulation (v3 endpoint)."""
    resp = client.get(
        f"{_api(base_url)}/api/v3/simulations/nodes/interfaces/services/",
        params={"simulation": sim_id},
        headers=_headers(token),
    )
    data = _checked_json(resp)
    services = data.get("results", data) if isinstance(data, dict) else data
    return [SSHService.from_api(s) for s in services
            if s.get("node_port", s.get("dest_port")) == 22]


def create_ssh_service_for_node(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    node_name: str,
) -> SSHService:
    """Create an SSH service on a specific node by name.

    Uses v3 endpoints. SSH services can only be added to outbound (unlinked)
    interfaces — typically eth0 which has external connectivity in ERA topologies.
    ERA needs SSH services on oob-server-01 and dhcp-oob.
    """
    headers = _headers(token)
    api = _api(base_url)

    # Find the target node (v3, paginated)
    node_id = None
    url = f"{api}/api/v3/simulations/nodes/?simulation={sim_id}&limit=100"
    all_node_names = []
    while url:
        resp = client.get(url, headers=headers)
        data = _checked_json(resp)
        for n in data.get("results", []):
            all_node_names.append(n.get("name", ""))
            if n.get("name") == node_name:
                node_id = n["id"]
        if node_id:
            break
        url = data.get("next")

    if not node_id:
        raise AirAPIError(
            f"Node '{node_name}' not found in simulation.\n"
            f"Available nodes: {', '.join(sorted(all_node_names))}"
        )

    # Find the node's outbound interface (unlinked, external connectivity)
    # SSH services can only be added to unlinked interfaces.
    iface_id = None
    url = f"{api}/api/v3/simulations/nodes/interfaces/?node={node_id}&limit=50"
    while url:
        resp = client.get(url, headers=headers)
        data = _checked_json(resp)
        for i in data.get("results", []):
            if i.get("outbound") or not i.get("connection"):
                iface_id = i["id"]
                break
        if iface_id:
            break
        url = data.get("next")

    if not iface_id:
        raise AirAPIError(
            f"No outbound interface found for node '{node_name}'.\n"
            "SSH services require an unlinked/outbound interface (typically eth0)."
        )

    # Create SSH service (v3)
    headers_json = {**headers, "Content-Type": "application/json"}
    resp = client.post(
        f"{api}/api/v3/simulations/nodes/interfaces/services/",
        headers=headers_json,
        json={"name": "SSH", "interface": iface_id, "node_port": 22},
    )
    return SSHService.from_api(_checked_json(resp))


def create_service_for_node(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    node_name: str,
    service_name: str = "SSH",
    node_port: int = 22,
) -> SSHService:
    """Create an arbitrary service on a node's outbound interface.

    Works identically to create_ssh_service_for_node but allows
    specifying the service name and port (e.g., HTTP on port 80).
    Returns an SSHService dataclass (reused for host/port info).
    """
    headers = _headers(token)
    api = _api(base_url)

    # Find the target node
    node_id = None
    url = f"{api}/api/v3/simulations/nodes/?simulation={sim_id}&limit=100"
    while url:
        resp = client.get(url, headers=headers)
        data = _checked_json(resp)
        for n in data.get("results", []):
            if n.get("name") == node_name:
                node_id = n["id"]
        if node_id:
            break
        url = data.get("next")

    if not node_id:
        raise AirAPIError(f"Node '{node_name}' not found in simulation.")

    # Find outbound interface
    iface_id = None
    url = f"{api}/api/v3/simulations/nodes/interfaces/?node={node_id}&limit=50"
    while url:
        resp = client.get(url, headers=headers)
        data = _checked_json(resp)
        for i in data.get("results", []):
            if i.get("outbound") or not i.get("connection"):
                iface_id = i["id"]
                break
        if iface_id:
            break
        url = data.get("next")

    if not iface_id:
        raise AirAPIError(
            f"No outbound interface found for node '{node_name}'."
        )

    # Create service
    headers_json = {**headers, "Content-Type": "application/json"}
    resp = client.post(
        f"{api}/api/v3/simulations/nodes/interfaces/services/",
        headers=headers_json,
        json={"name": service_name, "interface": iface_id, "node_port": node_port},
    )
    return SSHService.from_api(_checked_json(resp))


def get_or_create_ssh_service_for_node(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    node_name: str,
) -> SSHService:
    """Find existing SSH service for a node, or create one."""
    return create_ssh_service_for_node(client, base_url, token, sim_id, node_name)


# ---------------------------------------------------------------------------
# Node listing (v1 — still used by NGC v3)
# ---------------------------------------------------------------------------

def list_simulation_nodes(
    client: httpx.Client, base_url: str, token: str, sim_id: str,
) -> list[dict]:
    """List all nodes in a simulation (v3, paginated)."""
    all_nodes = []
    url = f"{_api(base_url)}/api/v3/simulations/nodes/?simulation={sim_id}&limit=100"
    while url:
        resp = client.get(url, headers=_headers(token))
        data = _checked_json(resp)
        all_nodes.extend(data.get("results", []))
        url = data.get("next")
    return all_nodes


# ---------------------------------------------------------------------------
# Node Instructions (v3) — pre-boot configuration
# ---------------------------------------------------------------------------

def _find_node_id(
    client: httpx.Client, base_url: str, token: str,
    sim_id: str, node_name: str,
) -> str:
    """Find a node's ID by name in a simulation. Raises AirAPIError if not found."""
    url = f"{_api(base_url)}/api/v3/simulations/nodes/?simulation={sim_id}&limit=100"
    all_names: list[str] = []
    while url:
        data = _checked_json(client.get(url, headers=_headers(token)))
        for n in data.get("results", []):
            all_names.append(n.get("name", ""))
            if n.get("name") == node_name:
                return n["id"]
        url = data.get("next")
    raise AirAPIError(
        f"Node '{node_name}' not found in simulation.\n"
        f"Available: {', '.join(sorted(all_names))}"
    )


def create_node_instruction(
    client: httpx.Client,
    base_url: str,
    token: str,
    sim_id: str,
    node_name: str,
    commands: list[str],
    *,
    name: str = "",
    wait_for_network: bool = False,
) -> dict:
    """Create a shell Node Instruction on a node (must be called before start).

    The Air agent executes the commands after the node boots.  For switches
    like air-oob-switch this configures the bridge before other nodes need it.

    Args:
        commands: List of shell command strings (joined with newlines).
        name: Human-readable instruction label.
        wait_for_network: Wait for network reachability before executing.
    """
    api = _api(base_url)
    headers = {**_headers(token), "Content-Type": "application/json"}

    node_id = _find_node_id(client, base_url, token, sim_id, node_name)

    # Air Node Instructions accept data as a string for shell executor
    script = "#!/bin/bash\n" + "\n".join(commands)

    body: dict = {
        "node": node_id,
        "executor": "shell",
        "data": script,
        "wait_for_network": wait_for_network,
    }
    if name:
        body["name"] = name

    # Try v3 flat endpoint first, fall back to v1 nested endpoint
    url_v3 = f"{api}/api/v3/simulations/nodes/instructions/"
    url_v1 = f"{api}/api/v1/simulation-node/{node_id}/instructions/"

    for url in (url_v3, url_v1):
        resp = client.post(url, headers=headers, json=body)
        if resp.status_code != 404:
            return _checked_json(resp)

    # Both failed with 404 — raise with details
    raise AirAPIError(
        f"Node Instructions endpoint not found. Tried:\n"
        f"  POST {url_v3}\n"
        f"  POST {url_v1}\n"
        f"Check Air API docs for the correct endpoint."
    )


