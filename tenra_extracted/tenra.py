import threading
import tkinter as tk
from tkinter import scrolledtext
import pystray
from PIL import Image, ImageDraw
import requests
import json
import subprocess
import glob
import os
import sys

# ─────────────────────────────────────────────
# AYARLAR
# ─────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"          # araç çağırma destekleyen model
WINDOW_W, WINDOW_H = 360, 520
WINDOW_X, WINDOW_Y = 1530, 40  # sağ üst köşe — çözünürlüğüne göre ayarla

SYSTEM_PROMPT = """Sen Tenra'sın — kullanıcının bilgisayarında çalışan kişisel AI asistanısın.
Türkçe konuşursun. Kısa ve net cevaplar verirsin.
Dosya bulma, komut çalıştırma, tarayıcı açma gibi görevlerde proaktifsin."""

# ─────────────────────────────────────────────
# ARAÇLAR
# ─────────────────────────────────────────────

def dosya_bul(arama: str) -> str:
    """Dosya adına göre arama yapar."""
    home = os.path.expanduser("~")
    sonuclar = glob.glob(f"{home}/**/*{arama}*", recursive=True)[:5]
    if sonuclar:
        return "Bulunan dosyalar:\n" + "\n".join(sonuclar)
    return f"'{arama}' adında dosya bulunamadı."

def url_ac(url: str) -> str:
    """Tarayıcıda URL açar."""
    if not url.startswith("http"):
        url = "https://" + url
    os.startfile(url)
    return f"Tarayıcıda açıldı: {url}"

def komut_calistir(komut: str) -> str:
    """Güvenli terminal komutu çalıştırır."""
    izinli = ["dir", "ls", "echo", "ping", "ipconfig", "python --version"]
    if not any(komut.strip().startswith(k) for k in izinli):
        return "Bu komutu çalıştırma iznin yok (güvenlik kısıtlaması)."
    result = subprocess.run(komut, shell=True, capture_output=True, text=True, timeout=10)
    return result.stdout or result.stderr or "Komut çalıştı (çıktı yok)."

def uygulama_ac(ad: str) -> str:
    """Windows uygulaması açar."""
    uygulamalar = {
        "not defteri": "notepad",
        "hesap": "calc",
        "dosya gezgini": "explorer",
        "vs code": "code",
        "terminal": "cmd"
    }
    anahtar = next((k for k in uygulamalar if k in ad.lower()), None)
    if anahtar:
        subprocess.Popen(uygulamalar[anahtar])
        return f"{anahtar.title()} açıldı."
    return f"'{ad}' uygulaması tanınmadı."

ARACLAR = {
    "dosya_bul": dosya_bul,
    "url_ac": url_ac,
    "komut_calistir": komut_calistir,
    "uygulama_ac": uygulama_ac,
}

# ─────────────────────────────────────────────
# OLLAMA BAĞLANTISI
# ─────────────────────────────────────────────

