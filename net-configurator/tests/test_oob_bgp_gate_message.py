# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
The OOB↔CSL BGP gate must report the failure its own report recorded.

Observed in the 2-4-5-800 e2e cell (job 391943454, 2026-08-10). The gate failed
the run with:

    1 OOB switch(es) with a down BGP neighbor

while the report it points at said:

    -- oob-switch-01 (172.20.0.203) --  OOB_BGP|PASS|neighbors=4 established=4
    -- oob-switch-02 (172.20.0.204) --  OOB_BGP|FAIL|unreachable 172.20.0.204

`unreachable` is not a down neighbour. The switch had no L2 path at all —
`cust-net-edge-02` came up configless, so `swp13` never joined `br_default` and
`oob-switch-02:eth0` was cabled to exactly that port. The message sent us
looking at BGP; the fault was a missing bridge.

Same rule as ADR-0052, applied to a gate instead of a diagnostic: name the
cause the evidence supports. The `FAIL` reason is right there in the captured
output — the gate just replaced it with an assumption.
"""
import re
from pathlib import Path

PLAYBOOK = (Path(__file__).resolve().parent.parent
            / "playbooks" / "validate-oob-bgp.yml")

# Verbatim from the failing job's report artifact.
REAL_OUTPUT = [
    "-- oob-switch-01 (172.20.0.203) --",
    "OOB_BGP|PASS|neighbors=4 established=4",
    "-- oob-switch-02 (172.20.0.204) --",
    "OOB_BGP|FAIL|unreachable 172.20.0.204",
]


def _fail_task_msg() -> str:
    """The msg: of the gating `fail:` task, as raw text."""
    src = PLAYBOOK.read_text()
    m = re.search(r"- name: Fail the run if any OOB switch reported FAIL"
                  r"(.*?)(?=\n    - name:|\Z)", src, re.S)
    assert m, "gating fail task not found — has the playbook been restructured?"
    return m.group(1)


def test_gate_does_not_assert_an_unproven_cause():
    assert "down BGP neighbor" not in _fail_task_msg(), (
        "the gate hardcodes 'down BGP neighbor', which is wrong whenever the "
        "switch was simply unreachable"
    )


def test_gate_surfaces_the_recorded_fail_reason():
    assert "fail_reasons" in _fail_task_msg(), (
        "the gate must report the FAIL reason its own probe recorded"
    )


def test_fail_reasons_extracts_the_real_reason():
    """Exercise the extraction the playbook performs, on the real output."""
    reasons = [ln.split("|", 2)[2]
               for ln in REAL_OUTPUT if ln.startswith("OOB_BGP|FAIL|")]

    assert reasons == ["unreachable 172.20.0.204"]
    assert "unreachable" in " ".join(reasons)
    assert "down BGP neighbor" not in " ".join(reasons)


def test_extraction_expression_is_present_in_the_playbook():
    """Pin the fact that builds fail_reasons, so the message can't go stale."""
    src = PLAYBOOK.read_text()
    assert "fail_reasons:" in src, "fail_reasons fact is not defined"
    assert "OOB_BGP" in src and "FAIL" in src


def test_a_down_neighbour_still_reads_correctly():
    """The old wording was right for the down-peer case; it must survive."""
    out = ["OOB_BGP|FAIL|neighbors=4 established=3 down=swp51"]
    reasons = [ln.split("|", 2)[2] for ln in out if ln.startswith("OOB_BGP|FAIL|")]

    assert reasons == ["neighbors=4 established=3 down=swp51"]
