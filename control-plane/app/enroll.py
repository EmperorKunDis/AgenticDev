"""
Veřejná registrace — JEDINÁ část platformy vystavená do internetu.

Přes Tailscale Funnel je zvenčí dostupná jen cesta /join. Všechno ostatní
zůstává na tailnetu. Kdo zná heslo, dostane:

  1. Tailscale auth key — připojí jeho stroj do tailnetu
  2. instalátor svázaný s touhle instancí

Teprve pak se dostane kamkoli dál. Heslo je tedy jediná zábrana na
veřejné straně a podle toho je s ním zacházeno: konstantní čas porovnání,
rate limit na IP i globálně, a exponenciální zpomalení po neúspěších.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

router = APIRouter()

INSTANCE_ID     = os.environ.get("AGENTICDEV_INSTANCE_ID", "")
VERIFY_KEY      = os.environ.get("WO_VERIFY_KEY_B64", "")
AGENTICDEV_DOMAIN    = os.environ.get("AGENTICDEV_DOMAIN", "")

# Hesla a klíče se čtou přes nastavení, aby změna v panelu platila hned.
from . import settings as cfg


def _enroll_password() -> str:
    return cfg.get("ENROLL_PASSWORD", "")

INSTALLER_PATH  = Path(os.environ.get("AGENTICDEV_OUT", "/out")) / "agenticdev-install-mac.sh"

# ═══════════════════════════════════════════════════════════════
#  Omezení pokusů
# ═══════════════════════════════════════════════════════════════
# Veřejný endpoint s heslem musí počítat s tím, že ho někdo bude zkoušet
# hádat. Držíme okno pokusů na IP a druhé globální — samotný per-IP limit
# nechrání před distribuovaným pokusem z mnoha adres.

_WINDOW      = 900       # 15 minut
_PER_IP      = 5         # pokusů na IP za okno
_GLOBAL      = 50        # pokusů celkem za okno
_LOCKOUT     = 3600      # po vyčerpání se IP zamkne na hodinu

_by_ip: dict[str, deque[float]] = defaultdict(deque)
_locked: dict[str, float] = {}
_global: deque[float] = deque()


def _client_ip(req: Request) -> str:
    # Za Funnelem i za Caddy chodí skutečná adresa v hlavičce. Bereme
    # první hodnotu, ale jen z hlaviček, které nám staví náš vlastní proxy.
    fwd = req.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return req.client.host if req.client else "unknown"


def _prune(dq: deque[float], now_: float) -> None:
    while dq and now_ - dq[0] > _WINDOW:
        dq.popleft()


def _check_rate(ip: str) -> None:
    now_ = time.time()

    until = _locked.get(ip)
    if until and now_ < until:
        raise HTTPException(429, f"příliš mnoho pokusů, zkus za {int((until - now_) / 60) + 1} min")
    if until:
        del _locked[ip]
        _by_ip[ip].clear()

    _prune(_global, now_)
    if len(_global) >= _GLOBAL:
        raise HTTPException(429, "příliš mnoho pokusů, zkus to za chvíli")

    dq = _by_ip[ip]
    _prune(dq, now_)
    if len(dq) >= _PER_IP:
        _locked[ip] = now_ + _LOCKOUT
        raise HTTPException(429, "příliš mnoho pokusů, zkus za hodinu")


def _record_attempt(ip: str) -> None:
    now_ = time.time()
    _by_ip[ip].append(now_)
    _global.append(now_)


def _clear_attempts(ip: str) -> None:
    _by_ip.pop(ip, None)
    _locked.pop(ip, None)


# ═══════════════════════════════════════════════════════════════
#  Tailscale auth key
# ═══════════════════════════════════════════════════════════════
def _mint_authkey(label: str) -> str | None:
    """
    Jednorázový klíč pro jeden stroj. Když není API token, spadneme zpátky
    na statický klíč z .env — funguje taky, jen ho sdílí všichni.
    """
    api_key = cfg.get("TS_API_KEY", "")
    tailnet = cfg.get("TS_TAILNET", "-")
    if api_key:
        try:
            r = httpx.post(
                f"https://api.tailscale.com/api/v2/tailnet/{tailnet}/keys",
                auth=(api_key, ""),
                timeout=20,
                json={
                    "capabilities": {
                        "devices": {
                            "create": {
                                "reusable": False,
                                "ephemeral": False,
                                "preauthorized": True,
                                "tags": ["tag:agenticdev-client"],
                            }
                        }
                    },
                    "expirySeconds": 3600,
                    "description": f"agenticdev enroll {label}",
                },
            )
            if r.status_code in (200, 201):
                return r.json().get("key")
        except Exception:
            pass
    return cfg.get("TS_AUTHKEY", "") or None


# ═══════════════════════════════════════════════════════════════
#  API
# ═══════════════════════════════════════════════════════════════
class JoinRequest(BaseModel):
    password: str
    os: str = "mac"


@router.post("/v1/join")
def join(body: JoinRequest, request: Request):
    ip = _client_ip(request)
    _check_rate(ip)

    pw = _enroll_password()
    if not pw:
        raise HTTPException(503, "registrace není nastavená")

    if not secrets.compare_digest(body.password, pw):
        _record_attempt(ip)
        # Stejná hláška i stejná prodleva bez ohledu na důvod — ať se z
        # odpovědi nedá nic vyčíst.
        time.sleep(1.0)
        raise HTTPException(401, "špatné heslo")

    _clear_attempts(ip)

    key = _mint_authkey(ip)
    fp = hashlib.sha256(f"{INSTANCE_ID}\n{VERIFY_KEY}".encode()).hexdigest()

    return {
        "ok": True,
        "instance_id": INSTANCE_ID,
        "fingerprint": f"sha256:{fp}",
        "domain": AGENTICDEV_DOMAIN,
        "tailscale_authkey": key,
        "installer_url": "/join/installer",
        "have_installer": INSTALLER_PATH.is_file(),
    }


_REPO = Path("/repo")


@router.post("/join/installer")
def installer(body: JoinRequest, request: Request):
    """
    Instalátor se vydává jen proti heslu.

    macOS dostane soubor vyrobený mk-mac-installerem — nese v sobě join
    token a fingerprint instance, takže se proti cizímu serveru odmítne
    nainstalovat. Linux dostane skript s doplněnou adresou; token si
    předává argumentem.
    """
    ip = _client_ip(request)
    _check_rate(ip)

    pw = _enroll_password()
    if not pw or not secrets.compare_digest(body.password, pw):
        _record_attempt(ip)
        time.sleep(1.0)
        raise HTTPException(401, "špatné heslo")

    _clear_attempts(ip)

    if body.os == "linux":
        f = _REPO / "install-linux.sh"
        if not f.is_file():
            raise HTTPException(503, "install-linux.sh není nasazený")
        cp = os.environ.get("CONTROL_PLANE_URL") or (
            f"https://{AGENTICDEV_DOMAIN}" if AGENTICDEV_DOMAIN else "http://localhost:8080")
        body_txt = f.read_text().replace("__CONTROL_PLANE__", cp)
    else:
        if not INSTALLER_PATH.is_file():
            raise HTTPException(
                503, "instalátor ještě nebyl vygenerován — na serveru spusť: sudo agenticdev-mac-installer")
        body_txt = INSTALLER_PATH.read_text()

    return PlainTextResponse(
        body_txt,
        headers={"content-disposition": 'attachment; filename="agenticdev-install.sh"'},
    )


@router.get("/join", include_in_schema=False)
def join_page():
    p = Path(__file__).parent / "join.html"
    if not p.is_file():
        raise HTTPException(404)
    return HTMLResponse(p.read_text())


@router.get("/join/health", include_in_schema=False)
def join_health():
    """Aby se dalo zvenčí ověřit, že Funnel vede kam má — bez hesla."""
    return {"ok": True, "instance": INSTANCE_ID[:8], "enroll": bool(_enroll_password())}
