"""
Tenra V5 — Floating Widget + Chat Window
Copilot tarzı: Ekranda her zaman küçük bir logo, tıklayınca chat açılır.
"""

import sys
import os
import re
import warnings
from datetime import datetime
from pathlib import Path
warnings.simplefilter("ignore")

# PyTorch warnings bastır
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

from PySide6.QtCore import Qt, QPoint, QSize, QTimer, Signal, QThread, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QGraphicsDropShadowEffect, QSizePolicy, QSizeGrip
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient,
    QIcon, QPixmap, QCursor, QKeyEvent, QGuiApplication
)


# ═══════════════════════════════════════════════
# RENK PALETİ
# ═══════════════════════════════════════════════
class Colors:
    BG_DARK = QColor(10, 10, 14)
    BG_PANEL = QColor(18, 18, 26)
    BG_INPUT = QColor(28, 28, 40)
    ACCENT = QColor(94, 235, 216)       # Tenra Teal
    ACCENT_DIM = QColor(94, 235, 216, 80)
    TEXT = QColor(240, 240, 240)
    TEXT_MUTED = QColor(136, 136, 148)
    BORDER = QColor(255, 255, 255, 20)
    USER_BG = QColor(255, 255, 255, 15)
    SUCCESS = QColor(76, 175, 114)
    ERROR = QColor(207, 102, 121)
    WIDGET_BG = QColor(20, 20, 30, 230)


# ═══════════════════════════════════════════════
# FLOATING WIDGET (Ekranda Yüzen Logo)
# ═══════════════════════════════════════════════
class FloatingWidget(QWidget):
    """Ekranda her zaman üstte duran, sürüklenebilir Tenra logosu."""
    
    clicked = Signal()

    def __init__(self):
        super().__init__()
        
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(56, 56)
        
        # Ekranın sağ alt köşesine yerleştir
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 80, screen.height() - 120)
        
        self._drag_pos = None
        self._hover = False
        
        # Pulse animasyonu
        self._pulse_opacity = 0.6
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._pulse)
        self._pulse_timer.start(50)
        self._pulse_dir = 1

    def _pulse(self):
        self._pulse_opacity += 0.01 * self._pulse_dir
        if self._pulse_opacity >= 1.0:
            self._pulse_dir = -1
        elif self._pulse_opacity <= 0.5:
            self._pulse_dir = 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Dış glow
        if self._hover:
            glow_color = QColor(94, 235, 216, int(80 * self._pulse_opacity))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow_color))
            painter.drawEllipse(2, 2, 52, 52)
        
        # Ana daire
        gradient = QLinearGradient(0, 0, 56, 56)
        gradient.setColorAt(0, QColor(30, 35, 50, 240))
        gradient.setColorAt(1, QColor(15, 18, 30, 240))
        painter.setBrush(QBrush(gradient))
        
        pen_color = QColor(94, 235, 216, int(200 * self._pulse_opacity))
        painter.setPen(QPen(pen_color, 2))
        painter.drawEllipse(4, 4, 48, 48)
        
        # "T" harfi
        painter.setPen(QPen(Colors.ACCENT, 2))
        font = QFont("Consolas", 22, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, "T")

    def enterEvent(self, event):
        self._hover = True
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._drag_pos:
                moved = (event.globalPosition().toPoint() - self.frameGeometry().topLeft() - self._drag_pos).manhattanLength()
                if moved < 5:  # Tıklama (sürükleme değil)
                    self.clicked.emit()
            self._drag_pos = None


# ═══════════════════════════════════════════════
# WIDGETS
# ═══════════════════════════════════════════════
class ClickableLabel(QLabel):
    clicked = Signal()
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

# ═══════════════════════════════════════════════
# SIMPLE ACTION WORKER THREAD
# ═══════════════════════════════════════════════
class SimpleActionWorker(QThread):
    """Kisa I/O islemlerini arkaplanda calistirir (UI donmasin diye)."""
    action_finished = Signal(str, str) # func_name, message
    
    def __init__(self, action_type, executor, params):
        super().__init__()
        self.action_type = action_type
        self.executor = executor
        self.params = params
        
    def run(self):
        try:
            if self.action_type == "delete":
                result = self.executor.execute("move_to_trash", self.params)
                msg = result.get("message", "İşlem tamamlandı.")
                self.action_finished.emit("move_to_trash", msg)
        except Exception as e:
            self.action_finished.emit("Hata", str(e))
