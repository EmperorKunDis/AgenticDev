#!/usr/bin/env bash
# Přejmenování produktu praut → AgenticDev.
#
# Klíčová past: "praut" znamená dvě různé věci. Produkt (mění se) a firmu
# Praut s.r.o. s doménou praut.cz a GitHub organizací (nemění se). Firemní
# výskyty proto nejdřív schováme za značky a na konci vrátíme.
set -euo pipefail
[[ -f LICENSE && -d control-plane ]] || { echo "✗ spusť z kořene repa" >&2; exit 1; }

files() {
  grep -rlI "$1" . --exclude-dir=.git --exclude-dir=dist \
       --exclude-dir=node_modules 2>/dev/null | sort -u || true
}
sub() {  # sub <hledat> <nahradit>
  local n=0
  while IFS= read -r f; do
    [[ -n "$f" ]] || continue
    sed -i.bak "s|$1|$2|g" "$f" && rm -f "$f.bak"; n=$((n+1))
  done <<< "$(files "$1")"
  [[ $n -gt 0 ]] && printf '  %-34s → %-30s %s souborů\n' "$1" "$2" "$n" || true
}

echo "▸ 1/4  Schovávám firemní identitu"
sub 'Praut s\.r\.o\.'        '@@FIRMA@@'
sub 'praut\.cz'              '@@DOMENA@@'
sub 'Praut-Startup-Support'  '@@ORG@@'
sub 'prautsvanda'            '@@TSUSER@@'

echo
echo "▸ 2/4  Přejmenovávám produkt"
# Od nejkonkrétnějšího k nejobecnějšímu, jinak by obecný vzor sežral
# části konkrétních.
sub 'Praut Platform'         'AgenticDev'
sub 'PRAUT_'                       'AGENTICDEV_'
sub '/srv/praut'             '/srv/agenticdev'
sub 'praut-install-vps'      'agenticdev-install-vps'
sub 'praut-install-mac'      'agenticdev-install-mac'
sub 'praut-mac-installer'    'agenticdev-mac-installer'
sub 'praut-app'              'agenticdev-app'
sub 'praut-backup'           'agenticdev-backup'
sub 'praut-ctl'              'agenticdev-ctl'
sub 'praut-git'              'agenticdev-git'
sub 'praut-decision'         'agenticdev-decision'
sub 'praut-launch'           'agenticdev-launch'
sub 'praut-info'             'agenticdev-info'
sub 'praut-trees'            'agenticdev-trees'
sub 'Praut\.app'             'AgenticDev.app'
sub 'praut/control-plane'    'agenticdev/control-plane'
sub 'praut/pod'              'agenticdev/pod'
sub 'praut/egress'           'agenticdev/egress'
sub 'praut\.ico'             'agenticdev.ico'
sub '\.praut'                '.agenticdev'
sub 'praut work'             'agenticdev work'
sub 'praut doctor'           'agenticdev doctor'
sub 'praut init'             'agenticdev init'
sub 'praut login'            'agenticdev login'
sub 'praut board'            'agenticdev board'
sub 'Praut/'                 'AgenticDev/'
sub 'name: praut'            'name: agenticdev'
sub 'praut'                  'agenticdev'
sub 'Praut'                  'AgenticDev'
sub 'PRAUT'                  'AGENTICDEV'

echo
echo "▸ 3/4  Vracím firemní identitu"
sub '@@FIRMA@@'    'Praut s.r.o.'
sub '@@DOMENA@@'   'praut.cz'
sub '@@ORG@@'      'Praut-Startup-Support'
sub '@@TSUSER@@'   'prautsvanda'

echo
echo "▸ 4/4  Přejmenovávám soubory"
mv launcher/praut                              launcher/agenticdev
mv linux/praut-launch                          linux/agenticdev-launch
mv linux/praut.desktop                         linux/agenticdev.desktop
mv vps/praut-ctl                               vps/agenticdev-ctl
mv workspace/_base/bin/praut-git               workspace/_base/bin/agenticdev-git
mv workspace/_base/bin/praut-decision          workspace/_base/bin/agenticdev-decision
mv workspace/_base/.pi/extensions/praut-git.ts workspace/_base/.pi/extensions/agenticdev-git.ts
mv brand/praut.ico                             brand/agenticdev.ico
mv site/praut.ico                              site/agenticdev.ico
mv mac/Praut.app/Contents/MacOS/Praut          mac/Praut.app/Contents/MacOS/AgenticDev
mv mac/Praut.app                               mac/AgenticDev.app
echo "  ✓ 11 souborů"
