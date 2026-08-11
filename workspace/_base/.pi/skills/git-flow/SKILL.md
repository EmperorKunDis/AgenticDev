---
name: git-flow
description: Větvení, checkpointy a odevzdání práce přes praut-git.
hidden: true
---

# Git flow

Nikdy nepracuj na `main`. Vždy přes `bin/praut-git`.

## Začátek úkolu

```bash
cd "$(bin/praut-git start "krátký popis úkolu" T-042)"
```

Založí větev z aktuálního `origin/main` a **samostatný worktree**.
Rozdělané úkoly tak leží vedle sebe, přepínáš bez stashování.

## Během práce

```bash
bin/praut-git checkpoint "co jsem právě dodělal"
```

Volej to často — po každém kusu, který dává smysl. Checkpointy jsou
levné, sesypou se při odevzdání. Dělají `git bisect` použitelným
a dovolují vrátit se o krok zpět.

Když je kus hotový a otestovaný:

```bash
bin/praut-git save feat import "import karet z DE systému"
```

Typ: `feat` `fix` `refactor` `test` `docs` `chore` `perf` `build` `ci`

## Odevzdání

```bash
bin/praut-git finish "feat(import): karty z DE systému"
```

Sesype wip commity do jednoho, narovná na main, odešle, otevře PR.

## Ostatní

```bash
bin/praut-git sync                # rebase na aktuální main
bin/praut-git list                # rozdělané úkoly
bin/praut-git who src/a.ts 42     # ze které session je ten řádek
bin/praut-git cleanup             # smaže smergované
```

## Pravidla

- Před `finish` vždy spusť testy. Když padají, neodevzdávej.
- Konflikt při rebase neřeš naslepo — ukaž ho člověku.
- Nikdy `git push --force` napřímo, `finish` používá `--force-with-lease`.
- Nikdy neměň historii větve, která už je v PR.
