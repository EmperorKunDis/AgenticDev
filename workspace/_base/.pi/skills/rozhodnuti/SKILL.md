---
name: rozhodnuti
description: Zapíše architektonické rozhodnutí jako ADR a pošle ho na VPS.
hidden: true
---

# Zápis rozhodnutí

1. Projdi `prd/40-decisions/`. Když podobné rozhodnutí už padlo,
   odkaž se na něj místo zakládání nového.

2. Založ `prd/40-decisions/ADR-NNN-nazev.md`:

```markdown
# ADR-NNN: název

**Stav:** přijato
**Datum:** <dnes>

## Kontext
Co nás k tomu vedlo.

## Varianty
Co jsme zvažovali a proč zamítli.

## Rozhodnutí
Co jsme zvolili.

## Důsledky
Co z toho plyne, včetně nevýhod.
```

3. Pošli na VPS jako precedent:

```bash
bin/agenticdev-decision "otázka" "co jsme zvolili" "proč"
```
