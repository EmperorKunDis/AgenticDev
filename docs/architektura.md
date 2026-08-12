# Agentní vývojová platforma AgenticDev — kompletní architektonický rozbor

**Verze:** 0.2 — po upřesnění náčrtu (`compose + harness`, `serving directors`)
**Datum:** 7. 8. 2026
**Vstup:** ruční náčrt (foto) + zadání
**Status:** návrh, nic z toho není postavené

---

## 0. Jak jsem četl náčrt (a co je nečitelné)

Tohle odděluju záměrně, ať víš, kde stavím na tvém vstupu a kde si domýšlím.

**Přečteno spolehlivě:**

| Prvek náčrtu | Čtení |
|---|---|
| 3 oranžové boxy vlevo | 3 pracovní stanice, uvnitř každé kontejner (obrazovka/kontejner) |
| Velký růžový rám vpravo | VPS |
| Zelený box uvnitř VPS | `info / PRD` |
| Hnědý box uvnitř VPS | `Git` |
| Hnědý box nahoře uvnitř VPS | **`compose + harness`** — katalog prostředí a agentní runtime |
| Modrý svislý pruh mezi stanicemi a VPS | **`serving directors`** — distribuční vrstva, která do podů servíruje directory |
| Červený box pod VPS | `Záznamy vývoje / Rozhodovací matice` |
| Barevné linky | tři paralelní kanály stanice ↔ VPS |

**Tři paralelní linky** čtu jako tři odlišné toky, ne jako tři kabely:
- **řídicí tok** (VPS → stanice): work order, director, harness, kontext
- **datový tok** (obousměrný): git, artefakty, PRD
- **telemetrický tok** (stanice → VPS): logy, trace, náklady, rozhodnutí

### Co z upřesnění vyplývá (a co to změnilo oproti v0.1)

`serving directors` mění charakter celé řídicí vrstvy. VPS neposílá jen **data a deklaraci** ("tady máš kontext a seznam povolených agentů, nějak si poraď"). VPS posílá **spustitelnou orchestrační logiku** — directora, který v podu převezme řízení úkolu, spouští workery, rozhoduje o dalším kroku a eskaluje.

To je zásadní rozdíl, protože:

1. Agentní vrstva přestává být konfigurace a stává se **distribuovaným softwarem**. Se vším, co k tomu patří: verzování, kompatibilita, podpisy, kanály, rollback, evaluace před nasazením.
2. Řídicí vrstva potřebuje vlastní CI/CD pipeline — **pipeline, která staví to, co staví tvoje zakázky**. Tvůj požadavek na plně automatizovaný DevOps se tím uzavírá sám do sebe.
3. Vzniká bezpečnostní hranice, kterou v0.1 neměla: director je kód přicházející po síti a spouštěný na stroji vývojáře nad klientským kódem. Musí být podepsaný a musí běžet v něčem, co ho neposlechne, když si řekne o víc, než smí.

Bod 3 je nejdůležitější a je rozvedený v kapitole **L2.7** a **L7**.

`compose + harness` do sebe zapadá: VPS drží jak **topologii prostředí** (které kontejnery, jaké služby, jaká síť), tak **runtime, který directory spouští**. Pod si stáhne obojí a teprve pak dostane directora.

---

## 1. Co to vlastně je

Stavíš **interní vývojovou platformu (IDP)** s agentní vrstvou. Tři vlastnosti, které to definují:

1. **VPS je jediný zdroj pravdy.** Stanice jsou vyměnitelné. Když někomu shoří notebook, přijdeš o nic.
2. **Řídicí vrstva rozhoduje, kdo dostane co.** Ne "všichni mají přístup ke všemu", ale "tenhle vývojář v téhle fázi tohohle projektu dostane přesně tenhle kontext a tyhle agenty".
3. **Všechno relevantní teče zpátky.** Kód, transkripty agentů, rozhodnutí, náklady, časy.

To třetí je z hlediska hodnoty nejdůležitější a nejsnáze se odflákne. Pokud write-back nebude vynucený, do půl roku ho nikdo nebude dělat a zbyde ti drahý git server.

**Vztah k Tatooine:** tohle je v podstatě distribuovaná verze Tatooine. Ledger, agent team a katalog sandboxů mají v tomhle návrhu přímé protějšky. Doporučuju to nestavět vedle, ale Tatooine povýšit na control plane a přesunout z lokálu na VPS.

---

## 2. Architektonické principy (invarianty)

Tohle jsou pravidla, která nesmí padnout, jinak systém degraduje.

**P1 — VPS je autorita, stanice jsou cache.**
Nic důležitého neexistuje jen lokálně. Lokální stav je vždy odvoditelný a zahoditelný.

**P2 — Kontejner je jednorázový.**
Vývojář smaže kontejner, spustí znovu, do 5 minut je zpátky ve stejném stavu. Když to neplatí, máš skrytý stav.

**P3 — Pull, ne push.**
Kontejner si *vyžádá* práci. VPS nikam netlačí. Odpadá NAT traversal, firewall na straně vývojáře, a stanice může být offline bez rozbití systému.

**P4 — Vše je adresované obsahem.**
Kontext bundle, image, artefakt — všechno má hash. Reprodukovatelnost a cache zdarma.

**P5 — Žádná tichá degradace.**
Když se kontext nevejde do okna, běh **spadne**, netruncuje se. (Přímo z tvého problému s gemma a nomic-embed — tiché ořezání je nejdražší chyba v agentních systémech, protože vypadá jako funkční výsledek.)

**P6 — Idempotence na každém zápisu.**
Každý write-back má dedupe key + unique constraint. Stejný princip jako `XpEvent` v Učebnici. Retry nesmí duplikovat.

**P7 — Oprávnění se odvozuje z fáze, ne z osoby.**
Vývojář nemá "práva". Má *work order*, který mu na dobu úkolu propůjčí konkrétní scope.

**P8 — Každý agentní běh je přehratelný.**
Uložené vstupy + model + seed + verze promptu = můžeš to pustit znovu za půl roku.

---

## 3. Vrstvová dekompozice

```
┌─ L7  Agentní vrstva (profily, orchestrace, evaluace)
├─ L6  Governance (bezpečnost, GDPR, klientská segregace, audit)
├─ L5  Observabilita (logy, metriky, trace, náklady)
├─ L4  CI/CD (gates, build, deploy, release)
├─ L3  Dev Pod (kontejner na stanici vývojáře)
├─ L2  Control Plane (řídicí vrstva — work orders, ledger)
├─ L1  Data Plane (Git, Postgres, S3, registry, PRD)
└─ L0  Infrastruktura (VPS, síť, zálohy)
```

---