# ═══════════════════════════════════════════════
# LLM WORKER THREAD
# ═══════════════════════════════════════════════
class LLMWorker(QThread):
    """Arkaplanda LLM çağrısı yapar (GUI donmasın diye)."""
    response_ready = Signal(str, str)  # (message, func_info)
    tool_executed = Signal(str, str)   # (func_name, result)
    tool_approval_requested = Signal(str, str) # (func_name, params_str)
    tool_started = Signal(str) # (func_name)
    
    def __init__(self, user_input: str, screenshot_path: str | None = None, chat_history: list = None, rpa_mode: bool = False):
        super().__init__()
        self.rpa_mode = rpa_mode
        self.user_input = user_input
        self.raw_user_input = user_input
        
        self.screenshot_path = screenshot_path
        self.chat_history = chat_history or []
        self.tool_approval_result = None

    def _wait_for_approval(self, func_name: str, params: dict) -> bool:
        import json, time
        self.tool_approval_result = None
        params_str = json.dumps(params, ensure_ascii=False, indent=2)
        self.tool_approval_requested.emit(func_name, params_str)
        
        while self.tool_approval_result is None:
            time.sleep(0.1)
            
        return self.tool_approval_result

    def _extract_quoted_name(self, text: str) -> str:
        match = re.search(r"[\"']([^\"']{2,120})[\"']", text)
        if match:
            return match.group(1).strip()

        name_match = re.search(r"(?:adli|adında|isimli)\s+([\w\-\. ]{2,80})", text, flags=re.IGNORECASE)
        if name_match:
            return name_match.group(1).strip()
        return ""

    def _extract_delete_target(self, text: str) -> str:
        text = text.strip()
        patterns = [
            r"(?:masaustunde|masaüstünde)\s+(.+?)\s+(?:dosyasini|dosyasını|dosyayi|dosyayı|klasoru|klasörü|klasor|klasör)?\s*sil",
            r"(?:desktopta|desktop'ta)\s+(.+?)\s+(?:dosyasini|dosyasını|dosyayi|dosyayı|klasoru|klasörü|klasor|klasör)?\s*sil",
            r"(.+?)\s+(?:dosyasini|dosyasını|dosyayi|dosyayı|klasoru|klasörü|klasor|klasör)?\s*sil$",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .,:;")
                value = re.sub(r"^(bir|su|şu|o)\s+", "", value, flags=re.IGNORECASE)
                if value:
                    return value
        return ""

    def _extract_google_query(self, text: str) -> str:
        lower = text.lower()
        quoted = self._extract_quoted_name(text)
        if quoted:
            return quoted

        # "muz hakkinda ..." kalibi
        split_token = "hakkında" if "hakkında" in lower else ("hakkinda" if "hakkinda" in lower else "")
        if split_token:
            left = lower.split(split_token)[0]
            tokens = re.findall(r"[a-z0-9çğıöşü]+", left)
            stop_words = {
                "yeni", "bir", "google", "sayfasi", "sayfası", "sayfa", "ac", "aç", "acip", "açıp",
                "web", "ve", "ile", "icin", "için", "hakkinda", "hakkında",
            }
            filtered = [t for t in tokens if t not in stop_words]
            if filtered:
                return " ".join(filtered[-4:]).strip()

        # "google'da x ara" kalibi
        search_match = re.search(r"(?:google'da|googleda|ara|search)\s*[:\-]?\s*(.+)", lower, flags=re.IGNORECASE)
        if search_match:
            candidate = search_match.group(1)
            candidate = re.sub(r"\b(aç|ac|açıp|acip|sayfa|sayfasi|sayfası)\b", "", candidate, flags=re.IGNORECASE)
            candidate = re.sub(r"\s+", " ", candidate).strip(" .,:;")
            if candidate:
                return candidate

        return ""

    def _is_action_intent(self, text: str) -> bool:
        import re
        lower = text.lower()
        action_tokens = (
            "ac", "aç", "sil", "olustur", "oluştur", "yarat", "ara", "calistir", "çalıştır",
            "tikla", "tıkla", "tasi", "taşı", "kopyala", "yaz", "guncelle", "güncelle",
        )
        words = re.findall(r'\b\w+\b', lower)
        return any(token in words for token in action_tokens)

    def _looks_like_manual_instructions(self, text: str) -> bool:
        lowered = text.lower()
        manual_tokens = (
            "adim",
            "adımlar",
            "takip",
            "tikla",
            "tıkl",
            "1.",
            "2.",
            "3.",
        )
        return any(token in lowered for token in manual_tokens)

    def _run_direct_shortcut(self, executor):
        lower = self.raw_user_input.lower()
        text = self.raw_user_input.strip()

        if "masa" in lower and "liste" in lower:
            return "list_desktop", executor.execute("list_desktop", {})

        if "sistem" in lower and re.search(r"\b(durum|bilgi|ozet|özet)\b", lower):
            return "get_system_info", executor.execute("get_system_info", {})

        if "google" in lower and any(word in lower for word in ("ac", "aç", "open")):
            from urllib.parse import quote_plus

            query = self._extract_google_query(text)
            if query:
                search_url = f"https://www.google.com/search?q={quote_plus(query)}"
                return "open_url", executor.execute("open_url", {"url": search_url})
            return "open_url", executor.execute("open_url", {"url": "https://www.google.com"})

        if "ara" in lower and ("web" in lower or "google" in lower):
            query = text
            for token in ("google'da", "googleda", "webde", "webde ara", "ara"):
                query = re.sub(token, "", query, flags=re.IGNORECASE).strip(" :")
            if not query:
                query = text
            return "web_search", executor.execute("web_search", {"query": query})

        if any(word in lower for word in ("ac", "aç")) and "http" in lower:
            url_match = re.search(r"https?://\S+", text, flags=re.IGNORECASE)
            if url_match:
                return "open_url", executor.execute("open_url", {"url": url_match.group(0)})

        create_words = ("olustur", "oluştur", "yarat")
        create_intent = any(word in lower for word in create_words) or (
            "yeni" in lower and ("dosya" in lower or "klasor" in lower or "klasör" in lower)
        )
        if "klasor" in lower or "klasör" in lower:
            if create_intent and "sil" not in lower:
                folder_name = self._extract_quoted_name(text)
                if not folder_name:
                    folder_name = f"YeniKlasor_{datetime.now().strftime('%H%M%S')}"
                return "create_folder", executor.execute("create_folder", {"path": folder_name})

        if "dosya" in lower and create_intent and "sil" not in lower:
            file_name = self._extract_quoted_name(text)
            if not file_name:
                file_name = f"YeniDosya_{datetime.now().strftime('%H%M%S')}.txt"
            if "." not in file_name:
                file_name = f"{file_name}.txt"
            return "create_file", executor.execute("create_file", {"path": file_name, "content": ""})

        if lower.startswith("komut:") or lower.startswith("powershell:"):
            raw_cmd = text.split(":", 1)[1].strip() if ":" in text else ""
            if raw_cmd:
                return "run_command", executor.execute("run_command", {"command": raw_cmd})

        if "sil" in lower and ("dosya" in lower or "klasor" in lower or "klasör" in lower):
            target = self._extract_quoted_name(text) or self._extract_delete_target(text)
            if target:
                return "confirm_delete", {"success": True, "message": target}

        if any(word in lower for word in ("ac", "aç", "başlat", "baslat")) and "uygulama" in lower:
            app_name = self._extract_quoted_name(text)
            if not app_name:
                app_name = re.sub(r"(uygulama|ac|aç|başlat|baslat)", "", text, flags=re.IGNORECASE).strip(" :")
            if app_name:
                return "open_app", executor.execute("open_app", {"name": app_name})

        return None
    
    def run(self):
        try:
            from core.function_executor import executor
            executor.approval_callback = self._wait_for_approval
            executor.tool_start_callback = lambda f_name: self.tool_started.emit(f_name)
            from core.hermes_agent import (
                analyze_screenshot_question,
                run_hermes_tool_loop,
                should_analyze_screenshot,
            )

            # Screenshot analysis mode
            if should_analyze_screenshot(self.user_input, self.screenshot_path):
                vision_result = analyze_screenshot_question(self.user_input, self.screenshot_path, chat_history=self.chat_history)
                if vision_result.get("ok"):
                    self.response_ready.emit(vision_result.get("reply", "Görüntü analiz edildi."), "")
                else:
                    self.response_ready.emit(
                        f"Ekran analizi hatası: {vision_result.get('error', 'Bilinmeyen hata')}",
                        "",
                    )
                return

            # Direct shortcut matching (keyword-based, no LLM needed)
            shortcut = self._run_direct_shortcut(executor)
            if shortcut:
                shortcut_name, shortcut_result = shortcut
                if shortcut_name == "confirm_delete":
                    target = shortcut_result.get("message", "")
                    if target:
                        self.response_ready.emit(f"__CONFIRM_DELETE__{target}", "")
                    else:
                        self.response_ready.emit("Silinecek hedef anlasilamadi.", "")
                    return
                msg = shortcut_result.get("message", "İşlem tamamlandı.")
                self.tool_executed.emit(shortcut_name, msg)
                self.response_ready.emit(msg, shortcut_name)
                return

            # Lightweight yes/no confirmation for pending dangerous actions
            if self._is_action_intent(self.raw_user_input):
                self.response_ready.emit(
                    "Komut icin once dogrudan arac denendi ama uygun eylem bulunamadi. "
                    "Lutfen tek cümlede hedefi net yazin. Ornek: masaustunde 'hermes denem v2' dosyasini sil.",
                    "",
                )
                return

            # Pass input directly without confusing system injections
            input_text = self.user_input

            # Full Hermes tool-calling agent loop
            agent_result = run_hermes_tool_loop(input_text, executor, chat_history=self.chat_history)
            if not agent_result.get("ok"):
                error_msg = agent_result.get("error", "Bilinmeyen hata")
                self.response_ready.emit(f"⚠ {error_msg}", "")
                return

            # Emit each tool execution result
            tool_results = agent_result.get("tool_results", [])
            for tool_call in tool_results:
                name = tool_call.get("name", "tool")
                result = tool_call.get("result", {})
                success = result.get("success", True)
                msg = result.get("message", "İşlem tamamlandı")
                status = "✓" if success else "✗"
                self.tool_executed.emit(name, f"{status} {msg}")

            # Determine final reply
            reply = (agent_result.get("reply") or "").strip()

            # If model gave manual instructions instead of acting, use tool result
            if tool_results and (not reply or self._looks_like_manual_instructions(reply)):
                last_tool_name = tool_results[-1].get("name", "")
                last_msg = tool_results[-1].get("result", {}).get("message", "")
                for tool_call in tool_results:
                    if tool_call.get("name") in {"move_to_trash", "delete_file"}:
                        self._pending_action = None
                        break
                is_info_only = all(
                    (tool_call.get("name") == "get_system_info") for tool_call in tool_results
                )
                if is_info_only and self._is_action_intent(self.raw_user_input):
                    reply = (
                        "Bu istek bir eylem komutu ama model sadece sistem ozeti istedi. "
                        "Komutu daha net verin: ornek 'masaustunde hermes denem v2 dosyasini sil'."
                    )
                elif last_msg and last_tool_name != "get_system_info":
                    reply = last_msg
                elif not reply:
                    reply = "İşlem arka planda tamamlandı."

            self.response_ready.emit(reply or "İşlem tamamlandı.", "")
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.response_ready.emit(f"Hata: {str(e)[:200]}", "")


# ═══════════════════════════════════════════════
# CHAT WINDOW (Ana Sohbet Penceresi)
# ═══════════════════════════════════════════════
class ChatWindow(QMainWindow):
    """Tenra sohbet penceresi — dark, glassmorphism, premium."""
    
    def __init__(self):
        super().__init__()
        self.chat_history = []
        self.rpa_mode = False
        self._pending_action = None
        self.setWindowTitle("Tenra")
        self.setMinimumSize(480, 650)
        self.resize(500, 700)
        self.setWindowFlags(Qt.WindowStaysOnTopHint) # FramelessWindowHint iptal edildi, resize kolaylassin
        # self.setAttribute(Qt.WA_TranslucentBackground) # Frameless degilse bu da iptal
        
        self._drag_pos = None
        self._worker = None
        self.latest_screenshot_path = None
        
        self._build_ui()
        self._position_window()
    
    def _position_window(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - self.width() - 20, screen.height() - self.height() - 80)
    
    def _build_ui(self):
        # Ana container
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Container frame (glassmorphism)
        self.container = QFrame()
        self.container.setStyleSheet(f"""
            QFrame {{
                background: rgba(24, 26, 32, 245);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
            }}
        """)
        
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # === HEADER ===
        header = QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet("QFrame { background: transparent; border-bottom: 1px solid rgba(255,255,255,0.06); border-radius: 0; }")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        
        # Logo + isim
        logo_label = QLabel("T")
        logo_label.setFont(QFont("Segoe UI", 18, QFont.ExtraBold))
        logo_label.setStyleSheet(f"QLabel {{ color: {Colors.ACCENT.name()}; background: transparent; border: none; padding: 0; margin: 0; }}")
        logo_label.setFixedWidth(30)
        
        title_label = QLabel("TENRA")
        title_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title_label.setStyleSheet(f"QLabel {{ color: {Colors.TEXT.name()}; background: transparent; border: none; padding: 0; margin: 0; }}")
        
        version_label = QLabel("v5")
        version_label.setFont(QFont("Segoe UI", 9, QFont.Light))
        version_label.setStyleSheet(f"QLabel {{ color: {Colors.TEXT_MUTED.name()}; background: transparent; border: none; padding: 0; margin-top: 4px; }}")
        
        # Status dot
        self.status_dot = QLabel("●")
        self.status_dot.setFont(QFont("Segoe UI", 8))
        self.status_dot.setStyleSheet(f"QLabel {{ color: {Colors.ACCENT.name()}; background: transparent; border: none; padding: 0; margin: 0; }}")
        
        status_text = QLabel("Aktif")
        status_text.setFont(QFont("Segoe UI", 9))
        status_text.setStyleSheet(f"QLabel {{ color: {Colors.TEXT_MUTED.name()}; background: transparent; border: none; padding: 0; margin: 0; }}")
        
        # Kapat butonu
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setFont(QFont("Segoe UI", 11))
        close_btn.setStyleSheet("""
            QPushButton { color: #666; background: transparent; border: none; border-radius: 14px; }
            QPushButton:hover { color: #fff; background: rgba(255,60,60,0.3); }
        """)
        close_btn.clicked.connect(self.hide)
        
        header_layout.addWidget(logo_label)
        header_layout.addWidget(title_label)
        header_layout.addWidget(version_label)
        header_layout.addStretch()
        header_layout.addWidget(self.status_dot)
        header_layout.addWidget(status_text)
        header_layout.addWidget(close_btn)
        
        # === CHAT AREA (Tek bir QTextBrowser) ===
        from PySide6.QtWidgets import QTextBrowser
        
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(False) # Linkleri kendimiz yonetelim
        self.chat_display.setOpenLinks(False)         # Metin kutusunun linki "iceri" almasini tamamen engelle
        self.chat_display.anchorClicked.connect(self._on_anchor_clicked)
        self.chat_display.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                padding: 10px;
            }
            QScrollBar:vertical { width: 8px; background: rgba(0,0,0,0.1); }
            QScrollBar::handle:vertical { background: rgba(255,255,255,0.2); border-radius: 4px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        
        # HTML chat yapisi icin ilk hazirlik
        self.chat_display.setHtml("<html><body style='font-family: Segoe UI; font-size: 14px; margin: 0; padding: 0;'></body></html>")
        
        # Welcome message
        self._add_message("Merhaba. Ben <b>Tenra</b>. Bilgisayarınızı yönetebilir, dosya işlemleri yapabilir, web'de arama yapabilirim. Bir şey sorun veya bir görev verin.", is_user=False)
        
        # === INPUT PREVIEW AREA (Attached SS) ===
        self.preview_frame = QFrame()
        self.preview_frame.setStyleSheet("background: rgba(0,0,0,0.4); border-radius: 8px;")
        self.preview_frame.hide()
        
        preview_layout = QHBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(8, 4, 8, 4)
        
        self.preview_img = ClickableLabel()
        self.preview_img.setFixedSize(60, 40)
        self.preview_img.setStyleSheet("background: #000; border-radius: 4px;")
        self.preview_img.setCursor(Qt.PointingHandCursor)
        self.preview_img.clicked.connect(self._open_preview_image)
        
        self.preview_text = QLabel("Ekran görüntüsü eklendi")
        self.preview_text.setStyleSheet("color: #4bd8c4;")
        self.preview_text.setFont(QFont("Segoe UI", 9))
        
        self.preview_close_btn = QPushButton("✕")
        self.preview_close_btn.setFixedSize(20, 20)
        self.preview_close_btn.setStyleSheet("QPushButton { background: transparent; color: #aaa; border: none; } QPushButton:hover { color: #ff5555; }")
        self.preview_close_btn.clicked.connect(self._clear_screenshot)
        
        preview_layout.addWidget(self.preview_img)
        preview_layout.addWidget(self.preview_text)
        preview_layout.addStretch()
        preview_layout.addWidget(self.preview_close_btn)
        
        # === INPUT AREA ===
        input_frame = QFrame()
        input_frame.setStyleSheet("QFrame { background: rgba(0,0,0,0.3); border-top: 1px solid rgba(255,255,255,0.06); border-radius: 0; border-bottom-left-radius: 16px; border-bottom-right-radius: 16px; }")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 10, 12, 10)
        input_layout.setSpacing(8)

        self.capture_btn = QPushButton("📷")
        self.capture_btn.setFixedSize(42, 38)
        self.capture_btn.setToolTip("Ekran görüntüsü al — sonra bu görsel üzerinden soru sorabilirsin")
        self.capture_btn.setFont(QFont("Segoe UI", 13))
        self.capture_btn.setStyleSheet("""
            QPushButton {
                background: rgba(94, 235, 216, 0.22);
                color: #d9fff8;
                border: 1px solid rgba(94, 235, 216, 0.45);
                border-radius: 10px;
            }
            QPushButton:hover { background: rgba(94, 235, 216, 0.34); }
            QPushButton:disabled { background: #2f3a3f; color: #778; border-color: #445; }
        """)
        self.capture_btn.clicked.connect(self._capture_screenshot)
        
        self.attach_btn = QPushButton("📎")
        self.attach_btn.setFixedSize(38, 38)
        self.attach_btn.setToolTip("Bilgisayardan fotoğraf yükle")
        self.attach_btn.setFont(QFont("Segoe UI", 12))
        self.attach_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #aaa;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 19px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.12); color: #fff; }
        """)
        self.attach_btn.clicked.connect(self._select_image)
        
        self.rpa_btn = QPushButton("🤖")
        self.rpa_btn.setFixedSize(38, 38)
        self.rpa_btn.setToolTip("Otonom Mod (RPA) — Farenizi ve klavyenizi kullanarak bilgisayari kontrol eder")
        self.rpa_btn.setFont(QFont("Segoe UI", 14))
        self.rpa_btn.setCheckable(True)
        self.rpa_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #aaa;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 19px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 0.12); color: #fff; }
            QPushButton:disabled { background: #2f3a3f; color: #778; border-color: #445; }
        """)
        self.rpa_btn.clicked.connect(self._toggle_rpa_mode)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ne yapayım?")
        self.input_field.setFont(QFont("Segoe UI", 11))
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 18px;
                padding: 10px 18px;
                color: {Colors.TEXT.name()};
            }}
            QLineEdit:focus {{
                background: rgba(255,255,255,0.08);
                border-color: rgba(94, 235, 216, 0.4);
            }}
        """)
        self.input_field.returnPressed.connect(self._send_message)
        
        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(38, 38)
        self.send_btn.setFont(QFont("Segoe UI", 14))
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT.name()};
                color: #000;
                border: none;
                border-radius: 19px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #73f2e1;
            }}
            QPushButton:disabled {{
                background: #444;
            }}
        """)
        self.send_btn.clicked.connect(self._send_message)
        
        # Yeniden boyutlandirma tasina artik gerek yok, varsayilan title bar calisacak
        # self.size_grip = QSizeGrip(input_frame)
        # self.size_grip.setFixedSize(16, 16)
        # self.size_grip.setStyleSheet("background: transparent;")
        
        input_layout.addWidget(self.capture_btn)
        input_layout.addWidget(self.attach_btn)
        input_layout.addWidget(self.rpa_btn)
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        
        # === TYPING INDICATOR ===
        self.typing_label = QLabel("Tenra düşünüyor")
        typing_font = QFont("Segoe UI", 10)
        typing_font.setItalic(True)
        self.typing_label.setFont(typing_font)
        self.typing_label.setStyleSheet("color: #4bd8c4; background: transparent; padding-left: 14px; padding-bottom: 4px;")
        self.typing_label.hide()
        
        # Animasyon sayaci
        self.typing_dots = 0
        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self._update_typing_animation)

        # Assemble
        container_layout.addWidget(header)
        container_layout.addWidget(self.chat_display, 1)
        container_layout.addWidget(self.typing_label)
        container_layout.addWidget(self.preview_frame)
        container_layout.addWidget(input_frame)
        
        main_layout.addWidget(self.container)
        
        # Frameless kapali oldugu icin drop shadow sadece ici karartir, siliyoruz
        # shadow = QGraphicsDropShadowEffect()
        # shadow.setBlurRadius(40)
        # shadow.setColor(QColor(0, 0, 0, 120))
        # shadow.setOffset(0, 10)
        # self.container.setGraphicsEffect(shadow)
        pass
    
    def _add_message(self, text: str, is_user: bool = False, is_tool: bool = False):
        display_text = text.replace("\n", "<br>")
        
        if is_user:
            html = f"""
            <table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 14px;">
              <tr>
                <td width="30%"></td>
                <td align="right">
                  <table cellspacing="0" cellpadding="0" style="background-color: rgba(255, 255, 255, 0.1); border-radius: 16px; border-bottom-right-radius: 4px;">
                    <tr>
                      <td style="padding: 12px 18px; color: #ffffff; font-family: 'Segoe UI', Arial, sans-serif; font-size: 15px;">
                        {display_text}
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
            """
        elif is_tool:
            html = f"""
            <table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 12px;">
              <tr>
                <td align="left">
                  <table cellspacing="0" cellpadding="0" style="background-color: rgba(20, 30, 35, 0.6); border-radius: 12px;">
                    <tr>
                      <td style="border-left: 3px solid #5eeef5; padding: 8px 14px; color: #5eeef5; font-family: Consolas, monospace; font-size: 13px;">
                        {display_text}
                      </td>
                    </tr>
                  </table>
                </td>
                <td width="30%"></td>
              </tr>
            </table>
            """
        else:
            html = f"""
            <table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 16px;">
              <tr>
                <td align="left">
                  <table cellspacing="0" cellpadding="0" style="background-color: rgba(30, 35, 40, 0.85); border-radius: 16px; border-bottom-left-radius: 4px;">
                    <tr>
                      <td style="padding: 14px 20px; color: #e6e6e6; font-family: 'Segoe UI', Arial, sans-serif; font-size: 15px;">
                        {display_text}
                      </td>
                    </tr>
                  </table>
                </td>
                <td width="20%"></td>
              </tr>
            </table>
            """
            
        self.chat_display.append(html)
        
        # Otomatik en alta kaydir
        QTimer.singleShot(50, lambda: self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        ))

    def _capture_screenshot(self):
        # Pencereyi gizle ve sistemin animasyonunu bekle
        self.hide()
        QTimer.singleShot(250, self._perform_screenshot_capture)

    def _select_image(self):
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(self, "Fotoğraf Seç", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            self.latest_screenshot_path = file_path
            pixmap = QPixmap(file_path).scaled(60, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_img.setPixmap(pixmap)
            self.preview_frame.show()
            self.input_field.setFocus()

    def _toggle_rpa_mode(self, checked):
        self.rpa_mode = checked
        if checked:
            self.rpa_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(76, 175, 80, 0.3);
                    color: #fff;
                    border: 1px solid #4CAF50;
                    border-radius: 10px;
                }
            """)
            self._add_message(
                "🤖 <b>Otonom Mod (Smart Vision RPA) Aktif:</b> Tenra artik mouse ve klavyenizi kullanarak bilgisayari kontrol edebilir.<br><br>"
                "<i style='color: #888; font-size: 11px;'>Sistem Notu: Model, koordinat tahmin etmek yerine doğrudan okuduğu metne (click_text_on_screen) tıklayacak şekilde Akıllı OCR moduna geçirildi.</i>", 
                is_tool=True
            )
            self._add_message(
                "Otonom mod acildi. Guvenli calisma icin yikici komutlarda onay penceresi gosterilecektir.",
                is_tool=True,
            )
            self.input_field.setPlaceholderText("Otonom Mod'da ne yapayım?")
        else:
            self.rpa_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.05);
                    color: #aaa;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                }
                QPushButton:hover { background: rgba(255, 255, 255, 0.1); }
            """)
            self._add_message("🤖 <b>Otonom Mod Kapatildi.</b>", is_tool=True)
            self.input_field.setPlaceholderText("Ne yapayım?")

    def _perform_screenshot_capture(self):
        try:
            screen = QGuiApplication.primaryScreen()
            if not screen:
                self.show()
                self._add_message("Ekran bulunamadi, goruntu alinamadi.", is_tool=True)
                return

            screenshot = screen.grabWindow(0)
            
            # Geri goster
            self.show()
            self.raise_()
            self.activateWindow()

            if screenshot.isNull():
                self._add_message("Ekran goruntusu alinamadi.", is_tool=True)
                return

            base_dir = Path(__file__).resolve().parent / "data" / "screenshots"
            base_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = base_dir / f"screen_{stamp}.png"

            if not screenshot.save(str(file_path), "PNG"):
                self._add_message("Ekran goruntusu dosyaya yazilamadi.", is_tool=True)
                return

            self.latest_screenshot_path = str(file_path)
            pixmap = QPixmap(str(file_path)).scaled(60, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_img.setPixmap(pixmap)
            self.preview_frame.show()
            self.input_field.setFocus()
            
        except Exception as err:
            self.show()
            self._add_message(f"Ekran goruntusu hatasi: {err}", is_tool=True)
            
    def _on_anchor_clicked(self, url):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        
        url_str = url if isinstance(url, str) else url.toString()
            
        if url_str == "action://approve_tool":
            if hasattr(self, "_worker") and self._worker and self._worker.isRunning():
                self._worker.tool_approval_result = True
                self._add_message("Islem onaylandi, calistiriliyor...", is_tool=True)
                self.typing_label.setText("Tenra düşünüyor")
                self.typing_timer.start(500)
            return
            
        if url_str == "action://deny_tool":
            if hasattr(self, "_worker") and self._worker and self._worker.isRunning():
                self._worker.tool_approval_result = False
                self._add_message("Islem reddedildi.", is_tool=True)
                self.typing_label.setText("İşlem iptal edildi.")
                QTimer.singleShot(2000, self.typing_label.hide)
            return

        if url_str == "action://approve_pending":
            self._handle_pending_confirmation(True)
            return

        if url_str == "action://deny_pending":
            self._handle_pending_confirmation(False)
            return

        url_obj = QUrl(url_str)
        QDesktopServices.openUrl(url_obj)

    def _update_typing_animation(self):
        self.typing_dots = (self.typing_dots + 1) % 4
        self.typing_label.setText("Tenra düşünüyor" + "." * self.typing_dots)

    def _on_tool_approval_requested(self, func_name: str, params_str: str):
        self.typing_timer.stop()
        self.typing_label.setText("Kullanici onayi bekleniyor...")
        html = f"""
        <table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 12px;">
          <tr><td align="left">
            <div style="background-color: #2b1f1f; border: 1px solid #c93b3b; border-radius: 8px; padding: 12px;">
              <b style="color:#ff6666;">⚠️ ONAY BEKLENİYOR: {func_name}</b><br>
              <pre style="color:#e0e0e0; font-size:11px; margin-top:8px; margin-bottom:12px;">{params_str}</pre>
              <a href="action://approve_tool" style="background:#4CAF50; color:#fff; padding:6px 14px; text-decoration:none; border-radius:4px; font-weight:bold; margin-right:10px;">✅ İzin Ver</a>
              <a href="action://deny_tool" style="background:#F44336; color:#fff; padding:6px 14px; text-decoration:none; border-radius:4px; font-weight:bold;">❌ Reddet</a>
            </div>
          </td></tr>
        </table>
        """
        self.chat_display.append(html)
        QTimer.singleShot(50, lambda: self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        ))

    def _handle_pending_confirmation(self, approved: bool):
        pending = getattr(self, "_pending_action", None)
        if not pending:
            self._add_message("Onay bekleyen bir islem yok.", is_tool=True)
            return

        if not approved:
            self._pending_action = None
            self._add_message("Islem iptal edildi.", is_tool=True)
            return

        action_type = pending.get("type")
        executor = pending.get("executor")
        params = pending.get("params", {})
        self._pending_action = None

        if action_type == "delete" and executor:
            self._add_message("İşlem başlatıldı, arka planda aranıyor...", is_tool=True)
            self._action_worker = SimpleActionWorker(action_type, executor, params)
            self._action_worker.action_finished.connect(self._on_simple_action_finished)
            self._action_worker.start()
            return

        self._add_message("Bekleyen islem formati gecersiz.", is_tool=True)
        
    def _on_simple_action_finished(self, func_name: str, message: str):
        self._add_message(f"⚡ <b>{func_name}</b> — {message}", is_tool=True)
        
    def _open_preview_image(self):
        if self.latest_screenshot_path:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            url = QUrl.fromLocalFile(self.latest_screenshot_path)
            QDesktopServices.openUrl(url)
        
    def _clear_screenshot(self):
        self.latest_screenshot_path = None
        self.preview_frame.hide()
        self.input_field.setFocus()

    def _request_delete_confirmation(self, target: str, executor):
        safe_target = target.replace("<", "&lt;").replace(">", "&gt;")
        self._pending_action = {
            "type": "delete",
            "executor": executor,
            "params": {"path": target},
        }
        self._add_message(
            (
                f"Masaüstünde '<b>{safe_target}</b>' hedefini çöp kutusuna taşımak istiyorum. "
                "Onaylıyor musun?<br/><br/>"
                "<a href='action://approve_pending' style='color:#4bd8c4; text-decoration:none; font-weight:bold; font-size:14px;'>✅ EVET</a>"
                "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                "<a href='action://deny_pending' style='color:#ff6666; text-decoration:none; font-weight:bold; font-size:14px;'>❌ HAYIR</a>"
            ),
            is_tool=True,
        )
    
    def _send_message(self):
        text = self.input_field.text().strip()
        if not text and not self.latest_screenshot_path:
            return

        # Handle simple yes/no confirmations before starting worker
        normalized = text.lower().strip()
        if normalized in {"evet", "eet", "evt", "yes", "onay", "tamam"} and self._pending_action:
            self._add_message(text, is_user=True)
            self._handle_pending_confirmation(True)
            self.input_field.clear()
            self.input_field.setFocus()
            return
        if normalized in {"hayir", "hayır", "iptal", "vazgec", "vazgeç", "no"} and self._pending_action:
            self._add_message(text, is_user=True)
            self._handle_pending_confirmation(False)
            self.input_field.clear()
            self.input_field.setFocus()
            return
        
        display_html = text
        if self.latest_screenshot_path:
            # Resim eklentisini mesaja görsel olarak dahil et ve tiklanabilir yap
            img_uri = f"file:///{self.latest_screenshot_path.replace(chr(92), '/')}"
            img_html = f"<a href='{img_uri}'><img src='{img_uri}' width='260' style='border-radius:10px;'></a><br><br>"
            display_html = img_html + text
            
        self._add_message(display_html, is_user=True)
        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.capture_btn.setEnabled(False)
        self.rpa_btn.setEnabled(False)
        self.preview_close_btn.setEnabled(False)
        self.status_dot.setStyleSheet("QLabel { color: #ff6644; background: transparent; border: none; }")
        
        # Hafizaya (Memory) mesaji ekle
        self.chat_history.append({"role": "user", "content": text})
        
        # Düşünüyor animasyonu başlat
        self.typing_label.show()
        self.typing_timer.start(500)

        # Arkaplanda LLM çalıştır
        self._worker = LLMWorker(text, screenshot_path=self.latest_screenshot_path, chat_history=self.chat_history, rpa_mode=self.rpa_mode)
        self._worker.response_ready.connect(self._on_response)
        self._worker.tool_executed.connect(self._on_tool_executed)
        self._worker.tool_approval_requested.connect(self._on_tool_approval_requested)
        self._worker.tool_started.connect(self._on_tool_started)
        self._worker.start()
        
        # Gonderildikten sonra attachmenti temizle
        self.preview_frame.hide()
        self.latest_screenshot_path = None
    
    def _on_tool_executed(self, func_name: str, result: str):
        self._add_message(f"⚡ <b>{func_name}</b> — {result}", is_tool=True)
    
    def _on_tool_started(self, func_name: str):
        human_readable = {
            "web_search": "İnternette araştırıyor",
            "browse_website": "Web sitesini okuyor",
            "execute_python": "Python kodunu çalıştırıyor",
            "read_file": "Dosyayı inceliyor",
            "patch": "Kodu güncelliyor",
            "search_files": "Dosyaları tarıyor",
            "run_command": "Sistem komutu çalıştırıyor",
            "click_screen": "Ekrana tıklıyor",
            "click_text_on_screen": "Ekrandaki metne tıklıyor",
            "click_element_by_image": "Görsel öğeye tıklıyor",
            "type_text": "Klavyeden yazıyor",
            "list_directory": "Klasörü inceliyor",
            "open_app": "Uygulama açıyor"
        }.get(func_name, f"{func_name} çalıştırılıyor")
        
        self.typing_label.setText(f"⚙️ {human_readable}...")
    
    def _on_response(self, message: str, func_info: str):
        self.typing_timer.stop()
        self.typing_label.hide()

        if isinstance(message, str) and message.startswith("__CONFIRM_DELETE__"):
            target = message.replace("__CONFIRM_DELETE__", "", 1)
            from core.function_executor import executor
            self._request_delete_confirmation(target, executor)
            self.input_field.setEnabled(True)
            self.send_btn.setEnabled(True)
            self.capture_btn.setEnabled(True)
            self.rpa_btn.setEnabled(True)
            self.preview_close_btn.setEnabled(True)
            self.input_field.setFocus()
            self.status_dot.setStyleSheet(f"QLabel {{ color: {Colors.ACCENT.name()}; background: transparent; border: none; }}")
            return

        if isinstance(message, str) and message == "action://approve_pending":
            self._handle_pending_confirmation(True)
            self.input_field.setEnabled(True)
            self.send_btn.setEnabled(True)
            self.capture_btn.setEnabled(True)
            self.rpa_btn.setEnabled(True)
            self.preview_close_btn.setEnabled(True)
            self.input_field.setFocus()
            self.status_dot.setStyleSheet(f"QLabel {{ color: {Colors.ACCENT.name()}; background: transparent; border: none; }}")
            return

        if isinstance(message, str) and message == "action://deny_pending":
            self._handle_pending_confirmation(False)
            self.input_field.setEnabled(True)
            self.send_btn.setEnabled(True)
            self.capture_btn.setEnabled(True)
            self.rpa_btn.setEnabled(True)
            self.preview_close_btn.setEnabled(True)
            self.input_field.setFocus()
            self.status_dot.setStyleSheet(f"QLabel {{ color: {Colors.ACCENT.name()}; background: transparent; border: none; }}")
            return
        
        # Hafizaya (Memory) cevabi ekle
        self.chat_history.append({"role": "assistant", "content": message})
        
        self._add_message(message)
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.capture_btn.setEnabled(True)
        self.rpa_btn.setEnabled(True)
        self.preview_close_btn.setEnabled(True)
        self.latest_screenshot_path = None # islem bitince sifirla
        self.input_field.setFocus()
        self.status_dot.setStyleSheet(f"QLabel {{ color: {Colors.ACCENT.name()}; background: transparent; border: none; }}")
    
    # Window dragging
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 52:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
    
    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
    
    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # QTextBrowser kendi width ve scroll islerini hallettigi icin
        # widget maksimum width ayarlamalarina artik gerek kalmadi.
        pass
    
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.hide()


