# ADR-0007: Prostředí sdílené, přihlášení a sessions na člověka

**Stav:** přijato
**Datum:** 12. 8. 2026

## Kontext

Pod běží na VPS ([ADR-0005](0005-pod-bezi-na-vps.md)) a záměr byl mít tam
jedno `~/.pi/agent` pro všechny, přičemž každý má vlastní předplatné —
kdo si vyvolá prostředí, odhlásí předchozího a přihlásí sebe.

To nefunguje. Přihlášení leží v jednom souboru `~/.pi/agent/auth.json` a
Pi si tokeny **obnovuje automaticky**, když vyprší. Když se během cizí
práce přihlásí druhý člověk, přepíše ten soubor; prvnímu pak Pi při
obnovení tokenu přečte cizí přihlášení a jeho práce buď spadne, nebo se
naúčtuje někomu jinému. Dva lidé naráz tedy pracovat nemohou, což je přímo
proti zadanému cíli — celý tým na klientských projektech.

Zároveň platí, že sdílené prostředí v `~/.pi/agent` být nemusí: server ho
už dnes posílá v bundlu do projektu a Pi načítá `.pi/settings.json`,
`.pi/skills/` i `.pi/extensions/` odtamtud.

## Rozhodnutí

Rozdělit to podle toho, co je opravdu společné:

| Co | Kde |
|---|---|
| Prostředí — nastavení, skills, hooky, extension | Sdílené, posílá server v bundlu do projektu |
| Přihlášení k modelu (`auth.json`) | Na člověka, přes `PI_CODING_AGENT_DIR` |
| Sessions a transkripty | Na člověka |

Žádné odhlašování a přihlašování při každém prostředí.

## Důsledky

Dva lidé mohou pracovat současně a útrata sedí na tom, kdo ji spotřeboval,
protože každý jede na svém předplatném. `/login` proběhne jednou na
člověka, ne při každém spuštění — což je podstatné, protože je to
interaktivní OAuth a VPS je headless.

Transkripty se nepromíchají. To je předpoklad toho, aby evidence běhů měla
čím se doložit.

Za to platíme tím, že se na VPS musí zakládat a spravovat adresář na
každého člověka, a že přihlášení k modelu není nic, co by šlo nastavit
centrálně za celý tým.

Prostředí zůstává jediné a mění se na serveru, takže platí dál, že o tom,
co agent smí, rozhoduje server.
