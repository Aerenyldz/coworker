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
import logging
import base64
from pathlib import Path
from urllib.parse import urlparse
import requests
import traceback
import keyboard
from datetime import datetime
from contextlib import redirect_stdout, redirect_stderr
from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse

try:
    import pyautogui
except Exception:
    pyautogui = None

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
logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
allowed_origins_env = os.getenv("TENRA_ALLOWED_ORIGINS", "")
raw_allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]

def _is_valid_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(parsed.hostname)

ALLOWED_ORIGINS = [o for o in raw_allowed_origins if _is_valid_origin(o)] or DEFAULT_ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = (Path(__file__).resolve().parent.parent / "frontend")

def _frontend_file(filename: str) -> Path:
    base = FRONTEND_DIR.resolve()
    candidate = (base / filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=404, detail="Frontend dosyası bulunamadı")
    if not candidate.exists():
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

def build_system_prompt(control_enabled: bool, screen_enabled: bool) -> str:
    control_state = "AÇIK" if control_enabled else "KAPALI"
    screen_state = "AÇIK" if screen_enabled else "KAPALI"
    return f"""Sen Tenra'sın: canlı, dost canlısı ama akıllı bir AI yardımcı-pet.
Kullanıcıyla sıcak ve kısa iletişim kurarsın, net ve güvenli olursun.
Türkçe konuşursun.

## Oturum durumu
- Canlı ekran erişimi: {screen_state}
- Bilgisayar kontrol izni: {control_state}

## Davranış kuralları
1. Kullanıcı ne isterse önce kısa ve anlaşılır bir plan söyle.
2. Sadece görev için gerekli işlemi yap, ekstra adım yapma.
3. Eğer "bilgisayar kontrol izni" KAPALI ise asla Python kodu üretme/çalıştırma; sadece kullanıcıyı yönlendir.
4. Eğer kontrol izni AÇIK ise çalıştırılabilir ```python``` kod bloğu verebilirsin.
5. Eğer canlı ekran erişimi AÇIK ise ekrana dair bağlamı dikkate al.
6. Belirsiz, riskli veya yıkıcı isteklerde kullanıcıyı uyar ve güvenli alternatif öner.
7. Yanıtlarını kısa, yardımsever ve odaklı tut.
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


def capture_screen_base64(max_width: int = 960, jpeg_quality: int = 65) -> str:
    if pyautogui is None:
        raise RuntimeError("Ekran yakalama modülü mevcut değil")

    screenshot = pyautogui.screenshot()
    width, height = screenshot.size
    if width > max_width:
        ratio = max_width / float(width)
        screenshot = screenshot.resize((max_width, int(height * ratio)))

    buffer = io.BytesIO()
    screenshot.convert("RGB").save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ─── CHAT ENDPOINT ───

@app.get("/screen")
def get_screen_frame():
    try:
        frame = capture_screen_base64()
        return {
            "ok": True,
            "capturedAt": datetime.utcnow().isoformat() + "Z",
            "image": f"data:image/jpeg;base64,{frame}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }

@app.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    permissions = data.get("permissions", {}) or {}
    control_enabled = bool(permissions.get("control", False))
    screen_enabled = bool(permissions.get("screen", False))
    screen_frame = data.get("screenFrame")
    user_messages = data.get("messages", [])

    if (
        screen_enabled
        and isinstance(screen_frame, str)
        and screen_frame
        and user_messages
        and isinstance(user_messages[-1], dict)
        and user_messages[-1].get("role") == "user"
    ):
        last = dict(user_messages[-1])
        last["images"] = [screen_frame]
        user_messages = user_messages[:-1] + [last]

    messages = [{"role": "system", "content": build_system_prompt(control_enabled, screen_enabled)}] + user_messages

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
                            logger.debug("Invalid stream chunk from Ollama: %r", chunk[:200])
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

            if not control_enabled:
                blocked_text = "Kontrol izni kapalı olduğu için kod çalıştırma engellendi."
                yield json.dumps({
                    "type": "code_exec",
                    "status": "blocked",
                    "output": blocked_text
                }) + "\n"
                messages.append({
                    "role": "user",
                    "content": "[SİSTEM] Kod çalıştırma engellendi çünkü kontrol izni kapalı."
                })
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