def ollama_sor(mesajlar: list) -> str:
    """Ollama'ya mesaj gönderir, streaming ile yanıt alır."""
    try:
        payload = {
            "model": MODEL,
            "messages": mesajlar,
            "stream": False,
        }
        r = requests.post(OLLAMA_URL, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data["message"]["content"]
    except requests.exceptions.ConnectionError:
        return "⚠️ Ollama bağlantısı kurulamadı. `ollama serve` çalışıyor mu?"
    except Exception as e:
        return f"⚠️ Hata: {e}"

def ajan_cevapla(kullanici, gecmis: list) -> str:
    """Kullanıcı mesajını ajan mantığıyla işler."""
    mesaj = kullanici.lower()

    # Basit araç yönlendirme (LLM çağrısından önce hızlı kontrol)
    if any(k in mesaj for k in ["dosya bul", "bul dosyayı", "nerede"]):
        arama = kullanici.split()[-1]
        return dosya_bul(arama)

    if any(k in mesaj for k in ["aç", "google", "youtube", "web", "site", "url"]):
        for kelime in kullanici.split():
            if "." in kelime or "http" in kelime:
                return url_ac(kelime)
        if "google" in mesaj:
            sorgu = mesaj.replace("google", "").replace("aç", "").strip()
            return url_ac(f"https://google.com/search?q={sorgu}")

    if any(k in mesaj for k in ["not defteri", "hesap makinesi", "dosya gezgini", "vs code"]):
        return uygulama_ac(kullanici)

    # LLM'e sor
    gecmis_kop = gecmis[-10:]  # son 10 mesaj
    mesajlar = [{"role": "system", "content": SYSTEM_PROMPT}] + gecmis_kop
    mesajlar.append({"role": "user", "content": kullanici})
    return ollama_sor(mesajlar)

# ─────────────────────────────────────────────
# CHAT PENCERESİ (tkinter)
# ─────────────────────────────────────────────

class TenraWindow:
    def __init__(self):
        self.root = None
        self.gecmis = []

    def goster(self, icon=None, item=None):
        if self.root and self.root.winfo_exists():
            self.root.lift()
            return
        t = threading.Thread(target=self._pencere_ac, daemon=True)
        t.start()

    def _pencere_ac(self):
        self.root = tk.Tk()
        root = self.root

        root.title("✦ Tenra")
        root.geometry(f"{WINDOW_W}x{WINDOW_H}+{WINDOW_X}+{WINDOW_Y}")
        root.configure(bg="#0d0d0d")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.96)

        # Başlık
        baslik = tk.Frame(root, bg="#111111", height=44)
        baslik.pack(fill="x")
        baslik.pack_propagate(False)

        tk.Label(
            baslik, text="✦ TENRA", bg="#111111", fg="#e8d5b0",
            font=("Courier New", 13, "bold"), padx=14
        ).pack(side="left", pady=10)

        tk.Label(
            baslik, text="⬤ online", bg="#111111", fg="#4caf72",
            font=("Courier New", 8)
        ).pack(side="right", padx=12, pady=10)

        # Ayırıcı çizgi
        tk.Frame(root, bg="#2a2a2a", height=1).pack(fill="x")

        # Chat alanı
        self.chat = scrolledtext.ScrolledText(
            root, bg="#0d0d0d", fg="#d4c9b8",
            font=("Courier New", 10), wrap="word",
            relief="flat", bd=0, padx=12, pady=10,
            insertbackground="#e8d5b0",
            state="disabled"
        )
        self.chat.pack(fill="both", expand=True, padx=0, pady=0)

        # Renk etiketleri
        self.chat.tag_config("user", foreground="#7eb8d4", font=("Courier New", 10, "bold"))
        self.chat.tag_config("tenra", foreground="#d4c9b8")
        self.chat.tag_config("meta", foreground="#555555", font=("Courier New", 8))
        self.chat.tag_config("hata", foreground="#cf6679")

        # Hoş geldin mesajı
        self._chat_ekle("tenra", "Merhaba. Ben Tenra.\n"
                                  "Dosya bul, uygulama aç,\n"
                                  "web'e git veya sohbet et.\n")

        # Giriş alanı
        alt = tk.Frame(root, bg="#111111", height=52)
        alt.pack(fill="x", side="bottom")
        alt.pack_propagate(False)

        tk.Frame(alt, bg="#2a2a2a", height=1).pack(fill="x")

        giriş_frame = tk.Frame(alt, bg="#111111")
        giriş_frame.pack(fill="x", padx=10, pady=8)

        self.giris = tk.Entry(
            giriş_frame, bg="#1a1a1a", fg="#e8d5b0",
            font=("Courier New", 10), relief="flat", bd=0,
            insertbackground="#e8d5b0"
        )
        self.giris.pack(side="left", fill="x", expand=True, ipady=6, padx=(8, 6))
        self.giris.bind("<Return>", self.gonder)
        self.giris.focus()

        gonder_btn = tk.Button(
            giriş_frame, text="→", bg="#2a2a2a", fg="#e8d5b0",
            font=("Courier New", 12, "bold"), relief="flat",
            cursor="hand2", bd=0, padx=10,
            command=lambda: self.gonder(None),
            activebackground="#3a3a3a", activeforeground="#ffffff"
        )
        gonder_btn.pack(side="right")

        root.protocol("WM_DELETE_WINDOW", self._kapat)
        root.mainloop()

    def _chat_ekle(self, kim: str, metin: str):
        self.chat.config(state="normal")
        if kim == "user":
            self.chat.insert("end", "› ", "user")
            self.chat.insert("end", metin + "\n\n", "user")
        elif kim == "tenra":
            self.chat.insert("end", metin + "\n", "tenra")
        elif kim == "meta":
            self.chat.insert("end", metin + "\n", "meta")
        self.chat.config(state="disabled")
        self.chat.see("end")

    def gonder(self, event):
        metin = self.giris.get().strip()
        if not metin:
            return
        self.giris.delete(0, "end")
        self._chat_ekle("user", metin)
        self._chat_ekle("meta", "düşünüyor...")

        self.gecmis.append({"role": "user", "content": metin})

        def arkaplanda():
            cevap = ajan_cevapla(metin, self.gecmis)
            self.gecmis.append({"role": "assistant", "content": cevap})
            if self.root and self.root.winfo_exists():
                self.root.after(0, lambda: self._guncelle(cevap))

        threading.Thread(target=arkaplanda, daemon=True).start()

    def _guncelle(self, cevap: str):
        # "düşünüyor..." satırını sil
        self.chat.config(state="normal")
        content = self.chat.get("1.0", "end")
        if "düşünüyor..." in content:
            start = self.chat.search("düşünüyor...", "1.0", "end")
            if start:
                end = f"{start}+{len('düşünüyor...')+1}c"
                self.chat.delete(start, end)
        self.chat.config(state="disabled")
        self._chat_ekle("tenra", f"✦ {cevap}\n")

    def _kapat(self):
        self.root.destroy()
        self.root = None


# ─────────────────────────────────────────────
# TRAY İKONU OLUŞTUR
# ─────────────────────────────────────────────

def tray_ikonu_olustur():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Altıgen arka plan
    d.ellipse([4, 4, 60, 60], fill=(17, 17, 17, 230))
    # Yıldız şekli (✦ temsili)
    d.polygon([32,8, 36,28, 56,32, 36,36, 32,56, 28,36, 8,32, 28,28], fill=(232, 213, 176))
    return img


# ─────────────────────────────────────────────
# ANA ÇALIŞMA
# ─────────────────────────────────────────────

if __name__ == "__main__":
    pencere = TenraWindow()

    menu = pystray.Menu(
        pystray.MenuItem("✦ Tenra'yı Aç", pencere.goster, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Çıkış", lambda icon, item: (icon.stop(), sys.exit(0)))
    )

    icon = pystray.Icon(
        name="Tenra",
        icon=tray_ikonu_olustur(),
        title="Tenra — AI Asistan",
        menu=menu
    )

    print("Tenra başlatıldı. Sistem tepsisine bak.")
    icon.run()
