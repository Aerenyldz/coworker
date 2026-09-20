@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   TENRA 2.0 - Masaustu AI Asistani
echo ===================================================
echo.

REM Ollama kontrolu
tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
if errorlevel 1 (
    echo [*] Ollama servisi arka planda baslatiliyor...
    start "" /b ollama serve
    timeout /t 2 /nobreak >nul
)

REM Sanal ortam kontrolu
if not exist ".venv\Scripts\python.exe" (
    echo [*] Sanal ortam olusturuluyor...
    python -m venv .venv
    if errorlevel 1 (
        echo [X] Python bulunamadi! Lutfen Python kurun.
        pause
        exit /b 1
    )
)

REM Bagimlilik kontrolu
echo [*] Bagimliliklar kontrol ediliyor...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt

REM Tenra 2.0 Baslat
echo.
echo [+] Tenra 2.0 baslatiliyor...
echo.

".venv\Scripts\python.exe" -m tenra

if errorlevel 1 (
    echo.
    echo [X] Tenra calisirken bir hata olustu.
    pause
)
