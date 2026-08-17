"""Developer environment inventory and multi-account GitHub authentication."""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .admin import operator, who
from .main import JWT_SECRET, _emit, db, now

router = APIRouter()
REPO_ROOT = Path(os.environ.get("AGENTICDEV_REPO_ROOT", "/repo"))
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", "/workspace-templates"))
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "").strip()
_KEY = hashlib.sha256((JWT_SECRET + ":github-identities:v1").encode()).digest()


def _encrypt(token: str) -> str:
    nonce = os.urandom(12)
    cipher = AESGCM(_KEY).encrypt(nonce, token.encode(), b"github_identity")
    return base64.urlsafe_b64encode(nonce + cipher).decode()


def _files(root: Path, patterns: tuple[str, ...]) -> list[str]:
    found: set[str] = set()
    if root.is_dir():
        for pattern in patterns:
            for path in root.rglob(pattern):
                if path.is_file() and ".git" not in path.parts:
                    found.add(str(path.relative_to(root)))
    return sorted(found)


@router.get("/v1/developer-settings")
def developer_settings(op: dict = Depends(operator)):
    with db() as c:
        identities = c.execute(
            """SELECT id, github_login, display_name, avatar_url, scopes, is_default,
                      last_verified_at, created_at
               FROM github_identity ORDER BY is_default DESC, github_login""").fetchall()
        agents = c.execute(
            """SELECT role, semver, prompt_ref, tool_allowlist, model_allowlist
               FROM agent_profile ORDER BY role, semver""").fetchall()
    return {
        "github": {"configured": bool(GITHUB_CLIENT_ID), "identities": identities},
        "inventory": {
            "agents": agents,
            "skills": _files(WORKSPACE_ROOT, ("SKILL.md",)),
            "hooks": _files(REPO_ROOT, ("*hook*.py", "*hook*.sh", "*hooks*.py", "*hooks*.sh")),
            "scripts": _files(WORKSPACE_ROOT / "_base" / "bin", ("*",))
                       + _files(WORKSPACE_ROOT, ("*.sh", "*.py", "*.ts")),
            "instructions": _files(WORKSPACE_ROOT, ("AGENTS.md", "scope", "settings.json")),
        },
    }


class GitHubDevicePoll(BaseModel):
    device_code: str


@router.post("/v1/github/device/start")
def github_device_start(op: dict = Depends(operator)):
    if not GITHUB_CLIENT_ID:
        raise HTTPException(503, "GITHUB_CLIENT_ID není nastavený / is not configured")
    r = httpx.post("https://github.com/login/device/code",
                   headers={"Accept": "application/json"},
                   data={"client_id": GITHUB_CLIENT_ID, "scope": "repo read:org user:email"},
                   timeout=20)
    if r.status_code != 200:
        raise HTTPException(502, f"GitHub device flow selhal / failed ({r.status_code})")
    data = r.json()
    return {k: data[k] for k in ("device_code", "user_code", "verification_uri",
                                  "expires_in", "interval") if k in data}


@router.post("/v1/github/device/poll")
def github_device_poll(body: GitHubDevicePoll, op: dict = Depends(operator)):
    if not GITHUB_CLIENT_ID:
        raise HTTPException(503, "GITHUB_CLIENT_ID není nastavený / is not configured")
    r = httpx.post("https://github.com/login/oauth/access_token",
                   headers={"Accept": "application/json"},
                   data={"client_id": GITHUB_CLIENT_ID, "device_code": body.device_code,
                         "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}, timeout=20)
    data = r.json()
    if data.get("error") in {"authorization_pending", "slow_down"}:
        return {"state": "pending", "slow_down": data.get("error") == "slow_down"}
    token = data.get("access_token")
    if not token:
        raise HTTPException(400, data.get("error_description") or "GitHub přihlášení selhalo")
    profile = httpx.get("https://api.github.com/user",
                        headers={"Authorization": f"Bearer {token}",
                                 "Accept": "application/vnd.github+json"}, timeout=20)
    if profile.status_code != 200:
        raise HTTPException(502, "GitHub profil se nepodařilo ověřit")
    user = profile.json()
    scopes = [x.strip() for x in data.get("scope", "").split(",") if x.strip()]
    with db() as c:
        principal_id = who(op)
        default = c.execute("SELECT 1 FROM github_identity WHERE is_default").fetchone() is None
        row = c.execute(
            """INSERT INTO github_identity
                 (principal_id,github_user_id,github_login,display_name,avatar_url,
                  token_encrypted,scopes,is_default,last_verified_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now())
               ON CONFLICT (github_user_id) DO UPDATE SET
                 principal_id=EXCLUDED.principal_id,github_login=EXCLUDED.github_login,
                 display_name=EXCLUDED.display_name,avatar_url=EXCLUDED.avatar_url,
                 token_encrypted=EXCLUDED.token_encrypted,scopes=EXCLUDED.scopes,
                 last_verified_at=now()
               RETURNING id,github_login,display_name,avatar_url,scopes,is_default,last_verified_at""",
            (principal_id, str(user["id"]), user["login"], user.get("name"), user.get("avatar_url"),
             _encrypt(token), scopes, default)).fetchone()
        _emit(c, principal_id, "github_identity", str(row["id"]), "connected",
              {"login": row["github_login"]}, f"github:{row['id']}:{now().isoformat()}")
    return {"state": "ready", "identity": row}


@router.post("/v1/github/identities/{identity_id}/default")
def github_default(identity_id: str, op: dict = Depends(operator)):
    with db() as c:
        if not c.execute("SELECT 1 FROM github_identity WHERE id=%s", (identity_id,)).fetchone():
            raise HTTPException(404, "GitHub identita neexistuje")
        c.execute("UPDATE github_identity SET is_default=false WHERE is_default")
        c.execute("UPDATE github_identity SET is_default=true WHERE id=%s", (identity_id,))
    return {"ok": True}


@router.delete("/v1/github/identities/{identity_id}")
def github_disconnect(identity_id: str, op: dict = Depends(operator)):
    with db() as c:
        row = c.execute("DELETE FROM github_identity WHERE id=%s RETURNING github_login,is_default",
                        (identity_id,)).fetchone()
        if not row:
            raise HTTPException(404, "GitHub identita neexistuje")
        if row["is_default"]:
            c.execute("""UPDATE github_identity SET is_default=true WHERE id=(
                         SELECT id FROM github_identity ORDER BY created_at LIMIT 1)""")
        _emit(c, who(op), "github_identity", identity_id, "disconnected",
              {"login": row["github_login"]}, f"github-disconnect:{identity_id}")
    return {"ok": True}
