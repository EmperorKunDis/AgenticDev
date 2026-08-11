# Security Policy / Bezpečnostní politika

## 🇬🇧 Reporting a vulnerability

**Do not open a public issue for security problems.**

Email: **svanda@praut.cz**

Please include:

- what the problem is and where in the code
- how to reproduce it
- what an attacker could achieve
- the version or commit hash you tested

**What to expect:**

| | |
|---|---|
| First reply | within 5 working days |
| Assessment | within 14 days |
| Fix for confirmed critical issues | as fast as we can, disclosed after a patch is available |

We are a small team. We will tell you honestly if something will take a
while rather than leave you waiting.

### Scope

In scope: the installer, control plane, harness, pod compose, workspace
policy composition, work-order signing, token handling.

Out of scope: vulnerabilities in upstream projects we package (Forgejo,
Postgres, MinIO, Caddy, Docker) — report those to their maintainers. We do
want to hear if we configure them insecurely.

### Known limitations of the current release

We would rather tell you than have you find out. As of this release:

- **Container escape is out of scope.** The pod runs non-root with all
  capabilities dropped and no Docker socket, and the scope boundary is
  enforced by read-only mounts rather than by asking the agent nicely — but
  a container is not a hypervisor.
- **The orchestration layer (directors) described in the architecture
  document is not implemented.**
- **No server-side merge gate.** Tests run inside the pod, which the agent
  controls. Suitable for a small trusted team, not for untrusted contributors.
- Join tokens do not expire and are shared per instance, not per person.
- Token accounting is approximate; cost figures on the dashboard are estimates.

These are tracked as blockers to a 1.0 release.

---

## 🇨🇿 Hlášení zranitelnosti

**Bezpečnostní problém nezakládej jako veřejný issue.**

E-mail: **svanda@praut.cz**

Napiš prosím:

- v čem je problém a kde v kódu
- jak to reprodukovat
- co s tím útočník dokáže
- verzi nebo commit, který jsi testoval

**Co můžeš čekat:**

| | |
|---|---|
| První odpověď | do 5 pracovních dnů |
| Posouzení | do 14 dnů |
| Oprava potvrzené kritické chyby | co nejrychleji, zveřejnění až po vydání záplaty |

Jsme malý tým. Když bude něco trvat, řekneme ti to rovnou, místo abychom
tě nechali čekat.

### Co spadá do rozsahu

Spadá: instalátor, control plane, harness, compose podu, skládání policy
workspace, podpis work orderů, práce s tokeny.

Nespadá: zranitelnosti v projektech, které jen balíme (Forgejo, Postgres,
MinIO, Caddy, Docker) — ty hlas jejich autorům. Ale pokud je konfigurujeme
nebezpečně, o tom slyšet chceme.

### Známá omezení téhle verze

Radši ti to řekneme, než abys na to přišel sám. K tomuhle vydání:

- **Útěk z kontejneru je mimo rozsah.** Pod běží bez rootu, se zahozenými
  capabilities a bez Docker socketu, a hranici scope vynucují read-only
  mounty, ne slušnost agenta — ale kontejner není hypervizor.
- **Orchestrační vrstva (directors) z architektonického rozboru není
  implementovaná.**
- **Není serverová brána před mergem.** Testy běží uvnitř podu, který řídí
  agent. Vhodné pro malý důvěryhodný tým, ne pro cizí přispěvatele.
- Join tokeny nemají expiraci a jsou sdílené na instanci, ne na osobu.
- Počítání tokenů je přibližné; útrata v nástěnce je odhad.

Tyhle body jsou vedené jako blokátory verze 1.0.
