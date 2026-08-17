"""Native subscription CLI adapters. No API-key fallback is permitted."""
from __future__ import annotations

import shutil


AUTH_MARKERS = ("not logged in", "login required", "authentication required", "unauthorized",
                "please run /login", "please login", "failed to authenticate",
                "oauth access token has been revoked")
RATE_MARKERS = ("rate limit", "rate_limit", "usage limit", "quota", "too many requests")


def classify_failure(text: str, returncode: int) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in AUTH_MARKERS): return "AUTH_REQUIRED"
    if any(marker in lowered for marker in RATE_MARKERS): return "RATE_LIMITED"
    return "OK" if returncode == 0 else "FAILED"


def command(provider: str, prompt: str | None = None, mode: str = "work") -> list[str]:
    if provider == "claude":
        binary = shutil.which("claude")
        flags = (["--permission-mode", "plan", "--setting-sources", "user",
                  "--add-dir", "/workspace"] if mode == "analysis" else [])
        return ([binary, *flags, "-p", prompt] if prompt is not None else [binary]) if binary else []
    if provider == "codex":
        binary = shutil.which("codex")
        # The privileged broker already supplies the hard security boundary:
        # read-only root/workspace mounts, narrow writable binds, no caps,
        # no-new-privileges and proxy-only networking. Codex's nested bwrap
        # cannot create a user namespace inside that container.
        flags = (["--dangerously-bypass-approvals-and-sandbox", "--ephemeral",
                  "--ignore-user-config", "--ignore-rules", "--cd", "/workspace"]
                 if mode == "analysis" else
                 ["--dangerously-bypass-approvals-and-sandbox", "--ignore-rules"])
        return ([binary, "exec", "--skip-git-repo-check", *flags, prompt]
                if prompt is not None else [binary]) if binary else []
    return []
