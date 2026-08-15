# P0 readiness gap analysis

Datum revize: 2026-08-15. Stav je určen podle spustitelného kódu, SQL,
Compose a CI, nikoli podle tvrzení v README. Revize zahrnula všechny verzované
soubory; binární grafické podklady byly inventarizovány, ale nejsou součástí
bezpečnostního rozhodování.

## Výsledek

**P0 není připravené k nasazení.** Zásadní požadavek (žádný root ekvivalent
pro běžného uživatele) přímo koliduje s přijatým ADR-0005 a se současným
launcherem. Podle zadání se proto implementace nesmí obejít kosmetickou změnou
nebo testem: nejprve je nutné přijmout náhradní architekturu popsanou v
[`docs/adr/0008-privileged-pod-launcher.md`](docs/adr/0008-privileged-pod-launcher.md).

## Metoda a hranice důkazu

- Statická kontrola: všechny verzované cesty přes `rg --files`, shell/Python,
  SQL migrace, oba Compose soubory, instalátory, CI a provozní skripty.
- Lokální kontroly dokazují pouze vlastnosti zdrojového stromu. Forgejo,
  firewall, Docker namespaces, Tailscale ACL, restic repository a obnovu dat
  nelze z repozitáře prohlásit za funkční.
- `NEEDS LIVE VERIFICATION` neznamená hotovo. Znamená, že existuje část
  implementace, ale rozhodující důkaz musí vzniknout na izolované VPS.
- Nález s více štítky používá nejzávažnější štítek a v textu uvádí, co už
  částečně existuje.

## Matice požadavků

### 1. Běžný uživatel nesmí mít docker-group/root ekvivalent

**CONFLICTS WITH CURRENT ARCHITECTURE**

- `vps/agenticdev-ctl`, větev `user add`, uživatele výslovně přidává do skupiny
  `docker` (`usermod -aG docker`).
- `launcher/agenticdev`, funkce `cmd_work`, vyžaduje úspěšné `docker info` a
  přímo provádí `docker compose`, `docker cp` a `docker exec`.
- Runner je `root` a mountuje `/var/run/docker.sock` v
  `vps/docker-compose.yml`. I když nejde o interaktivní účet zaměstnance,
  nedůvěryhodný workflow má přes socket host-root dopad a sousedí se secrets.
- ADR-0005 tento root ekvivalent přijímá jako známou cenu. To odporuje cílovému
  invariantu, ne pouze detailu implementace.

### 2. Úzký privileged launcher/helper

**MISSING**

V repozitáři není root-owned helper, systemd socket/service ani přesně omezené
API pro lifecycle podu. `vps/agenticdev-ctl` je široký rootovský administrační
nástroj; launcher naopak komunikuje s Docker daemonem přímo. Požadované
rozhraní, validační schéma, vazba identity na projekt a ochrana cest chybí.

### 3. Ověřit signed Work Order před spuštěním podu

**PARTIAL**

- `control-plane/app/main.py::next_work_order` kanonicky serializuje manifest a
  podepisuje jej Ed25519.
- `launcher/agenticdev::cmd_work` však zahodí `signature`, vybere jen části
  `policy` a `task`, spojí je s nepodepsaným workspace bundlem a sám zapíše
  `policy.json`. Následně spustí kontejnery bez ověření podpisu.
- `pod/harness/harness.py::load_policy` kontroluje přítomnost polí, deadline a
  některá pravidla, nikoli Ed25519 podpis. `WO_VERIFY_KEY_B64` se do control
  plane předává, ale startovací hranice jej nepoužívá.
- Interaktivní session bez Work Orderu je výslovně povolená. Pro P0 musí být
  produkční start fail-closed, nebo musí mít samostatný, serverem podepsaný typ
  oprávnění.

### 4. Resource limits

**MISSING**

`pod/compose.yaml` nemá CPU, memory, PID ani ulimit stropy ani pro `pod`, ani pro
`egress`. Work Order sice nese `max_wall_clock_min` a rozpočet, ale launcher je
do výsledné policy nepřenáší a runtime je nevynucuje. VPS služby rovněž nemají
limity, což umožňuje noisy-neighbour/DoS dopad.

