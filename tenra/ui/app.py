import sys
import subprocess
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from threading import Thread

from tenra.ui.floating_widget import FloatingWidget
from tenra.ui.chat_window import ChatWindow
from tenra.config import MAIN_MODEL, OLLAMA_URL

# ═══════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════
class TenraApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setFont(QFont("Segoe UI", 10))

        self.widget = FloatingWidget()
        self.widget.clicked.connect(self._toggle_chat)
        self.widget.close_requested.connect(self.app.quit)

        self.chat = ChatWindow()

    def _toggle_chat(self):
        if self.chat.isVisible():
            self.chat.hide()
        else:
            self.chat.show()
            self.chat.input_field.setFocus()

    def run(self):
        self.widget.show()
        self.chat.show()
        self.chat.input_field.setFocus()

        from threading import Thread
        def preload():
            try:
                import requests
                
                requests.post(
                    f"{OLLAMA_URL}/generate",
                    json={"model": MAIN_MODEL, "prompt": "hi", "stream": False,
                          "keep_alive": "30m", "options": {"num_predict": 1}},
                    timeout=60,
                )
            except Exception as e:
                print(f"[Tenra] Model preload hatası: {e}")

        Thread(target=preload, daemon=True).start()
        print("[Tenra] Floating widget aktif. Logoya tiklayarak sohbeti acin.")
        sys.exit(self.app.exec())


def check_and_install_dependencies():
    """Tenra baslatilmadan once gerekli modullerin kurulu olup olmadigini kontrol eder."""
    print("[+] Tenra V7: Bagimliliklar kontrol ediliyor...")
    import subprocess, sys

    required = {
        "PySide6": "PySide6",
        "requests": "requests",
        "pyautogui": "pyautogui",
        "send2trash": "send2trash",
        "bs4": "beautifulsoup4",
        "PIL": "Pillow",
        "pytesseract": "pytesseract",
        "speech_recognition": "SpeechRecognition",
        "pyaudio": "PyAudio",
    }
    # ddgs kontrolü
    try:
        from ddgs import DDGS  # noqa
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # noqa
        except ImportError:
            required["ddgs"] = "ddgs"

    missing = []
    for module_name, pip_name in required.items():
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print(f"[*] Eksik kutuphaneler: {', '.join(missing)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("[+] Kutuphaneler kuruldu! Yeniden baslatın.")
            sys.exit(0)
        except Exception as e:
            print(f"[-] Kurulum hatasi: {e}")
            sys.exit(1)



def main():
    check_and_install_dependencies()
    tenra = TenraApp()
    tenra.run()

if __name__ == "__main__":
    main()
