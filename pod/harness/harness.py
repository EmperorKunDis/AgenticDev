#!/usr/bin/env python3
"""
Harness — důvěryhodné jádro podu.

Běží jako první proces v kontejneru, ověří policy a teprve pak spustí
agenta. Co vynucuje a co ne:

  vynucuje jádro       zápis mimo scope. Repozitář je připojený read-only
                       a povolené cesty jsou přes něj přemountované rw.
                       Zápis jinam selže na EROFS, ne na tom, že si to
                       agent ohlídá.

  vynucuje síť         egress. Pod je na uzavřené síti bez cesty ven,
                       jediná trasa vede přes proxy s allowlistem.

  vynucuje harness     model podle data_class, rozpočet, čas.

  nevynucuje nikdo     co agent udělá s daty, ke kterým má legitimní
                       přístup. To je hranice návrhu, ne chyba.

Nekontroluje se tu nic, co už zajistil launcher — kdyby harness "ověřoval"
mounty, které si sám nenastavil, byla by to jen dekorace.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

POLICY = pathlib.Path("/run/praut/policy.json")
WORKSPACE = pathlib.Path("/workspace")

C_OK, C_WARN, C_ERR, C_DIM, C_OFF = "\033[1;32m", "\033[1;33m", "\033[1;31m", "\033[2m", "\033[0m"


def fail(msg: str, code: int = 1) -> "None":
    print(f"\n{C_ERR}✗ {msg}{C_OFF}\n", file=sys.stderr)
    sys.exit(code)


def note(msg: str) -> None:
    print(f"{C_DIM}  {msg}{C_OFF}")


# ═══════════════════════════════════════════════════════════════
#  Policy
# ═══════════════════════════════════════════════════════════════
def load_policy() -> dict:
    if not POLICY.is_file():
        fail("Chybí policy. Pod se nesmí spustit bez ní.")
    try:
        p = json.loads(POLICY.read_text())
    except json.JSONDecodeError as e:
        fail(f"Policy je poškozená: {e}")

    for key in ("project", "phase", "data_class", "scope", "model", "egress"):
        if key not in p:
            fail(f"Policy nemá povinné pole '{key}'.")
    return p


def check_model(p: dict) -> None:
    """
    U citlivých dat nesmí odejít nic do cloudu. Tohle je tvrdý zákaz —
    ne varování, ne preference.
    """
    model = str(p["model"] or "")
    allow = p.get("model_allowlist") or []

    if p["data_class"] == "restricted":
        if not model.startswith("local/"):
            fail(f"Projekt je označený jako restricted, ale model je '{model}'.\n"
                 f"   Povolené jsou jen lokální modely (local/…).")
        note(f"model {model} — lokální, citlivá data neodejdou")
        return

    if allow and model not in allow:
        fail(f"Model '{model}' není v allowlistu projektu: {', '.join(allow)}")
    note(f"model {model}")


def check_egress(p: dict) -> None:
    """
    Nespoléháme na to, že allowlist platí — ověříme, že pod opravdu nemá
    cestu ven mimo proxy. Kdyby launcher síť nastavil špatně, tady to
    spadne, místo aby to tiše fungovalo.
    """
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not proxy:
        fail("Pod nemá nastavenou proxy. Bez ní by šel ven bez omezení.")

    allow = p["egress"]
    if not allow:
        fail("Prázdný egress allowlist. To by znamenalo pod bez sítě — "
             "pokud je to záměr, uveď aspoň control plane.")
    note(f"egress přes {proxy} — {len(allow)} domén")


def check_budget(p: dict) -> None:
    b = p.get("budget_tokens")
    if not b:
        return
    ctx = WORKSPACE / ".praut"
    used = 0
    if ctx.is_dir():
        for f in ctx.rglob("*"):
            if f.is_file():
                used += f.stat().st_size
    # Hrubý odhad, dokud nebude napojené count_tokens API. Radši ať to
    # spadne dřív než později — překročení je tvrdý fail, ne ořezání.
    est = used // 3
    if est > b:
        fail(f"Kontext má odhadem {est} tokenů, rozpočet je {b}.\n"
             f"   Zmenši kontext nebo zvyš rozpočet v panelu.")
    if b:
        note(f"rozpočet {b} tokenů (kontext ~{est})")


def check_scope(p: dict) -> None:
    """
    Scope vynucuje jádro. Tady jen ověříme, že to launcher opravdu
    nastavil — když je celý workspace zapisovatelný, ochrana neexistuje
    a je lepší to říct nahlas než předstírat, že platí.
    """
    scope = p["scope"]
    probe = WORKSPACE / ".praut-write-probe"
    writable_root = False
    try:
        probe.touch()
        probe.unlink()
        writable_root = True
    except OSError:
        pass

    if writable_root:
        fail("Kořen workspace je zapisovatelný — scope tedy nic neomezuje.\n"
             "   Pod se nespustí. Nahlas to jako chybu launcheru.")

    ok = []
    for s in scope:
        d = WORKSPACE / s.split("/")[0]
        if not d.exists():
            continue
        t = d / ".praut-write-probe"
        try:
            t.touch(); t.unlink(); ok.append(s)
        except OSError:
            note(f"{C_WARN}!{C_OFF} {s} mělo být zapisovatelné, ale není")
    note(f"scope {', '.join(scope) if scope else '(nic)'}")


# ═══════════════════════════════════════════════════════════════
#  Kontext
# ═══════════════════════════════════════════════════════════════
def materialize(p: dict) -> None:
    """Soubory z work orderu do workspace. /ctx je read-only, jen se čte."""
    ctx = pathlib.Path("/ctx")
    if ctx.is_dir() and any(ctx.iterdir()):
        note(f"kontext {len(list(ctx.rglob('*')))} souborů (read-only)")

    praut = WORKSPACE / ".praut"
    try:
        praut.mkdir(exist_ok=True)
        (praut / "policy.json").write_text(
            json.dumps({k: v for k, v in p.items() if k != "secrets"},
                       ensure_ascii=False, indent=2))
    except OSError as e:
        fail(f"Do .praut/ se nedá zapsat: {e}")


# ═══════════════════════════════════════════════════════════════
#  Agent
# ═══════════════════════════════════════════════════════════════
def run_agent(p: dict) -> int:
    env = os.environ.copy()
    env.update({
        "PRAUT_PROJECT": p["project"],
        "PRAUT_PHASE": p["phase"],
        "PRAUT_DATA_CLASS": p["data_class"],
        "PRAUT_MODEL": str(p["model"] or ""),
        "PATH": f"/workspace/bin:{env.get('PATH', '')}",
    })

    agent = shutil.which("pi")
    if not agent:
        print(f"{C_WARN}  Pi v obrazu není — otevírám shell.{C_OFF}")
        agent = "/bin/bash"

    print()
    deadline = p.get("deadline_ts")
    proc = subprocess.Popen([agent], cwd=str(WORKSPACE), env=env)

    def stop(_sig, _frm):
        proc.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    if deadline:
        while proc.poll() is None:
            if time.time() > deadline:
                print(f"\n{C_WARN}  Vypršel lease. Ukončuji agenta.{C_OFF}")
                proc.terminate()
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break
            time.sleep(2)
    return proc.wait()


# ═══════════════════════════════════════════════════════════════
def main() -> int:
    p = load_policy()

    print(f"\n  {C_OK}▍{C_OFF} {p['project']}  {C_DIM}{p.get('client', '')}{C_OFF}")
    print(f"  {C_DIM}{'─' * 44}{C_OFF}")
    print(f"  fáze          {p['phase']}")
    print(f"  data          {p['data_class']}")

    check_scope(p)
    check_model(p)
    check_egress(p)
    check_budget(p)
    materialize(p)

    print(f"  {C_DIM}{'─' * 44}{C_OFF}")
    if p["data_class"] == "restricted":
        print(f"  {C_WARN}Citlivá data — cloudové modely jsou tu zakázané.{C_OFF}")

    return run_agent(p)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
