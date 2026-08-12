# ADR-0006: „Hotovo" je smergovaný PR se zeleným workflow

**Stav:** přijato
**Datum:** 12. 8. 2026

## Kontext

Dosud `release?outcome=done` přepnul úkol do stavu `review` a čekalo se na
člověka. Stav `done` nenastavoval nikdy nikdo, takže „hotovo" bylo něčí
tvrzení, ne vlastnost kódu. Testy si přitom pouštěl agent sám ve svém
podu a nikdo je neověřoval jinde — jediná cesta, kterou se do klientského
repozitáře může dostat rozbitý kód.

## Rozhodnutí

Podmínkou mergu je **zelené workflow z repozitáře projektu** (testy a
lint), spuštěné runnerem na VPS, ne v podu agenta. Branch protection merge
bez něj nepustí. Stav `done` se úkolu nastaví **až mergem PR**.

Dokud v repozitáři není co spustit, workflow projde. Rozdíl mezi „testy
neexistují" a „testy padají" musí být v logu vidět, aby se z prvního
nestal trvalý stav.

## Důsledky

„Hotovo" přestává být názor. Zároveň to znamená, že úkol, který je
dodělaný, ale z jakéhokoli důvodu nejde smergovat, zůstane nedokončený —
a to je záměr, ne chyba.

Člověk zůstává v cestě u schválení PR. Automatika nerozhoduje o tom, co
se smerguje, jen brání mergi bez zelených testů.

Control plane se musí o mergi dozvědět, aby stav přepnul. Přidává to
závislost na Forgeju směrem k serveru, kterou dosud neměl.

Runner na VPS pouští joby v kontejnerech, takže obvykle potřebuje docker
socket. Je to slabší hranice než pod, kterému jsme socket záměrně nedali,
a běží to na stejném stroji — kdo tam pustí workflow, pustí ho vedle
databáze a podpisového klíče.
