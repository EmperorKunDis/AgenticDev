#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Praut — generátor instalátoru Macu
#
#  Vyrobí JEDEN soubor svázaný S TOUTO instancí VPS:
#     /srv/praut/out/praut-install-mac.sh
#
#  Vazba = čtyři věci zapečené do souboru při generování:
#     1. adresa control plane (doména + tailnet fallback)
#     2. join token — zná ho jen tenhle VPS
#     3. fingerprint identity instance (ověří se proti /v1/identity)
#     4. SSH host key Forgeja (pinned known_hosts)
#
#  Když ten soubor pustíš proti jiné instanci, odmítne se nainstalovat.
#
#  Spouštění:  sudo praut-mac-installer        (kdykoliv, idempotentní)
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

ENVF="${PRAUT_ENV:-/srv/praut/config/.env}"
SRC="${PRAUT_SRC:-/srv/praut/src}"
OUT="${PRAUT_OUT:-/srv/praut/out}"
BODY="$SRC/install-mac.sh"

[[ -r "$ENVF" ]] || { echo "✗ nenašel jsem $ENVF" >&2; exit 1; }
[[ -r "$BODY" ]] || { echo "✗ nenašel jsem $BODY" >&2; exit 1; }

# shellcheck disable=SC1090
set -a; . "$ENVF"; set +a

: "${PRAUT_INSTANCE_ID:?v .env chybí PRAUT_INSTANCE_ID}"
: "${JOIN_TOKEN:?v .env chybí JOIN_TOKEN}"
: "${WO_VERIFY_KEY_B64:?v .env chybí WO_VERIFY_KEY_B64}"
: "${VPS_HOST:?v .env chybí VPS_HOST}"

CP_FALLBACK="http://${VPS_HOST}:8080"
if [[ "${PRAUT_MODE:-tailnet}" == "public" && -n "${PRAUT_DOMAIN:-}" ]]; then
  CP_PRIMARY="https://${PRAUT_DOMAIN}"
else
  CP_PRIMARY="$CP_FALLBACK"
fi

# fingerprint identity — musí souhlasit s tím, co počítá /v1/identity
IDENT="sha256:$(printf '%s\n%s' "$PRAUT_INSTANCE_ID" "$WO_VERIFY_KEY_B64" \
                | sha256sum | cut -d' ' -f1)"

# host key Forgeja — ať se Mac při prvním clone neptá na fingerprint
KH="$(ssh-keyscan -T 5 -p 2222 "$VPS_HOST" 2>/dev/null || true)"
[[ -n "$KH" ]] || echo "  ! Forgejo ještě neodpovídá na 2222 — known_hosts se nepřipne" >&2

STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
install -d -m 0750 "$OUT"
TARGET="$OUT/praut-install-mac.sh"
TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT

# ─── 1. hlavička s vazbou (proměnné se dosazují) ────────────────
cat >"$TMP" <<EOF
#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  PRAUT — instalátor Macu
#
#  Vygenerováno: $STAMP
#  Instance:     $PRAUT_INSTANCE_ID
#  Control plane: $CP_PRIMARY
#
#  Tenhle soubor patří k JEDNÉ konkrétní instanci Praut. Obsahuje
#  join token — ber ho jako heslo, neposílej ho veřejným kanálem.
#
#  Použití na Macu:   bash praut-install-mac.sh
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

PRAUT_INSTANCE="$PRAUT_INSTANCE_ID"
PRAUT_CP_PRIMARY="$CP_PRIMARY"
PRAUT_CP_FALLBACK="$CP_FALLBACK"
PRAUT_IDENTITY="$IDENT"
PRAUT_JOIN_TOKEN="$JOIN_TOKEN"
PRAUT_GIT_HOST="$VPS_HOST"
PRAUT_GIT_PORT="2222"
PRAUT_GENERATED="$STAMP"
PRAUT_KNOWN_HOSTS_B64="$(printf '%s' "$KH" | base64 -w0)"
PRAUT_BODY_B64="$(base64 -w0 <"$BODY")"
EOF

# ─── 2. statická logika (bez dosazování) ───────────────────────
cat >>"$TMP" <<'OUTER'

B='\033[1;36m'; G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; D='\033[2m'; O='\033[0m'
step(){ printf "\n${B}▸ %s${O}\n" "$*"; }
ok()  { printf "${G}  ✓${O} %s\n" "$*"; }
warn(){ printf "${Y}  !${O} %s\n" "$*"; }
die() { printf "\n${R}✗ %s${O}\n" "$*" >&2; exit 1; }

