# ADR-0003: Postup úkolu vynucuje harness, directory se neverzují zvlášť

**Stav:** přijato
**Datum:** 12. 8. 2026

## Kontext

`docs/architektura.md` i tabulka `director_version` popisují directora
jako samostatně verzovaný a podepsaný artefakt, který se vydává po
kanálech (canary, beta, stable) a stahuje se na stanici. Work order na
něj odkazuje a `_pick_director` ho vybírá z databáze.

Runtime k tomu ale neexistuje — nic z toho se nikdy nespustí. Agent
pracuje bez postupu, přestože work order už dneska vozí
`max_loop_iterations` a `human_gate`.

## Rozhodnutí

Postup úkolu — plán, test, implementace, review, hotovo — a limity
opakování vynucuje **harness uvnitř podu**. Zvlášť verzovaný director
runtime se nestaví.

## Důsledky

`director_version` zůstává v databázi jako kompatibilní přišpendlení
verzí, ale žádnou logiku nedodává. Kdo čte schéma, čte něco, co se
neděje — proto tenhle záznam.

Odpadá vydávání directorů po kanálech, takže se nová verze postupu nedá
vyzkoušet na jednom člověku a pak rozšířit. Verzuje se s harnessem.

Postup se tím stěhuje do důvěryhodného jádra podu. Když se později
ukáže, že directory mají být samostatné, znamená to logiku z harnessu
vytáhnout — což je dražší, než kdyby tam nikdy nebyla.

Cena, kterou tím platíme vědomě: vzniká něco, co existuje, místo něčeho,
co je správně navržené a nenapsané.
