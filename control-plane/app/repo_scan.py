"""Pure deterministic repository tree scanner; safe to exercise with hostile fixtures."""
from __future__ import annotations

import hashlib
from typing import Any

IGNORED = {".git", "node_modules", "vendor", "dist", "build", ".venv", "__pycache__"}
MANIFESTS = {"pyproject.toml", "requirements.txt", "package.json", "go.mod", "Cargo.toml",
             "Makefile", "Dockerfile", "compose.yaml", "docker-compose.yml"}
LICENSES = {"license", "license.md", "license.txt", "copying", "notice"}
ENTRYPOINTS = {"main.py", "app.py", "manage.py", "main.go", "main.ts", "main.js",
               "index.ts", "index.js", "server.ts", "server.js"}
CI_PARTS = {".github", ".forgejo", ".gitlab-ci.yml"}
TEST_PARTS = {"tests", "test", "spec", "pytest.ini", "vitest.config.ts", "jest.config.js"}


def scan_tree(entries: list[dict[str, Any]], sha: str) -> dict[str, Any]:
    paths = sorted(str(e.get("path")) for e in entries
                   if e.get("type") == "blob" and e.get("path"))
    blobs = {str(e.get("path")): str(e.get("sha") or e.get("id") or "")
             for e in entries if e.get("type") == "blob" and e.get("path")}
    safe = [p for p in paths if not any(part in IGNORED for part in p.split("/"))]
    suffixes: dict[str, int] = {}
    for path in safe:
        suffix = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else "(none)"
        suffixes[suffix] = suffixes.get(suffix, 0) + 1
    return {
        "schema": "agenticdev.static-scan/v1", "commit_sha": sha,
        "tree_hash": hashlib.sha256("\n".join(paths).encode()).hexdigest(), "blobs": blobs,
        "files_total": len(paths), "files_scanned": len(safe), "ignored": len(paths)-len(safe),
        "languages_by_extension": dict(sorted(suffixes.items(), key=lambda x: (-x[1], x[0]))[:30]),
        "manifests": [p for p in safe if p.rsplit("/", 1)[-1] in MANIFESTS],
        "dependency_manifests": [p for p in safe if p.rsplit("/", 1)[-1] in MANIFESTS],
        "licenses": [p for p in safe if p.rsplit("/", 1)[-1].lower() in LICENSES],
        "entrypoints": [p for p in safe if (p.rsplit("/", 1)[-1] in ENTRYPOINTS or
                         (p.split("/", 1)[0] == "cmd" and p.endswith(".go")))],
        "ci": [p for p in safe if any(part in CI_PARTS for part in p.split("/"))],
        "tests": [p for p in safe if any(part.lower() in TEST_PARTS for part in p.split("/"))],
        "documentation": [p for p in safe if p.lower().endswith((".md", ".rst", ".adoc"))],
        "untrusted_executable_instructions": [p for p in safe if p.rsplit("/", 1)[-1] in
          {"AGENTS.md", "CLAUDE.md", ".mcp.json", "settings.json", "pre-commit", "post-checkout"}],
    }
