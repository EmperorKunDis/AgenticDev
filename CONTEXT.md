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
„náš agent", „model" (model je dodavatel inteligence, agent je program).

Viz [ADR-0001](docs/adr/0001-agent-je-pi.md).
