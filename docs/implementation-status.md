# Implementation status / Stav implementace

Last audited / Poslední audit: 2026-08-16.

The native subscription and repository-intelligence code path is implemented
in the repository. Produkční připravenost is deliberately a separate claim:
it requires the live acceptance evidence below.

## Implemented / Implementováno

- Automatic collision-safe enrollment, Unix/Forgejo/workstation provisioning,
  per-device Ed25519 proof-of-possession and no implicit project access.
- Native `claude -p` and `codex exec`, explicit provider selection, per-UID
  credential homes, provider profiles without secrets, and recoverable
  `AUTH_REQUIRED`/`RATE_LIMITED` outcomes without fallback.
- Deterministic import scan; commit/analyzer-version pinning; mapper,
  architecture, quality/security/operations and synthesis roles; validated
  citations; questions, revision and human approval before mutating work.
- Approved analysis in context bundles and explicitly confirmed documentation
  proposal PRs only.
- Signed read-only analysis Work Orders, separate analysis output volume,
  canonical provider-neutral skills, deterministic scope/diff/secret/test/review
  gates, audit events and transcripts.
- Root broker boundary, per-user mounts and credentials, egress allowlist,
  quotas, no human Docker/sudo membership, and a Forgejo runner without the
  host Docker socket.

## Implemented but awaiting live proof / Čeká na live důkaz

- Clean-VPS strict runtime acceptance, including adversarial mount, cgroup,
  quota, egress, lifecycle and interruption tests.
- Two clean Macs end to end: one Claude subscription and one Codex subscription,
  including login reuse, expiry/quota recovery, analysis, approval, task, tests
  and PR.
- Rootless Forgejo runner isolation plus fail-closed branch protection against
  real Forgejo status names.
- Three clean-Mac onboarding run, including a non-precreated login such as
  `sandokan`, replay/collision/interruption cases and controlled recovery.

Until those artifacts exist, the accurate release label is **alpha,
implementation complete but production acceptance incomplete** / **alfa,
implementace dokončena, produkční přijetí nedokončeno**.
