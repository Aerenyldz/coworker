#!/usr/bin/env python
"""
Tenra V5 — Kurulum Kontrol Aracı
Tüm bağımlılıkların ve sistemin hazır olup olmadığını kontrol eder.
"""

import sys
import os

print("=" * 60)
print("TENRA V5 — KURULUM KONTROL")
print("=" * 60)
print()

# 1. Python sürümü
print(f"✓ Python: {sys.version}")
print()

# 2. Temel paketler
print("Paket kontrolleri:")
packages = [
    ("PySide6", "PySide6"),
    ("requests", "requests"),
    ("torch", "torch"),
    ("transformers", "transformers"),
    ("keyboard", "keyboard"),
    ("pyautogui", "pyautogui"),
]

all_ok = True
for pkg_name, import_name in packages:
    try:
        __import__(import_name)
        print(f"  ✓ {pkg_name}")
    except ImportError as e:
        print(f"  ✗ {pkg_name} — {e}")
        all_ok = False

print()

# 3. Ollama bağlantısı
print("Sistem kontrolleri:")
try:
    import requests
    response = requests.get("http://localhost:11434/api/tags", timeout=3)
    if response.status_code == 200:
        data = response.json()
        models = [m["name"] for m in data.get("models", [])]
        print(f"  ✓ Ollama çalışıyor")
        print(f"    Yüklü modeller: {', '.join(models) if models else 'Hiç model yok!'}")
    else:
        print(f"  ✗ Ollama yanıt vermiyor ({response.status_code})")
        all_ok = False
except requests.exceptions.ConnectionError:
    print(f"  ✗ Ollama bağlantısı kurulamadı")
    print(f"    Çözüm: 'ollama serve' komutunu terminalde çalıştırın")
    all_ok = False
except Exception as e:
    print(f"  ✗ Ollama kontrol hatası: {e}")
    all_ok = False

print()

# 4. Model dosyaları
print("Model dosyaları:")
model_path = os.path.join(os.path.dirname(__file__), "tenra_v5", "merged_model")
if os.path.exists(model_path):
    files = os.listdir(model_path)
    print(f"  ✓ {model_path} var")
    print(f"    Dosyalar: {', '.join(files[:3])}{'...' if len(files) > 3 else ''}")
else:
    print(f"  ✗ {model_path} bulunamadı")
    all_ok = False

print()

# 5. Sonuç
print("=" * 60)
if all_ok:
    print("✓ HER ŞEY HAZIR — run_tenra_v5.bat çalıştırabilirsiniz!")
else:
    print("✗ BAZI SORUNLAR VAR — Yukarıdaki uyarıları kontrol edin")
print("=" * 60)

