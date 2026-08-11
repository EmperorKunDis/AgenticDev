Projdi před odevzdáním, krok po kroku, a u každého počkej na výsledek:

1. `git status` a `git diff` — co se skutečně změnilo
2. Ověř, že nic není mimo `.agenticdev/scope`
3. Spusť testy a lint
4. Projdi diff jako reviewer: úniky tajemství, neošetřené vstupy,
   tiché polykání výjimek, kód nesrozumitelný za půl roku
5. Když je vše v pořádku: `bin/agenticdev-git finish "titulek"`

Když něco selže, zastav se a řekni co. Neobcházej to.
