#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  AgenticDev — preflight čerstvého VPS
#
#  Pusť PŘED instalací. Systému se nedotkne, jen řekne, co by
#  instalaci pokazilo. Vrací 0, když se dá pokračovat.
#
#      bash tools/preflight-vps.sh
#
#  Proč zvlášť a ne uvnitř instalátoru: instalátor mění systém, a když
#  spadne v polovině kvůli málu paměti nebo obsazenému portu, uklízí se
#  to ručně. Tohle se dá pustit i z cizího stroje přes ssh.
# ═══════════════════════════════════════════════════════════════
set -uo pipefail

G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; B='\033[1;36m'; D='\033[2m'; O='\033[0m'
fail=0; warn=0
ok()   { printf "${G}  ✓${O} %s\n" "$*"; }
bad()  { printf "${R}  ✗${O} %s\n" "$*"; fail=$((fail+1)); }
soft() { printf "${Y}  !${O} %s\n" "$*"; warn=$((warn+1)); }
info() { printf "${D}    %s${O}\n" "$*"; }
hdr()  { printf "\n${B}▸ %s${O}\n" "$*"; }

printf "\n  AgenticDev — preflight\n"

# ─── Systém ────────────────────────────────────────────────────
hdr "Systém"
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  if [[ "${ID:-}" =~ ^(debian|ubuntu)$ ]]; then
    ok "$PRETTY_NAME"
  else
    bad "instalátor podporuje jen Debian/Ubuntu, tady je ${ID:-neznámé}"
  fi
else
  bad "chybí /etc/os-release — nepoznám distribuci"
fi

[[ $EUID -eq 0 ]] && ok "běžím jako root" \
  || soft "nejsi root — instalátor root potřebuje (sudo)"

ARCH=$(uname -m)
case "$ARCH" in
  x86_64|aarch64) ok "architektura $ARCH" ;;
  *) bad "architektura $ARCH — obrazy pro ni nemusí existovat" ;;
esac

# ─── Paměť a místo ─────────────────────────────────────────────
hdr "Zdroje"
MEM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)
if   (( MEM_MB >= 3800 )); then ok "RAM ${MEM_MB} MB"
elif (( MEM_MB >= 1800 )); then
  soft "RAM ${MEM_MB} MB — doporučené minimum je 4 GB"
  info "Postgres, Forgejo a MinIO se do 2 GB vejdou jen na zkoušku"
else bad "RAM ${MEM_MB} MB je málo, potřebuješ aspoň 2 GB"
fi

DISK_GB=$(df -BG --output=avail /srv 2>/dev/null | tail -1 | tr -dc '0-9' || echo 0)
: "${DISK_GB:=0}"
if   (( DISK_GB >= 20 )); then ok "volné místo ${DISK_GB} GB"
elif (( DISK_GB >= 10 )); then soft "volné místo ${DISK_GB} GB — obrazy a data vyrostou"
else bad "volné místo ${DISK_GB} GB je málo, potřebuješ aspoň 10 GB"
fi

CORES=$(nproc 2>/dev/null || echo 1)
(( CORES >= 2 )) && ok "$CORES jader" || soft "$CORES jádro — build control plane potrvá"

# ─── Porty ─────────────────────────────────────────────────────
hdr "Porty"
if command -v ss >/dev/null; then
  BUSY=""
  for p in 80 443 3000 5432 8080 9000 9001 2222; do
    ss -tlnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${p}\$" && BUSY="$BUSY $p"
  done
  [[ -z "$BUSY" ]] && ok "žádný z potřebných portů není obsazený" \
    || { bad "obsazené porty:$BUSY"; info "zastav, co na nich běží, nebo použij jiný stroj"; }
else
  soft "chybí ss (iproute2) — porty nezkontroluji"
fi

# ─── Konflikty ─────────────────────────────────────────────────
hdr "Co už na stroji je"
if [[ -e /srv/agenticdev/config/.env ]]; then
  soft "instalace už tu je — instalátor ji zaktualizuje a tajemství nechá"
else
  ok "čistý stroj, žádná předchozí instalace"
fi
command -v docker >/dev/null && ok "docker $(docker --version 2>/dev/null | cut -d, -f1 | awk '{print $3}')" \
  || info "docker nainstaluje instalátor"
if command -v tailscale >/dev/null; then
  TS_IP=$(tailscale ip -4 2>/dev/null | head -1)
  [[ -n "$TS_IP" ]] && ok "tailscale připojený, IP $TS_IP" \
    || soft "tailscale nainstalovaný, ale nepřipojený — 'tailscale up --ssh'"
else
  info "tailscale nainstaluje instalátor"
fi
if command -v apparmor_status >/dev/null 2>&1 || [[ -d /sys/kernel/security/apparmor ]]; then
  ok "apparmor je k dispozici"
else
  soft "apparmor nenalezen — kontejnery pojedou bez jeho profilu"
fi

# ─── Síť ───────────────────────────────────────────────────────
hdr "Síť"
for host in download.docker.com tailscale.com codeberg.org; do
  if curl -fsS --max-time 8 -o /dev/null "https://$host" 2>/dev/null; then
    ok "$host"
  else
    bad "$host nedostupný — instalace se bez něj nedotáhne"
  fi
done
if getent hosts registry-1.docker.io >/dev/null 2>&1; then
  ok "docker hub se překládá"
else
  soft "registry-1.docker.io se nepřeložil — zkontroluj DNS"
fi

# ─── Čas ───────────────────────────────────────────────────────
hdr "Hodiny"
if command -v timedatectl >/dev/null; then
  if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes; then
    ok "čas synchronizovaný"
  else
    soft "čas není synchronizovaný — TLS certifikáty a lease na tom stojí"
    info "systemctl enable --now systemd-timesyncd"
  fi
else
  soft "timedatectl chybí — synchronizaci času nezkontroluji"
fi

# ─── Výsledek ──────────────────────────────────────────────────
echo
if (( fail )); then
  printf "${R}✗ %d věcí musíš spravit, než začneš.${O}" "$fail"
  (( warn )) && printf " Dalších %d stojí za pohled." "$warn"
  printf "\n\n"
  exit 1
fi
if (( warn )); then
  printf "${Y}! Jde to, ale %d věcí stojí za pohled.${O}\n\n" "$warn"
else
  printf "${G}✓ Stroj je připravený.${O}\n\n"
fi
exit 0
