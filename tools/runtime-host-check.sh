#!/usr/bin/env bash
# Hard security gate. No warning fallback: every line is required by broker runtime.
set -u
bad=0
pass(){ echo "PASS $*"; }
fail(){ echo "FAIL $*" >&2; bad=1; }
[[ -d /run/systemd/system ]] && pass systemd || fail "systemd is required"
[[ "$(stat -fc %T /sys/fs/cgroup 2>/dev/null)" == cgroup2fs ]] && pass cgroup-v2 || fail "unified cgroup v2 is required"
for ns in user pid net mnt; do [[ -e "/proc/self/ns/$ns" ]] && pass "namespace-$ns" || fail "kernel namespace $ns missing"; done
[[ -r /proc/sys/kernel/unprivileged_userns_clone ]] || pass "userns controlled by runtime"
command -v docker >/dev/null || { fail "Docker must be installed before runtime validation"; exit 1; }
docker info >/dev/null 2>&1 || { fail "Docker daemon unavailable"; exit 1; }
DRIVER=$(docker info --format '{{.Driver}}' 2>/dev/null)
ROOT=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null)
[[ "$DRIVER" == overlay2 ]] && pass overlay2 || fail "storage driver must be overlay2, got $DRIVER"
command -v xfs_quota >/dev/null && pass xfs-quota-tool || fail "xfs_quota (xfsprogs) is required"
check_xfs_quota(){
 local path=$1 label=$2 fs opts
 fs=$(findmnt -n -o FSTYPE -T "$path" 2>/dev/null); opts=$(findmnt -n -o OPTIONS -T "$path" 2>/dev/null)
 [[ "$fs" == xfs ]] && pass "$label-xfs" || fail "$label must be on XFS, got $fs"
 [[ ",$opts," == *,pquota,* || ",$opts," == *,prjquota,* ]] && pass "$label-project-quota" || fail "$label XFS mount needs pquota/prjquota"
}
check_xfs_quota "$ROOT" docker-root
check_xfs_quota /srv workload-root
DTYPE=$(docker info 2>/dev/null | awk -F: '/Supports d_type/ {gsub(/ /,"",$2);print $2;exit}')
[[ "$DTYPE" == true ]] && pass d-type || fail "overlay2 backing filesystem must support d_type"
SEC=$(docker info --format '{{json .SecurityOptions}}' 2>/dev/null)
[[ "$SEC" == *seccomp* ]] && pass seccomp || fail "Docker seccomp is required"
exit "$bad"
