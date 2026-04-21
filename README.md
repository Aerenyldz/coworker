# Tenra V5 — Masaüstü AI Asistanı

Ekranın köşesinde yüzen, her zaman erişilebilen kişisel AI asistanı.

## Özellikler
- 🎯 **Yüzen Widget** — Ekranda sabit duran, sürüklenebilir logo
- 💬 **Doğal Dil** — Türkçe sohbet ve anlama
- ⚡ **Sistem Kontrolü** — Dosya yönetimi, komut çalıştırma, uygulama açma
- 🧠 **Akıllı Router** — Kullanıcı isteklerini otomatik işlevlere yönlendirme
- 🔗 **Ollama Entegrasyonu** — Yerel LLM modelleri ile çalışma

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
- Tenra V5'i çalıştırır

### Manuel Başlatma
```bash
.venv\Scripts\activate
python tenra_v5\main.py
```

---

## Kontrol Aracı

Kurulum sorunları için:
```bash
python check_setup.py
```

Bağımlılıkları, Ollama bağlantısını ve model dosyalarını kontrol eder.

---

## Kullanım

1. **Widget'i Tıkla** — Ekranda yüzen "T" logosu
2. **Sohbeti Aç** — Sohbet penceresi belirecek
3. **Mesaj Gönder** — Türkçe olarak komut yaz
4. **ESC Tuşu** — Sohbeti kapat

### Örnek Komutlar
- "Dosyaları listele"
- "Google'da ara: Python öğretimi"
- "Not defterini aç"
- "Sistem bilgisini göster"

---

## Ayarlar (`config.py`)

```python
RESPONDER_MODEL = "hermes3:8b"  # Kullanılacak Ollama modeli
OLLAMA_URL = "http://localhost:11434/api"  # Ollama sunucu adresi
USE_LOCAL_ROUTER = False  # Local FunctionGemma router (opsiyonel)
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
│   ├── llm.py                # LLM arayüzü
│   ├── router.py             # İstek yönlendirme
│   ├── function_executor.py  # İşlev çalıştırıcı
│   └── ...
├── merged_model/             # Yerel router modeli
└── data/                      # Veritabanları
```

---

## Geliştirme

Yeni işlevler eklemek için `tenra_v5/core/function_executor.py` dosyasını düzenleyin.

---

## Lisans

Tenra V5 — Özel Kullanım Yazılımı

