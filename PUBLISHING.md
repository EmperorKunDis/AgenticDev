# Než to vydáš / Before you publish

Věci, které za tebe nikdo neudělá. Projdi shora dolů.
Things nobody can do for you. Work top to bottom.

---

## 1. Doplň zástupné texty / Fill in the placeholders

V repu je pár míst označených `[DOPLŇ:]` nebo `[FILL IN:]`. Najdeš je takhle:

```bash
grep -rn "DOPLŇ\|FILL IN" --include="*.md" --include="*.yml" .
```

| Soubor | Co doplnit |
|---|---|
| `LICENSE` | jméno licencora (ty osobně, nebo s.r.o.) a e-mail pro komerční licence |
| `LICENSE-FAQ.md` | e-mail pro komerční licence, v obou jazycích |
| `SECURITY.md` | e-mail pro hlášení zranitelností, v obou jazycích |


Odkazy na repozitář už doplněné jsou — míří na
`Praut-Startup-Support/AgenticDev`. Když repo přejmenuješ, projeď je znovu.

**Nechej licenci projít právníkem.** BSL 1.1 s příjmovou hranicí je obchodní
rozhodnutí s reálnými dopady na to, kdo ti smí a nesmí platit. Tenhle text
je připravený, ale není to právní posudek.

---

## 2. Rozhodni hranici / Decide the threshold

V `LICENSE` je teď **1 000 000 EUR** ročního obratu. Je to jediné číslo,
které tu hranici určuje — změň ho, pokud chceš jinou. Stejnou hodnotu pak
oprav i v `LICENSE-FAQ.md` a v obou README.

---

## 3. Ochranná známka / Trademark

Licence nekryje jméno ani logo — ta zůstávají tvoje bez ohledu na to, co si
kdo s kódem udělá. Je to užitečná páka: kdokoliv smí kód forknout, ale
nesmí tomu říkat AgenticDev. Registraci zvaž zvlášť.

---

## 4. Založ repozitář / Create the repository

```bash
git init
git add .
git commit -m "AgenticDev"
git branch -M main
git remote add origin git@github.com:Praut-Startup-Support/AgenticDev.git
git push -u origin main
```

Zapni v nastavení repozitáře:

- **Settings → Actions → General** → povol workflow
- **Settings → Actions → General → Workflow permissions** → *Read and write*
  (release workflow potřebuje nahrát artefakty)
- **Settings → Code security** → Dependabot alerts, secret scanning

---

## 5. První vydání / First release

```bash
make verify && make dist && bash dist/agenticdev-install-vps.sh --check
git tag v0.1.0
git push --tags
```

Workflow postaví artefakt, ověří, že je build reprodukovatelný, podepíše ho
přes Sigstore a založí **draft** release. Zkontroluj ho a vydej ručně.

Podpis je keyless — žádný soukromý klíč neexistuje, podpis je vázaný na
repozitář a workflow přes OIDC. Kdokoliv si ho ověří bez důvěry k tobě.

---

## 6. Otestuj to jako cizí člověk / Test as a stranger

Tohle je ta část, kterou lidi vynechávají a pak se diví.

- [ ] Čistý VPS, jen podle README, bez znalostí navíc
- [ ] `sha256sum -c` sedí
- [ ] Instalace doběhne a vypíše oba odkazy
- [ ] Registrační stránka je vidět z mobilních dat (ne z tailnetu!)
- [ ] Špatné heslo vrátí chybu, po pěti pokusech zamkne
- [ ] macOS klient projde a na ploše je ikona
- [ ] Linux klient projde a ikona je v nabídce aplikací
- [ ] Windows klient projde přes WSL2
- [ ] Klik na ikonu otevře agenta a výběr projektu
- [ ] Admin panel jde otevřít, nastavení se uloží a platí
- [ ] Instalátor puštěný podruhé nic nerozbije

---

## 7. Co v README musí zůstat / What must stay in the README

Sekce **Known limitations**. Nemaž ji, dokud ty body neopravíš:

- orchestrační vrstva (directors) není implementovaná
- není serverová brána před mergem
- chybí observabilita
- join tokeny nemají expiraci
- počítání tokenů je odhad, ceny neověřené

Vydat alfu je v pořádku. Vydat alfu bez varování není — někdo si to nasadí
do firmy a zjistí to sám.

---

## 8. Zálohy / Backups

`WO_SIGNING_KEY_B64` z `/srv/agenticdev/config/.env` si ulož mimo server. Bez něj
neověříš dřív vydané work ordery a nikdo ti ho nedopočítá.

A obnov si zálohu dřív, než ji budeš potřebovat. Záloha, kterou jsi nikdy
neobnovil, není záloha.
