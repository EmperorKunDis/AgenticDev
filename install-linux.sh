#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  AGENTICDEV — připojení Linuxu
#
#      bash agenticdev-install.sh <TOKEN>
#
#  Idempotentní. Můžeš pustit znovu, nic nerozbije.
#  Nespouštěj přes sudo — instaluje se do tvého domovského adresáře.
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

B='\033[1;36m'; G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; D='\033[2m'; O='\033[0m'
step(){ printf "\n${B}▸ %s${O}\n" "$*"; }
ok()  { printf "${G}  ✓${O} %s\n" "$*"; }
warn(){ printf "${Y}  !${O} %s\n" "$*"; }
die() { printf "${R}✗ %s${O}\n" "$*" >&2; exit 1; }

TOKEN="${1:-}"
CP="${AGENTICDEV_CP:-__CONTROL_PLANE__}"
HOME_DIR="$HOME/.agenticdev"
WORK_DIR="$HOME/AgenticDev"
BIN_DIR="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"

clear 2>/dev/null || true
cat <<'BANNER'
  ┌────────────────────────────────┐
  │   P R A U T                    │
  │   připojení Linuxu             │
  └────────────────────────────────┘
BANNER

[[ -n "$TOKEN" ]] || die "Chybí heslo. Použij příkaz z registrační stránky."
[[ "$(uname)" == "Linux" ]] || die "Tenhle instalátor je pro Linux."
[[ $EUID -ne 0 ]] || die "Nespouštěj přes sudo — pusť to jako svůj uživatel."

# ═══ 1. Nástroje ═══════════════════════════════════════════════
step "Nástroje"

# Distribuce se liší jen jménem správce balíčků a názvy balíčků.
if   command -v apt-get >/dev/null; then PM=apt
elif command -v dnf     >/dev/null; then PM=dnf
elif command -v pacman  >/dev/null; then PM=pacman
elif command -v zypper  >/dev/null; then PM=zypper
else PM=""; fi

pkg_install() {
  [[ -n "$PM" ]] || { warn "neznámý správce balíčků — doinstaluj ručně: $*"; return 0; }
  case "$PM" in
    apt)    sudo apt-get update -qq && sudo apt-get install -y -qq "$@" ;;
    dnf)    sudo dnf install -y -q "$@" ;;
    pacman) sudo pacman -Sy --noconfirm --needed "$@" ;;
    zypper) sudo zypper -q install -y "$@" ;;
  esac
}