## L0 — Infrastruktura

### Volba providera a sizing

Pro 3 vývojáře + agenti + CI + observabilita:

| Profil | Specifikace | Poznámka |
|---|---|---|
| Minimum | 4 vCPU / 16 GB / 160 GB NVMe | funguje, ale CI bude škrtit |
| **Doporučeno** | **8 vCPU (dedikované) / 32 GB / 400 GB NVMe** | control plane + data + CI runner |
| Cílový stav | výše + druhý malý VPS jen na CI runnery | CI nesmí hladovět control plane |

Ceny se hýbou, tak jen řádově: dedikované 8/32 se dnes pohybuje kolem €40–70/měsíc u Hetzneru nebo srovnatelných, u českých providerů (VSHosting, Master Internet, Wedos) dráž, ale s českou fakturací a supportem. **Ověř aktuální ceník.**

**Zásadní rozhodnutí: LLM inference na VPS neběží.** Držet tam GPU je řádově dražší než celý zbytek. Inference jde buď přes API (Anthropic/OpenAI), nebo lokálně na stanici přes Ollama — což už máš. VPS orchestruje, neinferuje.

### Síť

Nevystavuj Gitea/Postgres/registry do internetu. Nikdy.

| Varianta | Pro | Proti |
|---|---|---|
| Čistý WireGuard | zdarma, jednoduchý, 3 statické peery | ruční správa klíčů, žádné ACL |
| **Tailscale** | ACL, MagicDNS, device auth, 2 min setup | závislost na cizí control plane, free tier limity |
| Headscale (self-hosted) | kontrola + funkce Tailscale | další věc k údržbě |

**Doporučení:** Tailscale. Při třech lidech je hodnota ACL a device revoke (viz tvoje zkušenost s odchodem zaměstnance) vyšší než náklad na závislost. Migrace na Headscale je později triviální.

Veřejně otevřené zůstává jen `443` na reverse proxy (Caddy — automatické TLS, konfigurace na 10 řádků) pro webhooky a případné veřejné artefakty. Vše ostatní jen přes tailnet.

### Zálohy

- **restic** → offsite S3 (Backblaze B2 / Wasabi), denně, šifrované, retenční politika 7/4/12
- Postgres: `pg_basebackup` + WAL archiving, ne jen `pg_dump`
- **Restore drill jednou za kvartál.** Záloha, kterou jsi nikdy neobnovil, není záloha.
- RTO cíl: kompletní rebuild VPS z IaC do 2 hodin

### IaC

Celý VPS popsaný jako kód od prvního dne. Ansible je pro tenhle rozsah lepší než Terraform (nemáš cloud resources, máš jeden stroj). Repo `agenticdev/infra`, playbooky idempotentní, tajemství přes `ansible-vault` nebo SOPS.

---

## L1 — Data Plane

| Komponenta | Volba | Alternativy | Proč tahle |
|---|---|---|---|
| Git + PR + CI | **Forgejo** | Gitea, GitLab CE | Forgejo Actions je kompatibilní s GH Actions syntaxí, celé to běží v ~1 GB RAM. GitLab CE sežere 8 GB. |
| Ledger | **PostgreSQL 16 + pgvector** | SQLite, Postgres + samostatná Qdrant | Jedna databáze pro relační data i embeddingy. Míň pohyblivých částí. |
| Objektové úložiště | **MinIO** | Garage, přímo B2 | S3 API, artefakty, transkripty, velké logy |
| Container registry | **Forgejo package registry** | Harbor | Harbor až když budeš chtít scanning a replikaci |
| PRD / znalosti | **Markdown v gitu + pgvector index** | Outline, Obsidian sync, Notion | Verzované, diffovatelné, agenti to čtou nativně |
| Tajemství | **SOPS + age** (repo) + Forgejo secrets (CI) | Infisical, Vault | Vault je na 3 lidi overkill. SOPS je 0 provozních nákladů. |
| **Harness** | OCI image v registry, pinovaný digestem | pip/npm balík | Harness je runtime — patří do image, ne do skriptu |
| **Directors** | repo `agenticdev/directors` → podepsané balíčky v MinIO | přímo z gitu | Potřebuješ podpis, kanály a rollback; git tag na to nestačí |
| **Compose katalog** | repo `agenticdev/pods`, per projekt | vlastní templating | Verzovaná topologie prostředí; pod launcher si ji stahuje |

### Poznámka k PRD store

Zelený box z náčrtu. Struktura, kterou doporučuju:

```
prd/
  <projekt>/
    00-context.md          # kdo je klient, co dělá, jazyk komunikace
    10-requirements.md      # funkční požadavky, číslované, stabilní ID
    20-constraints.md       # technické, legislativní, rozpočtové
    30-architecture.md      # cílový stav
    40-decisions/           # ADR, jeden soubor = jedno rozhodnutí
    50-glossary.md          # doménové pojmy klienta — kritické pro agenty
    90-phases/
      discovery.md          # co je v téhle fázi in-scope, DoD
      implementation.md
      ...
```

Glosář je nedoceněný. Agent, který nezná klientovu terminologii, generuje syntakticky správný a sémanticky špatný kód.

### Chunking a embeddingy

Tvůj problém s token limity `nomic-embed-text` je systémový, ne náhodný. Pravidla:

- Chunk po sémantických jednotkách (nadpis H2/H3), ne po fixním počtu znaků
- **Tvrdý validátor:** chunk > limit modelu → build indexu spadne, nezkrátí se
- Ukládej `chunk_hash` — reindexuj jen změněné
- Vždy měj vedle vektorového i fulltextový index (Postgres `tsvector`) a dělej hybridní retrieval. Čistě vektorové vyhledávání selhává na přesných identifikátorech (názvy funkcí, čísla požadavků).

---

## L2 — Control Plane (řídicí vrstva)

Jádro zadání. Tohle je ten modrý pruh z náčrtu.

### 2.1 Doménový model

```sql
-- Projekty a struktura práce
project        (id, client_id, code, repo_url, status, data_class, model_policy)
phase          (id, project_id, kind, order_idx, dod_ref, status)
task           (id, phase_id, kind, title, spec_ref, dod, status, risk_class)

-- Lidé a stroje
principal      (id, kind[human|agent|service], display_name, active)
workstation    (id, principal_id, device_key_fp, last_seen_at)

-- Přidělování práce
assignment     (id, task_id, principal_id, workstation_id,
                lease_expires_at, heartbeat_at, state)
work_order     (id, assignment_id, manifest_hash, issued_at, revoked_at)

-- Kontext a agenti
context_bundle (id, manifest_hash, spec_json, size_tokens, built_at)
agent_profile  (id, role, version, prompt_ref, tool_allowlist,
                model_allowlist, budget_tokens, budget_czk)
agent_run      (id, task_id, profile_id, input_hash, model, seed,
                tokens_in, tokens_out, cost_czk, duration_ms,
                outcome, transcript_uri)

-- Výstupy a rozhodnutí
artifact       (id, task_id, kind, uri, sha256, created_by, created_at)
decision       (id, task_id, question, options_json, criteria_json,
                weights_json, chosen, rationale, decided_by, decided_at,
                state[auto|pending_human|approved|rejected])

-- Auditní stopa
event          (id, ts, actor_id, subject_type, subject_id, verb,
                payload_jsonb, dedupe_key, prev_hash, hash)
```

