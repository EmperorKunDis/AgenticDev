# Slovník

Vlastní pojmy tohohle projektu. Jedna až dvě věty na pojem, žádné
implementační detaily. Když někdo použije slovo z `_Vyhýbej se_`, je to
znamení, že si dva lidé nerozumí.

---

## Agent

Program, který v podu píše kód — konkrétně **Pi**
(`@earendil-works/pi-coding-agent`). Spouští ho výhradně harness, až po
kontrole policy. Server agenta neposílá, posílá mu nastavení: instrukce,
skills, oprávnění a kontext podle fáze a projektu.

_Vyhýbej se_: Claude Code (jiný produkt; celá workspace vrstva je psaná
pro Pi — `.pi/settings.json`, Pi skills, extension proti Pi API),
„náš agent".

Viz [ADR-0001](docs/adr/0001-agent-je-pi.md).

## Model

Inteligence, kterou agent volá. Vybírá si ji a platí **vývojář na svém
stroji**; server ji nedodává a klíč k ní nikdy nedrží. Server volbu jen
omezuje — `model_allowlist` u projektu říká, co je povolené, egress
allowlist rozhoduje, na kterou doménu se pod vůbec dostane.

_Vyhýbej se_: „agent" (to je program, který model volá), „AI",
„dodavatel" bez upřesnění, jestli jde o firmu, nebo o endpoint.

Viz [ADR-0002](docs/adr/0002-klic-k-modelu-u-vyvojare.md).

## Director

Postup, kterým musí úkol projít, a limity, kolik se smí opakovat.
Vynucuje ho harness uvnitř podu, ne server.

_Vyhýbej se_: „orchestrátor", „workflow" (to je běh v Actions).
Pozor: tabulka `director_version` v databázi popisuje directora jako
zvlášť verzovaný a podepsaný artefakt s kanály. Tak to dneska není a
[ADR-0003](docs/adr/0003-postup-ukolu-vynucuje-harness.md) říká proč.

## Připojení stroje

První kontakt člověka s instancí: na registrační stránce prokáže znalost
sdíleného hesla, **řekne jméno, příjmení a e-mail**, a dostane klíč do
tailnetu a instalátor. Bez toho se nedostane nikam dál.

_Vyhýbej se_: „registrace" bez upřesnění — v platformě jsou tři různé
kroky, které tak jdou pojmenovat (tenhle, ten následující a přihlášení).

## Registrace stanice

Krok, který dělá instalátor: pošle serveru fingerprint device keye toho
stroje a identitu člověka z připojení. Vznikne z toho řádek ve
`workstation` a SSH klíč se založí ve Forgeju. Jeden člověk může mít víc
stanic; odebrat se dá jednotlivá.

## Přihlášení stanice

Co dělá launcher při každém spuštění: vymění fingerprint device keye za
krátkodobý token. Neplatí déle než lease a nepřenáší se mezi stroji.

_Vyhýbej se_: „login" pro tohle i pro heslo do panelu — panel je jiná
cesta s jiným tajemstvím.
