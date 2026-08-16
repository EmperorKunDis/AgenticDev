"""Repository intelligence API. Imported repositories are always data, never code."""
from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .main import FORGEJO_TOKEN, FORGEJO_URL, current_ws, db
from .repo_scan import scan_tree

router = APIRouter()
ANALYZER_VERSION = "repository-intelligence/0.1.0"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _slug(repo_url: str) -> str:
    path = urlparse(repo_url).path.removesuffix(".git").strip("/")
    parts = path.split("/")
    if len(parts) != 2 or not all(parts):
        raise HTTPException(503, "repozitář nemá podporovanou serverovou identitu")
    return "/".join(parts)


def deterministic_scan(repo_url: str) -> tuple[str, dict[str, Any]]:
    """Read only Forgejo tree scan. It never checks out or executes repository files."""
    headers = {"Authorization": f"token {FORGEJO_TOKEN}"}
    slug = _slug(repo_url)
    metadata = httpx.get(f"{FORGEJO_URL}/api/v1/repos/{slug}", headers=headers, timeout=20)
    if metadata.status_code != 200:
        raise HTTPException(503, "metadata repozitáře nelze načíst")
    default_branch = str(metadata.json().get("default_branch") or "main")
    ref = httpx.get(f"{FORGEJO_URL}/api/v1/repos/{slug}/branches/{quote(default_branch, safe='')}",
                    headers=headers, timeout=20)
    if ref.status_code != 200:
        raise HTTPException(503, "default branch nelze načíst")
    sha = str(ref.json().get("commit", {}).get("id", "")).lower()
    if not SHA_RE.fullmatch(sha):
        raise HTTPException(503, "Forgejo nevrátilo commit SHA")
    tree = httpx.get(f"{FORGEJO_URL}/api/v1/repos/{slug}/git/trees/{sha}?recursive=true",
                     headers=headers, timeout=60)
    if tree.status_code != 200:
        raise HTTPException(503, "strom repozitáře nelze načíst")
    entries = tree.json().get("tree") or []
    scan = scan_tree(entries, sha)
    scan["default_branch"] = default_branch
    return sha, scan


def queue_static_scan(project_id: str, repo_url: str) -> dict:
    sha, scan = deterministic_scan(repo_url)
    with db() as c:
        row = c.execute(
            """INSERT INTO repository_analysis
                 (project_id,commit_sha,analyzer_version,state,static_scan)
               VALUES (%s,%s,%s,'awaiting_provider',%s)
               ON CONFLICT (project_id,commit_sha,analyzer_version) DO UPDATE
                 SET static_scan=EXCLUDED.static_scan,updated_at=now()
               RETURNING *""", (project_id, sha, ANALYZER_VERSION, json.dumps(scan))).fetchone()
        c.execute("UPDATE project SET analysis_status='awaiting_provider' WHERE id=%s", (project_id,))
        phase = c.execute("SELECT id FROM phase WHERE project_id=%s AND kind='implementation'",
                          (project_id,)).fetchone()
        if phase:
            c.execute("""INSERT INTO task(phase_id,kind,title,spec_ref,dod,write_scope,state,priority)
                         SELECT %s,'repository-analysis','Analyze imported repository',%s,%s,'{}','ready',0
                         WHERE NOT EXISTS (SELECT 1 FROM task WHERE spec_ref=%s)""",
                      (phase["id"], f"analysis:{row['id']}",
                       json.dumps(["structured result", "commit-pinned citations", "human approval"]),
                       f"analysis:{row['id']}"))
    return row


def _member(project: str, ws: dict) -> dict:
    with db() as c:
        row = c.execute("""SELECT p.* FROM project p JOIN project_member pm ON pm.project_id=p.id
                           WHERE p.code=%s AND pm.principal_id=%s AND pm.active""",
                        (project, ws["principal_id"])).fetchone()
    if not row:
        raise HTTPException(404, "projekt nenalezen")
    return row


class ProviderUpdate(BaseModel):
    provider: str
    auth_status: str
    account_label: str | None = None


@router.post("/v1/provider-profile")
def provider_profile(body: ProviderUpdate, ws: dict = Depends(current_ws)):
    if body.provider not in {"claude", "codex"} or body.auth_status not in {
            "ready", "auth_required", "rate_limited"}:
        raise HTTPException(400, "neplatný provider nebo stav")
    with db() as c:
        return c.execute("""INSERT INTO provider_profile
             (principal_id,provider,auth_status,last_verified_at,account_label)
             VALUES (%s,%s,%s,now(),%s) ON CONFLICT (principal_id,provider) DO UPDATE SET
             auth_status=EXCLUDED.auth_status,last_verified_at=now(),account_label=EXCLUDED.account_label
             RETURNING principal_id,provider,auth_status,last_verified_at,account_label""",
             (ws["principal_id"], body.provider, body.auth_status, body.account_label)).fetchone()


