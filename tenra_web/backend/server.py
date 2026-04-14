"""
Tenra V4 — Open Interpreter Pattern
LLM artık "tool calling" API'sine güvenmek yerine Python kodu üretir,
backend bu kodu doğrudan exec() ile çalıştırır.
"""
import json
import re
import io
import sys
import os
from pathlib import Path
import requests
import traceback
import keyboard
from contextlib import redirect_stdout, redirect_stderr
from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse

# Acil Stop Kapatma (ESC tuşuna basıldığında sistemi olduğu gibi öldürür)
try:
    keyboard.add_hotkey('esc', lambda: os._exit(0))
except Exception:
    # Bazı ortamlarda global hotkey erişimi olmayabilir.
    pass

# Overlay (kırmızı çerçeve)
try:
    from overlay import show_red_border, hide_red_border
except:
    def show_red_border(): pass
    def hide_red_border(): pass

app = FastAPI(title="Tenra V4")

DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
allowed_origins_env = os.getenv("TENRA_ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in allowed_origins_env.split(",") if o.strip()] or DEFAULT_ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = (Path(__file__).resolve().parent.parent / "frontend")

def _frontend_file(filename: str) -> Path:
    candidate = (FRONTEND_DIR / filename).resolve()
    if candidate.parent != FRONTEND_DIR.resolve() or not candidate.exists():
        raise HTTPException(status_code=404, detail="Frontend dosyası bulunamadı")
    return candidate

# Frontend servis
@app.get("/")
def read_root():
    return FileResponse(_frontend_file("index.html"))

@app.get("/styles.css")
def get_css():
    return FileResponse(_frontend_file("styles.css"))

@app.get("/app.js")
def get_js():
    return FileResponse(_frontend_file("app.js"))

# ─── MODEL AYARLARI ───
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "tenra:latest"

SYSTEM_PROMPT = r"""Sen Tenra'sın — kullanıcının bilgisayarında çalışan güçlü bir AI asistanısın.
Kullanıcının Windows bilgisayarında SINIRSIZ yetkiye sahipsin.

## ÇOK ÖNEMLİ KURALLAR:

### KOD YAZARAK ÇALIŞ:
Bir görev verildiğinde, planını KISA anlat, ardından ```python bloğu içinde çalıştırılabilir Python kodu yaz.
Bu kod backend tarafından otomatik çalıştırılacak ve çıktısı sana geri gelecek.

### KULLANILABILIR KÜTÜPHANELER:
- os, subprocess, glob, shutil, pathlib — dosya/sistem işlemleri
- pyautogui — mouse hareket ettirme, tıklama, yazı yazma
- keyboard — tuşlara basma
- requests — HTTP istekleri
- Tüm standart Python kütüphaneleri

### MOUSE VE KLAVYE KONTROLÜ:
```python
import pyautogui
pyautogui.FAILSAFE = True

# Fareyi hareket ettir
pyautogui.moveTo(500, 300, duration=0.5)

# Tıkla
pyautogui.click()

# Sağ tıkla
pyautogui.click(button='right')

# Yazı yaz
pyautogui.write('merhaba', interval=0.05)

# Tuş kombinasyonu
pyautogui.hotkey('ctrl', 'a')

# Ekran görüntüsü al
screenshot = pyautogui.screenshot()
screenshot.save('ekran.png')
```

### BİR UYGULAMAYI VEYA BİLGİSAYAR İÇİ BİR ŞEYİ AÇMA (ÇOK ÖNEMLİ):
Uygulamaları (örn. hesap makinesi, duckduckgo, spotify) açmak için asla "shell:appsfolder" gibi garip şeyler yazma veya mouse/koordinat sallama! Bunun yerine İNSAN GİBİ başlat menüsünü kullan:
```python
import pyautogui, time
pyautogui.press('win')
time.sleep(0.5)
pyautogui.write('duckduckgo', interval=0.05) # Açılacak uygulamanın adı
time.sleep(0.5)
pyautogui.press('enter')
```

### WEB SİTESİ AÇMA:
Eğer bir web adresine (örn. google, youtube) gidilecekse mouse DEĞİL, DAİMA `webbrowser` kullan:
```python
import webbrowser
webbrowser.open("https://google.com")
```

### BİLGİSAYARDAKİ DOSYALARI (MASAÜSTÜ) YÖNETME (ÇÖP KUTUSU / AÇMA):
Masaüstü klasörünün yolu: `r"C:\Users\ahmet\OneDrive\Desktop"`
1. "Masaüstündeki bir dosyayı aç / başlat" denirse WİNDOWS ARAMA KULLANMA! Farenizi kullanma! Direkt:
```python
import os
# Sadece tam dosya yolunu vererek başlat (EXE, PDF, TXT vb.)
os.startfile(r"C:\Users\ahmet\OneDrive\Desktop\dosyadi.txt")
```
2. "Şunu çöpe at / geri dönüşüme taşı / sil" denirse DAİMA `send2trash` kütüphanesini kullan:
```python
from send2trash import send2trash
send2trash(r"C:\Users\ahmet\OneDrive\Desktop\silinecek_dosya.txt")
```
3. "Masaüstünde yeni dosya/not oluştur" denirse:
```python
with open(r"C:\Users\ahmet\OneDrive\Desktop\yeni.txt", "w", encoding="utf-8") as f:
    f.write("merhaba")
```

### TARAYICI VE WEB İŞLEMLERİ (ÇOK ÖNEMLİ):
"Google'ı aç", "Youtube aç" gibi isteklerde ASLA mouse koordinatlarını kafadan hesaplayarak tıklamaya çalışma! (Mouse'un kontrolden çıkarıp sapıtmasına sebep olur). DAİMA `webbrowser` modülünü kullan:
```python
import webbrowser
webbrowser.open("https://google.com")
webbrowser.open("https://youtube.com")
```

### KURALLAR:
1. SADECE İSTENENİ YAP (FAZLASINI DEĞİL): Sana sadece bir klasör/dosya 'oluşturman' veya 'taşıman' söylendiyse, SADECE `os` kodu ile dosya işlemini yap ve dur. İşlem bittikten sonra kendi inisiyatifinle klavye (pyautogui) kullanıp o klasörü aratmaya veya açmaya ASLA ÇALIŞMA!
2. BAŞLAT MENÜSÜ KISITLAMASI: Dosya veya klasör isimleri Windows Başlat (win) aramasından ARATILMAZ. Başlat araması sadece UYGULAMA (Hesap makinesi, Spotify, Chrome) başlatmak içindir.
3. İZİN BEKLEME SEN YAP: "Yapmamı ister misiniz?" asla deme. Dümdüz kodu yaz ve çalıştır. İşlem başarısız olursa bir başka yöntemle tekrar dene.
4. HER ZAMAN ```python BLOĞU KULLAN: Açıklama yaz, sonra kod bloğu ekle. Kod bloğu olmayan mesajların kodları çalıştırılmaz.
5. KISA KONUŞ: İşlemi kod ile yap ve kısa bir bilgi ver, boş uzatma.
6. Türkçe konuşursun.
"""

# ─── KOD ÇALIŞTIRICI ───

# Paylaşımlı namespace — tüm exec() çağrıları aynı ortamda çalışır
_exec_globals = {
    "__builtins__": __builtins__,
}

def execute_python_code(code: str) -> dict:
    """Python kodunu exec() ile çalıştırır, stdout ve stderr'i yakalar."""
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    try:
        show_red_border()
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(code, _exec_globals)
        hide_red_border()
        
        stdout_val = stdout_capture.getvalue()
        stderr_val = stderr_capture.getvalue()
        
        return {
            "success": True,
            "stdout": stdout_val if stdout_val else "(Çıktı yok)",
            "stderr": stderr_val if stderr_val else ""
        }
    except Exception as e:
        hide_red_border()
        return {
            "success": False,
            "stdout": stdout_capture.getvalue(),
            "stderr": traceback.format_exc()
        }


def extract_python_blocks(text: str) -> list:
    """Markdown metninden ```python ... ``` bloklarını çıkarır."""
    pattern = r'```python\s*\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    return matches


# ─── CHAT ENDPOINT ───

@app.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    user_messages = data.get("messages", [])
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + user_messages

    def generate_response():
        MAX_TURNS = 5  # Maksimim kod çalıştırma turu (sonsuz döngüyü engeller) 
        
        for turn in range(MAX_TURNS):
            # Ollama'ya sor (TOOL CALLING YOK, sadece metin)
            payload = {
                "model": MODEL,
                "messages": messages,
                "stream": True,
                # tools parametresi YOK — artık LLM kendi başına kod yazacak
            }
            
            full_response = ""
            
            try:
                with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    for chunk in r.iter_lines():
                        if not chunk:
                            continue
                        try:
                            chunk_data = json.loads(chunk.decode("utf-8"))
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
                        message = chunk_data.get("message", {})
                        
                        content = message.get("content", "")
                        if content:
                            full_response += content
                            yield json.dumps({"type": "content", "content": content}) + "\n"
                        
                        if chunk_data.get("done"):
                            break
            except Exception as e:
                yield json.dumps({"type": "error", "content": str(e)}) + "\n"
                return
            
            # LLM cevabını mesaj geçmişine ekle
            messages.append({"role": "assistant", "content": full_response})
            
            # Python kodu var mı kontrol et
            code_blocks = extract_python_blocks(full_response)
            
            if not code_blocks:
                # Kod yoksa cevap tamamdır, döngüden çık
                break
            
            # Kod blokları var — çalıştır!
            for i, code in enumerate(code_blocks):
                yield json.dumps({
                    "type": "code_exec", 
                    "status": "running",
                    "code": code[:200]  # Frontend'e özet göster
                }) + "\n"
                
                result = execute_python_code(code)
                
                status = "success" if result["success"] else "error"
                output_text = result["stdout"]
                if result["stderr"]:
                    output_text += "\n" + result["stderr"]
                
                yield json.dumps({
                    "type": "code_exec",
                    "status": status,
                    "output": output_text[:2000]  # Çıktıyı sınırla
                }) + "\n"
                
                # Çalıştırma sonucunu LLM'e geri bildir
                messages.append({
                    "role": "user",
                    "content": f"[KOD ÇALIŞTIRILDI]\nÇıktı:\n{output_text[:1500]}"
                })
            
            # Döngü devam eder — LLM çalıştırma sonucunu görüp yeni kod yazabilir veya cevap verebilir
        
    return StreamingResponse(generate_response(), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
