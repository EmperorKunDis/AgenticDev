# AgenticDev

**Self-hosted agentic development platform.** One VPS holds all data,
context, and orchestration. Developers run the agent on their own machine
against a project checkout, with instructions, scope, and phase supplied by
the server — and decisions, runs, and costs written back to an auditable
ledger.

🇨🇿 [Česká verze tohoto dokumentu](README.cs.md)

> **Status: alpha.** The sandbox and the Windows and Linux clients have not
> yet been exercised in production. Read
> [Known limitations](#known-limitations) before you deploy this.

---

## What it actually is

Most "AI coding agent" setups put the agent on the developer's laptop and
hope for the best. AgenticDev inverts that:

- **The server supplies the working context.** Which project, which phase,
  which files are in scope, which instructions and skills the agent gets —
  all of it is composed on the server per phase and per project, not
  configured on each laptop.
- **Everything is written back.** Decisions, runs, costs, and artifacts land
  in a Postgres ledger with a hash chain, not in someone's chat history.
- **Onboarding is one link.** A new machine joins with a password and
  registers itself; you revoke it from the panel.

- **The agent is sandboxed.** It runs in a container with no route to the
  internet — the only path out is a proxy that allows the domains you list.
  The repository is mounted read-only and only the paths in scope are
  remounted writable, so a write outside scope fails at the kernel, not
  because the agent chose to behave.

One company = one VPS. There is no central service. We never learn that you
installed it.

---

## Requirements

| | |
|---|---|
| Server | Debian 12 or Ubuntu 22.04/24.04, 4 GB RAM minimum, root access |
| Network | **Tailscale** — hard requirement, not optional |
| Clients | macOS, Linux, or Windows 10 build 19041+ (via WSL2) — plus Docker, which the installer sets up |
| Optional | A model provider API key, or a local Ollama instance |

**Before you install**, two things in your Tailscale admin console:

1. [DNS](https://login.tailscale.com/admin/dns) → *HTTPS Certificates* →
   **Enable HTTPS**. Without it the server cannot get a certificate for its
   `.ts.net` name.
2. [Access controls](https://login.tailscale.com/admin/acls) → *Funnel* →
   **Add Funnel to policy**. Without it the public enrollment page will not
   come up.

The installer checks both and tells you if either is missing.

---

## Install

### 1. Server — once

Download the release artifact and its checksum, verify, then run it. Do not
pipe it into bash; the installer refuses to run that way on purpose.

```bash
curl -fLO https://github.com/Praut-Startup-Support/AgenticDev/releases/latest/download/agenticdev-install-vps.sh
curl -fLO https://github.com/Praut-Startup-Support/AgenticDev/releases/latest/download/agenticdev-install-vps.sh.sha256
sha256sum -c agenticdev-install-vps.sh.sha256

scp agenticdev-install-vps.sh root@your-vps:/root/
ssh root@your-vps 'bash /root/agenticdev-install-vps.sh'
```

It asks five questions and does the rest: Docker, firewall, SSH hardening,
Tailscale, Postgres, Forgejo, MinIO, Caddy, the control plane, daily backups.

Useful flags:

```bash
bash agenticdev-install-vps.sh --check      # verify the payload, touch nothing
bash agenticdev-install-vps.sh --yes        # non-interactive, reads env vars
bash agenticdev-install-vps.sh --mac-only   # regenerate the Mac installer only
```

When it finishes it prints two links:

| Link | Who | Where it works |
|---|---|---|
| **Admin panel** | you | tailnet only |
| **Enrollment page** | your team | public internet |

You pick both passwords during the install.

### 2. Clients — unlimited machines, anywhere

Send the enrollment link to anyone. They open it, type the join password,
pick their operating system, and get two commands to paste.

**macOS · Linux · Windows.** Windows runs through WSL2.

The installer registers that machine under the person's own name and email,
uploads their SSH key to Forgejo, and puts a **AgenticDev icon** on their desktop.
Clicking it opens the agent and a project picker.

They show up in the admin panel's *team* tab, where you can revoke any single
machine.

**What is actually exposed to the internet:** exactly one path — the
enrollment page — published through [Tailscale
Funnel](https://tailscale.com/kb/1223/funnel). No public IP or domain needed.
The password is the only gate on it, so it is rate limited per IP and
globally, and locks an address out for an hour after five failures.

Everything else — the panel, git, the API — stays on your tailnet.

### 3. Admin panel

Model provider and API key, egress allowlist, both passwords, lease duration,
Tailscale keys, and SMTP are editable in the panel and take effect
immediately. Settings that need a container restart live in
`/srv/agenticdev/config/.env` and the panel shows them read-only.

---

## Daily use

Click the **AgenticDev** icon, or from a terminal:

```bash
agenticdev work                 # pick a project, get a task, start a pod
agenticdev work acme            # straight to one project
agenticdev doctor          # check local prerequisites
```

`adev` works as a shorthand for `agenticdev`.

The pod comes up with an egress proxy in front of it, a read-only context
bundle, secrets on tmpfs with a TTL, and a git checkout on a work branch.
Teardown removes all of it.

---

## How the sandbox works

`agenticdev work` does not run the agent on your machine. It brings up two
containers:

```
   egress ── allowlist ──► internet
      ▲
      │  the only route out
      │
    pod ── no default route, no Docker socket, non-root, all caps dropped
      │
      └── /workspace   repo read-only, scope paths remounted rw
          /ctx         context bundle, read-only
          /run/agenticdev   token and policy, tmpfs, gone on teardown
```

Git operations that touch the network stay on the host — the agent commits
locally and never holds credentials to your repository. The launcher pushes
the work branch after the pod exits.

The harness refuses to start if the workspace root turns out to be
writable, or if the pod has no proxy configured. A misconfigured sandbox
fails loudly instead of quietly not protecting anything.

---

## How permissions work

This is the part worth understanding.

Each phase has a `scope` file listing the paths it may write to:

| Phase | Writable |
|---|---|
| discovery | `prd/**`, `docs/**` |
| design | + `design/**` |
| implementation | `src/**`, `tests/**`, ADRs |
| hardening | + `infra/**` |
| delivery | `docs/**`, README, CHANGELOG |

The control plane sends that list to the launcher, which mounts the
repository read-only and remounts exactly those paths writable. So changing
what an agent may do during design means editing
`workspace/_phase/design/scope` — not editing a user, and not trusting the
agent to respect a rule.

`control-plane/app/workspace.py` also merges `.pi/settings.json` across the
base and phase layers, and chains `AGENTS.md` — but those carry
instructions, not the boundary. The boundary is the mount.

---

## Where to change things

| I want to… | Edit |
|---|---|
| change what an agent may do in a phase | `workspace/_phase/<phase>/scope` |
| add a phase | `workspace/_phase/<new>/`, then `make verify` |
| change instructions for all projects | `workspace/_base/AGENTS.md` |
| add a service on the server | `vps/docker-compose.yml` and `vps/Caddyfile` |
| change the database schema | `vps/sql/001_schema.sql` — as a migration, not a rewrite |
| change what the harness enforces | `pod/harness/harness.py` |

---

## Building from source

The release artifact is a self-extracting script built from this repository.
You can build and verify it yourself:

```bash
make verify     # check that every path the tree promises actually exists
make dist       # build dist/agenticdev-install-vps.sh and its checksum
make check-dist # run the built artifact's own --check
```

`make dist` is deterministic: building the same commit twice produces the
same checksum.

---

## Known limitations

Honest status. These are tracked as blockers to 1.0:

- **No server-side merge gate.** The agent runs its own tests inside its own
  pod. Fine for a small trusted team; not sufficient otherwise.
- **No observability stack.** Grafana and Loki are commented out; the harness
  logs to stdout.
- **Join tokens never expire** and are per-instance, not per-person.
- **Token counting is an estimate** (`len/3`), and model prices in `PRICING`
  are unverified. Dashboard cost figures are indicative only.
- **CI is not written.** Forgejo Actions is enabled; no workflows exist.
- **The orchestration layer (directors) does not exist.** The architecture
  document describes it; the code does not contain it. The agent works
  without a state machine.
- **Container escape is out of scope.** The pod drops all capabilities,
  runs non-root, and has no Docker socket — but a container is not a
  hypervisor. Treat it as a strong fence, not a vault.

See [SECURITY.md](SECURITY.md) for the security implications.

---

## Licence

**Business Source License 1.1** — source-available, not OSI open source.

Free for evaluation, development, education, and production use at
organizations under **EUR 1,000,000** annual revenue. Larger organizations
need a commercial licence. Every version converts to **Apache-2.0 four years
after release**.

Plain-language explanation in both languages: [LICENSE-FAQ.md](LICENSE-FAQ.md).
Binding text: [LICENSE](LICENSE).

Commercial licensing: **svanda@praut.cz**

© 2026 Praut s.r.o.

---

## Website

A one-page site lives in [`site/`](site/) and deploys to GitHub Pages.
See [site/README.md](site/README.md) for the two things to fill in before
it goes live.

---

## Publishing your own fork

See [PUBLISHING.md](PUBLISHING.md) — placeholders to fill in, release
process, and a test checklist.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Contributions require a CLA, because
the project is dual-licensed and we cannot sell commercial licences for code
we do not hold the rights to.
