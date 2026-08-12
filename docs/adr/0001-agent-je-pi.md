# ADR-0001: Agentem v podu je Pi, ne Claude Code

**Stav:** přijato
**Datum:** 12. 8. 2026

## Kontext

Kód platformy všude instaluje a spouští Pi
(`@earendil-works/pi-coding-agent`): obraz podu, harness (`which("pi")`),
launcher i všechny tři klientské instalátory. Čtyři popisky v kódu a
dokumentaci ale tvrdily Claude Code, takže při čtení repozitáře nebylo
jasné, co se doopravdy spustí.

## Rozhodnutí

Agentem je Pi. Zmínky o Claude Code jsou chyba v dokumentaci a srovnávají
se s kódem.

## Důsledky

Workspace vrstva zůstává psaná pro Pi — `.pi/settings.json`, Pi skills,
extension v TypeScriptu proti Pi API. Přechod na jiného agenta by
znamenal přepsat tuhle vrstvu celou, ne přehodit jméno binárky; proto to
stojí za zaznamenání.

Cena, kterou platíme: tým používá Claude Code jinde, takže lidé pracují
se dvěma různými agenty a jejich konfiguracemi.