`event` je append-only, bez UPDATE a DELETE (vynuceno na úrovni rolí v Postgresu). `prev_hash`/`hash` tvoří hash chain — o tom níž v L6.

`UNIQUE (subject_type, subject_id, verb, dedupe_key)` řeší idempotenci. Stejný vzor jako `XpEvent`.

### 2.2 Kontrakt: Work Order

Tohle je centrální artefakt celého systému. Kontejner na stanici si o něj řekne, dostane podepsaný JSON:

```jsonc
{
  "work_order_id": "wo_01J...",
  "issued_at": "2026-08-07T09:12:00Z",
  "expires_at": "2026-08-07T13:12:00Z",

  "task": {
    "id": "tsk_...",
    "project": "montexbau",
    "phase": "implementation",
    "kind": "feature",
    "risk_class": "standard",
    "title": "Import zaměstnaneckých karet z DE systému",
    "spec_ref": "prd/montexbau/10-requirements.md#REQ-042",
    "dod": [
      "unit testy pokrývají mapování polí",
      "integrační test proti fixture DE exportu",
      "ADR pro volbu parseru"
    ]
  },

  "repo": {
    "url": "git@vps:agenticdev/montexbau.git",
    "base_ref": "main@a3f91c2",
    "work_branch": "task/tsk_.../wip",
    "write_scope": ["src/import/**", "tests/import/**", "prd/montexbau/40-decisions/**"]
  },

  "context_bundle": {
    "manifest_hash": "sha256:7c1e...",
    "budget_tokens": 120000,
    "items": [
      {"uri": "s3://ctx/7c1e/00-context.md", "sha256": "...", "tokens": 1840},
      {"uri": "s3://ctx/7c1e/50-glossary.md", "sha256": "...", "tokens": 2210}
    ]
  },

  // ─── to, co servíruje modrý pruh z náčrtu ───
  "runtime": {
    "compose": {
      "ref": "pods/montexbau/compose.yaml@v12",
      "sha256": "..."
    },
    "harness": {
      "image": "registry.vps/agenticdev/harness@sha256:9b2f...",
      "api_version": "5.3.0"
    },
    "director": {
      "id": "feature-director",
      "version": "5.1.2",
      "channel": "stable",
      "uri": "s3://directors/feature-director-5.1.2.tar.zst",
      "sha256": "...",
      "signature": "cosign:...",
      "requires_harness": "^5.2"
    }
  },

  // workery, které director SMÍ spustit — nic víc
  "worker_pool": [
    {"role": "architect",   "profile": "architect@3.2",   "budget_czk": 40},
    {"role": "implementer", "profile": "implementer@5.1", "budget_czk": 180},
    {"role": "reviewer",    "profile": "reviewer@2.8",    "budget_czk": 60}
  ],

  // vynucuje HARNESS, ne director — director tyhle hodnoty nemůže přepsat
  "policy": {
    "model_allowlist": ["claude-sonnet-5", "local/qwen2.5-coder:32b"],
    "egress_allowlist": ["api.anthropic.com", "registry.npmjs.org", "vps.tailnet"],
    "human_gate": ["schema_migration", "dependency_add", "prod_deploy"],
    "max_wall_clock_min": 240,
    "budget_czk_total": 320,
    "max_loop_iterations": {"implement_test": 5, "review_rework": 3}
  },

  "telemetry": {
    "otlp_endpoint": "https://vps.tailnet/otlp",
    "token": "<short-lived JWT>"
  },

  "signature": "ed25519:..."
}
```

Čti to pozorně — je v tom celé zadání:
- **"přiděluje informace"** → `context_bundle`
- **"části agentního systému"** → `runtime.director` + `worker_pool`
- **"na základě projektu, fáze, úkonu"** → director se vybírá z trojice `task.project` / `task.phase` / `task.kind`
- **write-back** → `telemetry` + `repo.work_branch`

**Nejdůležitější řádek celého dokumentu:** `policy` vynucuje **harness**, ne director. Director je pro harness nedůvěryhodný vstup — může si o cokoli říct, ale harness ho neposlechne, když to není v politice. Kdyby politiku vynucoval director, stačilo by jedno špatné nasazení (nebo prompt injection v jeho vstupu) a máš agenta s neomezeným rozpočtem a volným internetem nad klientským kódem.

Sémantika verzí: `harness` je pinovaný digestem (immutable), `director` verzí + hashem + podpisem. Work order je tím kompletně reprodukovatelný — za rok umíš postavit bit-identické prostředí a přehrát běh.

### 2.3 Fázové brány (co dostaneš v které fázi)

| Fáze | Kontext | Agenti | Zápis do repa | Brána |
|---|---|---|---|---|
| Discovery | klient, byznys kontext, konkurence | researcher, analyst | jen `prd/**` | člověk schvaluje scope |
| Design | requirements, constraints, ADR | architect, ui/ux | `prd/**`, `design/**` | člověk schvaluje architekturu |
| Implementation | spec, glosář, existující kód | implementer, reviewer, tester | `src/**`, `tests/**` | automatické CI gates |
| Hardening | + bezpečnostní politiky | security, perf, qa | `src/**`, `infra/**` | člověk schvaluje release |
| Delivery | + dokumentace, runbooky | doc-writer, releaser | `docs/**` | člověk |
| Support | + provozní logy, incidenty | oncall, debugger | hotfix branch | člověk u prod zásahu |

Tohle je přesně to, co jsi chtěl. Vývojář v discovery fázi *fyzicky nemůže* commitnout do `src/` — nedostal scope.

### 2.4 Rozhodovací matice

Červený box z náčrtu. Když agent narazí na volbu, kterou nemá v politice pokrytou:

1. Vytvoří `decision` řádek: otázka, varianty, kritéria, váhy, doporučení
2. Stav = `pending_human`, úkol se **blokuje**
3. Notifikace (ntfy / Slack)
4. Ty rozhodneš → `approved` + rationale
5. Rozhodnutí se **materializuje jako ADR** do `prd/<projekt>/40-decisions/`
6. Podobná rozhodnutí se příště nabízejí jako precedent (vector search nad `decision.question`)

