"""
Veřejná registrace — JEDINÁ část platformy vystavená do internetu.

Přes Tailscale Funnel je zvenčí dostupná jen cesta /join. Všechno ostatní
zůstává na tailnetu.

Proč všechny endpointy registrace leží POD /join a stránka na ně odkazuje
relativně: Funnel připojí cíl `http://<vps>:8080/join` na korytko `/`, a
cestu požadavku k cíli přilepí. Zvenčí se tedy `/api` promění na
`/join/api`. Kdyby stránka volala absolutní `/v1/join`, vzniklo by
`/join/v1/join` a registrace by zvenčí nefungovala — což je přesně to
místo, kde má fungovat. Na tailnetu se na stejnou stránku dostaneš přes
`/join/` a relativní odkazy míří tam, kam mají.

Kdo zná heslo, dostane:

  1. Tailscale auth key — připojí jeho stroj do tailnetu
  2. instalátor svázaný s touhle instancí

Teprve pak se dostane kamkoli dál. Heslo je tedy jediná zábrana na
veřejné straně a podle toho je s ním zacházeno: konstantní čas porovnání,
rate limit na IP i globálně, a exponenciální zpomalení po neúspěších.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from . import ratelimit

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
# hádat. Pět pokusů na IP za 15 minut, padesát celkem, pak hodina zámku.
_limiter = ratelimit.Limiter(window=900, per_ip=5, global_cap=50, lockout=3600)

_client_ip = ratelimit.client_ip


def _check_rate(ip: str) -> None:
    _limiter.check(ip)


def _record_attempt(ip: str) -> None:
    _limiter.record(ip)


def _clear_attempts(ip: str) -> None:
    _limiter.clear(ip)


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


@router.post("/join/api")
@router.post("/v1/join")            # historický alias, funguje z tailnetu
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
        # Relativně: stránka si to slepí se svou vlastní adresou, takže to
        # platí i zvenčí přes Funnel, i z tailnetu.
        "installer_url": "installer",
        "have_installer": INSTALLER_PATH.is_file(),
    }


_REPO = Path("/repo")


def _control_plane_url() -> str:
    return os.environ.get("CONTROL_PLANE_URL") or (
        f"https://{AGENTICDEV_DOMAIN}" if AGENTICDEV_DOMAIN else "http://localhost:8080")


@router.post("/join/installer")
def installer(body: JoinRequest, request: Request):
    """
    Instalátor se vydává jen proti heslu.

    macOS dostane soubor vyrobený mk-mac-installerem — nese v sobě join
    token a fingerprint instance, takže se proti cizímu serveru odmítne
    nainstalovat. Linux a Windows dostanou skript s doplněnou adresou;
    heslo si předávají argumentem.

    Windows verze je PowerShell: připraví WSL a uvnitř něj si vyžádá
    linuxový instalátor. Vydává se tudy, a ne bez hesla, aby se zvenčí
    nedalo stahovat nic bez průchodu registrací.
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
        return PlainTextResponse(
            f.read_text().replace("__CONTROL_PLANE__", _control_plane_url()),
            headers={"content-disposition": 'attachment; filename="agenticdev-install.sh"'},
        )

    if body.os == "windows":
        f = _REPO / "install-windows.ps1"
        if not f.is_file():
            raise HTTPException(503, "install-windows.ps1 není nasazený")
        return PlainTextResponse(
            f.read_text().replace("__CONTROL_PLANE__", _control_plane_url()),
            headers={"content-disposition": 'attachment; filename="agenticdev-install.ps1"'},
        )

    if not INSTALLER_PATH.is_file():
        raise HTTPException(
            503, "instalátor ještě nebyl vygenerován — na serveru spusť: sudo agenticdev-mac-installer")

    return PlainTextResponse(
        INSTALLER_PATH.read_text(),
        headers={"content-disposition": 'attachment; filename="agenticdev-install.sh"'},
    )


# Obě varianty, s lomítkem i bez. Přesměrování by tady bylo horší než
# duplicitní route: zvenčí by Location mířila na cestu, kterou Funnel
# nemapuje. Stránka si adresu endpointů skládá ze své vlastní (viz
# join.html), takže jí je jedno, jak se k ní kdo dostal.
@router.get("/join", include_in_schema=False)
@router.get("/join/", include_in_schema=False)
def join_page():
    p = Path(__file__).parent / "join.html"
    if not p.is_file():
        raise HTTPException(404)
    return HTMLResponse(p.read_text())


@router.get("/join/health", include_in_schema=False)
def join_health():
    """Aby se dalo zvenčí ověřit, že Funnel vede kam má — bez hesla."""
    return {"ok": True, "instance": INSTANCE_ID[:8], "enroll": bool(_enroll_password())}
