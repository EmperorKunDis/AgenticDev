# HANDOFF

Stav repozitáře a co s ním dál. Psáno pro chvíli, kdy někdo (člověk nebo
agent) dostane přístup k repu a má pokračovat.

Poslední aktualizace: 11. 8. 2026

---

## 1. Rozhodnutí, které blokuje zbytek

**Jak se produkt jmenuje?**

Teď je to rozjeté:

| Kde | Co tam stojí |
|---|---|
| `LICENSE` → `Licensed Work` | `AgenticDev` |
| `README.md`, `README.cs.md` nadpis | `AgenticDev` |
| repozitář, web, doména | `AgenticDev` |

`Licensed Work` v licenci je **právní identifikátor** — určuje, co přesně je
licencováno. Musí sedět s tím, jak se produkt reálně jmenuje, jinak je
licence napadnutelná.

Až padne rozhodnutí, sjednotit jedním průchodem:

```bash
# varianta A — produkt se jmenuje AgenticDev
grep -rl "AgenticDev" --include="*.md" LICENSE . \
  | xargs sed -i 's/AgenticDev/AgenticDev/g'

# varianta B — produkt zůstává AgenticDev, AgenticDev je jen repo
# (pak není co měnit, jen zkontrolovat, že to web nemate)
```

Pozor: `Praut s.r.o.` jako licencor se **nemění** ani v jedné variantě.

---

## 2. Co nikdy neběželo

Nic z toho nebylo vyzkoušeno proti reálnému systému. Kód se parsuje a
struktura sedí, ale to je všechno.

| Co | Riziko |
|---|---|
| **Sandbox (pod)** | mounty, proxy a uid nikdy neběžely proti Dockeru |
| **Windows klient** | WSL2 cesta, `wslpath`, zástupce s ikonou |
| **Linux klient** | detekce správce balíčků, ikona v nabídce |
| **Registrační stránka** | Funnel, rate limit v provozu, Tailscale auth key |
| **Admin panel → nastavení** | tabulka `setting`, uložení, projev bez restartu |
| **Ikony** | `.icns` se generuje až na macOS přes `iconutil` |
| **Release workflow** | podpis přes cosign, reprodukovatelnost v CI |

**Testovat v tomhle pořadí** — každý krok staví na předchozím:

1. Server na čistém VPS podle README, bez znalostí navíc
2. `curl https://<host>.ts.net:8443/join/health` z mobilních dat (ne z tailnetu)
3. Registrační stránka v prohlížeči, špatné heslo, pak správné
4. macOS klient až do ikony na ploše
5. Klik na ikonu → naběhne pod → agent odpoví
6. Zápis mimo scope musí selhat na EROFS
7. Admin panel, změna modelu, projeví se bez restartu
8. Linux klient, Windows klient
9. `git tag v0.1.0` → workflow → draft release

---

## 3. Co je hotové a ověřené

- Build je **reprodukovatelný** — dvě sestavení dala stejný součet
- `make verify` projde, všech 16 shell skriptů se parsuje
- Registrační endpoint otestován jednotkově: špatné heslo 401, po pěti
  pokusech 429, IP zamčená
- 12 vlastností izolace ověřeno proti `pod/compose.yaml`
- V dokumentaci nezbyly odkazy na neexistující cesty

---

## 4. Známé díry, vědomě ponechané

Jsou popsané v README i SECURITY.md. Nejsou to překvapení, ale nedělej,
že tam nejsou:

| Díra | Dopad |
|---|---|
| Není serverová brána před mergem | testy si pouští agent sám |
| Orchestrační vrstva (directors) neexistuje | agent pracuje bez stavového automatu |
| Join heslo nemá expiraci | odvolání = změna hesla všem |
| Počítání tokenů `len/3` | útrata v panelu je orientační |
| Chybí observabilita | Grafana a Loki zakomentované |
| Ceny modelů neověřené | `PRICING` je odhad |

Pořadí, v jakém by se to mělo řešit, je v README v sekci o omezeních.

---

## 5. Drobnosti k dodělání

- [ ] `site/index.html` — nahradit `DOPLN_FORM_ID` skutečným ID z Formspree.
      Nasazovací workflow schválně spadne, dokud to nikdo neudělá.
- [ ] DNS: `CNAME agenticdev → agenticdev-startup-support.github.io.`
- [ ] Settings → Pages → Source: **GitHub Actions**
- [ ] Settings → Actions → Workflow permissions: **Read and write**
- [ ] Topics a Website v About na GitHubu
- [ ] Licenci nechat projít právníkem — BSL s příjmovou hranicí je obchodní
      rozhodnutí, ne technické

---

## 6. Věci, na které si dát pozor při úpravách

**`agenticdev-git` a worktree.** V podu je kořen repozitáře `/workspace`, takže
`dirname` vyjde na `/`. Proto existuje proměnná `AGENTICDEV_TREES`, kterou
launcher nastaví na adresář připojený z hostitele. Kdyby ji někdo odstranil,
rozdělaná práce se bude ztrácet při každém teardownu a nikdo si toho hned
nevšimne.

**Scope vynucují mounty, ne instrukce.** Když přidáš fázi, `scope` soubor
není doporučení — launcher podle něj staví `compose.override.yaml`. Fáze bez
`scope` znamená pod, ve kterém nejde zapsat nikam.

**Egress allowlist je allowlist.** `FilterDefaultDeny Yes` v tinyproxy je to
podstatné. Bez něj by se z toho stal blocklist a všechno neuvedené by prošlo.

**Harness odmítne nastartovat**, když je kořen workspace zapisovatelný nebo
chybí proxy. To je záměr — špatně nastavený sandbox má spadnout nahlas, ne
tiše nechránit nic.

**Dokumentace popisovala věci, které v kódu nebyly.** Stalo se to opakovaně
(pod, harness, egress-proxy, directors, `.claude/settings.json`). Než něco
napíšeš do README, ověř `grep`em, že to existuje.
