# Tenra 2.0 — Windows paketleme
# 1) PyInstaller ile klasör üret
# 2) (Opsiyonel) Inno Setup ile kurulum .exe oluştur

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$Root\run_tenra.py")) { $Root = (Get-Location).Path }

Set-Location $Root
Write-Host "[Tenra] Paketleme başlıyor: $Root"

$pyi = Join-Path $Root ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $pyi)) {
    & "$Root\.venv\Scripts\pip.exe" install pyinstaller
}

& $pyi --noconfirm "$Root\tenra.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller başarısız" }

Write-Host "[Tenra] dist\Tenra\Tenra.exe hazır."

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($iscc) {
    Write-Host "[Tenra] Inno Setup bulundu, kurulum paketi üretiliyor..."
    New-Item -ItemType Directory -Force -Path "$Root\dist_installer" | Out-Null
    & $iscc "$Root\installer\tenra_setup.iss"
    Write-Host "[Tenra] Kurulum: dist_installer\TenraSetup-2.0.0.exe"
} else {
    Write-Host "[Tenra] Inno Setup yok — sadece dist\Tenra klasörü üretildi."
    Write-Host "         Kurulum .exe için Inno Setup 6 kurun, sonra bu scripti tekrar çalıştırın."
}