# ═══════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════
class TenraApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setFont(QFont("Segoe UI", 10))
        
        # Floating widget (her zaman görünür)
        self.widget = FloatingWidget()
        self.widget.clicked.connect(self._toggle_chat)
        
        # Chat window (başta gizli)
        self.chat = ChatWindow()
        
    def _toggle_chat(self):
        if self.chat.isVisible():
            self.chat.hide()
        else:
            self.chat.show()
            self.chat.input_field.setFocus()
    
    def run(self):
        self.widget.show()
        
        # Modelleri arkaplanda yükle
        from threading import Thread
        def preload():
            try:
                import requests
                from config import OLLAMA_URL, RESPONDER_MODEL

                requests.post(
                    f"{OLLAMA_URL}/generate",
                    json={
                        "model": RESPONDER_MODEL,
                        "prompt": "merhaba",
                        "stream": False,
                        "keep_alive": "30m",
                        "options": {"num_predict": 1},
                    },
                    timeout=60,
                )
            except Exception as e:
                print(f"[Tenra] Model preload hatası: {e}")
        
        Thread(target=preload, daemon=True).start()
        
        print("[Tenra] Floating widget aktif. Logoya tiklayarak sohbeti acin.")
        print("[Tenra] ESC ile sohbeti kapatin.")
        
        sys.exit(self.app.exec())


