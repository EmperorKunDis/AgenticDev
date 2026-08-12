# ═══════════════════════════════════════════════════════════════
#  AGENTICDEV — připojení Windows
#
#      powershell -ExecutionPolicy Bypass -File agenticdev-install.ps1
#
#  Pody běží na VPS (ADR-0005), takže tady se nic těžkého neinstaluje:
#  Tailscale, jeden konfigurační soubor a zástupce na plochu.
#  WSL2 už není potřeba — Docker ani agent na tomhle stroji neběží.
#
#  Idempotentní. Můžeš pustit znovu.
# ═══════════════════════════════════════════════════════════════
#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ControlPlane = "__CONTROL_PLANE__",
    [string]$Login = ""
)

$ErrorActionPreference = "Stop"

function Step($m) { Write-Host "`n> $m" -ForegroundColor Cyan }
function OK($m)   { Write-Host "  * $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "`nx $m" -ForegroundColor Red; exit 1 }

Clear-Host
@"
  ┌────────────────────────────────┐
  │   P R A U T                    │
  │   připojení Windows            │
  └────────────────────────────────┘
"@ | Write-Host

# ═══ 1. Tailscale ══════════════════════════════════════════════
# Jediná síť, po které je VPS vidět.
Step "Tailscale"
$ts = Get-Command tailscale.exe -ErrorAction SilentlyContinue
if (-not $ts) {
    $known = "$env:ProgramFiles\Tailscale\tailscale.exe"
    if (Test-Path $known) { $ts = @{ Source = $known } }
}
if (-not $ts) {
    Warn "instaluji Tailscale"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id tailscale.tailscale --accept-source-agreements --accept-package-agreements
    } else {
        Die "Nemám winget. Nainstaluj Tailscale z https://tailscale.com/download/windows a pusť to znovu."
    }
    $known = "$env:ProgramFiles\Tailscale\tailscale.exe"
    if (Test-Path $known) { $ts = @{ Source = $known } } else { Die "Tailscale se nenainstaloval." }
}
$tsExe = $ts.Source
OK "tailscale"

& $tsExe status *>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  Přihlas se do stejné sítě jako VPS. Klíč máš z registrační stránky:" -ForegroundColor Yellow
    Write-Host "     tailscale up --authkey tskey-..."
    Write-Host ""
    Read-Host "  Až budeš připojený, zmáčkni Enter"
}

# ═══ 2. Kam se připojovat ══════════════════════════════════════
Step "Kde je VPS"
$vps = $ControlPlane -replace '^https?://', '' -replace '[:/].*$', ''
if (-not $vps -or $vps -eq "__CONTROL_PLANE__") {
    Die "Instalátor neví, kde je VPS. Vyžádej si nový z registrační stránky."
}
OK $vps

# Login na VPS zakládá správce příkazem `agenticdev-ctl user add`, takže
# ho tenhle stroj nemá odkud zjistit — musí ho říct člověk.
if (-not $Login) {
    Write-Host ""
    Write-Host "  Tvoje přihlašovací jméno na VPS (dal ti ho správce):"
    $Login = Read-Host "  login"
}
if (-not $Login) { Die "Bez loginu se nepřihlásím." }

$cfgDir = Join-Path $env:USERPROFILE ".agenticdev"
New-Item -ItemType Directory -Force -Path $cfgDir *>$null
@"
AGENTICDEV_VPS=$vps
AGENTICDEV_LOGIN=$Login
"@ | Set-Content -Path (Join-Path $cfgDir "vps") -Encoding UTF8
OK "uloženo do $cfgDir\vps"

# ═══ 3. Zástupce na plochu ═════════════════════════════════════
Step "Zástupce"
$dir = Join-Path $env:LOCALAPPDATA "AgenticDev"
New-Item -ItemType Directory -Force -Path $dir *>$null

# Ikonu si stáhneme z VPS; když to nejde, zástupce bude se systémovou.
$ico = Join-Path $dir "agenticdev.ico"
try {
    Invoke-WebRequest -Uri "$ControlPlane/brand/agenticdev.ico" -OutFile $ico -TimeoutSec 15
} catch { Warn "ikonu se nepodařilo stáhnout" }

$cmdFile = Join-Path $dir "agenticdev.cmd"
@"
@echo off
title AgenticDev
"$tsExe" ssh $Login@$vps agenticdev work
if errorlevel 1 pause
"@ | Set-Content -Path $cmdFile -Encoding ASCII

$desktop = [Environment]::GetFolderPath("Desktop")
$lnk = Join-Path $desktop "AgenticDev.lnk"
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath = $cmdFile
$sc.WorkingDirectory = $dir
$sc.Description = "Otevře agenta a výběr projektu"
if (Test-Path $ico) { $sc.IconLocation = $ico }
$sc.Save()
OK "AgenticDev na ploše"

# ═══ 4. Zkouška ════════════════════════════════════════════════
Step "Zkouška"
try {
    Invoke-WebRequest -Uri "$ControlPlane/v1/health" -TimeoutSec 8 -UseBasicParsing *>$null
    OK "VPS odpovídá"
} catch {
    Warn "VPS neodpovídá — zkontroluj: tailscale status"
}

Write-Host ""
Write-Host "  Hotovo." -ForegroundColor Green
Write-Host ""
Write-Host "  Klikni na ikonu AgenticDev, nebo z příkazové řádky:"
Write-Host "      tailscale ssh $Login@$vps" -ForegroundColor Yellow
Write-Host "      agenticdev" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Poprvé se v Pi přihlas k modelu přes /login. Pak už to platí." -ForegroundColor DarkGray
Write-Host ""
