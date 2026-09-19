# Tenra V6 — Masaüstü AI Asistanı

Ekranın köşesinde yüzen, her zaman erişilebilen kişisel AI asistanı.

## Özellikler
- 🎯 **Yüzen Widget** — Ekranda sabit duran, sürüklenebilir logo
- 💬 **Doğal Dil** — Türkçe sohbet ve anlama
- ⚡ **Sistem Kontrolü** — Dosya yönetimi, komut çalıştırma, uygulama açma
- 🧠 **Otonom Agent** — Hermes tabanlı çok adımlı tool-calling sistemi
- 📝 **Dosya Düzenleme** — Patch (find-and-replace) ile hedefli kod düzenleme
- 🔓 **Entegre Hermes Protokolü** — Natively aktif, filtresiz, sınırsız AI ve onay pencereleri olmadan doğrudan çalışma
- 🔗 **Ollama Entegrasyonu** — Yerel LLM modelleri ile çalışma

---

## V6 Yenilikler
- ✅ **Robot mod kaldırıldı** — Akıllı sistem ile değiştirildi
- ✅ **Entegre Hermes Protokolü** — Sohbet botu doğrudan Hermes altyapısı ile çalışır, onay pencereleri kaldırılmıştır
- ✅ **Dosya düzenleme yetkisi** — `patch` aracı ile hedefli düzenleme
- ✅ **Gelişmiş sistem promptu** — Daha otonom ve akıllı AI davranışı
- ✅ **Yükseltilmiş hız ve konfor** — Riskli işlemlerde doğrudan yetki (onay istemeden)

---

## Kurulum

### 1. Gereksinimler
- Python 3.11+
- [Ollama](https://ollama.ai) kurulu ve `ollama serve` komutunun çalışır halde olması

### 2. Sanal Ortam (ilk kez)
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r tenra_v5\requirements.txt
```

### 3. Ollama Modeli
Ollama'yı başlatıp gerekli modeli yükleyin:
```bash
ollama serve
# Başka bir terminal'de:
ollama pull hermes3:8b
```

---

## Çalıştırma

### Kolay Başlatma (Önerilir)
```bash
run_tenra_v5.bat
```

Bu dosya otomatik olarak:
- Sanal ortamı oluşturur/etkinleştirir
- Bağımlılıkları kurar
- Sistemi kontrol eder
- Tenra V6'yı çalıştırır

### Manuel Başlatma
```bash
.venv\Scripts\activate
python tenra_v5\main.py
```

---

## Kullanım

1. **Widget'i Tıkla** — Ekranda yüzen "T" logosu
2. **Sohbeti Aç** — Sohbet penceresi belirecek
3. **Mesaj Gönder** — Türkçe olarak komut yaz
4. **ESC Tuşu** — Sohbeti kapat

### Entegre Hermes Protokolü (Sansürsüz ve Engelsiz)
- Asistan varsayılan olarak **Hermes Protokolü** ile çalışır.
- Herhangi bir trigger kelime yazmanıza gerek yoktur, doğrudan otonomdur.
- Etik/güvenlik filtreleri veya onay pencereleri olmadan dosya silme, oluşturma ve sistem komutları doğrudan yerine getirilir.

### Örnek Komutlar
- "Dosyaları listele"
- "Google'da ara: Python öğretimi"
- "Not defterini aç"
- "Sistem bilgisini göster"
- "test.txt dosyasında 'hello' yerine 'merhaba' yaz"
- "masaüstünde 'notlar' klasörü oluştur"

---

## Ayarlar (`config.py`)

```python
RESPONDER_MODEL = "hermes3:8b"  # Kullanılacak Ollama modeli
OLLAMA_URL = "http://localhost:11434/api"  # Ollama sunucu adresi
MAX_TOOL_STEPS = 5  # Normal modda araç çağrı limiti
MAX_TOOL_STEPS_UNCENSORED = 8  # Sansürsüz modda araç çağrı limiti
```

---

## Sorun Giderme

### "Ollama sunucusu çalışmıyor"
```bash
# Yeni terminal'de:
ollama serve
```

### "Modeller yüklenmedi"
```bash
ollama pull hermes3:8b
```

### "PySide6 hatası"
```bash
pip install --upgrade PySide6
```

### "Genel sorun"
Kontrol aracını çalıştırın:
```bash
python check_setup.py
```

---

## Mimari

```
tenra_v5/
├── main.py                    # GUI ve Ana uygulama
├── config.py                  # Merkezi ayarlar
├── core/
│   ├── hermes_agent.py       # Hermes tool-calling agent
│   ├── function_executor.py  # İşlev çalıştırıcı (27 araç)
│   ├── llm.py                # LLM arayüzü
│   ├── router.py             # İstek yönlendirme
│   ├── settings_store.py     # Ayarlar yöneticisi
│   └── ...
└── data/                      # Veritabanları
```

---

## Lisans

Tenra V6 — Özel Kullanım Yazılımı

