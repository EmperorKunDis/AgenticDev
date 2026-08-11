#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  PRAUT — připojení Macu
#
#      curl -fsSL http://<vps>/install-mac.sh | bash -s -- <TOKEN>
#
#  Idempotentní. Můžeš pustit znovu, nic nerozbije.
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

B='\033[1;36m'; G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; D='\033[2m'; O='\033[0m'
step(){ printf "\n${B}▸ %s${O}\n" "$*"; }
ok()  { printf "${G}  ✓${O} %s\n" "$*"; }
warn(){ printf "${Y}  !${O} %s\n" "$*"; }
die() { printf "${R}✗ %s${O}\n" "$*" >&2; exit 1; }

TOKEN="${1:-}"
CP="${PRAUT_CP:-__CONTROL_PLANE__}"
HOME_DIR="$HOME/.praut"
WORK_DIR="$HOME/Praut"
APP="/Applications/Praut.app"

clear
cat <<'BANNER'
  ┌────────────────────────────────┐
  │   P R A U T                    │
  │   připojení Macu               │
  └────────────────────────────────┘
BANNER

[[ -n "$TOKEN" ]] || die "Chybí token. Použij příkaz, který ti poslal správce."
[[ "$(uname)" == "Darwin" ]] || die "Tenhle instalátor je pro macOS."

# ═══ 1. Nástroje ═══════════════════════════════════════════════
step "Nástroje"
if ! command -v brew >/dev/null; then
  warn "instaluji Homebrew (zeptá se na heslo)"
  NONINTERACTIVE=1 /bin/bash -c \
    "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
  [[ -x "$p" ]] && eval "$($p shellenv)" && break
done
command -v brew >/dev/null || die "Homebrew se nenainstaloval."
ok "homebrew"

for pkg in jq git node fzf; do
  command -v "${pkg}" >/dev/null || brew install -q "$pkg" >/dev/null 2>&1
done
ok "jq · git · node · fzf"

# Agent běží v kontejneru, ne přímo na tvém Macu. Colima místo Docker
# Desktopu schválně — Desktop je pro firmy nad 250 zaměstnanců nebo
# 10 M $ obratu placený, Colima je Apache-2.0 a stačí na to.
if ! command -v docker >/dev/null; then
  warn "instaluji Docker (colima)"
  brew install -q colima docker >/dev/null 2>&1 || true
fi
if command -v colima >/dev/null && ! docker info >/dev/null 2>&1; then
  warn "startuji colima (poprvé to chvíli trvá)"
  colima start --cpu 2 --memory 4 >/dev/null 2>&1 || \
    warn "colima se nespustila — zkus ručně: colima start"
fi
docker info >/dev/null 2>&1 && ok "docker" \
  || warn "Docker neběží. Bez něj se pod nespustí — spusť: colima start"

command -v pi >/dev/null || {
  warn "instaluji Pi"
  npm install -g @earendil-works/pi-coding-agent >/dev/null 2>&1 \
    || sudo npm install -g @earendil-works/pi-coding-agent; }
ok "pi"

# ═══ 2. Terminál ═══════════════════════════════════════════════
step "Terminál"
[[ -d /Applications/Ghostty.app ]] || brew install -q --cask ghostty >/dev/null 2>&1 || true
if [[ -d /Applications/Ghostty.app ]]; then
  mkdir -p "$HOME/.config/ghostty"
  if [[ -f "$HOME/.config/ghostty/config" ]] && ! grep -q '^# Praut' "$HOME/.config/ghostty/config"; then
    cp "$HOME/.config/ghostty/config" "$HOME/.config/ghostty/config.pred-prautem"
    warn "tvoje konfigurace Ghostty zazálohována jako config.pred-prautem"
  fi
  curl -fsSL "$CP/ghostty-config" -o "$HOME/.config/ghostty/config" 2>/dev/null || true
  brew list --cask font-jetbrains-mono >/dev/null 2>&1 || \
    brew install -q --cask font-jetbrains-mono >/dev/null 2>&1 || true
  ok "ghostty"
else
  warn "Ghostty se nenainstaloval — použije se Terminal.app"
fi

# ═══ 3. Síť ════════════════════════════════════════════════════
step "Síť"
if [[ ! -d /Applications/Tailscale.app ]] && ! command -v tailscale >/dev/null; then
  brew install -q --cask tailscale >/dev/null 2>&1 || true
  open -a Tailscale 2>/dev/null || true
  echo
  echo "    Přihlas se v Tailscale a zmáčkni Enter."
  read -r </dev/tty
fi
curl -fsS --max-time 8 "$CP/v1/health" >/dev/null 2>&1 \
  || die "VPS není dostupný. Jsi přihlášený v Tailscale?"
ok "spojení s VPS"

# ═══ 4. Klíče ══════════════════════════════════════════════════
step "Klíče tohoto Macu"
mkdir -p "$HOME_DIR"; chmod 700 "$HOME_DIR"
[[ -f "$HOME_DIR/device.key" ]] || \
  ssh-keygen -t ed25519 -N '' -C "praut-$(scutil --get ComputerName 2>/dev/null || hostname)" \
    -f "$HOME_DIR/device.key" -q