### 5. Skutečné sandbox adversarial testy

**MISSING**

CI v `.github/workflows/test.yml` parsuje zdroje, testuje git helper,
reprodukovatelnost a Compose interpolaci. Nespouští útoky z podu: Docker socket,
host filesystem, capabilities, namespaces, mount escape, symlink/path
traversal, procfs, secrets a sousední kontejnery nejsou ověřeny.

### 6. Egress default-deny testy

**PARTIAL**

`pod/compose.yaml` dává pod pouze na `internal: true` síť a
`pod/egress/entrypoint.sh` generuje tinyproxy konfiguraci s
`FilterDefaultDeny Yes`; prázdný seznam tedy staticky vypadá fail-closed.
Neexistuje však integrační test, který z podu prokáže blokaci přímé IP, DNS,
nepovolené domény, suffix-confusion, alternativních portů, IPv6 a proxy bypassu
a současně průchod explicitně povoleného cíle.

### 7. Cross-user a cross-project isolation

**MISSING**

Unix home odděluje per-user `PI_DIR`, ale členství všech uživatelů v `docker`
ruší veškerou izolaci. Launcher navíc dovoluje uživateli měnit stažený Compose,
override i `.env` ve vlastním home a Docker daemon změny privilegovaně provede.
Projektový seznam v `control-plane/app/workspace.py::projects` nemá membership
filtr a `bundle` vybírá projekt pouze podle kódu, takže serverová autorizace
uživatel→projekt chybí.

### 8. Expirovatelné single-use enrollment tokeny

**MISSING**

- `JOIN_TOKEN` je jedna dlouhodobá environment proměnná a
  `control-plane/app/admin.py::register_ws` ji pouze porovnává.
- Ve schématu není hash enrollment tokenu, `expires_at`, `used_at`, účel ani
  vazba na osobu. Tabulka `enrollment` je jen evidence formuláře.
- Veřejný join používá sdílené heslo `ENROLL_PASSWORD`; úspěch jej
  nespotřebuje. Tailscale auth key může být ephemeral/preauthorized, ale není
  náhradou za jednorázovou autorizaci registrace workstation.

### 9. Ověřená Forgejo merge gate

**NEEDS LIVE VERIFICATION**

`control-plane/app/admin.py::_forgejo_seed_workflow`, `_forgejo_branch_gate` a
`gate_status` nasazují workflow, branch protection a porovnávají pozorované
status contexts; webhook má HMAC kontrolu v
`control-plane/app/hooks.py::_signature_ok`. Skutečný runner/status/merge byl
ale podle kódu pouze nakonfigurován. `gate_status` navíc považuje gate za `ok`
i při `required_approvals == 0`. Je nutný živý negativní i pozitivní PR test.

### 10. Repo bez testů nesmí automaticky projít zeleně

**MISSING**

Šablona `TEST_WORKFLOW` v `control-plane/app/admin.py` pro `kind=none` jen vydá
warning a skončí úspěšně. To je přesný opak požadavku. Detekce také obsahuje
fail-open `pip install ... || true`, takže neinstalovatelný Python projekt může
být vyhodnocen zavádějícím způsobem.

### 11. Minimálně jedno human approval

**MISSING**

`MERGE_GATE_APPROVALS` má v `control-plane/app/settings.py` výchozí hodnotu
nula; `_forgejo_branch_gate` ji předává Forgeju. Stavová kontrola nulu pouze
zobrazí jako problém, ale `gate_status["ok"]` approval nezahrnuje. Server tedy
nevynucuje nejméně jedno schválení.

### 12. Direct push na `main` zakázán server-side

**PARTIAL**

Forgejo branch protection se vytváří přes API a zapíná status check. Z kódu
není prokázáno, že zakazuje direct push všem relevantním rolím/adminům ani že
neexistuje bypass. Musí vzniknout automatický API test konfigurace a živý pokus
o přímý push, který server odmítne.

