#!/usr/bin/env python3
"""Root-owned, fail-closed runtime broker for AgenticDev.

The unprivileged client may submit only a signed Work Order and its device JWT.
All Docker arguments and host paths are constructed here from fixed templates.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pwd
import re
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PROJECT = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
TEMPLATES = {"agent-pod-v1"}
ALLOWED_KEYS = {"action", "work_order", "device_token"}


class Reject(Exception):
    pass


def canonical(manifest: dict) -> bytes:
    unsigned = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()


def parse_time(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError) as exc:
        raise Reject("invalid_time") from exc


@dataclass(frozen=True)
class Limits:
    cpus: str
    memory_mb: int
    pids: int
    wall_seconds: int
    disk_mb: int


class ReplayStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS nonce (value TEXT PRIMARY KEY, used_at INTEGER NOT NULL)")

    def consume(self, nonce: str) -> None:
        try:
            self.db.execute("INSERT INTO nonce VALUES (?,?)", (nonce, int(time.time())))
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            raise Reject("replay") from exc


class Broker:
    def __init__(self, verify_key: bytes, issuer: str, control_plane: str,
                 broker_secret: str, state: ReplayStore, audit_file: Path,
                 runner: Callable[[list[list[str]]], None] | None = None,
                 clock: Callable[[], float] = time.time):
        self.key = Ed25519PublicKey.from_public_bytes(verify_key)
        self.issuer = issuer
        self.cp = control_plane.rstrip("/")
        self.secret = broker_secret
        self.state = state
        self.audit_file = audit_file
        self.runner = runner or self._run
        self.clock = clock

    def audit(self, verb: str, m: dict, reason: str, peer_user: str) -> None:
        subject = m.get("subject") or {}
        task = m.get("task") or {}
        row = {"ts": datetime.now(timezone.utc).isoformat(), "verb": verb,
               "reason": reason, "peer_user": peer_user,
               "principal_id": subject.get("principal_id"),
               "project": task.get("project"), "task_id": task.get("id"),
               "work_order_id": m.get("work_order_id")}
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.audit_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as out:
            out.write(json.dumps(row, sort_keys=True) + "\n")
        try:
            self._post("/v1/broker/audit", row, None)
        except Reject:
            pass  # root-owned local audit is authoritative during CP outage

    def handle(self, request: dict, peer_user: str) -> dict:
        manifest = request.get("work_order") if isinstance(request, dict) else {}
        try:
            if set(request) - ALLOWED_KEYS or request.get("action") != "start":
                raise Reject("narrow_protocol_violation")
            if not isinstance(manifest, dict) or not isinstance(request.get("device_token"), str):
                raise Reject("invalid_request")
            self._verify(manifest, peer_user)
            auth = self._post("/v1/broker/authorize", {"work_order": manifest}, request["device_token"])
            self._match_authorization(manifest, auth, peer_user)
            self.state.consume(manifest["nonce"])
            plan = self.runtime_plan(manifest, auth, request["device_token"])
            self.audit("start", manifest, "accepted", peer_user)
            try:
                self.runner(plan)
            finally:
                self.audit("stop", manifest, "workload_exited", peer_user)
            return {"ok": True, "work_order_id": manifest["work_order_id"]}
        except Reject as exc:
            self.audit("reject", manifest if isinstance(manifest, dict) else {}, str(exc), peer_user)
            return {"ok": False, "reason": str(exc)}

    def _verify(self, m: dict, peer_user: str) -> None:
        required = {"schema", "issuer", "key_id", "work_order_id", "nonce", "not_before",
                    "expires_at", "subject", "task", "runtime", "policy", "signature"}
        if not required <= set(m):
            raise Reject("unsigned_or_incomplete")
        if m["schema"] != "agenticdev.work-order/v1" or m["issuer"] != self.issuer or m["key_id"] != "primary":
            raise Reject("untrusted_issuer")
        sig = m["signature"]
        if not isinstance(sig, str) or not sig.startswith("ed25519:"):
            raise Reject("unsigned_or_incomplete")
        try:
            self.key.verify(base64.b64decode(sig[8:], validate=True), canonical(m))
        except (InvalidSignature, ValueError):
            raise Reject("bad_signature")
        now = self.clock()
        if parse_time(m["not_before"]) > now + 5:
            raise Reject("not_yet_valid")
        if parse_time(m["expires_at"]) <= now:
            raise Reject("expired")
        s, t, r = m["subject"], m["task"], m["runtime"]
        if not all(ID.fullmatch(str(s.get(k, ""))) for k in ("principal_id", "workstation_id")):
            raise Reject("invalid_subject")
        if s.get("unix_user") != peer_user:
            raise Reject("wrong_user")
        if not ID.fullmatch(str(t.get("id", ""))) or not PROJECT.fullmatch(str(t.get("project", ""))):
            raise Reject("invalid_task")
        if r.get("template") not in TEMPLATES or set(r) != {"template", "limits"}:
            raise Reject("runtime_template_denied")
        self._limits(r.get("limits"))
        if any(k in m for k in ("host_path", "mounts", "image", "command", "environment", "network", "docker_flags")):
            raise Reject("forbidden_runtime_input")

    @staticmethod
    def _limits(raw: dict) -> Limits:
        try:
            limits = Limits(str(raw["cpus"]), int(raw["memory_mb"]), int(raw["pids"]),
                            int(raw["wall_seconds"]), int(raw["disk_mb"]))
            cpu = float(limits.cpus)
        except (KeyError, TypeError, ValueError) as exc:
            raise Reject("invalid_limits") from exc
        if not (0.1 <= cpu <= 8 and 128 <= limits.memory_mb <= 32768 and
                16 <= limits.pids <= 4096 and 60 <= limits.wall_seconds <= 14400 and
                128 <= limits.disk_mb <= 102400):
            raise Reject("invalid_limits")
        return limits

    def _post(self, path: str, body: dict, token: str | None) -> dict:
        headers = {"Content-Type": "application/json", "X-AgenticDev-Broker": self.secret}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            req = urllib.request.Request(self.cp + path, json.dumps(body).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=3) as res:
                return json.load(res)
        except (OSError, urllib.error.HTTPError, ValueError) as exc:
            raise Reject("control_plane_unavailable_or_denied") from exc

    @staticmethod
    def _match_authorization(m: dict, a: dict, peer_user: str) -> None:
        expected = {"principal_id": m["subject"]["principal_id"],
                    "workstation_id": m["subject"]["workstation_id"],
                    "unix_user": peer_user, "project": m["task"]["project"],
                    "task_id": m["task"]["id"], "phase": m["task"]["phase"],
                    "work_order_id": m["work_order_id"], "kill_epoch": m["kill_epoch"]}
        if not a.get("authorized") or any(a.get(k) != v for k, v in expected.items()):
            raise Reject("authorization_mismatch")

    @staticmethod
    def safe_dir(root: Path, *ids: str) -> Path:
        if any(not (ID.fullmatch(x) or PROJECT.fullmatch(x)) for x in ids):
            raise Reject("unsafe_path_id")
        root = root.resolve(strict=True)
        cur = root
        for item in ids:
            cur = cur / item
            cur.mkdir(mode=0o700, exist_ok=True)
            if cur.is_symlink() or root not in cur.resolve().parents:
                raise Reject("symlink_escape")
        return cur

    def runtime_plan(self, m: dict, a: dict, device_token: str) -> list[list[str]]:
        limits = self._limits(m["runtime"]["limits"])
        root = Path(os.environ.get("AGENTICDEV_WORK_ROOT", "/srv/agenticdev/workloads"))
        work = self.safe_dir(root, m["subject"]["principal_id"], a["project"], a["task_id"])
        state_root = Path(os.environ.get("AGENTICDEV_BROKER_STATE", "/var/lib/agenticdev-broker/runs"))
        state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        run_state = self.safe_dir(state_root, m["work_order_id"])
        wo_file, token_file = run_state / "work-order.json", run_state / "token"
        wo_file.write_text(json.dumps(m, sort_keys=True, separators=(",", ":")))
        token_file.write_text(device_token)
        os.chmod(wo_file, 0o600); os.chmod(token_file, 0o600)
        net, name = "ad-" + m["work_order_id"], "agenticdev-" + m["work_order_id"]
        allow = ",".join(m["policy"].get("egress_allowlist") or [])
        pod = ["docker", "run", "-d", "--rm", "--name", name, "--user", "1000:1000",
               "--read-only", "--security-opt", "no-new-privileges", "--cap-drop", "ALL",
               "--pids-limit", str(limits.pids), "--cpus", limits.cpus,
               "--memory", f"{limits.memory_mb}m", "--memory-swap", f"{limits.memory_mb}m",
               "--storage-opt", f"size={limits.disk_mb}M", "--network", net,
               "--env", "HTTP_PROXY=http://egress:8888", "--env", "HTTPS_PROXY=http://egress:8888",
               "--env", "NO_PROXY=localhost,127.0.0.1", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
               "--tmpfs", "/run/agenticdev:rw,noexec,nosuid,size=8m,mode=0700,uid=1000,gid=1000",
               "--mount", f"type=bind,src={work},dst=/workspace,readonly",
               "--entrypoint", "sleep", "agenticdev/pod:installed", "infinity"]
        for scope in m["repo"].get("write_scope", []):
            top = scope.split("/", 1)[0]
            if not PROJECT.fullmatch(top):
                raise Reject("unsafe_scope")
            target = self.safe_dir(work, top); os.chown(target, 1000, 1000)
            pod[-3:-3] = ["--mount", f"type=bind,src={target},dst=/workspace/{top}"]
        egress = "egress-" + m["work_order_id"]
        return [["docker", "network", "create", "--internal", net],
                ["docker", "network", "create", net + "-outside"],
                ["docker", "run", "-d", "--rm", "--name", egress, "--network", net,
                 "--read-only", "--security-opt", "no-new-privileges", "--cap-drop", "ALL",
                 "--tmpfs", "/tmp", "--env", "AGENTICDEV_EGRESS_ALLOW=" + allow,
                 "agenticdev/egress:installed"],
                ["docker", "network", "connect", net + "-outside", egress], pod,
                ["docker", "cp", str(wo_file), name + ":/run/agenticdev/work-order.json"],
                ["docker", "cp", str(token_file), name + ":/run/agenticdev/token"],
                ["docker", "exec", "--user", "0", name, "chown", "1000:1000",
                 "/run/agenticdev/work-order.json", "/run/agenticdev/token"],
                ["timeout", "--signal=TERM", str(limits.wall_seconds), "docker", "exec",
                 "--user", "1000:1000", "-i", name, "python3", "/opt/agenticdev/harness.py"],
                ["docker", "rm", "-f", name], ["docker", "rm", "-f", egress],
                ["docker", "network", "rm", net], ["docker", "network", "rm", net + "-outside"],
                ["rm", "-f", str(wo_file), str(token_file)]]

    @staticmethod
    def _run(plan: list[list[str]]) -> None:
        commands, cleanup = plan[:-5], plan[-5:]
        try:
            for command in commands:
                subprocess.run(command, check=True, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise Reject("runtime_start_failed") from exc
        finally:
            for command in cleanup:
                subprocess.run(command, check=False, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def serve(broker: Broker, socket_path: Path) -> None:
    socket_path.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path)); os.chmod(socket_path, 0o660); server.listen(16)
        while True:
            conn, _ = server.accept()
            with conn:
                uid = int.from_bytes(conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)[4:8], "little")
                try:
                    request = json.loads(conn.recv(1024 * 1024))
                    response = broker.handle(request, pwd.getpwuid(uid).pw_name)
                except Exception:
                    response = {"ok": False, "reason": "invalid_request"}
                conn.sendall(json.dumps(response).encode())


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--socket", default="/run/agenticdev/broker.sock")
    args = p.parse_args()
    broker = Broker(base64.b64decode(os.environ["WO_VERIFY_KEY_B64"]), os.environ["AGENTICDEV_INSTANCE_ID"],
                    os.environ["CONTROL_PLANE_URL"], os.environ["BROKER_SECRET"],
                    ReplayStore(Path("/var/lib/agenticdev-broker/replay.sqlite3")),
                    Path("/var/log/agenticdev-broker.jsonl"))
    serve(broker, Path(args.socket))


if __name__ == "__main__":
    main()