class AnalysisStart(BaseModel):
    provider: str


@router.post("/v1/projects/{project}/analysis/retry")
def retry_analysis(project: str, body: AnalysisStart, ws: dict = Depends(current_ws)):
    proj = _member(project, ws)
    with db() as c:
        profile = c.execute("SELECT auth_status FROM provider_profile WHERE principal_id=%s AND provider=%s",
                            (ws["principal_id"], body.provider)).fetchone()
        if not profile or profile["auth_status"] != "ready":
            raise HTTPException(409, "AUTH_REQUIRED")
        analysis = queue_static_scan(str(proj["id"]), proj["repo_url"])
        c.execute("""UPDATE work_order SET revoked_at=now() WHERE assignment_id IN
                     (SELECT a.id FROM assignment a JOIN task t ON t.id=a.task_id
                      WHERE t.spec_ref=%s AND a.state='active')""",
                  (f"analysis:{analysis['id']}",))
        c.execute("""UPDATE assignment SET state='released' WHERE task_id IN
                     (SELECT id FROM task WHERE spec_ref=%s) AND state='active'""",
                  (f"analysis:{analysis['id']}",))
        c.execute("UPDATE task SET state='ready' WHERE spec_ref=%s AND state<>'done'",
                  (f"analysis:{analysis['id']}",))
        row = c.execute("""UPDATE repository_analysis SET state='analyzing',provider=%s,error=NULL,
                           updated_at=now() WHERE id=%s RETURNING *""",
                        (body.provider, analysis["id"])).fetchone()
        c.execute("UPDATE project SET analysis_status='analyzing' WHERE id=%s", (proj["id"],))
    return row


class AnalysisResult(BaseModel):
    result: dict
    questions: list[dict] = Field(default_factory=list)


def _validate_result(result: dict, scan: dict) -> None:
    required = {"repository_map", "architecture", "commands", "glossary", "risks",
                "missing_documentation", "first_tasks", "citations"}
    if not required.issubset(result) or not isinstance(result.get("citations"), list):
        raise HTTPException(422, "analysis JSON schema je neplatné")
    for citation in result["citations"]:
        if not isinstance(citation, dict) or not isinstance(citation.get("path"), str):
            raise HTTPException(422, "citace nemá cestu")
        path = citation["path"]
        if (path.startswith("/") or ".." in path.split("/") or
                citation.get("blob_sha") != (scan.get("blobs") or {}).get(path)):
            raise HTTPException(422, "citace není připnutá k analyzovanému commitu")
        if not (citation.get("symbol") or citation.get("line")):
            raise HTTPException(422, "citace musí mít symbol nebo řádek")


@router.post("/v1/projects/{project}/analysis/result")
def submit_result(project: str, body: AnalysisResult, ws: dict = Depends(current_ws)):
    proj = _member(project, ws)
    with db() as c:
        row = c.execute("""SELECT * FROM repository_analysis WHERE project_id=%s AND state='analyzing'
                           ORDER BY updated_at DESC LIMIT 1""", (proj["id"],)).fetchone()
        if not row:
            raise HTTPException(409, "analýza neběží")
        _validate_result(body.result, row["static_scan"])
        state = "questions" if body.questions else "review"
        out = c.execute("""UPDATE repository_analysis SET result=%s,questions=%s,state=%s,updated_at=now()
                           WHERE id=%s RETURNING *""",
                        (json.dumps(body.result), json.dumps(body.questions), state, row["id"])).fetchone()
        c.execute("UPDATE project SET analysis_status=%s WHERE id=%s", (state, proj["id"]))
    return out


class Answers(BaseModel):
    answers: dict


@router.post("/v1/projects/{project}/analysis/answers")
def analysis_answers(project: str, body: Answers, ws: dict = Depends(current_ws)):
    proj = _member(project, ws)
    with db() as c:
        row = c.execute("""UPDATE repository_analysis SET answers=%s,state='review',updated_at=now()
                           WHERE id=(SELECT id FROM repository_analysis WHERE project_id=%s AND state='questions'
                           ORDER BY updated_at DESC LIMIT 1) RETURNING *""",
                        (json.dumps(body.answers), proj["id"])).fetchone()
        if not row: raise HTTPException(409, "analýza nečeká na odpovědi")
        c.execute("UPDATE project SET analysis_status='review' WHERE id=%s", (proj["id"],))
    return row


@router.post("/v1/projects/{project}/analysis/revise")
def revise_analysis(project: str, body: AnalysisResult, ws: dict = Depends(current_ws)):
    proj = _member(project, ws)
    with db() as c:
        row = c.execute("""SELECT * FROM repository_analysis WHERE project_id=%s
                           AND state IN ('questions','review') ORDER BY updated_at DESC LIMIT 1""",
                        (proj["id"],)).fetchone()
        if not row: raise HTTPException(409, "analýza není v lidské revizi")
        _validate_result(body.result, row["static_scan"])
        return c.execute("""UPDATE repository_analysis SET result=%s,questions=%s,state='review',
                            updated_at=now() WHERE id=%s RETURNING *""",
                         (json.dumps(body.result), json.dumps(body.questions), row["id"])).fetchone()


