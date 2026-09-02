#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Switch operational-health probe (Tier 1) — READ ONLY.
#
# Runs ON a Cumulus Linux switch. Intended to be streamed over SSH:
#     sshpass -e ssh ... cumulus@<switch> "bash -s -- '<sudo_pw>'" < switch_health_probe.sh
#
# Emits one line per check to stdout:
#     CHECK|<name>|<PASS|FAIL|WARN|INFO>|<detail>
#
# It changes nothing on the switch. FRR/NVUE commands need root, so the sudo
# password is passed as $1 and used via `sudo -S`. This probe is the standalone,
# not-yet-wired-into-validate-all Tier-1 check set:
#   apply       — config applied cleanly (no pending diff) + core daemons up
#   bgp         — every configured BGP neighbor (all VRFs/AFs) is Established
#   evpn_es     — EVPN Ethernet Segments instantiated, no duplicate ESI
#   evpn_vni    — EVPN VNIs present
#   intf        — proto_down / oper-state inventory (informational here:
#                 server-edge MH bonds are legitimately down in switches-only)

PW="${1:-}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

# Capture the running config once (commands form) — reused by evpn_es/evpn_vni
# to derive per-switch expectations (MH segments configured, VTEP or not).
CFG=/tmp/_sh_cfg.txt
S nv config show -o commands > "$CFG" 2>/dev/null

# ---- apply: no pending config diff + core daemons active --------------------
diff_out="$(S nv config diff 2>/dev/null)"
daemons_bad=""
for d in nvued frr switchd; do
  systemctl is-active --quiet "$d" 2>/dev/null || daemons_bad="$daemons_bad $d"
done
# Strip the benign 'cumulus user hashed-password: *' pseudo-diff — a perennial
# Cumulus nv-config-diff artifact (the managed/locked-password representation)
# that never clears and is NOT a real pending change. Only its exact key path is
# removed, so any real pending config still counts.
diff_real="$(printf '%s\n' "$diff_out" | grep -vE "^- set:[[:space:]]*$|^[[:space:]]+(system|aaa|user|cumulus):[[:space:]]*$|^[[:space:]]+hashed-password:")"
# grep -c prints "0" and exits 1 on zero matches; capturing its stdout is enough
# (a trailing `|| echo 0` would append a SECOND 0 and break the == "0" test).
diff_lines=$(printf '%s' "$diff_real" | grep -c . 2>/dev/null); diff_lines=${diff_lines:-0}
if [ "$diff_lines" = "0" ] && [ -z "$daemons_bad" ]; then
  echo "CHECK|apply|PASS|nv config diff empty; nvued/frr/switchd active"
else
  det="pending_diff_lines=$diff_lines"
  [ -n "$daemons_bad" ] && det="$det; inactive:$daemons_bad"
  echo "CHECK|apply|FAIL|$det"
fi

# ---- bgp: all neighbors Established across every VRF/AF ----------------------
S vtysh -c 'show bgp vrf all summary json' > /tmp/_sh_bgp.json 2>/dev/null
python3 - <<'PY'
import json, os
def _link_up(nbr):
    # Unnumbered BGP peer name == its interface. A down peer whose interface is
    # missing or carrier-down has no cabled peer (spare uplink / uninstantiated
    # breakout sub-port) -> not a failure, just nothing on the other end.
    try:
        with open('/sys/class/net/%s/carrier' % nbr) as f:
            return f.read().strip() == '1'
    except Exception:
        return False
try:
    d = json.load(open('/tmp/_sh_bgp.json'))
except Exception as e:
    print("CHECK|bgp|FAIL|cannot parse 'show bgp vrf all summary json': %s" % e)
    raise SystemExit
total = 0; up = 0; down = []; storage_down = []
# {vrfName: {ipv4Unicast:{peers:{nbr:{state}}}, l2VpnEvpn:{peers:{...}}, ...}}
for vrf, vd in (d or {}).items():
    if not isinstance(vd, dict):
        continue
    for af, afd in vd.items():
        if not isinstance(afd, dict):
            continue
        for nbr, p in (afd.get('peers') or {}).items():
            if not isinstance(p, dict):
                continue
            st = str(p.get('state', '') or '?')
            # 'NoNeg' = the BGP session is UP but this address-family was not
            # negotiated for this peer — e.g. l2vpn-evpn left enabled on an ISL
            # underlay peer-group while EVPN actually rides the loopback
            # 'overlay' peer-group (the dedicated cl/cs design). It is
            # NOT a down session, so it must not count as a failure (nor inflate
            # the total).
            if st == 'NoNeg':
                continue
            if st == 'Established':
                total += 1; up += 1
                continue
            # STORAGE-VRF external peers (the ext-storage aggregate) are
            # NON-GATING (design C2): a down one is surfaced as a separate WARN
            # pointing at the fix, never a FAIL, and is not counted toward the
            # gating total/down list. All other VRFs keep the behavior below.
            if str(vrf) == 'STORAGE':
                storage_down.append("%s/%s/%s=%s" % (vrf, af, nbr, st))
                continue
            # Down (Idle/Active/Connect/...): an unnumbered peer on a missing or
            # carrier-down interface is a spare/uncabled uplink (no peer on the
            # other end) -> benign, skip. A down numbered peer, or a down peer
            # whose link is UP, is a real failure.
            if str(nbr).startswith('swp') and not _link_up(nbr):
                continue
            total += 1
            down.append("%s/%s/%s=%s" % (vrf, af, nbr, st))
