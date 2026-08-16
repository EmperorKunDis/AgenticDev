#!/usr/bin/env bash
# Destructive acceptance test for a CLEAN, ISOLATED, disposable VPS only.
set -uo pipefail
P=0 F=0 S=0
STRICT=${AGENTICDEV_ACCEPTANCE_REQUIRE_COMPLETE:-YES}
pass(){ echo "PASS $1${2:+ — $2}"; P=$((P+1)); }
fail(){ echo "FAIL $1${2:+ — $2}"; F=$((F+1)); }
skip(){ echo "SKIP $1 — $2"; S=$((S+1)); }
need_root(){ [[ $EUID -eq 0 ]] || { echo 'FAIL harness — run as root on a disposable VPS'; exit 2; }; }
check_no_group(){ local u=$1 g=$2 n=$3; id -nG "$u" | tr ' ' '\n' | grep -qx "$g" && fail "$n" "$u is in $g" || pass "$n"; }
as_user(){ runuser -u "$ACCEPTANCE_USER" -- env AGENTICDEV_DEVICE_TOKEN="$DEVICE_TOKEN" "$@"; }
need_root
[[ "${AGENTICDEV_ACCEPTANCE_DISPOSABLE:-}" == YES ]] || { echo 'FAIL harness — set AGENTICDEV_ACCEPTANCE_DISPOSABLE=YES only on a disposable VPS'; exit 2; }
: "${ACCEPTANCE_USER:?}" "${DEVICE_TOKEN:?}" "${ACCEPTANCE_WORK_ORDER:?}"
check_no_group "$ACCEPTANCE_USER" docker user-not-docker
check_no_group "$ACCEPTANCE_USER" sudo user-not-sudo
for spec in '/var/run/docker.sock docker-socket' '/run/containerd/containerd.sock containerd-socket'; do set -- $spec; runuser -u "$ACCEPTANCE_USER" -- python3 - "$1" <<'PY' >/dev/null 2>&1 && fail "$2" readable || pass "$2"
import socket,sys
s=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1])
PY
done
runuser -u "$ACCEPTANCE_USER" -- docker run --rm hello-world >/dev/null 2>&1 && fail direct-docker-run succeeded || pass direct-docker-run
read -r mode owner group < <(stat -c '%a %U %G' /run/agenticdev/broker.sock)
[[ "$mode $owner $group" == '660 root agenticdev-broker' ]] && pass broker-socket "$mode $owner:$group" || fail broker-socket "$mode $owner:$group"
hard=0
props=$(systemctl show agenticdev-broker.service -p User -p Group -p NoNewPrivileges -p ProtectHome -p ProtectSystem -p ProtectKernelTunables -p ProtectKernelModules -p ProtectControlGroups -p MemoryDenyWriteExecute 2>/dev/null)
for expected in User=root Group=agenticdev-broker NoNewPrivileges=yes ProtectHome=yes ProtectSystem=strict ProtectKernelTunables=yes ProtectKernelModules=yes ProtectControlGroups=yes MemoryDenyWriteExecute=yes; do
 grep -qx "$expected" <<<"$props" || { fail systemd-hardening "missing $expected"; hard=1; }
done
[[ $hard -eq 0 ]] && pass systemd-hardening expected-properties
bash /srv/agenticdev/src/tools/runtime-host-check.sh >/tmp/agenticdev-runtime-host-check.log 2>&1 && pass runtime-host-gate || fail runtime-host-gate "see /tmp/agenticdev-runtime-host-check.log"
start=$(as_user agenticdev-broker-client start <"$ACCEPTANCE_WORK_ORDER" 2>&1) || { fail valid-work-order "$start"; start=''; }
if [[ -n "$start" ]]; then pass valid-work-order; wid=$(jq -r .work_order_id <<<"$start"); else wid=''; fi
if [[ -n "$wid" ]]; then
 as_user agenticdev-broker-client start <"$ACCEPTANCE_WORK_ORDER" >/dev/null 2>&1 && fail replay-nonce accepted || pass replay-nonce
else skip replay-nonce 'valid start failed'; fi
# Live signature rejection from mutations of the issued document.
if [[ -n "$wid" ]]; then
 jq 'del(.signature)' "$ACCEPTANCE_WORK_ORDER" | as_user agenticdev-broker-client start >/dev/null 2>&1 && fail unsigned-work-order accepted || pass unsigned-work-order
 jq '.task.title="tampered"' "$ACCEPTANCE_WORK_ORDER" | as_user agenticdev-broker-client start >/dev/null 2>&1 && fail modified-work-order accepted || pass modified-work-order