cat <<BANNER
  ┌────────────────────────────────────────┐
  │   P R A U T   —   připojení Macu       │
  └────────────────────────────────────────┘
BANNER
printf "  ${D}instance %s · vygenerováno %s${O}\n" \
  "${PRAUT_INSTANCE:0:8}" "$PRAUT_GENERATED"

[[ "$(uname)" == "Darwin" ]] || die "Tenhle instalátor je pro macOS."
[[ $EUID -ne 0 ]] || die "Nespouštěj přes sudo — pusť to jako svůj uživatel."
for t in curl shasum; do command -v "$t" >/dev/null || die "chybí $t"; done

# ═══ 1. Najdi VPS ══════════════════════════════════════════════
step "Hledám VPS"
CP=""
probe() { curl -fsS --max-time 8 "$1/v1/identity" 2>/dev/null; }
IDENT_JSON=""
for cand in "$PRAUT_CP_PRIMARY" "$PRAUT_CP_FALLBACK"; do
  [[ -n "$cand" ]] || continue
  if IDENT_JSON="$(probe "$cand")"; then CP="$cand"; break; fi
done

if [[ -z "$CP" ]]; then
  warn "VPS není vidět — pravděpodobně chybí Tailscale."
  if [[ ! -d /Applications/Tailscale.app ]] && ! command -v tailscale >/dev/null; then
    if command -v brew >/dev/null; then
      warn "instaluji Tailscale"
      brew install -q --cask tailscale >/dev/null 2>&1 || true
    else
      echo "     Nainstaluj Tailscale: https://tailscale.com/download/mac"
    fi
  fi
  open -a Tailscale 2>/dev/null || true
  echo
  echo "     Přihlas se v Tailscale do stejné sítě jako VPS a zmáčkni Enter."
  read -r </dev/tty
  for cand in "$PRAUT_CP_PRIMARY" "$PRAUT_CP_FALLBACK"; do
    if IDENT_JSON="$(probe "$cand")"; then CP="$cand"; break; fi
  done
fi
[[ -n "$CP" ]] || die "VPS pořád nedostupný ($PRAUT_CP_PRIMARY, $PRAUT_CP_FALLBACK).
   Zkontroluj: tailscale status"
ok "$CP"

# ═══ 2. Ověř, že je to TEN VPS ═════════════════════════════════
step "Ověřuji identitu VPS"
got_fp=$(sed -n 's/.*"fingerprint"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' <<<"$IDENT_JSON")
got_id=$(sed -n 's/.*"instance_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' <<<"$IDENT_JSON")
[[ -n "$got_fp" ]] || die "VPS neodpověděl identitou. Starší verze control plane?"
if [[ "$got_fp" != "$PRAUT_IDENTITY" ]]; then
  die "TOHLE JE JINÝ VPS.
   instalátor patří k: ${PRAUT_INSTANCE}
   odpovídá:           ${got_id:-?}
   Nic jsem neměnil. Vyžádej si instalátor z toho správného VPS."
fi
ok "instance ${got_id:0:8} — souhlasí"

# ═══ 3. Připni git host key ════════════════════════════════════
if [[ -n "$PRAUT_KNOWN_HOSTS_B64" ]]; then
  step "Připínám SSH klíč gitu"
  mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
  touch "$HOME/.ssh/known_hosts"; chmod 600 "$HOME/.ssh/known_hosts"
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    grep -qxF "$line" "$HOME/.ssh/known_hosts" 2>/dev/null \
      || printf '%s\n' "$line" >> "$HOME/.ssh/known_hosts"
  done < <(base64 --decode <<<"$PRAUT_KNOWN_HOSTS_B64")
  ok "$PRAUT_GIT_HOST:$PRAUT_GIT_PORT"
fi

# ═══ 4. Vlastní instalace ══════════════════════════════════════
BODY="$(mktemp "${TMPDIR:-/tmp}/praut-install-mac.XXXXXX")"
trap 'rm -f "$BODY"' EXIT
base64 --decode <<<"$PRAUT_BODY_B64" >"$BODY"
export PRAUT_CP="$CP"
export PRAUT_INSTANCE_ID="$PRAUT_INSTANCE"
bash "$BODY" "$PRAUT_JOIN_TOKEN"
OUTER

install -m 0640 "$TMP" "$TARGET"
( cd "$OUT" && sha256sum "$(basename "$TARGET")" > "$(basename "$TARGET").sha256" )
bash -n "$TARGET" || { echo "✗ vygenerovaný soubor má syntaktickou chybu" >&2; exit 1; }

echo "$TARGET"
