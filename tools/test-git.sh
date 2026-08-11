#!/usr/bin/env bash
# Projede agenticdev-git na dočasném repozitáři. Nic nemaže mimo /tmp.
set -euo pipefail
PG="$(cd "$(dirname "$0")/.." && pwd)/workspace/_base/bin/agenticdev-git"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/o" "$T/w"
git init -q --bare "$T/o"
cd "$T/w" && git init -q -b main && git config user.email t@t.cz && git config user.name T
mkdir -p src tests && echo x > src/a.ts && echo x > tests/.keep
git add -A && git commit -qm init && git remote add origin "$T/o" && git push -qu origin main

export AGENTICDEV_SESSION=test-session
W=$("$PG" start "Import karet z DE systému" T-042 2>/dev/null)
[[ -d "$W" ]] || { echo "✗ start nevytvořil worktree"; exit 1; }
cd "$W"
[[ "$(git branch --show-current)" == task/T-042-* ]] || { echo "✗ špatná větev"; exit 1; }
echo "✓ start — worktree a větev s diakritikou"

echo b > src/b.ts && "$PG" checkpoint k1 >/dev/null 2>&1
echo c > src/c.ts && "$PG" checkpoint k2 >/dev/null 2>&1
[[ $(git log --oneline --grep='^wip(' | wc -l) -eq 2 ]] || { echo "✗ checkpointy"; exit 1; }
echo "✓ checkpointy"

echo t > tests/i.test.ts && "$PG" save feat import "karty z DE" >/dev/null 2>&1
echo "✓ save"

"$PG" finish "feat(import): karty z DE systému" >/dev/null 2>&1
B=$(git branch --show-current)
[[ $(git log --oneline "origin/main..origin/$B" | wc -l) -eq 1 ]] \
  || { echo "✗ wip se nesesypaly"; exit 1; }
echo "✓ finish — wip sesypané do jednoho commitu"

# pozor: grep -q uzavře rouru a s pipefail to vypadá jako chyba — čteme do proměnné
OUT=$("$PG" who src/b.ts 2>&1)
[[ "$OUT" == *test-session* ]] || { echo "✗ provenance"; echo "$OUT"; exit 1; }
echo "✓ provenance přežila sesypání"
echo; echo "✓ VŠE PROŠLO"
