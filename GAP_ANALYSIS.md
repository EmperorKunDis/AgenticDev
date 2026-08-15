# P0 readiness gap analysis

Datum revize: 2026-08-15. Stav je určen podle spustitelného kódu, SQL,
Compose a CI, nikoli podle tvrzení v README. Revize zahrnula všechny verzované
soubory; binární grafické podklady byly inventarizovány, ale nejsou součástí
bezpečnostního rozhodování.

## Výsledek

**P0 jako celek není připravené k nasazení.** ADR-0008 bylo přijato a první
runtime boundary je implementované, ale vyžaduje live VPS ověření a dokončení
interaktivního attach/worktree provisioning. Ostatní P0 bloky zůstávají mimo
scope této změny.

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

**NEEDS LIVE VERIFICATION**

- `vps/agenticdev-ctl user add` i upgrade v `install-vps.sh` odstraňují uživatele
  z `docker` a `sudo`; uživatel dostává pouze přístup k úzkému broker socketu.
- `launcher/agenticdev::cmd_work` už Docker nevolá a bez podepsaného Work Orderu
  nemá fallback.
- Runner je `root` a mountuje `/var/run/docker.sock` v
  `vps/docker-compose.yml`. I když nejde o interaktivní účet zaměstnance,
  nedůvěryhodný workflow má přes socket host-root dopad a sousedí se secrets.
- Negativní source-level testy změnu dokazují; skutečná práva socketů a group
  refresh po upgradu musí potvrdit live VPS test.

### 2. Úzký privileged launcher/helper

**NEEDS LIVE VERIFICATION**

`vps/broker.py` a `vps/agenticdev-broker.service` tvoří root-owned boundary.
Request má pouze `action`, celý immutable `work_order` a `device_token`;
jakékoli další pole se odmítne. Runtime plán používá pevné images, příkazy,
sítě a mounty. Chybí živý důkaz systemd hardeningu a funkční interaktivní attach.

### 3. Ověřit signed Work Order před spuštěním podu

**NEEDS LIVE VERIFICATION**

- `control-plane/app/main.py::next_work_order` kanonicky serializuje manifest a
  podepisuje jej Ed25519.
- Broker ověřuje Ed25519 podpis, issuer/key ID, nbf/exp, subject, template a
  limity před side effectem; nonce atomicky spotřebuje v root-owned SQLite.
- Control plane online ověřuje exact manifest hash, JWT workstation,
  principal, project membership, task/phase, assignment/lease a kill epoch.
- Nedostupný control plane i nepodepsaný interaktivní start jsou fail-closed.

### 4. Resource limits

**NEEDS LIVE VERIFICATION**

Podepsaná template nese CPU, RAM, PID, wall-clock a disk limity. Broker je
překládá na pevné Docker flags a test kontroluje jejich přítomnost. Skutečné
vynucení cgroups, timeoutu a `--storage-opt size` musí potvrdit live storage
driver/cgroup test.

### 5. Skutečné sandbox adversarial testy

**PARTIAL**

CI nově provádí broker negativní testy pro podpis, čas, replay, identity,
membership/kill odmítnutí, traversal/symlink, zakázané runtime vstupy a pevný
hardening plán. Útoky ze skutečně běžícího kontejneru stále vyžadují live VPS.

### 6. Egress default-deny testy

**PARTIAL**

`pod/compose.yaml` dává pod pouze na `internal: true` síť a
`pod/egress/entrypoint.sh` generuje tinyproxy konfiguraci s
`FilterDefaultDeny Yes`; prázdný seznam tedy staticky vypadá fail-closed.
Neexistuje však integrační test, který z podu prokáže blokaci přímé IP, DNS,
nepovolené domény, suffix-confusion, alternativních portů, IPv6 a proxy bypassu
a současně průchod explicitně povoleného cíle.

### 7. Cross-user a cross-project isolation

**PARTIAL**

`project_member` nyní filtruje project list/bundle, issuance i broker online
authorization. Host paths vznikají z principal/project/task ID pod root-owned
kořenem a symlink/traversal se odmítá. Cross-user/cross-project pokusy jsou
unit-testované; čtení z reálného adversarial podu vyžaduje live VPS.

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

1. Na izolované VPS ověřit přijatý broker backend, systemd/socket permissions,
   cgroups, storage driver, síť a adversarial workload; dokončit interaktivní
   attach a bezpečné naplnění broker-owned worktree.
2. Autorizační model principal↔project je zaveden; samostatný další P0 blok musí
   později doplnit jednorázové enrollment credentials a offboarding.
3. Podepsaný Work Order a immutable runtime template jsou implementovány;
   produkční přijetí blokuje živý end-to-end důkaz.
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

Zdrojový strom již uživateli Docker oprávnění nedává, ale bez live upgrade testu
nelze potvrdit odstranění starých supplementary groups ani práva socketů.
Broker backend zatím nemá použitelný interaktivní attach a broker-owned git
provisioning. Docker `--storage-opt size` závisí na storage driveru a musí být
ověřen. Forgejo runner nadále drží host Docker socket (oddělený P0 blok) a
ostatní readiness mezery z této matice zůstávají. P0 proto není ready.
