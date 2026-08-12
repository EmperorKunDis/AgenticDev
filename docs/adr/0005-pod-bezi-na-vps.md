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

**Každý člověk potřebuje na VPS účet ve skupině `docker`, a to je na
tomhle stroji rovnocenné rootovi.** Kdo smí mluvit s Docker socketem, umí
si nastartovat kontejner s připojeným `/`, takže si přečte
`/srv/agenticdev/config/.env` — podpisový klíč work orderů, heslo k
databázi, všechna tajemství instance. Dokud pody běžely na notebooku,
tenhle problém neexistoval, protože socket byl na notebooku.

Pro tříčlenný tým, který si věří, je to snesitelné a je to i dnešní stav
mnoha firem. Přestává to být snesitelné ve chvíli, kdy má na VPS účet
někdo, komu nechceš dát root — externista, junior, klient. Cesty ven jsou
rootless Docker na člověka, nebo privilegovaný pomocník, který pod
nastartuje za uživatele, aby sám socket nepotřeboval. Ani jedno není
hotové a je to největší nezavřená věc tohohle rozhodnutí.

Zbývá dořešit, jak se vývojář k podu připojí — zatím Tailscale SSH a
`agenticdev` na VPS.