@router.post("/v1/projects/{project}/analysis/approve")
def approve_analysis(project: str, ws: dict = Depends(current_ws)):
    proj = _member(project, ws)
    with db() as c:
        row = c.execute("""UPDATE repository_analysis SET state='ready',approved_at=now(),approved_by=%s,
                           updated_at=now() WHERE id=(SELECT id FROM repository_analysis WHERE project_id=%s
                           AND state='review' ORDER BY updated_at DESC LIMIT 1) RETURNING *""",
                        (ws["principal_id"], proj["id"])).fetchone()
        if not row: raise HTTPException(409, "analýza není připravená ke schválení")
        c.execute("UPDATE project SET analysis_status='ready' WHERE id=%s", (proj["id"],))
        c.execute("UPDATE task SET state='done' WHERE spec_ref=%s",
                  (f"analysis:{row['id']}",))
        c.execute("""UPDATE assignment SET state='released' WHERE task_id IN
                     (SELECT id FROM task WHERE spec_ref=%s) AND state='active'""",
                  (f"analysis:{row['id']}",))
    return row


@router.get("/v1/projects/{project}/analysis")
def get_analysis(project: str, ws: dict = Depends(current_ws)):
    proj = _member(project, ws)
    with db() as c:
        return c.execute("SELECT * FROM repository_analysis WHERE project_id=%s ORDER BY updated_at DESC LIMIT 1",
                         (proj["id"],)).fetchone()


class Proposal(BaseModel):
    changes: dict[str, str]
    confirmed: bool = False


@router.post("/v1/projects/{project}/analysis/propose-pr")
def propose_analysis_pr(project: str, body: Proposal, ws: dict = Depends(current_ws)):
    """Create a proposal branch only after an explicit human confirmation."""
    proj = _member(project, ws)
    if not body.confirmed:
        raise HTTPException(409, "návrh PR vyžaduje explicitní potvrzení")
    allowed = lambda p: (p in {"AGENTS.md", "CONTEXT.md"} or
                         (p.startswith("docs/adr/") and p.endswith(".md")))
    if not body.changes or any(not allowed(path) or ".." in path.split("/")
                               for path in body.changes):
        raise HTTPException(400, "návrh smí měnit jen AGENTS, CONTEXT a docs/adr/*.md")
    with db() as c:
        ready = c.execute("SELECT id FROM repository_analysis WHERE project_id=%s AND state='ready' LIMIT 1",
                          (proj["id"],)).fetchone()
    if not ready: raise HTTPException(409, "nejdřív schval analýzu")
    slug = _slug(proj["repo_url"]); branch = f"agenticdev/analysis-{str(ready['id'])[:8]}"
    headers = {"Authorization": f"token {FORGEJO_TOKEN}"}
    metadata = httpx.get(f"{FORGEJO_URL}/api/v1/repos/{slug}", headers=headers, timeout=20)
    if metadata.status_code != 200: raise HTTPException(502, "metadata repozitáře nelze načíst")
    default_branch = str(metadata.json().get("default_branch") or "main")
    created = httpx.post(f"{FORGEJO_URL}/api/v1/repos/{slug}/branches", headers=headers,
                         json={"new_branch_name": branch, "old_branch_name": default_branch}, timeout=20)
    if created.status_code not in (201, 409): raise HTTPException(502, "větev návrhu nevznikla")
    for path, content in body.changes.items():
        url = f"{FORGEJO_URL}/api/v1/repos/{slug}/contents/{path}"
        current = httpx.get(url, headers=headers, params={"ref": branch}, timeout=20)
        payload = {"branch": branch, "message": f"docs: propose {path} from approved analysis",
                   "content": base64.b64encode(content.encode()).decode()}
        if current.status_code == 200: payload["sha"] = current.json().get("sha")
        response = httpx.request("PUT" if current.status_code == 200 else "POST", url,
                                 headers=headers, json=payload, timeout=20)
        if response.status_code not in (200, 201): raise HTTPException(502, f"návrh {path} se nezapsal")
    pull = httpx.post(f"{FORGEJO_URL}/api/v1/repos/{slug}/pulls", headers=headers,
        json={"base":default_branch, "head":branch, "title":"docs: repository intelligence proposal",
              "body":"Explicitly confirmed proposal from an approved AgenticDev analysis."}, timeout=20)
    if pull.status_code != 201: raise HTTPException(502, "proposal PR nevznikl")
    return {"ok": True, "branch": branch, "pull_request": pull.json().get("html_url")}
