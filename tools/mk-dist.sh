#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  AgenticDev — build instalátoru VPS / VPS installer build
#
#  Z repozitáře vyrobí jeden self-extracting soubor:
#     dist/agenticdev-install-vps.sh
#     dist/agenticdev-install-vps.sh.sha256
#
#  DETERMINISTICKÝ: stejný commit → stejný kontrolní součet.
#  Toho dosahujeme tím, že do tar.gz nejdou časy, vlastníci ani
#  pořadí závislé na souborovém systému.
#
#  Používá se ručně (`make dist`) i z CI při vydání releasu.
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
STUB="$ROOT/install-vps.sh"
OUT="$DIST/agenticdev-install-vps.sh"
MARKER='#__AGENTICDEV_PAYLOAD_BELOW__'

# Reprodukovatelnost: čas z posledního commitu, jinak pevná epocha.
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git -C "$ROOT" log -1 --pretty=%ct 2>/dev/null || echo 1700000000)}"
export SOURCE_DATE_EPOCH

[[ -f "$STUB" ]] || { echo "✗ chybí $STUB" >&2; exit 1; }
grep -q "^${MARKER}\$" "$STUB" \
  || { echo "✗ v $STUB chybí značka $MARKER" >&2; exit 1; }

echo "▸ Build"
rm -rf "$DIST"; mkdir -p "$DIST"

# Python tarfile dává stejný výstup na GNU/Linux i macOS/BSD.
AGENTICDEV_PAYLOAD_ROOT="$ROOT" AGENTICDEV_PAYLOAD_OUT="$DIST/payload.tar.gz" \
  python3 "$ROOT/tools/build-payload.py"

# Hlavička = stub až po značku včetně, pak base64 payload.
awk -v m="$MARKER" '$0==m{print; exit} {print}' "$STUB" > "$OUT"
base64 < "$DIST/payload.tar.gz" | tr -d '\n' >> "$OUT"
printf '\n' >> "$OUT"
rm -f "$DIST/payload.tar.gz"
chmod +x "$OUT"

# Kontroly, ať nevydáme rozbitý soubor.
bash -n "$OUT" || { echo "✗ vygenerovaný soubor se neparsuje" >&2; exit 1; }

( cd "$DIST" && shasum -a 256 agenticdev-install-vps.sh > agenticdev-install-vps.sh.sha256 )

SIZE=$(wc -c < "$OUT")
SUM=$(cut -d' ' -f1 < "$DIST/agenticdev-install-vps.sh.sha256")
printf '  ✓ %s\n    %s bajtů\n    sha256 %s\n' "$OUT" "$SIZE" "$SUM"
