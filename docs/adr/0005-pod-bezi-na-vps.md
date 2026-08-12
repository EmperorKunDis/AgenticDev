# ADR-0005: Pod běží na VPS, ne na stroji vývojáře

**Stav:** přijato
**Datum:** 12. 8. 2026
**Nahrazuje:** [ADR-0002](0002-klic-k-modelu-u-vyvojare.md)

## Kontext

Dosud platilo, že server pošle nastavení a pod se spustí na notebooku
vývojáře: launcher pouštěl `docker compose` lokálně, mountoval
`$HOME/AgenticDev/<projekt>` a běžel pod uid toho člověka.

Konfigurace Pi ale má existovat jen na VPS. Z notebooku je nedosažitelná,
takže se muselo rozhodnout, co se přestěhuje — konfigurace k podu, nebo
pod ke konfiguraci.

Zvážená alternativa byla nechat pod na notebooku a posílat mu společnou
konfiguraci včetně přihlášení v bundlu. Znamenalo by to, že VPS rozdává
jeden společný klíč do každého podu, a nejnepříjemnější neověřená plocha
projektu — Docker na třech operačních systémech, WSL2, tři instalátory —
by zůstala.

## Rozhodnutí

Pod běží **na VPS**. Vývojář se k němu připojí vzdáleně. Konfigurace Pi
i přihlášení k modelu leží na VPS, ne na klientských strojích.

## Důsledky

Na strojích týmu **není potřeba Docker**. Tím zmizí celá cesta přes WSL2 i
většina práce, kterou dělaly tři klientské instalátory — a s nimi ta část
platformy, která nikdy neběžela proti reálnému systému.

Transkripty a sessions začnou padat na VPS. `transcript_uri` v `agent_run`
přestane být prázdný a evidence běhů bude mít čím se doložit; dosud
sessions umíraly s podem.

Egress proxy je jedna, na serveru, místo jedné na každém notebooku. Scope
dál vynucují mounty a git po síti dělá hostitel — jen tím hostitelem je
teď VPS, na kterém stejně běží Forgejo.

VPS musí utáhnout pody celého týmu naráz. Doporučení 4 GB RAM přestává
platit a je potřeba ho přepočítat podle počtu lidí, kteří pracují zároveň.

README i web tvrdí, že agent běží na tvém stroji. To přestává být pravda
a musí se srovnat, jinak je to zase dokumentace popisující něco, co v kódu
není.

Otevřené zůstává, jak se vývojář ke svému podu připojí a jestli je
`~/.pi/agent` jeden společný, nebo na člověka — u předplatných účtů to má
důsledky, které nejsou technické.
