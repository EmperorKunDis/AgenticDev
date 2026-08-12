# ADR-0004: `restricted` vynucuje egress, ne jméno modelu

**Stav:** přijato
**Datum:** 12. 8. 2026

## Kontext

Harness dosud kontroloval, že jméno modelu začíná na `local/`, a to
považoval za záruku, že se citlivá data nedostanou do cloudu.

Není. Pi umí model přepnout **za běhu** přes `/model` (Ctrl+L), takže
kontrola při startu říká jen to, s čím agent začal, ne s čím pracuje.
Navíc model si vybírá vývojář ve své konfiguraci, takže platforma jméno
nemusí vůbec znát.

## Rozhodnutí

Hranicí je **cíl, ne jméno**. U projektu s `data_class = restricted`
pošle server egress allowlist, ve kterém není žádný cloudový endpoint.
Pod je na síti bez routy ven, takže se ke cloudu fyzicky nedostane — ať
si v Pi kdokoli vybere cokoli.

Kontrola jména v harnessu zůstává jako brzká a čitelná hláška, ne jako
záruka. Když se rozejde s allowlistem, platí allowlist.

## Důsledky

Je to stejný princip jako u scope: hranici drží jádro a síť, ne slušnost
agenta. Odpadá tím i to, že by platforma musela rozumět konfiguraci Pi.

`model_allowlist` u projektu tím přestává být kontrolou a zůstává údajem
pro lidi v panelu. Kdo si od něj sliboval vynucení, musí vědět, že
vynucuje egress.

Cena: `restricted` je použitelné jen tam, kde existuje endpoint lokálního
modelu, na který allowlist ukáže. Dokud žádný není, je taková třída dat
projekt, ve kterém agent nemá s čím pracovat — viz ADR o odložení
lokálních modelů.
