"""
Omezení pokusů o uhádnutí hesla.

Používají to dvě místa, obě chráněná jen heslem: registrace strojů
(veřejná přes Funnel) a přihlášení do admin panelu. Panel je sice na
tailnetu, ale heslo bez omezení pokusů je heslo, které se dá zkoušet
tak dlouho, dokud nesedne — a tailnet je kompromitovaný stroj kolegy.

Držíme dvě okna: na IP a globální. Samotný per-IP limit nechrání před
pokusem z mnoha adres. Stav je v paměti procesu: po restartu se zapomene,
což je vědomý kompromis — trvalý stav by znamenal tabulku, kterou by šlo
zaplnit zvenčí.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


def client_ip(req: Request) -> str:
    """
    Za Funnelem i za Caddy chodí skutečná adresa v X-Forwarded-For.
    Bereme první hodnotu — tu, kterou tam zapsal náš vlastní proxy.
    """
    fwd = req.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return req.client.host if req.client else "unknown"


class Limiter:
    def __init__(self, window: int = 900, per_ip: int = 5,
                 global_cap: int = 50, lockout: int = 3600) -> None:
        self.window = window
        self.per_ip = per_ip
        self.global_cap = global_cap
        self.lockout = lockout
        self._by_ip: dict[str, deque[float]] = defaultdict(deque)
        self._locked: dict[str, float] = {}
        self._global: deque[float] = deque()

    def _prune(self, dq: deque[float], now_: float) -> None:
        while dq and now_ - dq[0] > self.window:
            dq.popleft()

    def check(self, ip: str) -> None:
        """Vyhodí 429, když je pokusů moc. Jinak nic."""
        now_ = time.time()

        until = self._locked.get(ip)
        if until and now_ < until:
            raise HTTPException(
                429, f"příliš mnoho pokusů, zkus za {int((until - now_) / 60) + 1} min")
        if until:
            del self._locked[ip]
            self._by_ip[ip].clear()

        self._prune(self._global, now_)
        if len(self._global) >= self.global_cap:
            raise HTTPException(429, "příliš mnoho pokusů, zkus to za chvíli")

        dq = self._by_ip[ip]
        self._prune(dq, now_)
        if len(dq) >= self.per_ip:
            self._locked[ip] = now_ + self.lockout
            raise HTTPException(
                429, f"příliš mnoho pokusů, zkus za {max(1, self.lockout // 60)} min")

    def record(self, ip: str) -> None:
        now_ = time.time()
        self._by_ip[ip].append(now_)
        self._global.append(now_)

    def clear(self, ip: str) -> None:
        self._by_ip.pop(ip, None)
        self._locked.pop(ip, None)
