#!/usr/bin/env sh
# ═══════════════════════════════════════════════════════════════
#  Egress proxy — jediná cesta z podu ven.
#
#  Pod je na síti bez routy do internetu. Všechno, co má odejít, jde
#  přes tenhle proces, a ten pustí jen domény z allowlistu.
#
#  Allowlist přichází v AGENTICDEV_EGRESS_ALLOW, čárkou oddělený. Prázdný
#  seznam znamená "nepustit nic" — ne "pustit všechno". Kdyby to bylo
#  naopak, chyba v konfiguraci by tiše otevřela síť dokořán.
# ═══════════════════════════════════════════════════════════════
set -eu

CONF=/tmp/tinyproxy.conf
FILTER=/tmp/allow.txt

: "${AGENTICDEV_EGRESS_ALLOW:=}"

# Regexy pro tinyproxy. Doména se ukotví z obou stran, aby "api.cz"
# nepustilo taky "api.cz.utocnik.example".
: > "$FILTER"
echo "$AGENTICDEV_EGRESS_ALLOW" | tr ',' '\n' | while IFS= read -r d; do
  d=$(printf '%s' "$d" | tr -d '[:space:]')
  [ -n "$d" ] || continue
  esc=$(printf '%s' "$d" | sed 's/\./\\./g')
  # doména samotná i libovolná subdoména
  printf '^%s$\n' "$esc"     >> "$FILTER"
  printf '^.*\\.%s$\n' "$esc" >> "$FILTER"
done

N=$(wc -l < "$FILTER" | tr -d ' ')

cat > "$CONF" <<EOF
User tinyproxy
Group tinyproxy
Port 8888
Timeout 600
MaxClients 40
StartServers 2

# Bez tohohle by proxy fungovala jako otevřený relay pro kohokoliv,
# kdo se na ni dostane.
Allow 0.0.0.0/0

# Allowlist. FilterDefaultDeny je to podstatné — bez něj by filtr
# fungoval jako blocklist a všechno neuvedené by prošlo.
Filter "$FILTER"
FilterURLs Off
FilterExtended On
FilterCaseSensitive Off
FilterDefaultDeny Yes

# CONNECT jen na HTTPS a git. Jinak by šlo tunelovat cokoliv.
ConnectPort 443
ConnectPort 2222

DisableViaHeader Yes
LogLevel Warning
EOF

echo "egress: $N pravidel z allowlistu"
if [ "$N" -eq 0 ]; then
  echo "egress: allowlist je prázdný — pod se ven nedostane" >&2
fi

exec tinyproxy -d -c "$CONF"