Ten šestý krok je důvod, proč to stavět. Po roce máš korpus rozhodnutí, který agentům dává tvůj vkus místo generického. To je aktivum, které nikdo jiný nemá.

### 2.5 Protokol

| Vrstva | Volba | Poznámka |
|---|---|---|
| Řídicí API | HTTP/JSON přes tailnet, OIDC token | jednoduché, debugovatelné |
| Události | Postgres `LISTEN/NOTIFY` | pro 3 stanice naprosto stačí |
| Telemetrie | OTLP (OpenTelemetry) | standard, ne vlastní formát |
| Alternativa při růstu | NATS JetStream | až když bude 10+ stanic |

**Nedělej NATS hned.** Postgres LISTEN/NOTIFY zvládne tvůj objem o dva řády. Přidat NATS později je půl dne práce.

### 2.6 Control Plane jako MCP server

Silné doporučení: řídicí vrstvu vystav **taky jako MCP server**. Agenti v kontejneru pak dostanou nástroje:

- `get_work_order()` — co mám dělat
- `query_prd(question)` — hybridní retrieval nad PRD projektu
- `record_decision(question, options, chosen, rationale)`
- `submit_artifact(kind, path)`
- `request_human_gate(reason)`
- `report_progress(dod_item, status)`

Tím se write-back přestane spoléhat na disciplínu vývojáře a stane se z něj nástroj, který agent volá přirozeně. Vynucení přes API místo přes proces je jediný způsob, jak to dlouhodobě přežije.

### 2.7 Distribuce harness a directorů

Tohle je kapitola, která ve v0.1 chyběla a je přímým důsledkem `serving directors`.

#### Mechanismus vs. politika

| | **Harness** | **Director** | **Worker** |
|---|---|---|---|
| Co to je | runtime substrát | orchestrační politika | jeden agentní běh |
| Mění se | zřídka (týdny) | často (dny) | často |
| Distribuce | OCI image, digest | podepsaný balíček | prompt v balíčku directora |
| Důvěra | **TCB — plně důvěryhodný** | polodůvěryhodný | nedůvěryhodný |
| Blast radius při chybě | systémový | jeden typ úkolu | jeden běh |
| Kdo vynucuje politiku | **on** | nikdo | nikdo |

Harness obsahuje: LLM klient s vynucením `model_allowlist`, registr a sandbox nástrojů, sestavení kontextu a rozpočet tokenů (tvrdý fail), MCP klient, OTel instrumentaci, idempotentní write-back klienta, respektování kill switche, účtování nákladů, řízení lease a heartbeatu.

Director obsahuje: stavový automat úkolu, mapování stav → worker, definice bran, alokaci rozpočtu mezi kroky, eskalační pravidla, verifikaci DoD.

**Tenhle řez je celý smysl rozdělení.** Můžeš měnit orchestraci každý den bez přestavby image a bez rizika, že si tím rozbiješ bezpečnostní vlastnosti systému.

#### Příklad: `feature-director@5.1`

```
INTAKE ──▶ PLAN ──[gate: plan_review]──▶ IMPLEMENT ⇄ TEST ──▶ REVIEW ──▶ SUBMIT ──▶ DONE
                        │                     ▲        │          │
                        │                     └─rework─┘          │
                        ▼                     (max 5×)      [gate: human
                  DECISION (pending_human)                   if risk≥elevated]
                                                                   │
                                                             rework (max 3×)
```

Pravidlo, které si napiš na zeď: **každý cyklus ve stavovém automatu musí mít omezený počet iterací a definovanou cestu při vyčerpání.** Neomezené rework smyčky jsou způsob, jak dostat účet za 400 € za zaškrtávátko. Při vyčerpání limitu se nezkouší dál — vznikne `decision` řádek a čeká se na člověka.

#### Kanály a nasazování

Directors se nasazují jako software, protože software to je:

| Kanál | Kdo ho dostává | Účel |
|---|---|---|
| `canary` | jen tvoje stanice | první ostré nasazení |
| `beta` | ty + jeden vývojář | 2–3 dny reálného provozu |
| `stable` | všichni | výchozí |

Promotion mezi kanály je automatická po splnění prahů (golden tasks pass rate, cena, počet eskalací), nebo ruční. Rollback = control plane přepne ukazatel kanálu na předchozí verzi; **rozběhnuté úkoly dojedou na staré verzi**, protože work order má verzi napevno.

Pipeline directora (běží ve stejném CI jako zakázky):

```
lint promptů → statická validace stavového automatu (dosažitelnost, cykly, limity)
  → golden tasks eval → porovnání s baseline (pass rate, cena, kroky)
  → podpis (cosign) → upload do MinIO → registrace verze v ledgeru
  → promote canary
```

Statická validace automatu je levná a chytí tři nejčastější chyby: nedosažitelný stav, cyklus bez limitu, stav bez východu při selhání.

#### Bezpečnostní kontrakt

1. Harness ověří **podpis** balíčku directora před spuštěním. Neověřený = pod se nespustí, událost do auditu.
2. Director běží ve stejném procesu jako harness, ale **nemá přístup k síti ani k secrets** — všechno jde přes harness API.
3. Director nemůže rozšířit `worker_pool`, `model_allowlist`, `egress_allowlist` ani rozpočet. Může jen čerpat z toho, co dostal.
4. Kompatibilita: control plane odmítne vydat work order s dvojicí harness/director, která nesplňuje `requires_harness`. Matice kompatibility je v ledgeru.
5. Kill switch: harness posílá heartbeat. Odebrání lease → director se zastaví na nejbližší hranici kroku, stav se checkpointuje na VPS, pod se ukončí čistě.

Bod 5 je odpověď na námitku "když director běží u vývojáře, jak ho zastavím". Zastavíš ho tím, že mu přestaneš prodlužovat oprávnění, ne tím, že mu pošleš příkaz.

---

## L3 — Dev Pod (kontejner na stanici)

### Základ

**Devcontainer spec** (`devcontainer.json`) — funguje s VS Code, Cursor, JetBrains i čistým CLI. Image se **staví v CI na VPS**, pushuje do registry, na stanici se pinuje digestem. Vývojář image nikdy nestaví lokálně — jinak máš tři různá prostředí a "u mě to jede".

### Startup sekvence

Na stanici vývojáře je nainstalovaná **jediná věc: launcher** (`agenticdev pod up <projekt>`). Ani Docker image, ani harness, ani directors — všechno si stáhne. Tím je onboarding nové stanice otázkou dvou příkazů.

