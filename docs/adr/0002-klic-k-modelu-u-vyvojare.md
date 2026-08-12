# ADR-0002: Klíč k modelu zůstává na stroji vývojáře

**Stav:** nahrazeno [ADR-0005](0005-pod-bezi-na-vps.md)
**Datum:** 12. 8. 2026

> Rozhodnutí neplatí. Pod se přestěhoval na VPS, takže konfigurace Pi i
> přihlášení k modelu leží tam, ne na stroji vývojáře. Záznam zůstává,
> protože důsledky, které popisuje — hlavně že bez brány není co počítat
> přesně — platí dál.

## Kontext

Bundle ze serveru nesl `model_allowlist`, ale žádný model, žádnou adresu
API a žádný klíč. Launcher proto zapisoval do policy `model: ""` a
harness pod odmítl spustit — v obou třídách dat, u každého projektu.
Bylo tedy nutné rozhodnout, kudy se model do podu dostane.

Ve hře byly dvě cesty: brána na VPS, která by držela klíč dodavatele a
podu vydávala krátkodobý token, nebo klíč u vývojáře.

## Rozhodnutí

Server pošle na stroj všechna data k práci. Model si k nim připojí
**vývojář podle vlastní volby** a klíč k němu drží u sebe. VPS klíč
dodavatele nikdy nevidí.

Kontrolu si server nechává jinde: `model_allowlist` u projektu vynucuje
harness a egress allowlist vynucuje proxy. Server tedy pořád rozhoduje,
co je povolené — jen nedodává prostředek.

## Důsledky

Útrata v panelu zůstane odhadem. Bez brány, kterou by šly všechny
požadavky, není co počítat přesně; platí dál `len/3` a neověřené ceny.

Klíče nejde rotovat centrálně a každý člen týmu potřebuje vlastní.
Naopak nehrozí, že by kompromitace VPS vydala klíč celé firmy.

Projekt označený `restricted` potřebuje lokální model, ke kterému pod
dosáhne — což je vlastní rozhodnutí, protože pod je na síti bez routy ven
a egress dnes pouští `CONNECT` jen na 443 a 2222.

Egress allowlist tím zůstává skutečnou hranicí volby: dodavatel, který
v něm není, je pro pod nedosažitelný, i kdyby k němu vývojář klíč měl.
