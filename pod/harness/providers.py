"""Native subscription CLI adapters. No API-key fallback is permitted."""
from __future__ import annotations

import shutil


AUTH_MARKERS = ("not logged in", "login required", "authentication required", "unauthorized",
                "please run /login", "please login")
RATE_MARKERS = ("rate limit", "rate_limit", "usage limit", "quota", "too many requests")


def classify_failure(text: str, returncode: int) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in AUTH_MARKERS): return "AUTH_REQUIRED"
    if any(marker in lowered for marker in RATE_MARKERS): return "RATE_LIMITED"
    return "OK" if returncode == 0 else "FAILED"


def command(provider: str, prompt: str | None = None, mode: str = "work") -> list[str]:
    if provider == "claude":
        binary = shutil.which("claude")
        flags = ["--permission-mode", "plan", "--setting-sources", "user"] if mode == "analysis" else []
        return ([binary, *flags, "-p", prompt] if prompt is not None else [binary]) if binary else []
    if provider == "codex":
        binary = shutil.which("codex")
        flags = (["--sandbox", "read-only", "--ephemeral", "--ignore-user-config", "--ignore-rules"]
                 if mode == "analysis" else ["--ignore-rules"])
        return ([binary, "exec", "--skip-git-repo-check", *flags, prompt]
                if prompt is not None else [binary]) if binary else []
    return []
