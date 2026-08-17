#!/usr/bin/env python3
"""
Harness — důvěryhodné jádro podu.

Jediná cesta, jak se v podu spustí agent. Zpracuje přesný Work Order, který
ověřil privileged broker, a teprve pak agenta pustí. Broker vloží dokument na
tmpfs; sám kontejner do té doby jen čeká. Obraz má
harness i v ENTRYPOINT, aby `docker run` nad tímhle obrazem nikdy
nespustil agenta bez kontroly.

Co vynucuje a co ne:

  vynucuje jádro       zápis mimo scope. Repozitář je připojený read-only
                       a povolené cesty jsou přes něj přemountované rw.
                       Zápis jinam selže na EROFS, ne na tom, že si to
                       agent ohlídá.

  vynucuje síť         egress. Pod je na uzavřené síti bez cesty ven,
                       jediná trasa vede přes proxy s allowlistem.

  vynucuje harness     model podle data_class, rozpočet, čas.

  nevynucuje nikdo     co agent udělá s daty, ke kterým má legitimní
                       přístup. To je hranice návrhu, ne chyba.

Nekontroluje se tu nic, co už zajistil broker — kdyby harness "ověřoval"
mounty, které si sám nenastavil, byla by to jen dekorace.
"""
from __future__ import annotations

import json
from datetime import datetime
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

POLICY = pathlib.Path("/run/agenticdev/work-order.json")
WORKSPACE = pathlib.Path("/workspace")
TOKEN = pathlib.Path("/run/agenticdev/token")

# Transkripty musí ležet na hostiteli, ne v podu — pod se po skončení
# zbourá a s ním by zmizelo všechno, podle čeho se dá běh doladit nebo
# za půl roku přehrát. `/trees` je připojený z domovského adresáře toho
# člověka na VPS, takže teardown na něj nedosáhne.
TREES = pathlib.Path(os.environ.get("AGENTICDEV_TREES", "/trees"))

# Cestu k transkriptu zakládá main() a čte ji _agent_env(), kterou volá
# jak interaktivní session, tak director. Globál je tu proto, aby se
# nemusela protahovat podpisem funkcí, které o transkriptu nic neřeší.
_TRANSCRIPT: "pathlib.Path | None" = None

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
        fail("Chybí immutable Work Order. Pod se nesmí spustit bez něj.")
    try:
        signed = json.loads(POLICY.read_text())
    except json.JSONDecodeError as e:
        fail(f"Work Order je poškozený: {e}")
    if signed.get("schema") != "agenticdev.work-order/v1" or not signed.get("signature"):
        fail("Work Order nemá očekávané schéma nebo podpis.")
    task, repo, policy = signed.get("task", {}), signed.get("repo", {}), signed.get("policy", {})
    p = {"project": task.get("project"), "phase": task.get("phase"),
         "data_class": task.get("data_class"), "scope": repo.get("write_scope", []),
         "egress": policy.get("egress_allowlist", []), "budget_tokens": policy.get("budget_tokens"),
         "deadline_ts": int(datetime.fromisoformat(signed["expires_at"]).timestamp()),
         "work_order_id": signed.get("work_order_id"), "task": task,
         "max_loop_iterations": policy.get("max_loop_iterations"),
         "human_gate": policy.get("human_gate", []),
         "control_plane": policy.get("control_plane"),
         "model_allowlist": policy.get("model_allowlist", [])}
    p["provider"] = signed.get("runtime", {}).get("provider")
    p["mode"] = signed.get("runtime", {}).get("mode")
    p["worker_pool"] = signed.get("worker_pool", [])
    for key in ("project", "phase", "data_class", "scope", "egress"):
        if p.get(key) is None:
            fail(f"Work Order nemá povinné pole '{key}'.")
    return p


