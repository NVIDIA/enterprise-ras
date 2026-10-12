# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""`ARCH` / `SITE` guards read the raw value and never expand it (GitLab #103, F6).

A command-line or environment variable is recursively expanded in make. A guard
that expands `$(ARCH)` to check it runs any `$(shell …)` inside the value while
checking, and a `$(eval)` residue loop expands `${…}` references a second time.
Each payload here creates a marker file if any part of it is ever executed.
"""
import os
import subprocess
from pathlib import Path

import pytest

NC = Path(__file__).resolve().parent.parent


def _payloads(marker):
    return {
        "make function": f"x$(shell touch {marker})",
        "make function, no space": f"2-8-5-200$(shell${{IFS}}touch${{IFS}}{marker})",
        "brace ref through the eval loop": f"x${{';touch${{IFS}}{marker};'}}",
        "info function": "x$(info LEAKED-BY-EXPANSION)",
    }


CASES = [(var, how, name)
         for var in ("ARCH", "SITE")
         for how in ("command line", "lower-case alias", "environment")
         for name in _payloads("M")]


def _make(var, how, value):
    env = {k: v for k, v in os.environ.items() if k not in ("ARCH", "SITE")}
    args = ["make", "-n", "help"]
    if var == "SITE":
        args.append("ARCH=2-8-5-200")
    if how == "command line":
        args.append(f"{var}={value}")
    elif how == "lower-case alias":
        args.append(f"{var.lower()}={value}")
    else:
        env[var] = value
    p = subprocess.run(args, cwd=str(NC), capture_output=True, text=True, env=env, timeout=60)
    return p.returncode, p.stdout + p.stderr


@pytest.mark.parametrize("var,how,name", CASES, ids=lambda x: str(x).replace(" ", "-"))
def test_payload_is_refused_as_text_and_never_runs(tmp_path, var, how, name):
    marker = tmp_path / "pwned"
    value = _payloads(marker)[name]
    rc, out = _make(var, how, value)
    assert not marker.exists(), f"{var} via {how} executed {value!r}:\n{out[:400]}"
    assert not any(line.strip() == "LEAKED-BY-EXPANSION" for line in out.splitlines()), (
        f"{var} via {how} was expanded:\n{out[:400]}")
    assert rc != 0, f"make accepted {var}={value!r}"
    assert f"Invalid {var}" in out, out[:400]
    assert "'$' is not allowed" in out, out[:400]


@pytest.mark.parametrize("var,value", [("ARCH", "2-8-9-400-sp"), ("SITE", "my.site")])
def test_ordinary_names_still_work(var, value):
    rc, out = _make(var, "command line", value)
    assert rc == 0, out[:400]
    assert f"Invalid {var}" not in out