if total == 0:
    print("CHECK|bgp|FAIL|no BGP neighbors found")
elif not down:
    print("CHECK|bgp|PASS|neighbors=%d established=%d" % (total, up))
else:
    print("CHECK|bgp|FAIL|established=%d/%d down=%s" % (up, total, ",".join(down[:8])))
# Non-gating STORAGE WARN (design C2) — emitted independently of the bgp
# PASS/FAIL above so the operator sees the ext-storage-FRR-down case and the fix.
if storage_down:
    print("CHECK|bgp_storage|WARN|%s; external storage eBGP down — run 'make fix-ext-storage'"
          % ",".join(storage_down[:8]))
PY

# ---- evpn_es: Ethernet Segments instantiated, no duplicate ESI --------------
# Expected local ES = the number of EVPN-MH segments configured on THIS switch.
# That is 0 on spines / GPU-fabric / OOB switches (no server multihoming bonds),
# where 0 instantiated ES is correct — so derive the expectation from the
# switch's own config instead of warning everywhere.
exp_es=$(grep -cE 'evpn multihoming segment local-id' "$CFG" 2>/dev/null); exp_es=${exp_es:-0}
S vtysh -c 'show evpn es json' > /tmp/_sh_es.json 2>/dev/null
EXP_ES="$exp_es" python3 - <<'PY'
import json, os
exp = int(os.environ.get('EXP_ES', '0') or 0)
try:
    d = json.load(open('/tmp/_sh_es.json'))
except Exception:
    print("CHECK|evpn_es|%s|cannot read 'show evpn es json' (%d configured)"
          % ("FAIL" if exp > 0 else "PASS", exp))
    raise SystemExit
items = list(d.values()) if isinstance(d, dict) else (d or [])
esis = [e.get('esi') for e in items if isinstance(e, dict) and e.get('esi')]
n = len(esis); dup = n - len(set(esis))
if dup > 0:
    print("CHECK|evpn_es|FAIL|es=%d duplicate_esi=%d (FRR rejects dup ESI -> protodown)" % (n, dup))
elif exp == 0:
    print("CHECK|evpn_es|PASS|no MH segments configured (es=%d)" % n)
elif n == 0:
    print("CHECK|evpn_es|FAIL|0 Ethernet Segments but %d configured (FRR reject / not instantiated)" % exp)
elif n < exp:
    print("CHECK|evpn_es|FAIL|es=%d < %d configured (missing segments)" % (n, exp))
else:
    print("CHECK|evpn_es|PASS|es=%d dup=0 (>=%d configured)" % (n, exp))
PY

# ---- evpn_vni: VNIs present (only on VTEPs; spines/underlay have none) -------
# A VTEP has 'nve vxlan source address' configured; spines (cs/gs) do not, so
# 0 VNIs is correct there — derive the expectation rather than warn everywhere.
is_vtep=$(grep -cE 'nve vxlan source address' "$CFG" 2>/dev/null); is_vtep=${is_vtep:-0}
S vtysh -c 'show evpn vni json' > /tmp/_sh_vni.json 2>/dev/null
IS_VTEP="$is_vtep" python3 - <<'PY'
import json, os
vtep = (int(os.environ.get('IS_VTEP', '0') or 0) > 0)
try:
    d = json.load(open('/tmp/_sh_vni.json'))
except Exception:
    print("CHECK|evpn_vni|%s|cannot read 'show evpn vni json'" % ("FAIL" if vtep else "PASS"))
    raise SystemExit
if isinstance(d, dict):
    vnis = [k for k in d if str(k).isdigit()]
else:
    vnis = [x for x in (d or []) if isinstance(x, dict) and x.get('vni')]
n = len(vnis)
if n > 0:
    print("CHECK|evpn_vni|PASS|vni_count=%d" % n)
elif not vtep:
    print("CHECK|evpn_vni|PASS|not a VTEP (no VNIs expected)")
else:
    print("CHECK|evpn_vni|FAIL|VTEP has 0 VNIs")
PY

# ---- intf: proto_down + oper-state inventory (informational) ----------------
pd=""; upc=0; downc=0
for dir in /sys/class/net/swp*; do
  [ -e "$dir/proto_down" ] || continue
  i=$(basename "$dir")
  [ "$(cat "$dir/proto_down" 2>/dev/null)" = "1" ] && pd="$pd $i"
  if [ "$(cat "$dir/operstate" 2>/dev/null)" = "up" ]; then upc=$((upc+1)); else downc=$((downc+1)); fi
done
if [ -n "$pd" ]; then
  echo "CHECK|intf|INFO|swp up=$upc down=$downc; proto_down:$pd (server-edge MH bonds expected down in switches-only)"
else
  echo "CHECK|intf|INFO|swp up=$upc down=$downc; no proto_down"
fi