```
── řídí LAUNCHER (na hostu) ──
1.  AUTH        device key (age/ed25519) → control plane → krátkodobý JWT
2.  FETCH       GET /work-orders/next → podepsaný work order
3.  VERIFY      ověření podpisu work orderu, kontrola expirace a kompatibility
4.  PULL        compose@ref  (ověření sha256)
                harness@digest  (docker pull, immutable)
                director balíček  (ověření cosign podpisu — jinak STOP)
5.  UP          docker compose up: pod + egress-proxy + služby projektu

── řídí HARNESS (v podu) ──
6.  GUARD       egress proxy nabíhá první, allowlist z policy.egress_allowlist
7.  MATERIALIZE git clone/fetch @ base_ref → work_branch
                context_bundle → /ctx (ro, ověření sha256 každé položky)
                secrets → /run/secrets (tmpfs, TTL)
8.  BUDGET      spočítání tokenů kontextu; překročení = tvrdý fail (P5)
9.  LOAD        načtení directora, kontrola requires_harness, sandbox
10. STREAM      OTLP export logů/trace/nákladů → VPS (od tohoto bodu kontinuálně)

── řídí DIRECTOR ──
11. ORCHESTRATE stavový automat: spouštění workerů z worker_pool,
                checkpoint stavu na VPS při každém přechodu,
                brány → decision řádky, eskalace
12. GATE        lokální brány: lint, typecheck, unit testy
13. SUBMIT      push branch, otevření PR, upload artefaktů, zápis decisions

── řídí LAUNCHER ──
14. RELEASE     uvolnění lease, teardown compose stacku
```

Krok 11 je nový oproti v0.1. **Checkpoint při každém přechodu stavu** je to, co dělá systém odolným: když vývojáři spadne notebook uprostřed úkolu, na VPS je poslední konzistentní stav a práce se dá obnovit na jiné stanici. Bez toho je pád stanice ztráta rozdělané práce.

Krok 6 před krokem 7 je záměrný. Egress proxy musí běžet dřív, než se do podu dostane jakýkoli klientský obsah.

### Izolace a egress

Tohle je bod, který se běžně podceňuje. **Agent se síťovým přístupem je exfiltrační kanál.** Pokud v kontejneru běží agent s klientským kódem a má volný internet, jedna prompt injection ve vstupních datech znamená únik.

Řešení: druhý kontejner ve stejné compose síti jako **egress proxy** (mitmproxy nebo Squid) s allowlistem domén z work orderu. Agent nemá výchozí bránu jinam. Blokovaný požadavek se loguje jako bezpečnostní událost.

(Mimochodem přesně tenhle vzor používá prostředí, ve kterém běžím já — allowlist domén na proxy s návratovým důvodem odmítnutí. Funguje.)

### Filesystem layout

```
/workspace       git repo, work branch          (rw, ale scope-omezený hookem)
/ctx             context bundle                 (ro, ověřený hashem)
/run/secrets     krátkodobá tajemství           (tmpfs, ro, TTL)
/var/pod/cache   npm/pip/uv/model cache         (named volume, přežívá restart)
/var/pod/out     artefakty před uploadem        (rw)
```

Pouze `/var/pod/cache` přežívá zničení podu. Všechno ostatní je odvoditelné.

### Vynucení write scope

Pre-commit hook + server-side hook ve Forgejo, který ověří, že změněné cesty odpovídají `repo.write_scope` z aktivního work orderu. Klientská kontrola je pohodlí, serverová je bezpečnost. Potřebuješ obě.

### Offline režim

Vývojář ve vlaku. Work order má TTL 4 hodiny → do vypršení může pracovat proti lokální cache. Write-back se řadí do lokální fronty (SQLite) a odešle se při obnovení spojení, idempotentně (viz P6). Po vypršení TTL se pod přepne do read-only.

---

## L4 — CI/CD

### Runner topologie

Forgejo Actions runner v Dockeru na VPS. **Od začátku počítej s tím, že CI přesuneš na samostatný stroj** — build kontejnerů umí sežrat všechnu paměť a shodit ti control plane. Než na to dojde, dej runneru cgroup limit (max 50 % CPU, 40 % RAM).

### Pipeline — PR gates

| Krok | Nástroj | Blokuje merge |
|---|---|---|
| Lint + format | biome / ruff / gofmt | ano |
| Typecheck | tsc / mypy | ano |
| Unit testy | vitest / pytest | ano |
| Coverage práh | | ano (nesnižovat oproti main) |
| Secret scan | **gitleaks** | ano |
| SAST | **semgrep** | ano (jen high) |
| Závislosti (CVE) | **osv-scanner** / trivy | ano (critical) |
| Licence | licensee / scancode | varování |
| Kontrola DoD | vlastní: DoD položky z work orderu vs. `report_progress` | ano |
| Kontrola provenance | každý commit má `Task-Id:` trailer a existující `agent_run` | ano |

Poslední dva jsou tvoje specialita a nemá je nikdo. Kontrola provenance znamená, že **nelze mergnout kód, který nemá v ledgeru záznam odkud se vzal**. Přesně tohle by ti ušetřilo nervy v té kauze s bývalým zaměstnancem.

### Pipeline — build & release

```
build → BuildKit s remote cache do registry
SBOM  → syft → přiloženo k image
sign  → cosign (keyless nebo s age klíčem)
push  → registry, adresováno digestem
```

Deploy nikdy netagem, vždy digestem. `latest` je zakázané slovo.

### Deploy

| Prostředí | Kam | Trigger | Schválení |
|---|---|---|---|
| Preview | VPS, ephemeral, `pr-<n>.dev.example.com` | otevření PR | ne |
| Staging | VPS | merge do `main` | ne |
| Produkce | klient / VPS | tag `v*` | **ano, člověk** |

Pro deploy doporučuju **Dokploy** nebo **Komodo** — self-hosted PaaS nad compose, dá ti UI, rollback a webhooky bez psaní vlastní deploy logiky. Coolify je alternativa, ale je těžší.

Preview prostředí na PR (wildcard DNS + Traefik) je označené jako nice2have, ale u agentního vývoje je to spíš must-have: bez něj nedokážeš rychle posoudit, co agent vlastně vyrobil.

### Větvení a releasy

- Trunk-based, krátkodobé větve, jedna větev = jeden task
- Conventional Commits + `Task-Id:` trailer
- `release-please` generuje changelog a semver automaticky
- Migrace databáze: forward-only, testované proti seedovanému snapshotu produkce v CI

---

## L5 — Observabilita

### Stack