def check_and_install_dependencies():
    """Tenra baslatilmadan once gerekli modullerin kurulu olup olmadigini kontrol eder, yoksa kurar."""
    print("[+] Tenra V5: Bagimliliklar kontrol ediliyor...")
    import subprocess
    import sys
    
    required = {
        "PySide6": "PySide6",
        "requests": "requests",
        "pyautogui": "pyautogui",
        "send2trash": "send2trash",
        "duckduckgo_search": "duckduckgo-search",
        "bs4": "beautifulsoup4",
        "PIL": "Pillow",
        "pytesseract": "pytesseract"
    }
    
    missing = []
    for module_name, pip_name in required.items():
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pip_name)
            
    if missing:
        print(f"[*] Eksik kutuphaneler tespit edildi: {', '.join(missing)}")
        print("[*] Otomatik olarak kuruluyor, lutfen bekleyin...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("[+] Kutuphaneler basariyla kuruldu! Lutfen uygulamayi yeniden baslatin.")
            sys.exit(0)
        except Exception as e:
            print(f"[-] Kutuphane kurulum hatasi: {e}")
            print("[-] Lutfen terminalden 'pip install -r requirements.txt' komutunu girin.")
            sys.exit(1)

if __name__ == "__main__":
    check_and_install_dependencies()
    tenra = TenraApp()
    tenra.run()