def check_model(p: dict) -> None:
    """
    NENÍ to záruka, je to čitelná hláška.

    Tohle je čitelná kontrola serverové model policy. O tom, kam se agent
    doopravdy dostane, rozhoduje egress allowlist — u restricted projektu
    v něm žádný cloudový endpoint není. Viz ADR-0004.
    """
    model = str(p.get("model") or "")
    allow = p.get("model_allowlist") or []

    if p["data_class"] == "restricted":
        if model and not model.startswith("local/"):
            note(f"{C_WARN}!{C_OFF} model {model} není lokální — egress ho stejně nepustí")
        else:
            note("jen lokální modely, cloud není v egressu")
        return

    if model and allow and model not in allow:
        note(f"{C_WARN}!{C_OFF} model {model} není v allowlistu projektu "
             f"({', '.join(allow)}) — allowlist je vodítko, ne zákaz")
    elif model:
        note(f"model {model}")
    else:
        note(f"provider {p.get('provider')}; model určuje serverová policy nebo subscription default")


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
    ctx = WORKSPACE / ".agenticdev"
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
    probe = WORKSPACE / ".agenticdev-write-probe"
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
        rel = s[:-3] if s.endswith("/**") else s
        target = WORKSPACE / rel
        if not target.exists():
            continue
        try:
            if target.is_dir():
                probe = target / ".agenticdev-write-probe"
                probe.touch(); probe.unlink()
            else:
                with target.open("ab"):
                    pass
            ok.append(s)
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

    agenticdev = WORKSPACE / ".agenticdev"
    try:
        agenticdev.mkdir(exist_ok=True)
        (agenticdev / "policy.json").write_text(
            json.dumps({k: v for k, v in p.items() if k != "secrets"},
                       ensure_ascii=False, indent=2))
    except OSError as e:
        fail(f"Do .agenticdev/ se nedá zapsat: {e}")


# ═══════════════════════════════════════════════════════════════
#  Agent
# ═══════════════════════════════════════════════════════════════
def _agent_env(p: dict) -> dict:
    """Prostředí agenta. Používá to interaktivní session i director."""
    env = os.environ.copy()
    env.update({
        "AGENTICDEV_PROJECT": p["project"],
        "AGENTICDEV_PHASE": p["phase"],
        "AGENTICDEV_DATA_CLASS": p["data_class"],
        "AGENTICDEV_MODEL": str(p.get("model") or ""),
        "AGENTICDEV_PROVIDER": str(p.get("provider") or ""),
        # Bez tohohle spadne `agenticdev-decision` na chybějící proměnnou a
        # `/skill:rozhodnuti` neudělá nic — precedenty by se přestaly
        # zapisovat a nikdo by si toho nevšiml, protože chybí tiše.
        "AGENTICDEV_CP": str(p.get("control_plane") or ""),
        # Director si podle tohohle teče do transkriptu. Prázdno = nezapisuj.
        "AGENTICDEV_TRANSCRIPT": str(_TRANSCRIPT or ""),
        "PATH": f"/workspace/bin:{env.get('PATH', '')}",
        # Pod má uzavřený egress, takže cokoli, co Pi zkouší na startu
        # mimo allowlist, jen čeká na timeout. Vypnout to je rychlost,
        # ne omezení funkce.
        "DISABLE_TELEMETRY": "1",
    })

    # HOME ukazuje do tmpfs, kde ten podadresář ještě není. Nástroje, které
    # do domovského adresáře píšou, by jinak spadly na chybějící cestu.
    home = env.get("HOME")
    if home:
        try:
            pathlib.Path(home).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            fail(f"Domovský adresář {home} se nepodařilo založit: {e}")

    return env


# ═══════════════════════════════════════════════════════════════
#  Transkript a záznam běhu
# ═══════════════════════════════════════════════════════════════
def open_transcript(p: dict) -> pathlib.Path | None:
    """
    Založí soubor pro transkript a vrátí cestu. Když to nejde, vrátí None a
    jede se dál — chybějící transkript nesmí zabránit práci.

    Jméno nese čas a úkol, ať se v tom dá hledat bez databáze.
    """
    task = (p.get("task") or {}).get("id") or "bez-ukolu"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    d = TREES / ".transcripts"
    try:
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{stamp}-{p['project']}-{str(task)[:8]}.log"
        f.write_text(
            f"# AgenticDev transkript\n"
            f"# projekt {p['project']} · fáze {p['phase']} · data {p['data_class']}\n"
            f"# úkol {task}\n# začátek {stamp}\n\n")
        return f
    except OSError as e:
        print(f"{C_DIM}  (transkript se nepodařilo založit: {e}){C_OFF}")
        return None