| Doména | Nástroj | Poznámka |
|---|---|---|
| Logy | **Loki** + Alloy | levné na disk, dobré retention politiky |
| Metriky | **Prometheus** + node/cadvisor/postgres exporter | |
| Trace | **Tempo** + OpenTelemetry Collector | |
| Dashboardy | **Grafana** | |
| Alerty | Alertmanager → **ntfy** (self-hosted) | ntfy je 20 MB kontejner, push na mobil zdarma |

Celý stack se vejde do ~3 GB RAM. Alternativa, pokud chceš míň součástek: **SigNoz** (all-in-one, ClickHouse pod tím), ale je náročnější na paměť.

### Klíčová myšlenka: agentní běh je distribuovaný trace

Nedělej vlastní formát logů pro agenty. Modeluj to jako OTel spany:

```
trace: task tsk_...
 └─ span: agent_run (implementer@5.1)
     ├─ span: context_load        [tokens=112k, cache_hit=true]
     ├─ span: llm_call            [model, tokens_in/out, cost_czk, latency]
     ├─ span: tool_call fs.write  [path, bytes]
     ├─ span: tool_call test.run  [exit=1, failed=3]
     ├─ span: llm_call            [oprava]
     └─ span: tool_call git.commit
```

Dostaneš zdarma: waterfall vizualizaci, kde agent trávil čas, kde hořely tokeny, které nástroje selhávají. Debugování agentů bez tracingu je hádání.

### Dashboardy, které chceš mít

1. **Ekonomika projektu** — náklady na tokeny × projekt × fáze, proti tvé blended sazbě 334 Kč/h. Konečně budeš vědět, jestli se agentní vývoj u konkrétní zakázky vyplácí, a to daty, ne pocitem. Tohle jde přímo do tvých ROI kalkulaček.
2. **Cycle time** — od `task.created` po `merged`, rozpad po fázích. Ukáže, kde je úzké hrdlo.
3. **DORA** — deploy frequency, lead time, MTTR, change failure rate.
4. **Kvalita agentů** — % běhů, které projdou CI na první pokus, po profilech a verzích. Regrese promptu uvidíš do hodiny.
5. **Human gate latence** — jak dlouho čekají rozhodnutí na tebe. Když je to medián 6 hodin, jsi ty úzké hrdlo.

### Retence

- Metriky: 90 dní (Prometheus), agregáty 2 roky
- Logy: 30 dní hot v Loki, pak do S3
- Trace: 14 dní plné, sampling 10 % na 1 rok
- **Transkripty agentů: neomezeně** (v S3, komprimované). Jsou to tvoje trénovací a auditní data.
- `event` tabulka: neomezeně, po roce partition + archivace

---

## L6 — Governance, bezpečnost, právo

### Segregace klientských dat

Nejtvrdší požadavek celého systému. Realizace:

- Jedna Forgejo organizace na klienta, členství per projekt
- Prefixy v MinIO per projekt, samostatné politiky
- Postgres row-level security podle `project_id`
- Kontext bundle **nikdy** neobsahuje data jiného projektu (validace při buildu bundlu)
- Klientská tajemství v samostatných SOPS souborech s vlastním age klíčem

### Politika modelů podle klasifikace dat

Tohle je konkrétní ovládací prvek, ne fráze:

| `data_class` | Povolené modely | Typický případ |
|---|---|---|
| `public` | cokoli | interní nástroje, open source |
| `internal` | cloud API s DPA | většina zakázek |
| `confidential` | cloud API s DPA + zero retention | finanční data, PREDICOR |
| `restricted` | **jen lokální Ollama** | zdravotnictví, osobní údaje pacientů |

Vynuceno v `policy.model_allowlist` ve work orderu. Pod fyzicky nedostane API klíč pro model, který není povolený. U zdravotnických zakázek (NIS/AIS kontext) je tohle rozdíl mezi "můžeme to vzít" a "nemůžeme".

### GDPR

- DPA s poskytovatelem LLM API, ověř data residency a retention
- Záznam o činnostech zpracování musí zmínit LLM zpracovatele
- Anonymizační filtr na vstupu do kontext bundlu (regex + NER na jména, rodná čísla, adresy) — ne jako jediná ochrana, ale jako druhá vrstva
- Právo na výmaz vs. neměnný audit log: řeš pseudonymizací, ne mazáním

**NIS2 / český zákon o kybernetické bezpečnosti:** pokud budeš dodávat zdravotnictví nebo dopravu, můžeš spadnout pod požadavky na dodavatelský řetězec. **Neověřuji zde aktuální stav legislativy — konzultuj s právníkem**, protože se to v posledních letech měnilo a nechci ti dávat zastaralou informaci.

### Auditní řetěz a důkazní hodnota

Vzhledem k tomu, čím sis prošel s bývalým zaměstnancem, tohle stojí za nadstandardní pozornost:

1. `event` tabulka je hash chain: `hash = sha256(prev_hash || payload)`
2. Denně se kořenový hash + `git rev-parse HEAD` všech repozitářů zapíše do denního manifestu
3. Manifest se **kvalifikovaně orazítkuje** (I.CA / PostSignum, TSA API)
4. Orazítkované manifesty se ukládají offsite

Výsledek: kdykoli později umíš prokázat, že konkrétní kód existoval v konkrétní čas a kdo (nebo který agent) ho vytvořil, s důkazní silou kvalifikovaného časového razítka. Náklad: pár korun denně a jeden cron.

### Offboarding

Checklist jako kód, ne jako vzpomínka:
- revoke device key v Tailscale + control plane
- rotace všech secrets, ke kterým měl přístup
- audit `event` tabulky za posledních 90 dní (co stahoval)
- odebrání z Forgejo organizací
- export jeho `agent_run` a `decision` záznamů (zůstávají firmě)

---

## L7 — Agentní vrstva

### Katalog directorů

Director se vybírá podle trojice `(projekt, fáze, druh úkolu)`. Výchozí katalog:

| Director | Fáze | Spouští workery | Typický počet kroků |
|---|---|---|---|
| `discovery-director` | discovery | researcher, analyst | 4–8 |
| `design-director` | design | architect, ui-ux | 3–6 |
| `feature-director` | implementation | architect, implementer, tester, reviewer | 8–20 |
| `bugfix-director` | implementation / support | debugger, implementer, tester | 4–10 |
| `refactor-director` | implementation | architect, implementer, tester | 6–15 |
| `hardening-director` | hardening | security, perf, qa | 5–12 |
| `delivery-director` | delivery | doc-writer, releaser | 3–6 |

Projekt může director přepsat (`project.director_overrides`) — např. u zdravotnického klienta poběží `feature-director-restricted`, který má víc lidských bran a jen lokální modely.

