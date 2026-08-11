# ═══════════════════════════════════════════════════════════════
#  PRAUT — připojení Windows
#
#      powershell -ExecutionPolicy Bypass -File praut-install.ps1 -Token <HESLO>
#
#  Praut potřebuje Docker a linuxový shell, takže na Windows běží ve
#  WSL2. Tenhle skript připraví Windows část (WSL, Tailscale, ikona)
#  a zbytek předá linuxovému instalátoru uvnitř WSL.
#
#  Idempotentní. Můžeš pustit znovu.
# ═══════════════════════════════════════════════════════════════
#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$ControlPlane = "__CONTROL_PLANE__",
    [string]$Distro = "Ubuntu"
)

$ErrorActionPreference = "Stop"

function Step($m) { Write-Host "`n> $m" -ForegroundColor Cyan }
function OK($m)   { Write-Host "  ✓ $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "`n✗ $m" -ForegroundColor Red; exit 1 }

Clear-Host
@"
  ┌────────────────────────────────┐
  │   P R A U T                    │
  │   připojení Windows            │
  └────────────────────────────────┘
"@ | Write-Host

# ═══ 0. Předpoklady ════════════════════════════════════════════
$admin = ([Security.Principal.WindowsPrincipal] `
          [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Die "Spusť PowerShell jako správce. WSL a Tailscale se jinak nenainstalují."
}

$build = [int](Get-CimInstance Win32_OperatingSystem).BuildNumber
if ($build -lt 19041) {
    Die "Potřebuju Windows 10 verze 2004 (build 19041) nebo novější. Máš build $build."
}

# ═══ 1. WSL2 ═══════════════════════════════════════════════════
Step "WSL2"
$wslOk = $false
try { wsl.exe --status *>$null; $wslOk = ($LASTEXITCODE -eq 0) } catch { $wslOk = $false }

if (-not $wslOk) {
    Warn "instaluji WSL — po dokončení bude potřeba restart"
    wsl.exe --install --no-launch
    if ($LASTEXITCODE -ne 0) { Die "WSL se nenainstalovalo." }
    Write-Host ""
    Write-Host "  Restartuj Windows a pusť tenhle skript znovu." -ForegroundColor Yellow
    exit 0
}
wsl.exe --set-default-version 2 *>$null
OK "wsl"

# ═══ 2. Distribuce ═════════════════════════════════════════════
Step "Linux uvnitř Windows"
# wsl --list vrací UTF-16 s nulovými bajty, jinak by porovnání selhalo
$installed = (wsl.exe --list --quiet) -replace "`0", "" -split "`r?`n" |
             Where-Object { $_.Trim() -ne "" } | ForEach-Object { $_.Trim() }

if ($installed -notcontains $Distro) {
    Warn "instaluji $Distro (chvíli to trvá)"
    wsl.exe --install -d $Distro --no-launch
    if ($LASTEXITCODE -ne 0) { Die "$Distro se nenainstalovala." }
    Write-Host ""
    Write-Host "  Otevři '$Distro' z nabídky Start, vytvoř si uživatele," -ForegroundColor Yellow
    Write-Host "  zavři okno a pusť tenhle skript znovu." -ForegroundColor Yellow
    exit 0
}

# Bez uživatele se do distribuce nedá nic nainstalovat
$whoami = (wsl.exe -d $Distro -- whoami 2>$null) -replace "`0", ""
if (-not $whoami -or $whoami.Trim() -eq "root") {
    Warn "v $Distro ještě není běžný uživatel"
    Write-Host "  Otevři '$Distro' z nabídky Start, vytvoř si uživatele a pusť mě znovu."
    exit 0
}
OK "$Distro (uživatel $($whoami.Trim()))"

# ═══ 3. Tailscale ══════════════════════════════════════════════
# Na Windows se instaluje nativně — WSL sdílí síť s hostitelem.
Step "Síť"
$ts = Get-Command tailscale.exe -ErrorAction SilentlyContinue
if (-not $ts -and -not (Test-Path "$env:ProgramFiles\Tailscale\tailscale.exe")) {
    Warn "instaluji Tailscale"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id tailscale.tailscale --silent --accept-package-agreements `
                       --accept-source-agreements *>$null
    } else {
        Warn "winget není k dispozici — nainstaluj Tailscale ručně:"
        Write-Host "     https://tailscale.com/download/windows"
        Read-Host "  Až budeš hotový, zmáčkni Enter"
    }
}
$tsExe = (Get-Command tailscale.exe -ErrorAction SilentlyContinue).Source
if (-not $tsExe) { $tsExe = "$env:ProgramFiles\Tailscale\tailscale.exe" }

$connected = $false
if (Test-Path $tsExe) {
    & $tsExe status *>$null
    $connected = ($LASTEXITCODE -eq 0)
}
if (-not $connected) {
    Write-Host ""
    Write-Host "  Přihlas se do Tailscale klíčem z registrační stránky:" -ForegroundColor Yellow
    Write-Host "     tailscale up --authkey ..."
    Read-Host "  Až budeš připojený, zmáčkni Enter"
}
OK "tailscale"

# ═══ 4. Instalace uvnitř WSL ═══════════════════════════════════
Step "Praut"
$inner = @"
set -e
curl -fsS -X POST '$ControlPlane/join/installer' \
  -H 'content-type: application/json' \
  -d '{"password":"$Token"}' -o /tmp/praut-install.sh
bash /tmp/praut-install.sh '$Token'
rm -f /tmp/praut-install.sh
"@ -replace "`r", ""

$tmp = [IO.Path]::GetTempFileName()
[IO.File]::WriteAllText($tmp, $inner, [Text.UTF8Encoding]::new($false))
$wslPath = (wsl.exe -d $Distro -- wslpath -a "'$($tmp -replace '\\','\\')'") -replace "`0", ""

wsl.exe -d $Distro -- bash $wslPath.Trim()
$rc = $LASTEXITCODE
Remove-Item $tmp -Force -ErrorAction SilentlyContinue
if ($rc -ne 0) { Die "Instalace uvnitř WSL selhala." }
OK "nainstalováno"

# ═══ 5. Ikona na plochu ════════════════════════════════════════
Step "Ikona"
$dir = Join-Path $env:LOCALAPPDATA "Praut"
New-Item -ItemType Directory -Force -Path $dir *>$null

$ico = Join-Path $dir "praut.ico"
try {
    Invoke-WebRequest -Uri "$ControlPlane/brand/praut.ico" -OutFile $ico -UseBasicParsing
} catch {
    Warn "ikonu se nepodařilo stáhnout, zástupce bude s výchozí"
}

$shell = New-Object -ComObject WScript.Shell
foreach ($base in @([Environment]::GetFolderPath("Desktop"),
                    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))) {
    if (-not (Test-Path $base)) { continue }
    $lnk = $shell.CreateShortcut((Join-Path $base "Praut.lnk"))
    $lnk.TargetPath       = "$env:SystemRoot\System32\wsl.exe"
    $lnk.Arguments        = "-d $Distro -- bash -lic 'praut work'"
    $lnk.Description      = "Otevře agenta a výběr projektu"
    $lnk.WorkingDirectory = $env:USERPROFILE
    if (Test-Path $ico) { $lnk.IconLocation = $ico }
    $lnk.Save()
}
OK "Praut na ploše i v nabídce Start"

Write-Host ""
Write-Host "  Hotovo." -ForegroundColor Green
Write-Host ""
Write-Host "  Klikni na ikonu Praut na ploše, nebo spusť ve WSL:"
Write-Host "      praut work"
Write-Host ""
