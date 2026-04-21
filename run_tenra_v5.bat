@echo off
chcp 65001 >nul
REM Tenra V5 — Başlatma dosyası

cd /d "%~dp0"

echo.
echo ════════════════════════════════════════════════
echo   TENRA V5 — Masaüstü Asistan Başlatılıyor
echo ════════════════════════════════════════════════
echo.

REM Sanal ortamı etkinleştir
if not exist .venv (
    echo [!] Sanal ortam bulunamadı. Oluşturuluyor...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

REM Bağımlılıkları kur (ilk kez ve güncellemeler)
echo [*] Bağımlılıklar kontrol ediliyor...
pip install --upgrade pip setuptools wheel >nul 2>&1
pip install -q -r tenra_v5\requirements.txt
if errorlevel 1 (
    echo.
    echo [X] Bağımlılık kurulum hatası! Lütfen internet bağlantınızı kontrol edin.
    echo.
    pause
    exit /b 1
)

REM Kurulum kontrol et
echo [*] Sistem kontrol ediliyor...
python check_setup.py
if errorlevel 1 (
    pause
    exit /b 1
)

echo.
echo [+] Tenra V5 başlatılıyor...
echo.

python tenra_v5\main.py

pause

