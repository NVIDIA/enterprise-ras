#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
Classify `show bgp vrf all summary json` for an OOB switch (design C1).

On an OOB switch in L3 mode every BGP neighbor is a required CSL-facing uplink
(unnumbered underlay + numbered overlay to CSL loopbacks), so "all neighbors
Established" == "OOB↔CSL BGP healthy". Unlike scripts/switch_health_probe.sh
this has **no carrier-down suppression**: a down `swpN` peer is always a FAIL —
that suppression is what let switch-health false-pass a copper-miscabled OOB
uplink (observed live). Only `NoNeg` (address-family not negotiated for a peer that
is otherwise up) is skipped, since it is not a down session.

Reads the JSON from stdin; prints one `OOB_BGP|PASS|...` / `OOB_BGP|FAIL|...`
line. Exit code mirrors the verdict (0 PASS, 1 FAIL) so a caller can gate.

Zero shared code with switch_health_probe.sh (intentional isolation).
"""
import json
import sys


def classify(data: dict) -> tuple[bool, str]:
    """Return (fail, line). ``fail`` True means at least one neighbor is down."""
    total = 0
    up = 0
    down = []
    for vrf, vd in (data or {}).items():
        if not isinstance(vd, dict):
            continue
        for af, afd in vd.items():
            if not isinstance(afd, dict):
                continue
            for nbr, p in (afd.get("peers") or {}).items():
                if not isinstance(p, dict):
                    continue
                st = str(p.get("state", "") or "?")
                # AF not negotiated for this peer — up session, different AF.
                if st == "NoNeg":
                    continue
                total += 1
                if st == "Established":
                    up += 1
                else:
                    down.append("%s/%s/%s=%s" % (vrf, af, nbr, st))
    if total == 0:
        return True, "OOB_BGP|FAIL|no BGP neighbors found"
    if down:
        return True, "OOB_BGP|FAIL|established=%d/%d down=%s" % (up, total, ",".join(down[:8]))
    return False, "OOB_BGP|PASS|neighbors=%d established=%d" % (total, up)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        print("OOB_BGP|FAIL|cannot parse 'show bgp vrf all summary json': %s" % e)
        return 1
    fail, line = classify(data)
    print(line)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
