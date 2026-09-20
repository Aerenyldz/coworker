# Tenra 2.0 — Otonom Masaüstü & Proje Geliştirici AI Asistanı

Antigravity mantığıyla yeniden inşa edilmiş, bilgisayarda ve projelerde otonom eylem gerçekleştiren yerel yapay zeka asistanı.

---

## 🌟 Öne Çıkan Özellikler

- 📁 **Proje & Çalışma Alanı (Workspace) Yönetimi:**
  - Sol kenar çubuğundan masaüstü veya herhangi bir dizindeki projeyi seçebilme.
  - Projeye özel ve bağımsız sohbet oturumları.
  - PowerShell ve dosya işlemlerinin doğrudan seçili proje dizinine kilitlenmesi.
- 🎙️ **Sesle Dikte (Speech-to-Text):**
  - Girdi çubuğunda mikrofon butonu (`🎙️`) ve `Ctrl + M` / `F4` kısayolları.
  - Hızlı ve yüksek doğrulukta Türkçe konuşma tanıma (`tr-TR`).
  - Windows 11 `Win + H` sesle yazma entegrasyonu.
- 🪟 **Gelişmiş Pencere Deneyimi:**
  - Normal masaüstü pencere davranışı (diğer uygulamalara tıklandığında arkaya geçebilir, `Alt + Tab` desteği).
  - İsteğe bağlı tek tıkla pencere sabitleme (`📌 Pin`).
- ⚡ **4 Çekirdek Otonom Araç:**
  - `shell`: PowerShell komut yürütme (seçili proje dizininde).
  - `file`: Dosya okuma, yazma, düzenleme (patch), silme, listeleme ve arama.
  - `web`: DuckDuckGo araması, sayfa okuma, URL açma.
  - `screen`: Tıklama, yazma, kısayol tuşları ve ekran alıntısı (snipping).
- 🧠 **Qwen3 Agent Motoru:**
  - Gerçek çok adımlı tool-calling döngüsü.
  - Yazım hatalarına (typo), eksik harflere ve Türkçe karakter kaymalarına tam tolerans.
  - Akıllı ve bulanık dosya çözümleme (`difflib` + fonetik eşleştirme).
- 👁️ **Görsel Zeka (Vision & OCR):**
  - Ekran alıntısı (snipping) ve dosya yükleme (`📷`, `📎`).
  - Moondream Vision modeli ve Tesseract OCR ile zenginleştirilmiş analiz.

---

## 🚀 Hızlı Başlangıç

### 1. Gereksinimler
- Windows 10/11
- Python 3.11+
- [Ollama](https://ollama.ai)

### 2. Ollama Modellerini İndirin
```bash
ollama pull qwen3:8b
ollama pull moondream:latest
```

### 3. Başlatma
Proje dizinindeki `tenra.bat` dosyasını çift tıklayın:
```bash
tenra.bat
```

Script otomatik olarak:
1. Arka planda Ollama servisini kontrol eder ve gerekiyorsa başlatır.
2. Python sanal ortamını (`.venv`) yapılandırır.
3. Bağımlılıkları kurar ve Tenra 2.0 Agent Studio'yu ekrana getirir.

---

## 🏗️ Proje Mimarisi

```
coworker/
├── tenra.bat              # Tek tıkla Windows başlatıcı
├── requirements.txt       # Üretim bağımlılıkları
├── README.md
├── tenra/                 # Tenra 2.0 ana paketi
│   ├── config.py          # Sistem istemi, model ve ortam ayarları
│   ├── core/
│   │   ├── agent.py       # Qwen3 otonom karar ve araç döngüsü
│   │   ├── executor.py    # 4 çekirdek araç (shell, file, web, screen)
│   │   ├── llm_backend.py # Ollama REST API istemcisi
│   │   └── workspace_manager.py # Proje ve sohbet yöneticisi
│   ├── ui/
│   │   ├── app.py         # Uygulama yaşam döngüsü
│   │   ├── chat_window.py # Agent Studio yatay ana penceresi
│   │   ├── sidebar_widget.py # Sol panel (Projeler & Sohbetler)
│   │   ├── floating_widget.py # Yüzen masaüstü widget'ı
│   │   ├── snipping.py    # Ekran alıntısı aracı
│   │   ├── colors.py      # Stüdyo tema renkleri
│   │   └── markdown.py    # Markdown & kart renderlayıcı
│   ├── voice/
│   │   └── stt.py         # Ses tanıma (Speech-to-Text) iş parçacığı
│   └── plugins/           # Eklenti yuvaları (Hermes3 vb.)
```

---

## ⌨️ Kısayollar

- `Enter`: Mesajı gönder
- `Ctrl + M` veya `F4`: Sesle dikteyi başlat / durdur (🎙️)
- `Esc`: Pencereyi gizle
- `📌`: Pencereyi en üste sabitle / normal moda al

---

## Lisans
Tenra 2.0 — Özel Kullanım Yazılımı
