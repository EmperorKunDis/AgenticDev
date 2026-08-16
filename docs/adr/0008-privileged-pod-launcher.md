# ADR-0008 (návrh): root-owned broker pro spouštění pracovních podů

- Stav: **Přijato; první implementace runtime boundary**
- Datum: 2026-08-15
- Nahrazuje bezpečnostní část ADR-0005; umístění podu na VPS zachovává.

## Kontext

ADR-0005 dal každému zaměstnanci skupinu `docker`, aby launcher mohl ovládat
Docker daemon. Docker socket je root-equivalent. Uživatel si navíc může upravit
Compose a mounty ve svém home. To je neslučitelné s invariantem, že tenký klient
ani běžný účet nesmí získat host secrets, root nebo cizí projekt.

Control plane Work Order podepisuje, ale současný launcher podpis před startem
neověřuje a vytváří vlastní policy. Pouhé odebrání skupiny `docker` by systém
znefunkčnilo; setuid obal nad stávajícím Compose by naopak zachoval libovolné
mounty a byl by stejně nebezpečný.

## Rozhodnutí k odsouhlasení

Zavést malý root-owned broker dostupný přes Unix socket. Běžný launcher mu smí
předat pouze neprůhledný podepsaný Work Order a svůj krátkodobý device token.
Nesmí předávat Compose, image, host path, command, environment ani síť.

Broker musí před jakýmkoli runtime side effectem:

1. ověřit Ed25519 podpis nad přesnými kanonickými bytes, verzi schématu,
   `issued_at`/`expires_at` a povinná pole;
2. online ověřit aktivní assignment, workstation, principal, project membership
   a kill-switch epoch; při nedostupnosti autority start odmítnout;
3. atomicky spotřebovat jednorázový nonce a odmítnout replay;
4. mapovat project/repo/scope pouze přes root-owned registry a cesty kontrolovat
   přes `openat2`/ekvivalent proti symlink a traversal útokům;
5. sestavit runtime z root-owned immutable šablony a allowlistu digestů;
6. nastavit CPU, RAM, PID, wall-clock a disk limity a restricted egress policy;
7. zapsat audit a vrátit pouze omezený attach handle, nikdy runtime socket.

Preferovaný backend je rootless Podman/containerd worker pod odděleným service
účtem a po jednom UID namespace na workload. Forgejo Actions runner musí běžet
na odděleném workeru nebo rootless backendu bez socketu aplikačního hostitele.
Běžní uživatelé nebudou členy `docker`, `sudo` ani broker service group s
obecným RPC.

## Fail-closed pravidla

- Chybějící/nesprávný klíč, podpis, assignment, membership, limit nebo network
  policy znamená odmítnutí. Neexistuje interaktivní nepodepsaný fallback.
- Nedostupný control plane znamená zákaz nového startu.
- Prázdný egress znamená žádný egress; restricted policy nesmí obsahovat
  internetový gateway ani veřejný DNS resolver.
- Kill switch odmítá start a broker ukončí workloady z předchozí epochy.
- Teardown podle broker-owned ID nesmí přijímat PID/container name od klienta.

## Alternativy

1. **Rootless Docker pro každého:** zmenší host-root dopad, ale bez serverového
   brokera stále dovolí uživateli obejít projektovou policy a číst jemu dostupné
   host cesty. Samostatně nestačí.
2. **Setuid wrapper nad `docker compose`:** zamítnuto; vstupní plocha Compose,
   build contextů, mountů a daemon API je příliš široká.
3. **Vzdálený izolovaný worker/VM na job:** bezpečnější blast radius a vhodná
   budoucí varianta, ale provozně dražší. Broker protocol má umožnit pozdější
   změnu backendu.

## Důsledky

Launcher přestane vlastnit lifecycle a nebude stahovat/upravovat Compose.
Worktrees a per-user credentials se musí přesunout pod broker-owned cesty a
vydávat workloadu jako explicitní, principal-bound mounty/secrets. Je nutná DB
migrace pro membership, nonce/consumption a kill epoch. Jde o vědomou změnu
bezpečnostní architektury, nikoli úpravu kvůli testu.

## Implementační upřesnění

Broker používá root-owned Unix socket a lokální SQLite replay store. Control
plane při každém startu znovu ověřuje přesný hash uloženého Work Orderu,
assignment, device JWT, principal, membership, lease a kill epoch. To je
záměrně online a fail-closed; samotný platný podpis nestačí po revokaci.

Host cesty broker odvozuje výhradně pod `/srv/agenticdev/workloads` z UUID
principala, project code a UUID tasku. Phase scope se redukuje na validovaný
top-level adresář. Root-owned rodiče brání uživateli v záměně mount targetu;
symlink v kterékoli odvozené komponentě je odmítnut.

První backend používá Docker pouze uvnitř root služby. Image, entrypoint,
network, security flags a mounts jsou pevnou součástí template
`agent-pod-v1`; klient Docker socket nevidí. Diskový strop používá Docker
`--storage-opt size` a před produkčním nasazením vyžaduje live ověření podpory
storage driveru. Interaktivní attach a úplná inicializace broker-owned git
worktree zůstávají provozními blokery, nikoli bezpečnostním fallbackem: broker
bez nich workload nespustí použitelně a klient se k Dockeru nevrací.

## Acceptance před označením „Přijato"

- threat model pro socket, runtime, filesystem, network a runner;
- prototyp API se zápornými testy pro každý validační krok;
- adversarial test pro socket/root/host/cross-user/cross-project/egress;
- provozní rozhodnutí rootless backend versus oddělený worker;
- rollback a offboarding postup bez znovuzavedení Docker přístupu.