MISSING=()
for c in curl git jq; do command -v "$c" >/dev/null || MISSING+=("$c"); done
[[ ${#MISSING[@]} -gt 0 ]] && pkg_install "${MISSING[@]}" >/dev/null 2>&1
for c in curl git jq; do command -v "$c" >/dev/null || die "chybí $c a nepodařilo se ho doinstalovat"; done
ok "curl · git · jq"

if ! command -v node >/dev/null; then
  warn "instaluji Node"
  case "$PM" in
    apt)    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - >/dev/null 2>&1
            pkg_install nodejs >/dev/null 2>&1 ;;
    *)      pkg_install nodejs npm >/dev/null 2>&1 ;;
  esac
fi
command -v node >/dev/null && ok "node $(node -v)" || warn "Node se nenainstaloval — doplň ručně"

command -v fzf >/dev/null || pkg_install fzf >/dev/null 2>&1 || true

if ! command -v pi >/dev/null; then
  warn "instaluji Pi"
  npm install -g @earendil-works/pi-coding-agent >/dev/null 2>&1 \
    || sudo npm install -g @earendil-works/pi-coding-agent >/dev/null 2>&1 \
    || warn "Pi se nenainstalovalo — zkus: sudo npm i -g @earendil-works/pi-coding-agent"
fi
command -v pi >/dev/null && ok "pi" || true

# ═══ 2. Docker ═════════════════════════════════════════════════
# Agent běží v kontejneru, ne přímo na tvém stroji. Bez Dockeru se
# `agenticdev work` odmítne spustit.
step "Docker"
if ! command -v docker >/dev/null; then
  warn "instaluji Docker"
  curl -fsSL https://get.docker.com | sudo sh >/dev/null 2>&1 \
    || die "Docker se nenainstaloval. Nainstaluj ho ručně a pusť mě znovu."
fi
sudo systemctl enable --now docker >/dev/null 2>&1 || true

# Přidání do skupiny docker je fakticky rozdání rootu bez hesla. Ptáme
# se, místo abychom to udělali potichu — alternativa je psát sudo.
if ! docker info >/dev/null 2>&1 && ! groups | grep -qw docker; then
  echo
  echo "    Docker potřebuje buď sudo u každého příkazu, nebo tě přidat"
  echo "    do skupiny 'docker'. Ta skupina je fakticky root bez hesla."
  printf "    Přidat tě do ní? [a/N] "
  read -r ans </dev/tty
  if [[ "${ans,,}" == "a" ]]; then
    sudo usermod -aG docker "$USER"
    warn "odhlas se a přihlas, jinak se změna neprojeví"
  else
    warn "dobře — pak potřebuješ rootless Docker, jinak pod nenaběhne"
    echo "        https://docs.docker.com/engine/security/rootless/"
  fi
fi
ok "docker"

# ═══ 3. Síť ════════════════════════════════════════════════════
step "Síť"
if ! command -v tailscale >/dev/null; then
  warn "instaluji Tailscale"
  curl -fsSL https://tailscale.com/install.sh | sh >/dev/null 2>&1 \
    || die "Tailscale se nenainstaloval."
fi
if ! tailscale status >/dev/null 2>&1; then
  echo
  echo "    Přihlas se do Tailscale a zmáčkni Enter."
  echo "    (klíč jsi dostal na registrační stránce: sudo tailscale up --authkey ...)"
  read -r </dev/tty
fi
curl -fsS --max-time 8 "$CP/v1/health" >/dev/null 2>&1 \
  || die "Server není vidět. Jsi přihlášený v Tailscale? Zkus: tailscale status"
ok "spojení se serverem"

# ═══ 4. Klíče ══════════════════════════════════════════════════
step "Klíče tohohle stroje"
mkdir -p "$HOME_DIR"; chmod 700 "$HOME_DIR"
[[ -f "$HOME_DIR/device.key" ]] || \
  ssh-keygen -t ed25519 -N '' -C "agenticdev-$(hostname)" -f "$HOME_DIR/device.key" -q
[[ -f "$HOME/.ssh/id_ed25519" ]] || {
  mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
  ssh-keygen -t ed25519 -N '' -C "$(whoami)@$(hostname)" -f "$HOME/.ssh/id_ed25519" -q; }
FP=$(ssh-keygen -lf "$HOME_DIR/device.key.pub" | awk '{print $2}')
ok "vygenerováno"

# ═══ 5. Registrace ═════════════════════════════════════════════
step "Registrace"
NAME=$(getent passwd "$USER" | cut -d: -f5 | cut -d, -f1)
[[ -n "$NAME" ]] || NAME="$USER"
HOSTN=$(hostname)
EMAIL=$(git config --global user.email 2>/dev/null || echo "")

RESP=$(curl -fsS -X POST "$CP/v1/workstations/register" \
  -H 'content-type: application/json' \
  -d "$(jq -nc --arg t "$TOKEN" --arg h "$HOSTN" --arg f "$FP" --arg n "$NAME" \
        --arg e "$EMAIL" --arg k "$(cat "$HOME/.ssh/id_ed25519.pub")" \
        '{join_token:$t,hostname:$h,device_key_fp:$f,display_name:$n,email:$e,ssh_public_key:$k}')") \
  || die "Registrace selhala. Zkontroluj heslo."
jq -e .workstation_id >/dev/null <<<"$RESP" || die "Server odmítl: $RESP"

cat > "$HOME_DIR/config" <<EOF
CONTROL_PLANE=$CP
DEVICE_KEY_FP=$FP
HOSTNAME_=$HOSTN
EOF
chmod 600 "$HOME_DIR/config"
ok "stroj '$HOSTN' zaregistrován"
[[ "$(jq -r .git_ready <<<"$RESP")" == "true" ]] \
  && ok "git klíč nahrán" || warn "git klíč se nenahrál, ozvi se správci"

GITHOST=$(sed 's|^ssh://git@||; s|/.*||; s|:.*||' <<<"$(jq -r .git_ssh <<<"$RESP")")
GITPORT=$(jq -r .git_ssh <<<"$RESP" | sed -n 's|.*:\([0-9]*\)$|\1|p')
[[ -n "$GITHOST" ]] && ssh-keyscan -p "${GITPORT:-22}" "$GITHOST" \
  >> "$HOME/.ssh/known_hosts" 2>/dev/null || true

# ═══ 6. agenticdev ══════════════════════════════════════════════════
step "Nástroj agenticdev"
mkdir -p "$BIN_DIR"
curl -fsSL "$CP/agenticdev" -o "$BIN_DIR/agenticdev" || die "agenticdev se nepodařilo stáhnout"
chmod +x "$BIN_DIR/agenticdev"
# Zkratka. Celé jméno se píše každý den, tři písmena stačí.
ln -sf "$BIN_DIR/agenticdev" "$BIN_DIR/adev"
mkdir -p "$WORK_DIR"

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [[ -f "$rc" ]] || continue
  grep -q '.local/bin' "$rc" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
done
export PATH="$BIN_DIR:$PATH"
ok "agenticdev"

# ═══ 7. Ikona na plochu ════════════════════════════════════════
step "Ikona"
mkdir -p "$APPS" "$ICONS"
curl -fsSL "$CP/brand/agenticdev-launch" -o "$BIN_DIR/agenticdev-launch" 2>/dev/null \
  || curl -fsSL "$CP/linux/agenticdev-launch" -o "$BIN_DIR/agenticdev-launch" 2>/dev/null || true
chmod +x "$BIN_DIR/agenticdev-launch" 2>/dev/null || true

for sz in 16 32 48 64 128 256 512; do
  d="$ICONS/${sz}x${sz}/apps"; mkdir -p "$d"
  curl -fsSL "$CP/brand/png/icon-$sz.png" -o "$d/agenticdev.png" 2>/dev/null || true
done

cat > "$APPS/agenticdev.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=AgenticDev
GenericName=Agentic development
Comment=Otevře agenta a výběr projektu
Exec=$BIN_DIR/agenticdev-launch
Icon=agenticdev
Terminal=false
Categories=Development;IDE;
StartupNotify=true
EOF
chmod +x "$APPS/agenticdev.desktop"

command -v update-desktop-database >/dev/null && \
  update-desktop-database "$APPS" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null && \
  gtk-update-icon-cache -f -t "$ICONS" >/dev/null 2>&1 || true

# Některá prostředí chtějí ikonu i fyzicky na ploše
DESKTOP=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
if [[ -d "$DESKTOP" ]]; then
  cp "$APPS/agenticdev.desktop" "$DESKTOP/agenticdev.desktop" 2>/dev/null || true
  chmod +x "$DESKTOP/agenticdev.desktop" 2>/dev/null || true
  gio set "$DESKTOP/agenticdev.desktop" metadata::trusted true 2>/dev/null || true
fi
ok "AgenticDev v nabídce aplikací"

# ═══ Hotovo ════════════════════════════════════════════════════
cat <<EOF

  ${G}Hotovo.${O}

  Klikni na ikonu ${B}AgenticDev${O} v nabídce aplikací, nebo spusť:

      ${D}agenticdev work${O}

EOF
