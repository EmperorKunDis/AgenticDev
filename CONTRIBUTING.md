# Contributing / Přispívání

🇬🇧 English below · 🇨🇿 Česky níže

---

## 🇬🇧 English

Thank you for considering a contribution. A few things worth knowing before
you spend time on it.

### The CLA, and why

This project is **dual-licensed**: the source is available under BSL 1.1, and
larger organizations buy a commercial licence. That funding is what keeps
development going.

We can only sell a commercial licence for code we hold the rights to. So
contributions require a **Contributor Licence Agreement** — you keep your
copyright, but you grant us the right to also distribute your contribution
under commercial terms.

If that is not acceptable to you, that is a legitimate position. Open an
issue describing the problem instead; a good bug report is a real
contribution.

### Before you open a pull request

1. **Open an issue first** for anything larger than a bug fix. It saves you
   from building something we then have to decline.
2. `make verify` and `make dist` must pass.
3. Shell scripts must pass `bash -n`. Keep `shellcheck` warnings down.
4. Both languages. User-facing text needs a Czech and an English version.
   Code comments: whichever the surrounding file uses.

### What we especially want

The [known limitations](README.md#known-limitations) are the honest backlog.
In rough order of value:

1. **CI/CD gate** — server-side checks before merge. Currently the agent runs
   its own tests in its own pod, which is not a gate.
2. **Director signing** — the harness verifies a signature nothing produces.
3. **Observability** — Grafana and Loki are commented out in compose.
4. **Real token counting** — replace the `len/3` estimate.

### Security

Do not open a public issue. See [SECURITY.md](SECURITY.md).

---

## 🇨🇿 Česky

Díky, že o příspěvku uvažuješ. Pár věcí, které je dobré vědět dřív, než na
tom strávíš čas.

### CLA a proč

Projekt je **dvojlicencovaný**: zdroj je dostupný pod BSL 1.1 a větší firmy
si kupují komerční licenci. Z toho se vývoj platí.

Komerční licenci můžeme prodat jen na kód, ke kterému máme práva. Proto
příspěvky vyžadují **Contributor Licence Agreement** — autorství zůstává
tobě, ale dáváš nám právo šířit tvůj příspěvek i za komerčních podmínek.

Jestli ti to nesedí, je to legitimní postoj. Založ místo toho issue s
popisem problému — dobré hlášení chyby je taky příspěvek.

### Než otevřeš pull request

1. **Nejdřív založ issue**, pokud jde o víc než opravu chyby. Ušetří ti to
   práci na něčem, co pak musíme odmítnout.
2. `make verify` a `make dist` musí projít.
3. Shellové skripty musí projít `bash -n`. Varování ze `shellcheck` drž při
   zemi.
4. Oba jazyky. Text, který uvidí uživatel, potřebuje českou i anglickou
   verzi. Komentáře v kódu: podle toho, co používá okolní soubor.

### Co bychom uvítali nejvíc

[Známá omezení](README.cs.md#známá-omezení) jsou poctivý backlog. Zhruba
podle přínosu:

1. **CI/CD brána** — serverová kontrola před mergem. Teď si agent pouští
   vlastní testy ve vlastním podu, což brána není.
2. **Podpisy directorů** — harness ověřuje podpis, který nikdo nevydává.
3. **Observabilita** — Grafana a Loki jsou v compose zakomentované.
4. **Skutečné počítání tokenů** — nahradit odhad `len/3`.

### Bezpečnost

Nezakládej veřejný issue. Viz [SECURITY.md](SECURITY.md).