### 13. `restricted` technicky blokuje cloudový egress

**PARTIAL**

`control-plane/app/workspace.py::bundle` pro restricted odebere globální
cloudové domény a doplní lokální model. Launcher však vždy přidá hostname
control plane a uživatel s Docker oprávněním může síť/allowlist změnit nebo
spustit jiný kontejner. Bez privileged boundary tedy mechanismus není
bezpečnostní hranicí. Chybí test všech cloud endpointů i přímé IP/IPv6.

### 14. Zálohy a restore test

**PARTIAL**

`vps/backup/restic-backup.sh` dělá `pg_dumpall`, restic backup, retenci a
částečný integrity check; instalátor vytváří timer. Restore skript/runbook a
automatický test obnovy Postgresu, Forgeja, MinIO, konfigurace a klíčů chybí.
`backup-check` pouze vypíše snapshoty.

### 15. Kill switch

**PARTIAL**

`control-plane/app/main.py::next_work_order` fail-closed odmítne nové Work
Ordery, pokud je `platform_state.issuing_enabled=false`, a admin/CLI umí stav
měnit. Kill switch však nezastaví již běžící pody, nerevokuje aktivní leases a
tokeny ani nezablokuje interaktivní session bez Work Orderu. Chybí automatický
test a živé ověření propagace.

### 16. Bezpečný offboarding

**MISSING**

Existuje kontrola `workstation.revoked_at` při autentizaci, ale není úplný
atomický offboarding příkaz. `user add/list/pending` nemá `user disable/remove`.
Nejsou současně revokovány workstation/JWT, leases, Unix login a SSH keys,
Forgejo key/session/token, běžící pod, per-user model credentials a sessions.
Chybí auditní událost i idempotentní test.

## Blokující závislosti a pořadí P0

1. Přijmout ADR-0008 a určit runtime backend (root-owned helper + rootless
   runtime, nebo izolovaný worker host). Bez toho nelze poctivě dokazovat body
   1, 2, 3, 5, 7 a 13.
2. Zavést serverový autorizační model principal↔project a jednorázové
   enrollment credentials; až potom migraci/offboarding.
3. Spouštět výhradně ověřený, neexpirovaný a identitě/projektu přiřazený Work
   Order; helper musí sám skládat neměnnou runtime konfiguraci a limity.
4. Přesunout merge runner mimo Docker socket na aplikační VPS (rootless nebo
   oddělený worker), nastavit fail-closed workflow a approval ≥ 1.
5. Přidat adversarial integrační suite, restore drill a kill/offboarding suite.
6. Teprve poté provést živý acceptance run a archivovat strojově čitelné
   výsledky. P1/P2 zůstávají blokované.

## Povinný live VPS acceptance důkaz

- uživatel není v `docker`/sudo a nedokáže otevřít socket, číst `.env`, cizí
  home/worktree ani spustit vlastní image;
- helper odmítne pozměněný, expirovaný, replayovaný a cizímu principalu nebo
  projektu vydaný Work Order;
- adversarial pod nepřekročí mount, capability, PID/CPU/RAM ani síťové hranice;
- restricted pod nedosáhne na cloud hostname ani IP, povolený lokální endpoint
  funguje a prázdná/chybná policy nic neotevře;
- Forgejo odmítne direct push, PR bez testů, červené testy a PR bez approval;
  po approval a zelených testech merge projde a podepsaný webhook nastaví stav;
- restore do čisté instance obnoví konzistentní data a klíče; po kill switchi
  skončí aktivní workload a po offboardingu nefunguje žádná stará session ani
  klíč.

## Rizika, která zůstávají po této fázi

Dokud není ADR rozhodnuto a implementováno, běžný zaměstnanec má efektivně root
na aplikační VPS a všechny ostatní softwarové hranice lze obejít. Nejvyšší
rizika jsou exfiltrace podpisového/modelového tajemství, přístup k jinému
projektu, host takeover přes Docker socket a falešně zelený merge. Současný stav
proto nesplňuje cílový invariant a nesmí být označen jako P0-ready.
