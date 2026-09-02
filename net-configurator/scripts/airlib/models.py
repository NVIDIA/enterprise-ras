# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""Typed data models for Air API objects — NGC Air 2.0 (v3)."""

from __future__ import annotations

from dataclasses import dataclass


class SimState:
    """The state vocabulary this codebase uses internally.

    Deliberately not NGC's own spelling: these names predate the v3 API here
    and are what the scripts, playbooks and logs read in terms of, so the
    translation happens once at the boundary (see _NGC_STATE_MAP) instead of
    leaking a vendor rename through the whole tool.
    """
    NEW = "NEW"
    LOADING = "LOADING"
    LOADED = "LOADED"
    STORING = "STORING"
    STORED = "STORED"


# The boundary translation. NGC v3 reports a finer-grained set of states than
# this tool distinguishes — several map onto one of ours (four flavours of
# 'still coming up' are all LOADING). Unknown states fall through unchanged
# rather than defaulting, so a new NGC state shows up in output as itself
# instead of being silently mislabelled as a state we understand.
_NGC_STATE_MAP = {
    "CREATING": "NEW", "IMPORTING": "NEW", "REQUESTING": "NEW", "PROVISIONING": "NEW",
    "PREPARE_BOOT": "LOADING", "BOOTING": "LOADING", "PREPARE_REBUILD": "LOADING", "REBUILDING": "LOADING",
    "ACTIVE": "LOADED",
    "PREPARE_SHUTDOWN": "STORING", "SHUTTING_DOWN": "STORING", "SAVING": "STORING",
    "INACTIVE": "STORED",
    "ERROR": "ERROR", "INVALID": "ERROR",
    "DELETING": "DELETED", "PREPARE_PURGE": "DELETED", "PURGING": "DELETED",
}


@dataclass
class Simulation:
    id: str
    title: str
    state: str
    owner: str = ""

    @classmethod
    def from_api(cls, data: dict) -> Simulation:
        raw_state = data.get("state", "")
        state = _NGC_STATE_MAP.get(raw_state.upper(), raw_state)
        owner = data.get("creator", "") or data.get("owner", "")
        if isinstance(owner, dict):
            owner = owner.get("username", "") or owner.get("email", "")
        return cls(
            id=data.get("id", ""),
            title=data.get("name") or data.get("title", ""),  # v3 uses "name"
            state=state,
            owner=str(owner),
        )

    @property
    def is_loaded(self) -> bool:
        return self.state == SimState.LOADED


@dataclass
class SSHService:
    host: str
    src_port: str | int
    dest_port: int

    @classmethod
    def from_api(cls, data: dict) -> SSHService:
        # NGC v3 uses worker_fqdn/worker_port/node_port; legacy uses host/src_port/dest_port
        return cls(
            host=data.get("worker_fqdn", data.get("host", "")),
            src_port=data.get("worker_port", data.get("src_port", "")),
            dest_port=data.get("node_port", data.get("dest_port", 22)),
        )

    @property
    def is_ready(self) -> bool:
        return bool(self.host) and self.host != "null"


@dataclass
class ResourceBudget:
    """Resource budget for the user's Air account."""
    id: str
    cpu: int
    cpu_used: int
    memory: int  # MB
    memory_used: int
    storage: int  # GB
    storage_used: int
    simulations: int
    simulations_used: int
    userconfigs: int  # bytes - total budget
    userconfigs_used: int  # bytes - already consumed
    image_uploads: int
    image_uploads_used: int

    @classmethod
    def from_api(cls, data: dict) -> ResourceBudget:
        # NGC v3 nests current usage under "usage" key
        usage = data.get("usage", {})
        return cls(
            id=data.get("id", ""),
            cpu=data.get("cpu", 0),
            cpu_used=usage.get("cpu", data.get("cpu_used", 0)),
            memory=data.get("memory", 0),
            memory_used=usage.get("memory", data.get("memory_used", 0)),
            storage=data.get("disk_storage", data.get("storage", 0)),
            storage_used=usage.get("disk_storage", data.get("storage_used", 0)),
            simulations=data.get("simulations", 0),
            simulations_used=usage.get("simulations", data.get("simulations_used", 0)),
            userconfigs=data.get("userconfigs", 0),
            userconfigs_used=usage.get("userconfigs", data.get("userconfigs_used", 0)),
            image_uploads=data.get("image_uploads", 0),
            image_uploads_used=usage.get("image_uploads", data.get("image_uploads_used", 0)),
        )

    @property
    def userconfigs_available(self) -> int:
        return self.userconfigs - self.userconfigs_used


@dataclass
class Node:
    name: str
    ip: str
    os: str

    @classmethod
    def from_dict(cls, data: dict) -> Node:
        return cls(
            name=data.get("name", ""),
            ip=data.get("ip", ""),
            os=data.get("os", ""),
        )
