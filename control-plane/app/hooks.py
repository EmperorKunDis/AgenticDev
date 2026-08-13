"""
Zakládání PR a webhook z Forgeja.

Proč tudy a ne z podu: agent nesmí držet přihlašovací údaje k repozitáři —
je to jedna z věcí, které o platformě tvrdíme nahlas. Pod tedy práci jen
dokončí, launcher na VPS větev odešle a PR otevře control plane svým
tokenem. Do těla PR přitom zapíše `Task-Id`, aby se po mergi dalo poznat,
který úkol je hotový.

„Hotovo" je smergovaný PR se zeleným workflow (ADR-0006), takže stav
`done` nastavuje výhradně tenhle webhook.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .main import _emit, current_ws, db

router = APIRouter()

FORGEJO_URL   = os.environ.get("FORGEJO_URL", "http://forgejo:3000")
FORGEJO_TOKEN = os.environ.get("FORGEJO_TOKEN", "")
HOOK_SECRET   = os.environ.get("FORGEJO_HOOK_SECRET", "")

_TASK_ID_RE = re.compile(r"Task-Id:\s*([0-9a-fA-F-]{36})")
# Větve zakládá `agenticdev-git start` jako task/<task-id>-<slug>.
_BRANCH_RE = re.compile(r"^task/([0-9a-fA-F-]{36})-")


# ═══════════════════════════════════════════════════════════════
#  Založení PR — volá launcher po odeslání větve
# ═══════════════════════════════════════════════════════════════
class NewPR(BaseModel):
    task_id: str
    branch: str
    title: str
    body: str = ""
    base: str = "main"


def _repo_slug(repo_url: str) -> str | None:
    """`ssh://git@host:2222/majitel/kod.git` → `majitel/kod`."""
    m = re.search(r"/([^/]+)/([^/]+?)(?:\.git)?$", repo_url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else None


@router.post("/v1/tasks/{task_id}/pull-request")
def open_pull_request(task_id: str, b: NewPR, ws: dict = Depends(current_ws)):
    if not FORGEJO_TOKEN:
        raise HTTPException(503, "FORGEJO_TOKEN není nastavený — PR musíš otevřít ručně")

    with db() as c:
        row = c.execute(
            """SELECT t.id, p.repo_url, p.code FROM task t
               JOIN phase ph ON ph.id = t.phase_id
               JOIN project p ON p.id = ph.project_id
               WHERE t.id = %s""", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "úkol neexistuje")

    slug = _repo_slug(row["repo_url"])
    if not slug:
        raise HTTPException(400, f"z repo_url '{row['repo_url']}' nepoznám majitele a jméno")

    # Task-Id v těle je to, po čem webhook úkol najde. Bez něj by se po
    # mergi nedalo poznat, co je hotové.
    body = f"{b.body}\n\nTask-Id: {task_id}\n".lstrip()

    try:
        r = httpx.post(
            f"{FORGEJO_URL}/api/v1/repos/{slug}/pulls",
            headers={"Authorization": f"token {FORGEJO_TOKEN}"},
            json={"head": b.branch, "base": b.base, "title": b.title, "body": body},
            timeout=30)
    except Exception as e:                              # noqa: BLE001
        raise HTTPException(502, f"Forgejo neodpovědělo: {e}")

    if r.status_code == 409:
        return {"ok": True, "note": "PR už existuje", "url": None}
    if r.status_code not in (200, 201):
        raise HTTPException(502, f"Forgejo odmítlo PR ({r.status_code}): {r.text[:200]}")

    url = r.json().get("html_url")
    with db() as c:
        c.execute("UPDATE task SET state = 'review' WHERE id = %s", (task_id,))
        _emit(c, ws["principal_id"], "task", task_id, "pull_request_opened",
              {"branch": b.branch, "url": url}, f"pr:{task_id}:{b.branch}")
    return {"ok": True, "url": url}


# ═══════════════════════════════════════════════════════════════
#  Webhook z Forgeja
# ═══════════════════════════════════════════════════════════════
def _signature_ok(raw: bytes, headers) -> bool:
    """
    Forgejo podepisuje tělo HMAC-SHA256 se sdíleným tajemstvím. Bez
    nastaveného tajemství webhook nepřijímáme — nepodepsaný požadavek by
    komukoli na tailnetu dovolil označovat úkoly za hotové.
    """
    if not HOOK_SECRET:
        return False
    sent = headers.get("x-forgejo-signature") or headers.get("x-gitea-signature") or ""
    want = hmac.new(HOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sent.strip().lower(), want)


def _task_from_payload(pr: dict) -> str | None:
    m = _TASK_ID_RE.search(pr.get("body") or "")
    if m:
        return m.group(1)
    m = _BRANCH_RE.match((pr.get("head") or {}).get("ref") or "")
    return m.group(1) if m else None


@router.post("/v1/hooks/forgejo", include_in_schema=False)
async def forgejo_hook(request: Request):
    raw = await request.body()
    if not _signature_ok(raw, request.headers):
        raise HTTPException(401, "neplatný podpis")

    import json
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "tělo není JSON")

    pr = payload.get("pull_request") or {}
    # Zajímá nás jedna jediná věc: PR se zavřel a byl smergovaný.
    if payload.get("action") != "closed" or not pr.get("merged"):
        return {"ok": True, "ignored": payload.get("action")}

    task_id = _task_from_payload(pr)
    if not task_id:
        return {"ok": True, "ignored": "v PR není Task-Id ani větev task/<id>-"}

    with db() as c:
        row = c.execute(
            "UPDATE task SET state = 'done' WHERE id = %s RETURNING id, title",
            (task_id,)).fetchone()
        if not row:
            return {"ok": True, "ignored": f"úkol {task_id} neexistuje"}
        _emit(c, None, "task", task_id, "done",
              {"pr": pr.get("html_url"), "merged_by": (pr.get("merged_by") or {}).get("login")},
              f"merged:{pr.get('id')}")
    return {"ok": True, "task": task_id, "state": "done"}