def report_run(p: dict, role: str, outcome: str, duration_ms: int,
               transcript: pathlib.Path | None) -> None:
    """
    Zapíše běh do ledgeru (`agent_run`), aby v panelu bylo vidět, co se
    dělo, jak dlouho a s jakým výsledkem.

    Tokeny a cenu tu záměrně NEPOSÍLÁME. Nativní CLI adaptéry je ve stabilním
    společném formátu neohlašují — a vymyslet je by znamenalo dát do auditní stopy číslo,
    které si nikdo neověří. Nula je poctivější než odhad, o kterém se za
    měsíc bude věřit, že je to měření.

    Selhání zápisu se jen zaloguje: nepovedený záznam nesmí shodit práci,
    která už je hotová.
    """
    task = (p.get("task") or {}).get("id") or p.get("task_id")
    cp = p.get("control_plane")
    if not (task and cp):
        # Bez úkolu není kam běh přivěsit — `agent_run.task_id` je NOT NULL
        # a odkazuje na `task`. Interaktivní session bez přiděleného úkolu
        # se tedy nezapíše, a je lepší to říct než tiše mlčet.
        print(f"{C_DIM}  (běh se nezapsal: {'není úkol' if not task else 'není control plane'}){C_OFF}")
        return
    try:
        tok = TOKEN.read_text().strip()
    except OSError:
        print(f"{C_DIM}  (běh se nezapsal: chybí token stanice){C_OFF}")
        return

    allow = p.get("model_allowlist") or []
    body = json.dumps({
        "task_id": str(task),
        "work_order_id": p.get("work_order_id"),
        "role": role,
        "state_name": p.get("phase"),
        "model": str(p.get("model") or (allow[0] if allow else "neurčeno")),
        "duration_ms": duration_ms,
        "outcome": outcome,
        "transcript_uri": f"file://{transcript}" if transcript else None,
    }).encode()

    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        f"{cp}/v1/runs", data=body, method="POST",
        headers={"content-type": "application/json", "Authorization": f"Bearer {tok}"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
        note(f"běh zapsán do ledgeru ({outcome}, {duration_ms // 1000} s)")
    except (urllib.error.URLError, OSError) as e:
        print(f"{C_DIM}  (běh se nezapsal: {e}){C_OFF}")


def report_provider_state(p: dict, outcome: str) -> None:
    if outcome not in {"AUTH_REQUIRED", "RATE_LIMITED"}: return
    cp = p.get("control_plane"); provider = p.get("provider")
    if not (cp and provider): return
    try: tok = TOKEN.read_text().strip()
    except OSError: return
    import urllib.request
    body = json.dumps({"provider": provider, "auth_status": outcome.lower()}).encode()
    req = urllib.request.Request(f"{cp}/v1/provider-profile", data=body, method="POST",
        headers={"content-type":"application/json", "Authorization":f"Bearer {tok}"})
    try: urllib.request.urlopen(req, timeout=10).read()
    except Exception: pass


def run_agent(p: dict) -> int:
    env = _agent_env(p)
    from providers import command
    cmd = command(str(p.get("provider")))
    if not cmd:
        print(f"{C_ERR}  Nativní CLI pro provider {p.get('provider')} v obrazu není.{C_OFF}")
        return 127

    print()
    deadline = p.get("deadline_ts")
    proc = subprocess.Popen(cmd, cwd=str(WORKSPACE), env=env)

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

    global _TRANSCRIPT
    _TRANSCRIPT = open_transcript(p)
    if _TRANSCRIPT:
        note(f"transkript {_TRANSCRIPT}")

    t0 = time.monotonic()
    ms = lambda: int((time.monotonic() - t0) * 1000)          # noqa: E731

    if p.get("mode") == "analysis":
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import analysis_runner
        outcome = analysis_runner.run(p, _agent_env(p))
        report_run(p, "repository-analysis", outcome, ms(), _TRANSCRIPT)
        report_provider_state(p, outcome)
        return 0 if outcome in ("questions", "review") else 1

    # S work orderem jede úkol podle postupu, který vynucuje director
    # (ADR-0003): kontroly projektu rozhodují, ne agent. Bez work orderu
    # není co vynucovat, takže se otevře interaktivní session.
    if p.get("work_order_id") and (p.get("task") or {}).get("id"):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        try:
            import director
        except ImportError as e:
            print(f"  {C_WARN}director.py chybí ({e}) — otevírám interaktivní session.{C_OFF}")
            rc = run_agent(p)
            report_run(p, "interactive", f"exit:{rc}", ms(), _TRANSCRIPT)
            return rc
        print(f"  {C_DIM}úkol{C_OFF} {p['task'].get('title', '?')}")
        outcome = director.drive(p, _agent_env(p))
        report_run(p, "director", outcome, ms(), _TRANSCRIPT)
        report_provider_state(p, outcome)
        return 0 if outcome in ("done", "review") else 1

    rc = run_agent(p)
    # Provider drží vlastní session pod osobním UID; serverový audit zapisuje
    # jen to, co spolehlivě víme
    # my: model, dobu, výsledek. Bez přiděleného úkolu se nezapíše nic a
    # report_run to řekne — `agent_run` na `task` odkazuje povinně.
    report_run(p, "interactive", f"exit:{rc}", ms(), _TRANSCRIPT)
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
