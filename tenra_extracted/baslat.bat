@echo off
echo ── Tenra Kurulum ──────────────────────────────────
echo.

:: Python var mı kontrol et
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadı. python.org'dan yükle.
    pause
    exit
)

:: Paketleri kur
echo [1/3] Paketler kuruluyor...
pip install pystray Pillow requests --quiet

:: Ollama çalışıyor mu?
echo [2/3] Ollama kontrol ediliyor...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [UYARI] Ollama çalışmıyor. Başlatılıyor...
    start "" ollama serve
    timeout /t 3 >nul
) else (
    echo [OK] Ollama çalışıyor.
)

:: Model var mı?
echo [3/3] Model kontrol ediliyor...
ollama list | find "qwen2.5:7b" >nul 2>&1
if errorlevel 1 (
    echo [İNDİRİLİYOR] qwen2.5:7b indiriliyor (4GB, bekle...)
    ollama pull qwen2.5:7b
)

echo.
echo ── Tenra başlatılıyor ────────────────────────────
echo Sistem tepsisine (sağ alt köşe saati yanı) bak!
echo.
python tenra.py