**Nezačínej se sedmi directory.** Napiš `feature-director` a `bugfix-director`, pusť je měsíc na reálné práci a teprve pak štěp. Předčasná specializace directorů je stejná chyba jako předčasná abstrakce v kódu.

### Workeři: role a profily

Worker je list stromu — jedno volání modelu s nástroji, bez vlastní orchestrace. Director rozhoduje *kdy*, worker *jak*.

| Role | Vstup | Výstup | Fáze |
|---|---|---|---|
| `researcher` | otázka, web, PRD | rešerše s citacemi | discovery |
| `analyst` | rešerše, klient | požadavky, číslované | discovery |
| `architect` | požadavky, constraints | architektura + ADR | design |
| `implementer` | spec, glosář, kód | diff + testy | implementation |
| `reviewer` | diff | review komentáře, blokace | implementation |
| `tester` | spec, diff | testy, fixtures | implementation |
| `security` | diff, závislosti | nálezy | hardening |
| `doc-writer` | kód, ADR | dokumentace, runbook | delivery |
| `releaser` | changelog | release notes, deploy | delivery |

Profil = `{system prompt, tool allowlist, model allowlist, budget, verze}`. **Profily jsou v gitu a mění se přes PR jako kód.** Změna promptu bez review je změna produkčního systému bez review.

### Sestavování kontextu

Deterministické, jinak nic nereprodukuješ:

```
bundle = f(project, phase, task_kind, task_spec_ref)
manifest_hash = sha256(seřazený seznam (uri, sha256))
cache_key = sha256(manifest_hash || profile_version || model)
```

Rozpočet tokenů se počítá **před** odesláním. Překročení = tvrdý fail s hláškou, které soubory ho způsobily. Žádné tiché ořezání (P5).

### Řešení KV cache thrashingu

Tvůj známý problém. Konstrukce promptu musí mít stabilní prefix:

```
[stabilní prefix — cachovaný]     system prompt, glosář, architektura
[semi-stabilní]                   spec úkolu
[volatilní — na konci]            aktuální stav kódu, historie kroků
```

Když měníš věci na začátku promptu, invaliduješ celou KV cache při každém kroku. Když měníš jen konec, prefix zůstane v cache. Rozdíl v latenci i ceně je řádový.

### Souběžnost

Dva agenti na stejném souboru = konflikt. Nejjednodušší řešení, které funguje: **jeden task = jedna větev = jeden agent zapisující**. Reviewer a tester běží read-only nad tou větví. Neřeš zamykání na úrovni souborů, není to potřeba a stojí to hodně složitosti.

### Evaluace

Bez toho jsi slepý vůči regresím. A od chvíle, kdy VPS distribuuje directory na cizí stanice, je evaluace **podmínkou nasazení**, ne luxusem.

- **Golden tasks:** 15–30 uzavřených úkolů z reálných zakázek, s ověřitelným výsledkem
- Běží v CI při každé změně `agent_profile` **i `director`**
- Metriky: pass rate, cena, počet lidských bran, počet kroků, počet vyčerpaných smyček
- Práh pro promotion do `stable`: pass rate ≥ baseline, cena ≤ baseline + 20 %, žádný nový nekonečný cyklus
- Eval běhy jsou přehratelné (P8) — když něco spadne, umíš to reprodukovat

Rozdělení evaluací podle vrstvy:

| Vrstva | Co testuješ | Jak |
|---|---|---|
| Worker | kvalita jednoho výstupu | prompt eval, srovnání s referencí |
| **Director** | **kvalita rozhodování o postupu** | golden task end-to-end, počet kroků, cena |
| Harness | funkčnost mechanismu | běžné unit/integrační testy |

Prostřední řádek se nejčastěji zanedbává. Director s dobrými workery a špatným stavovým automatem vyrobí správný výsledek za pětinásobek peněz.

### Rozpočty a kill switch

- Rozpočet na task (CZK i tokeny) ve work orderu, vynucený **harnessem** v runtime
- Alokace rozpočtu mezi stavy dělá director, ale **strop drží harness**
- Rozpočet na projekt na měsíc
- Alert při 80 % rozpočtu
- **Kill switch dvoustupňový:**
  - měkký: control plane přestane vydávat nové work ordery
  - tvrdý: revokace aktivních lease → běžící directors se zastaví na nejbližším checkpointu (do ~60 s)

---

## 4. Rizika a anti-patterns

| # | Riziko | Dopad | Mitigace |
|---|---|---|---|
| R1 | **VPS je SPOF** | vysoký | zálohy + IaC + restore drill; git clone na každé stanici je de facto replika |
| R2 | **Over-engineering na 3 lidi** | vysoký | fázovaná roadmapa níž; nestav L7 dřív než L1 |
| R3 | **Write-back se přestane dělat** | vysoký | vynutit přes API/MCP, ne přes proces; CI gate na provenance |
| R4 | Latence při stahování kontextu | střední | content-addressed cache na stanici, mění se jen delta |
| R5 | Únik tokenů / nákladů | střední | rozpočty, alerty, kill switch |
| R6 | Prompt injection z klientských dat | **vysoký** | egress allowlist, agent nemá secrets, human gate na citlivé akce |
| R7 | Zahlcení ledgeru telemetrií | nízký | sampling, retenční politika, partitioning |
| R8 | Bus factor = 1 (ty) | **vysoký** | runbooky, IaC, dokumentace v `docs/` jako součást DoD |
| R9 | Agent generuje kód, kterému nikdo nerozumí | střední | reviewer profil + povinný lidský review u `risk_class >= elevated` |
| R10 | Vendor lock na jeden LLM | nízký | model allowlist podporuje víc providerů od začátku |
| R11 | **Vadný director se rozjede na všech stanicích** | vysoký | kanály canary/beta/stable, golden tasks jako brána, rollback přes ukazatel kanálu |
| R12 | **Neomezená smyčka directora** | vysoký | `max_loop_iterations` vynucené harnessem, statická validace automatu v CI, rozpočtový strop |
| R13 | Rozjetá kompatibilita harness × director | střední | `requires_harness` semver, matice v ledgeru, control plane odmítne nekompatibilní pár |
| R14 | Podvržený director (dodavatelský řetězec) | střední | cosign podpis, harness odmítne nepodepsaný balíček, MinIO jen přes tailnet |
| R15 | **Politika se přesune z harnessu do directora** | **vysoký** | architektonický test v CI: director nesmí importovat síťové ani secret API |

**R2, R8 a R15 jsou ty, které tenhle projekt reálně zabijou.** R15 je zákeřný, protože se to stane postupně — jednou uděláš výjimku "jen pro tenhle případ" a za rok je politika rozsypaná ve dvaceti directorech. Ohlídej to testem, ne disciplínou.

---

