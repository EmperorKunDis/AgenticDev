#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Praut — build instalátoru VPS / VPS installer build
#
#  Z repozitáře vyrobí jeden self-extracting soubor:
#     dist/praut-install-vps.sh
#     dist/praut-install-vps.sh.sha256
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
OUT="$DIST/praut-install-vps.sh"
MARKER='#__PRAUT_PAYLOAD_BELOW__'

# Reprodukovatelnost: čas z posledního commitu, jinak pevná epocha.
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git -C "$ROOT" log -1 --pretty=%ct 2>/dev/null || echo 1700000000)}"
export SOURCE_DATE_EPOCH

# Co do balíčku NEPATŘÍ.
EXCLUDES=(
  --exclude='./.git'          --exclude='./.github'
  --exclude='./dist'          --exclude='./data'
  --exclude='./.env'          --exclude='./*.key'
  --exclude='./*.pem'         --exclude='./secrets'
  --exclude='./.venv'         --exclude='./__pycache__'
  --exclude='*.pyc'           --exclude='./.wo-cache'
)

[[ -f "$STUB" ]] || { echo "✗ chybí $STUB" >&2; exit 1; }
grep -q "^${MARKER}\$" "$STUB" \
  || { echo "✗ v $STUB chybí značka $MARKER" >&2; exit 1; }

echo "▸ Build"
rm -rf "$DIST"; mkdir -p "$DIST"

# Payload. `--sort=name` + pevný mtime/uid/gid = stejný bajt pokaždé.
tar --sort=name \
    --mtime="@${SOURCE_DATE_EPOCH}" \
    --owner=0 --group=0 --numeric-owner \
    --format=gnu \
    "${EXCLUDES[@]}" \
    -cf "$DIST/payload.tar" -C "$ROOT" . 2>/dev/null

gzip -n -9 -c "$DIST/payload.tar" > "$DIST/payload.tar.gz"
rm -f "$DIST/payload.tar"

# Hlavička = stub až po značku včetně, pak base64 payload.
awk -v m="$MARKER" '$0==m{print; exit} {print}' "$STUB" > "$OUT"
base64 -w0 "$DIST/payload.tar.gz" >> "$OUT"
printf '\n' >> "$OUT"
rm -f "$DIST/payload.tar.gz"
chmod +x "$OUT"

# Kontroly, ať nevydáme rozbitý soubor.
bash -n "$OUT" || { echo "✗ vygenerovaný soubor se neparsuje" >&2; exit 1; }

( cd "$DIST" && sha256sum praut-install-vps.sh > praut-install-vps.sh.sha256 )

SIZE=$(wc -c < "$OUT")
SUM=$(cut -d' ' -f1 < "$DIST/praut-install-vps.sh.sha256")
printf '  ✓ %s\n    %s bajtů\n    sha256 %s\n' "$OUT" "$SIZE" "$SUM"
