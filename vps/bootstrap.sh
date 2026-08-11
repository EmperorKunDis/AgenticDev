#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Praut Platform — bootstrap čerstvého VPS
#  Debian 12 / Ubuntu 24.04, spouštěj jako root
#  Idempotentní: můžeš pustit opakovaně
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

log()  { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Spusť jako root."
[[ -f /etc/os-release ]] || die "Neznámý systém."
. /etc/os-release
[[ "$ID" =~ ^(debian|ubuntu)$ ]] || die "Podporováno jen Debian/Ubuntu, mám: $ID"

# ─── 1. Základ ─────────────────────────────────────────────────
log "Aktualizace a základní balíčky"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  ca-certificates curl gnupg git jq ufw fail2ban unattended-upgrades \
  restic apache2-utils age >/dev/null

# ─── 2. Docker ─────────────────────────────────────────────────
if ! command -v docker >/dev/null; then
  log "Instalace Dockeru"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" \
    -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$ID $VERSION_CODENAME stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin >/dev/null
else
  log "Docker už je nainstalovaný — přeskakuji"
fi
systemctl enable --now docker

# ─── 3. Tailscale ──────────────────────────────────────────────
if ! command -v tailscale >/dev/null; then
  log "Instalace Tailscale"
  curl -fsSL https://tailscale.com/install.sh | sh
  warn "Spusť ručně: tailscale up --ssh --advertise-tags=tag:vps"
else
  log "Tailscale už je nainstalovaný"
fi

# ─── 4. Firewall ───────────────────────────────────────────────
log "Firewall (ufw)"
ufw --force reset >/dev/null
ufw default deny incoming  >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp   comment 'ssh'        >/dev/null
ufw allow 443/tcp  comment 'https'      >/dev/null
ufw allow 41641/udp comment 'tailscale' >/dev/null
ufw allow in on tailscale0              >/dev/null
ufw --force enable >/dev/null
# Docker obchází ufw — publikujeme proto jen na tailnet, viz compose
sysctl -w net.ipv4.ip_forward=1 >/dev/null

# ─── 5. SSH hardening ──────────────────────────────────────────
log "SSH hardening"
cat > /etc/ssh/sshd_config.d/99-praut.conf <<'SSHEOF'
PasswordAuthentication no
PermitRootLogin prohibit-password
KbdInteractiveAuthentication no
MaxAuthTries 3
SSHEOF
systemctl reload ssh 2>/dev/null || systemctl reload sshd

# ─── 6. Automatické bezpečnostní aktualizace ───────────────────
log "Unattended upgrades"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'AUEOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
AUEOF

# ─── 7. Adresáře ───────────────────────────────────────────────
log "Adresářová struktura"
install -d -m 0750 /srv/praut/{data,config,backup}
install -d -m 0750 /srv/praut/data/{postgres,forgejo,minio,caddy,directors}

# ─── 8. Zálohy ─────────────────────────────────────────────────
log "Instalace zálohovacího systemd timeru"
install -m 0700 "$(dirname "$0")/backup/restic-backup.sh" /usr/local/bin/praut-backup
cat > /etc/systemd/system/praut-backup.service <<'SVCEOF'
[Unit]
Description=Praut Platform záloha (restic)
After=network-online.target
[Service]
Type=oneshot
EnvironmentFile=/srv/praut/config/.env
ExecStart=/usr/local/bin/praut-backup
SVCEOF
cat > /etc/systemd/system/praut-backup.timer <<'TMREOF'
[Unit]
Description=Denní záloha Praut Platform
[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
RandomizedDelaySec=15m
[Install]
WantedBy=timers.target
TMREOF
systemctl daemon-reload
systemctl enable praut-backup.timer >/dev/null

log "Hotovo."
cat <<'NEXTEOF'

  Další kroky:
    1) tailscale up --ssh
    2) zkopíruj .env do /srv/praut/config/.env
    3) cd /srv/praut && docker compose up -d
    4) make -C <repo> smoke

  Ověř, že Postgres a MinIO NEJSOU dostupné z veřejné IP:
    nmap -Pn <verejna-ip>   →  má být otevřený jen 22 a 443

NEXTEOF