[[ -f "$HOME/.ssh/id_ed25519" ]] || {
  mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
  ssh-keygen -t ed25519 -N '' -C "$(whoami)@$(hostname)" -f "$HOME/.ssh/id_ed25519" -q; }
FP=$(ssh-keygen -lf "$HOME_DIR/device.key.pub" | awk '{print $2}')
ok "vygenerováno"

# ═══ 5. Registrace ═════════════════════════════════════════════
step "Registrace"
NAME=$(id -F 2>/dev/null || whoami)
HOSTN=$(scutil --get ComputerName 2>/dev/null || hostname)
EMAIL=$(git config --global user.email 2>/dev/null || echo "")

RESP=$(curl -fsS -X POST "$CP/v1/workstations/register" \
  -H 'content-type: application/json' \
  -d "$(jq -nc --arg t "$TOKEN" --arg h "$HOSTN" --arg f "$FP" --arg n "$NAME" \
        --arg e "$EMAIL" --arg k "$(cat "$HOME/.ssh/id_ed25519.pub")" \
        '{join_token:$t,hostname:$h,device_key_fp:$f,display_name:$n,email:$e,ssh_public_key:$k}')") \
  || die "Registrace selhala. Zkontroluj token."
jq -e .workstation_id >/dev/null <<<"$RESP" || die "Server odmítl: $RESP"

cat > "$HOME_DIR/config" <<EOF
CONTROL_PLANE=$CP
DEVICE_KEY_FP=$FP
HOSTNAME_=$HOSTN
EOF
chmod 600 "$HOME_DIR/config"
ok "stroj '$HOSTN' zaregistrován"
[[ "$(jq -r .git_ready <<<"$RESP")" == "true" ]] \
  && ok "git klíč nahrán — clone bude fungovat" \
  || warn "git klíč se nenahrál, ozvi se správci"

# důvěra ke známému git serveru, ať clone neptá na fingerprint
GITHOST=$(sed 's|^ssh://git@||; s|/.*||; s|:.*||' <<<"$(jq -r .git_ssh <<<"$RESP")")
GITPORT=$(jq -r .git_ssh <<<"$RESP" | sed -n 's|.*:\([0-9]*\)$|\1|p')
[[ -n "$GITHOST" ]] && ssh-keyscan -p "${GITPORT:-22}" "$GITHOST" >> "$HOME/.ssh/known_hosts" 2>/dev/null || true

# ═══ 6. praut ══════════════════════════════════════════════════
step "Nástroj praut"
curl -fsSL "$CP/praut" -o "$HOME_DIR/praut" || die "praut se nepodařilo stáhnout"
chmod +x "$HOME_DIR/praut"
if sudo -n true 2>/dev/null; then sudo install -m755 "$HOME_DIR/praut" /usr/local/bin/praut
else
  mkdir -p "$HOME/bin"; install -m755 "$HOME_DIR/praut" "$HOME/bin/praut"
  grep -q 'HOME/bin' "$HOME/.zshrc" 2>/dev/null || echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.zshrc"
fi
mkdir -p "$WORK_DIR"
ok "praut"

# ═══ 7. Aplikace ═══════════════════════════════════════════════
step "Aplikace"
rm -rf "$APP"
curl -fsSL "$CP/praut-app.tar.gz" -o /tmp/praut-app.tar.gz 2>/dev/null \
  && tar xzf /tmp/praut-app.tar.gz -C /Applications 2>/dev/null \
  || { mkdir -p "$APP/Contents/MacOS"
       curl -fsSL "$CP/praut-app-plist" -o "$APP/Contents/Info.plist" 2>/dev/null
       curl -fsSL "$CP/praut-app-bin"   -o "$APP/Contents/MacOS/Praut" 2>/dev/null; }
chmod +x "$APP/Contents/MacOS/Praut" 2>/dev/null || true

# Ikona. .icns se nedá vyrobit jinde než na macOS, tak ji sestavíme tady
# z iconsetu, který přišel v balíčku.
ICONSET="$APP/Contents/Resources/AppIcon.iconset"
if [[ -d "$ICONSET" ]] && command -v iconutil >/dev/null; then
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns" 2>/dev/null \
    && rm -rf "$ICONSET" && ok "ikona" \
    || warn "ikonu se nepodařilo sestavit, aplikace pojede s výchozí"
fi

xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
touch "$APP"; rm -f /tmp/praut-app.tar.gz
[[ -x "$APP/Contents/MacOS/Praut" ]] && ok "Praut.app v Applications" || warn "aplikaci se nepodařilo vytvořit"

open -a Dock 2>/dev/null || true
defaults write com.apple.dock persistent-apps -array-add \
  "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>$APP</string><key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>" 2>/dev/null \
  && killall Dock 2>/dev/null && ok "přidáno do Docku" || true

# ═══ HOTOVO ════════════════════════════════════════════════════
clear
cat <<EOF

  ${G}Hotovo. Tenhle Mac je připojený.${O}

  ${B}Práce${O}     klikni na ${Y}Praut${O} v Docku
  ${B}Nástěnka${O}  $CP

  ${D}Ještě jednou se přihlas do Pi:${O}
     ${Y}pi${O}   a uvnitř   ${Y}/login${O}

EOF