## 5. Roadmapa

Odhady jsou v člověkodnech tvé práce, ne kalendářních dnech.

| Fáze | Obsah | Odhad | Hodnota po dokončení |
|---|---|---|---|
| **F0** | VPS, Tailscale, Caddy, Forgejo, Postgres, restic, Ansible | 3–4 dny | máš zdroj pravdy a zálohy |
| **F1** | Launcher, compose katalog, pod image, egress proxy, ruční work order jako JSON v gitu | 3–5 dnů | reprodukovatelné prostředí pro všechny tři |
| **F2** | Control plane API, ledger, work orders, leases, idempotentní write-back | 6–8 dnů | **jádro zadání funguje** |
| **F3** | CI gates, registry, SBOM, staging deploy | 4–5 dnů | kvalita je vynucená, ne doufaná |
| **F4** | Loki/Prometheus/Tempo/Grafana, OTel v podu, nákladová telemetrie | 3–4 dny | vidíš, co se děje a co to stojí |
| **F5a** | **Harness**: LLM klient, sandbox nástrojů, rozpočty, vynucení politiky, MCP klient | 5–8 dnů | máš důvěryhodný základ, na kterém se dá stavět |
| **F5b** | **Directors**: stavový automat, `feature-director` + `bugfix-director`, brány, rozhodovací matice | 5–8 dnů | **agentní vrstva funguje** |
| **F5c** | **Distribuce**: podpisy, kanály, kompatibilita, rollback, pipeline directorů | 3–4 dny | můžeš to bezpečně pustit na cizí stanice |
| **F6** | Preview prostředí, evaluace, hash chain + časová razítka, precedenty rozhodnutí | 5–7 dnů | nice2have, ale F6 je tvoje konkurenční výhoda |

**Celkem ~34–49 člověkodnů** do plné podoby. F0–F2 (~13–17 dnů) je minimální životaschopná verze, která splňuje jádro zadání.

**Nedělej to lineárně za sebou.** Udělej F0, pak F1, a pak jeď F2 a F3 souběžně — CI potřebuješ dřív, než si myslíš.

**F5c nepřeskakuj**, ani když to bude vypadat jako byrokracie. Než jsi sám, spouštíš directory jen u sebe a podpisy jsou zbytečné. Ve chvíli, kdy je pošleš na stanici partnerky a třetího vývojáře, distribuuješ spustitelný kód po síti nad klientskými daty. Bez F5c to je díra, kterou uvidíš až ve chvíli, kdy jí něco proteče.

---

## 6. NICE2HAVE (nezařazeno do roadmapy)

Seřazeno podle poměru hodnota/náklad:

1. **Precedenty rozhodnutí** (vector search nad `decision`) — po roce máš firemní know-how strojově čitelné. Nejvyšší dlouhodobá hodnota.
2. **Automatický status report klientovi** — z ledgeru se generuje týdenní PDF na tvůj branded letterhead. Máš už pipeline na PDF (LAGARDE), tohle je jen data source navíc.
3. **Nákladová atribuce do fakturace** — token cost per project → podklad pro fakturaci nebo aspoň pro cenotvorbu příští zakázky.
4. **Ephemeral preview per PR** — u agentního vývoje spíš must-have.
5. **Chaos drill** — jednou za kvartál shodit VPS a obnovit ze zálohy. Zjistíš, co v runbooku chybí.
6. **Onboarding pod** — nový člověk dostane work order typu `onboarding`, projde ho a je produktivní. Navazuje na tvůj CEO onboarding dokument.
7. **Renovate bot** — automatické PR na aktualizace závislostí, mergované automaticky, když projdou gates.
8. **Statusová stránka** interní (Gatus / Uptime Kuma) — 30 minut práce.
9. **Napojení na M.I.K.E./WhisperFlow** — diktovaná poznámka → automaticky `task` v ledgeru. Máš už STT pipeline.
10. **Zrcadlení gitu na externí forge** (šifrovaně) — pojistka proti R1.

---

## 7. Rozhodnutí, která potřebuju od tebe

Vyřešeno v v0.2: `compose + harness`, `serving directors`. Zbývá:

**K directorům (nové, blokuje F5):**

1. **Je director deklarativní, nebo kód?** YAML stavový automat interpretovaný harnessem je bezpečnější a snáz validovatelný, ale narazíš na strop expresivity. Python modul v sandboxu je mocnější, ale těžší uhlídat. **Doporučuju deklarativní s možností volat pojmenované predikáty** — 90 % případů zvládne YAML.
2. **Je harness nový kód, nebo úprava existujícího?** Pokud Tatooine už má agent runtime, harness je jeho refaktor, ne greenfield. Mění to odhad F5a řádově.
3. **Kolik directorů reálně potřebuješ na start?** Moje doporučení jsou dva. Pokud si myslíš víc, řekni proč — možná mi uniká typ práce, který dělá jiný tvar.

**Zbývá z v0.1:**

4. **Kdo jsou ti tři vývojáři?** Ty + partnerka + kdo? Ovlivňuje to role, fázové brány i to, kdo je v kanálu `beta`.
5. **Poběží workery na cloud API, lokálním Ollama, nebo mix?** Ovlivňuje sizing stanic i politiku dat.
6. **Je mezi cílovými klienty někdo se zdravotnickými nebo jinak citlivými daty?** Pokud ano, `restricted` třída a `feature-director-restricted` musí být v návrhu od začátku, ne dolepené.
7. **Máš rozpočtový strop na VPS/měsíc?**
8. **Chceš Tatooine povýšit na control plane, nebo stavět vedle?** Doporučuju povýšit — a s upřesněním o harnessu to platí ještě víc, protože Tatooine už ten runtime nejspíš z části má.
9. **Jak moc ti záleží na tom auditním řetězu s razítky?** Je to 1 den práce navíc a mění to důkazní pozici při případném sporu.

---

## 8. Co bych na tvém místě udělal jako první

Ne architekturu. **Napiš stavový automat jednoho directora — `feature-director` — jako YAML a projeď podle něj ručně jeden reálný task.** Ty sám, bez harnessu, bez control plane, s work orderem jako JSON souborem v gitu. Na papíře odškrtávej stavy a zapisuj, kolik kroků a peněz to sežralo.

Za den zjistíš dvě věci, které se z návrhu vyčíst nedají:
- jestli tvoje reálná práce má tvar stavového automatu, nebo je moc nelineární
- kde jsou brány, které bys skutečně chtěl mít lidské (na papíře jich navrhneš míň, než v praxi potřebuješ)

Teprve pak stav F0. Většina interních platforem umře na tom, že se postaví dřív, než někdo ověřil, že řeší reálný problém.
