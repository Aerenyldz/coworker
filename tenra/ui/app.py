import sys
from threading import Thread

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from tenra.ui.chat_window import ChatWindow
from tenra.ui.tray import TrayController
from tenra.config import MAIN_MODEL, OLLAMA_URL, APP_NAME


class TenraApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setFont(QFont("Segoe UI", 10))
        self.app.setQuitOnLastWindowClosed(False)  # Tray'de arka planda kalsın

        self.chat = ChatWindow()

        self.tray = TrayController()
        self.tray.show_requested.connect(self._show_ui)
        self.tray.hide_requested.connect(self._hide_to_tray)
        self.tray.quit_requested.connect(self._quit_app)
        if self.tray.show():
            self.tray.notify(APP_NAME, "Arka planda çalışıyor. Tepsi simgesine tıklayın.")

    def _show_ui(self):
        self.chat.show()
        self.chat.raise_()
        self.chat.activateWindow()
        self.chat.input_field.setFocus()

    def _hide_to_tray(self):
        self.chat.hide()

    def _quit_app(self):
        self.app.quit()

    def run(self):
        self.chat.show()
        self.chat.input_field.setFocus()

        def preload():
            try:
                import requests
                requests.post(
                    f"{OLLAMA_URL}/generate",
                    json={
                        "model": MAIN_MODEL,
                        "prompt": "hi",
                        "stream": False,
                        "keep_alive": "30m",
                        "options": {"num_predict": 1},
                    },
                    timeout=60,
                )
            except Exception as e:
                print(f"[Tenra] Model ön yükleme hatası: {e}")

        Thread(target=preload, daemon=True).start()
        print("[Tenra] Hazır. Sistem tepsisi ile açabilirsiniz.")
        sys.exit(self.app.exec())


def check_and_install_dependencies():
    """Tenra başlatılmadan önce gerekli modülleri kontrol eder."""
    print("[+] Tenra: Bağımlılıklar kontrol ediliyor...")
    import subprocess

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
    try:
        from ddgs import DDGS  # noqa: F401
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # noqa: F401
        except ImportError:
            required["ddgs"] = "ddgs"

    missing = []
    for module_name, pip_name in required.items():
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print(f"[*] Eksik kütüphaneler: {', '.join(missing)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("[+] Kütüphaneler kuruldu! Yeniden başlatın.")
            sys.exit(0)
        except Exception as e:
            print(f"[-] Kurulum hatası: {e}")
            sys.exit(1)


def main():
    check_and_install_dependencies()
    tenra = TenraApp()
    tenra.run()


if __name__ == "__main__":
    main()
