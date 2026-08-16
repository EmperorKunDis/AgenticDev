"""Deterministic runtime hooks. Broker/kernel controls remain authoritative."""
from __future__ import annotations

import pathlib
import re
import subprocess

SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|secret|token)\s*[:=]\s*['\"][^'\"]{12,}"),
)


def changed_diff(workspace: pathlib.Path) -> str:
    p = subprocess.run(["git", "diff", "--no-ext-diff", "--binary", "--", "."],
                       cwd=workspace, capture_output=True, text=True)
    return p.stdout


def secret_findings(diff: str) -> list[str]:
    findings = []
    for number, line in enumerate(diff.splitlines(), 1):
        if not line.startswith("+") or line.startswith("+++"): continue
        if any(pattern.search(line) for pattern in SECRET_PATTERNS):
            findings.append(f"diff:{number}")
    return findings
