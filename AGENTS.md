# Repository Guidelines

## Project Structure & Module Organization

AgenticDev is a self-hosted platform built mainly from Python services and Bash deployment tooling. The FastAPI control plane lives in `control-plane/app/`; the root-owned runtime broker and VPS operations are under `vps/`; and the isolated agent image and harness are in `pod/`. The user launcher is in `launcher/`. Shared agent instructions and phase scopes live in `workspace/`. Repository checks and packaging helpers are in `tools/`, while broker and integration tests are in `tests/`. Documentation belongs in `docs/` and top-level Markdown files. Web and brand assets are under `site/` and `brand/`.

## Build, Test, and Development Commands

- `make help` lists supported targets.
- `make verify` checks required files and script syntax.
- `make test-git` tests the Git helper in a temporary repository.
- `make test-broker` runs Python broker tests with `unittest` discovery.
- `make test` runs the complete local verification suite.
- `make dist` builds the generated VPS installer in `dist/`.
- `make check-dist` builds and validates the installer without installing it.
- `make preflight` checks VPS prerequisites; `make smoke` targets an installed deployment.

Install control-plane dependencies in a virtual environment with `python3 -m pip install -r control-plane/requirements.txt`.

## Coding Style & Naming Conventions

Follow the surrounding file. Use `snake_case` for Python functions and modules, `PascalCase` for test classes, and lowercase hyphenated names for shell tools. Keep scripts Bash-compatible and validate them with `bash -n`; run `shellcheck` when available. Do not edit generated files in `dist/` directly. Update English and Czech user-facing documentation together when both versions exist.

## Testing Guidelines

Tests use the standard-library `unittest` framework and follow `tests/test_*.py`. Add focused regression tests for security boundaries, authorization, filesystem isolation, and workload lifecycle changes. Exercise both allowed and rejected paths. Run `make test` before submission; packaging changes must also pass `make check-dist`.

## Commits, Pull Requests & Security

Use short, imperative, scoped subjects such as `security: harden privileged runtime boundary` or `test: isolate broker filesystem roots in CI`. Keep commits focused. Pull requests should explain operational and security impact, reference relevant issues or ADRs, list exact test commands, and include screenshots for visible UI changes. Never weaken fail-closed behavior to satisfy a test. Do not expose Docker/containerd sockets, secrets, raw host paths, or privileged runtime flags to ordinary users. Report vulnerabilities through `SECURITY.md`, not public issues.