else skip unsigned-work-order 'valid start failed'; skip modified-work-order 'valid start failed'; fi
expect_reject(){ local name=$1 expected=$2 file=$3 out
 out=$(as_user agenticdev-broker-client start <"$file" 2>&1) && { fail "$name" accepted; return; }
 [[ $(jq -r '.reason // empty' <<<"$out" 2>/dev/null) == "$expected" ]] && pass "$name" "$expected" || fail "$name" "wrong rejection: $out"
}
for spec in 'expired expired' 'future not_yet_valid' 'other-principal wrong_user'; do set -- $spec; f="${ACCEPTANCE_CASE_DIR:-}/$1.json"; [[ -f "$f" ]] && expect_reject "$1" "$2" "$f" || skip "$1" "signed fixture $f not supplied"; done
for c in other-project revoked-workstation missing-membership kill-switch traversal symlink-escape; do
 skip "$c" "requires a separately issued stored Work Order plus controlled server-state setup; a mutated file would be a false proof"
done
if [[ -n "$wid" ]]; then
 inspect=$(docker inspect "agenticdev-$wid" 2>/dev/null || true)
 [[ -n "$inspect" ]] || fail runtime-inspect missing
 [[ $(jq -r '.[0].HostConfig.PidMode' <<<"$inspect") != host ]] && pass no-host-pid || fail no-host-pid
 [[ $(jq -r '.[0].HostConfig.NetworkMode' <<<"$inspect") != host ]] && pass no-host-network || fail no-host-network
 [[ $(jq -r '.[0].HostConfig.Privileged' <<<"$inspect") == false ]] && pass not-privileged || fail not-privileged
 [[ $(jq -r '.[0].HostConfig.PidsLimit' <<<"$inspect") -gt 0 ]] && pass pid-limit-configured || fail pid-limit-configured
 [[ $(jq -r '.[0].HostConfig.Memory' <<<"$inspect") -gt 0 ]] && pass ram-limit-configured || fail ram-limit-configured
 [[ $(jq -r '.[0].HostConfig.NanoCpus' <<<"$inspect") -gt 0 ]] && pass cpu-limit-configured || fail cpu-limit-configured
 probe=$(as_user agenticdev-broker-client probe "$wid" 2>/dev/null || true)
 if jq -e '.ok and .probe' >/dev/null <<<"$probe"; then
  while IFS=$'\t' read -r st name detail; do case "$st" in PASS)pass "$name" "$detail";;FAIL)fail "$name" "$detail";;*)skip "$name" "$detail";;esac;done < <(jq -r '.probe[]|[.status,.name,.detail]|@tsv' <<<"$probe")
 else fail runtime-probe "$probe"; fi
 timeout 5 runuser -u "$ACCEPTANCE_USER" -- env AGENTICDEV_DEVICE_TOKEN="$DEVICE_TOKEN" agenticdev-broker-client attach "$wid" </dev/null >/dev/null 2>&1; rc=$?
 [[ $rc == 0 || $rc == 124 ]] && pass own-attach || fail own-attach "exit $rc"
 other=${ACCEPTANCE_OTHER_USER:-}
 if [[ -n "$other" ]]; then runuser -u "$other" -- env AGENTICDEV_DEVICE_TOKEN="$DEVICE_TOKEN" agenticdev-broker-client attach "$wid" </dev/null >/dev/null 2>&1 && fail foreign-attach accepted || pass foreign-attach; else skip foreign-attach ACCEPTANCE_OTHER_USER-not-set; fi
 as_user agenticdev-broker-client attach "$wid" --command sh >/dev/null 2>&1 && fail arbitrary-attach-command accepted || pass arbitrary-attach-command
 if [[ -n "$other" ]]; then runuser -u "$other" -- env AGENTICDEV_DEVICE_TOKEN="$DEVICE_TOKEN" agenticdev-broker-client stop "$wid" >/dev/null 2>&1 && fail foreign-stop accepted || pass foreign-stop; else skip foreign-stop ACCEPTANCE_OTHER_USER-not-set; fi
 as_user agenticdev-broker-client stop "$wid" >/dev/null 2>&1 && pass own-stop || fail own-stop
else
 for c in no-host-pid no-host-network not-privileged pid-limit-configured ram-limit-configured cpu-limit-configured runtime-probe own-attach foreign-attach arbitrary-attach-command foreign-stop own-stop; do skip "$c" 'valid workload unavailable'; done
fi
# These require deliberately short/small signed limits. Never infer enforcement from config alone.
for c in pid-limit-enforced ram-limit-enforced wall-clock-enforced disk-limit-enforced allowed-proxy-endpoint restricted-cloud-denied alternate-port-denied; do skip "$c" 'supply dedicated signed acceptance fixture and endpoint'; done
if jq -s -e 'map(.verb)|index("start") and index("attach") and index("stop") and index("reject")' /var/log/agenticdev-broker.jsonl >/dev/null 2>&1; then pass lifecycle-audit; else fail lifecycle-audit missing-events; fi
echo "SUMMARY PASS=$P FAIL=$F SKIP=$S"
if (( F != 0 )); then exit 1; fi
if [[ "$STRICT" == YES && $S -ne 0 ]]; then
 echo "FAIL completeness — $S mandatory checks were not executed (set up every documented fixture; do not waive this on a readiness run)"
 exit 3
fi
exit 0
