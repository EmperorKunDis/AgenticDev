# Praut Platform

**Vlastní agentní vývojová platforma.** VPS drží všechna data, kontext a
orchestraci. Vývojáři spouštějí agenta na svém stroji nad checkoutem
projektu, ale instrukce, scope a fázi dodává server — a rozhodnutí, běhy i
náklady se zapisují zpátky do auditovatelného ledgeru.

Agent běží v kontejneru bez cesty do internetu — ven se dostane jen přes
proxy s allowlistem. Repozitář je připojený read-only a zapisovatelné jsou
jen cesty ze scope, takže zápis jinam selže na úrovni jádra.

🇬🇧 [English version of this document](README.md)

> **Stav: alfa.** Běží v ostrém provozu v jedné firmě. Než to nasadíš,
> přečti si [Známá omezení](#známá-omezení) na konci. Radši ti to řekneme,
> než abys na to přišel sám.

---

## Požadavky

| | |
|---|---|
| Server | Debian 12 nebo Ubuntu 22.04/24.04, aspoň 4 GB RAM, root |
| Síť | **Tailscale** — tvrdý požadavek, ne volba |
| Klienti | macOS, Linux nebo Windows 10 build 19041+ (přes WSL2) |
| Volitelně | API klíč k modelu, nebo lokální Ollama |

**Než začneš**, dvě věci v Tailscale konzoli:

1. [DNS](https://login.tailscale.com/admin/dns) → *HTTPS Certificates* →
   **Enable HTTPS**. Bez toho server nedostane certifikát pro svoje
   `.ts.net` jméno.
2. [Access controls](https://login.tailscale.com/admin/acls) → *Funnel* →
   **Add Funnel to policy**. Bez toho nenaběhne veřejná registrační stránka.

Instalátor obojí zkontroluje a řekne ti, co chybí.

---

## Instalace

### 1. Server — jednou

Stáhni soubor, ověř součet, spusť. Nepouštěj ho přes rouru — instalátor to
schválně odmítá.

```bash
curl -fLO https://github.com/Praut-Startup-Support/AgenticDev/releases/latest/download/praut-install-vps.sh
curl -fLO https://github.com/Praut-Startup-Support/AgenticDev/releases/latest/download/praut-install-vps.sh.sha256
sha256sum -c praut-install-vps.sh.sha256

scp praut-install-vps.sh root@tvuj-server:/root/
ssh root@tvuj-server 'bash /root/praut-install-vps.sh'
```

Zeptá se na pět věcí včetně dvou hesel, zbytek udělá sám. Na konci vypíše
dva odkazy:

| Odkaz | Pro koho | Odkud funguje |
|---|---|---|
| **Admin panel** | jen ty | jen z tailnetu |
| **Registrační stránka** | tvůj tým | z celého internetu |

### 2. Klienti — neomezeně strojů, kdekoliv

Pošli registrační odkaz komukoliv. Zadá heslo, vybere si systém a dostane
dva příkazy ke zkopírování.

**macOS · Linux · Windows.** Windows jede přes WSL2.

Instalátor stroj zaregistruje pod jménem a e-mailem toho člověka, nahraje
mu SSH klíč do Forgeja a položí na plochu **ikonu Praut**. Klik na ni
otevře agenta a výběr projektu.

Objeví se v panelu v záložce *tým*, kde jde každý stroj zvlášť odpojit.

**Co je reálně na internetu:** jediná cesta — registrační stránka —
vystavená přes [Tailscale Funnel](https://tailscale.com/kb/1223/funnel).
Nepotřebuje veřejnou IP ani doménu. Heslo je na ní jediná zábrana, takže má
limit pokusů na IP i globálně a po pěti neúspěších zamkne adresu na hodinu.

Všechno ostatní — panel, git, API — zůstává na tailnetu.

### 3. Admin panel

Dodavatel modelů a API klíč, allowlist domén, obě hesla, platnost lease,
Tailscale klíče a SMTP se mění přímo v panelu a platí okamžitě. Věci, které
potřebují restart kontejneru, žijí v `/srv/praut/config/.env` a panel je
ukazuje jen ke čtení.

---

## Denní práce

**Klikneš na Praut v Docku.** Otevře se Ghostty, vybereš projekt
šipkami (nebo filtruješ psaním), a jsi v Pi. Normální konverzace.

```
  projekt ›
  montexbau   MontexBau s.r.o.    implementation   3 úkolů
  schekonom   SCH-EKONOM s.r.o.   discovery        0 úkolů
```

Z terminálu totéž: `praut work`

### Víc projektů zároveň

Každý projekt = jedno okno. Nic nevypínáš.

```bash
praut work montexbau      # okno 1
praut work schekonom      # okno 2 (⌘T v Ghostty)
```

### Jiná fáze, aniž bys ji měnil týmu

```bash
praut work montexbau --phase delivery
```

Projekt zůstane pro ostatní v implementation. Změna fáze v nástěnce
navíc nikoho nevyhodí — konfigurace se zapíše na disk při startu
a běžící session jede dál.

### Přepínání mezi úkoly

```bash
praut-git list
cd "$(praut-git switch zaokrouhleni)"
```

Rozdělané úkoly leží fyzicky vedle sebe v `~/Praut/.praut-trees/`.

---

## Nový projekt

Nástěnka → **Projekty**:

| Pole | Poznámka |
|---|---|
| Kód | `montexbau` — stane se názvem repa |
| Klient | název firmy |
| Klasifikace dat | `restricted` = jen lokální modely, vynuceno |
| **Existující repozitář** | vyplň URL → naklonuje se i s historií a větvemi |

Když necháš pole prázdné, vznikne prázdné repo s kostrou `prd/`.
Hned potom vyplň `prd/50-glossary.md` — je to nejdůležitější soubor
projektu.

---

## Git

`bin/praut-git` — deterministický shell, nula tokenů. Agent i člověk
volají to samé. Pi ho volá automaticky po každých třech editacích
a na konci session.

```bash
cd "$(praut-git start "Import karet z DE" T-042)"
praut-git checkpoint "kostra"
praut-git save feat import "mapování polí"
praut-git finish "feat(import): karty z DE"
```

Worktree na úkol · checkpointy se při `finish` sesypou do jednoho
commitu · `git notes` drží ID session, takže `praut-git who src/a.ts 42`
řekne, odkud ten řádek je.

Test: `make test-git`

---

## Fáze

| Fáze | Smí měnit |
|---|---|
| discovery | `prd/**`, `docs/**` |
| design | + `design/**` |
| implementation | `src/**`, `tests/**`, ADR |
| hardening | + `infra/**` |
| delivery | `docs/**`, README, CHANGELOG |

---

## Přizpůsobení

`/srv/praut/src/workspace/`:

```
_base/          AGENTS.md, .pi/ (skills, extension), bin/
_phase/<fáze>/  scope + doplněk AGENTS.md
<projekt>/      specifika projektu
```

`AGENTS.md` se řetězí, `settings.json` slévá. Vlastní skill pro klienta:
`workspace/<projekt>/.pi/skills/nazev/SKILL.md`.

---

## Co ověřit

- **`.pi/extensions/praut-git.ts`** je psaný podle dokumentace Pi,
  ne odzkoušený proti běžícímu Pi. Ověř `api.addTool`, `api.addCommand`
  a názvy událostí. `bin/praut-git` na extension nezávisí.
- Pi se ptá na důvěru k projektové složce — nastav `defaultProjectTrust`.
- **Dva lidi můžou vzít stejný úkol.** Zámky nejsou. Při třech lidech
  to vyřešíte tím, že si to řeknete.
- Zálohy: doplň `RESTIC_REPOSITORY` do `/srv/praut/config/.env`.
- CI/CD ve Forgejo Actions není napsané.


---

## Licence

**Business Source License 1.1** — source-available, ne OSI open source.

Zdarma pro vyzkoušení, vývoj, výuku a produkční provoz ve firmách s obratem
**do 1 000 000 EUR**. Větší firmy potřebují komerční licenci. Každá verze se
**čtyři roky po vydání mění na Apache-2.0**.

Vysvětlení lidsky, česky i anglicky: [LICENSE-FAQ.md](LICENSE-FAQ.md).
Závazné znění: [LICENSE](LICENSE).

Komerční licence: **svanda@praut.cz**

© 2026 Praut s.r.o.

---

## Známá omezení

Poctivý stav. Vedeno jako blokátory verze 1.0:

- **Directors se nepodepisují.** Harness ověřuje podpis, který zatím nikdo
  nevydává. Nespouštěj pody na strojích, které nemáš pod kontrolou.
- **Není serverová brána před mergem.** Agent si pouští vlastní testy ve
  vlastním podu. Pro malý důvěryhodný tým stačí, jinak ne.
- **Chybí observabilita.** Grafana a Loki jsou v compose zakomentované,
  harness loguje na stdout.
- **Join tokeny nemají expiraci** a jsou na instanci, ne na osobu.
- **Počítání tokenů je odhad** (`len/3`) a ceny v `PRICING` nejsou ověřené.
  Útrata v nástěnce je orientační.
- **CI není napsané.** Forgejo Actions je zapnuté, workflow chybí.
- **Útěk z kontejneru je mimo rozsah.** Pod běží bez rootu, se zahozenými
  capabilities a bez Docker socketu — ale kontejner není hypervizor. Ber to
  jako pevný plot, ne jako trezor.

Bezpečnostní dopady najdeš v [SECURITY.md](SECURITY.md).

---

## Vydáváš vlastní fork?

Viz [PUBLISHING.md](PUBLISHING.md) — co doplnit, jak vydat release a co
otestovat.

---

## Přispívání

Viz [CONTRIBUTING.md](CONTRIBUTING.md). Příspěvky vyžadují podepsání CLA,
protože projekt je dvojlicencovaný a nemůžeme prodávat komerční licence na
kód, ke kterému nemáme práva.
