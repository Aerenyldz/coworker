"""
Tenra V5 — Floating Widget + Chat Window
Copilot tarzı: Ekranda her zaman küçük bir logo, tıklayınca chat açılır.
"""

import sys
import os
import warnings
warnings.simplefilter("ignore")

from PySide6.QtCore import Qt, QPoint, QSize, QTimer, Signal, QThread, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QGraphicsDropShadowEffect, QSizePolicy
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient,
    QIcon, QPixmap, QCursor, QKeyEvent
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
# CHAT MESSAGE WIDGET
# ═══════════════════════════════════════════════
class MessageBubble(QFrame):
    def __init__(self, text: str, is_user: bool = False, is_tool: bool = False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        label.setFont(QFont("Segoe UI", 10))
        
        if is_user:
            label.setStyleSheet(f"color: {Colors.TEXT.name()}; background: transparent;")
            self.setStyleSheet(f"""
                QFrame {{
                    background: rgba(255,255,255,0.06);
                    border-radius: 14px;
                    border-bottom-right-radius: 4px;
                }}
            """)
            layout.setAlignment(Qt.AlignRight)
        elif is_tool:
            label.setFont(QFont("Consolas", 9))
            label.setStyleSheet(f"color: {Colors.ACCENT.name()};")
            self.setStyleSheet(f"""
                QFrame {{
                    background: rgba(94, 235, 216, 0.05);
                    border: 1px solid rgba(94, 235, 216, 0.15);
                    border-radius: 8px;
                }}
            """)
        else:
            label.setStyleSheet(f"color: {Colors.TEXT.name()}; background: transparent;")
            self.setStyleSheet("QFrame { background: transparent; }")
        
        layout.addWidget(label)


# ═══════════════════════════════════════════════
# LLM WORKER THREAD
# ═══════════════════════════════════════════════
class LLMWorker(QThread):
    """Arkaplanda LLM çağrısı yapar (GUI donmasın diye)."""
    response_ready = Signal(str, str)  # (message, func_info)
    tool_executed = Signal(str, str)   # (func_name, result)
    
    def __init__(self, user_input: str):
        super().__init__()
        self.user_input = user_input
    
    def run(self):
        try:
            from core.llm import route_query
            from core.function_executor import executor
            import requests
            from config import RESPONDER_MODEL, OLLAMA_URL
            
            # 1. Router — kullanıcının ne istediğini anla
            func_name, params = route_query(self.user_input)
            
            # 2. Eğer fonksiyon çağrısı varsa çalıştır
            func_result = None
            if func_name not in ("thinking", "nonthinking"):
                func_result = executor.execute(func_name, params)
                self.tool_executed.emit(
                    func_name, 
                    func_result.get("message", "")
                )
            
            # 3. Responder LLM'e gönder
            system_msg = "Sen Tenra'sın — kullanıcının bilgisayarında çalışan Türkçe yapay zeka asistanısın. Kısa ve net cevap ver."
            
            messages = [{"role": "system", "content": system_msg}]
            
            if func_result and func_result.get("success"):
                context = f"Kullanıcı istedi: {self.user_input}\nÇalıştırılan fonksiyon: {func_name}\nSonuç: {func_result.get('message', '')}"
                if func_result.get("data"):
                    context += f"\nVeri: {str(func_result['data'])[:500]}"
                messages.append({"role": "user", "content": context})
            else:
                messages.append({"role": "user", "content": self.user_input})
            
            # Ollama'ya sor
            response = requests.post(
                f"{OLLAMA_URL}/chat",
                json={
                    "model": RESPONDER_MODEL,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.7}
                },
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                reply = data.get("message", {}).get("content", "Cevap alınamadı.")
                # Qwen3 thinking tags temizle
                import re
                reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL).strip()
                self.response_ready.emit(reply, func_name if func_name not in ("thinking", "nonthinking") else "")
            else:
                self.response_ready.emit("⚠️ Ollama'dan cevap alınamadı.", "")
                
        except Exception as e:
            self.response_ready.emit(f"⚠️ Hata: {str(e)}", "")


# ═══════════════════════════════════════════════
# CHAT WINDOW (Ana Sohbet Penceresi)
# ═══════════════════════════════════════════════
class ChatWindow(QMainWindow):
    """Tenra sohbet penceresi — dark, glassmorphism, premium."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tenra")
        self.setMinimumSize(480, 650)
        self.resize(500, 700)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self._drag_pos = None
        self._worker = None
        
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
                background: rgba(12, 12, 18, 245);
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
        logo_label.setFont(QFont("Consolas", 18, QFont.Bold))
        logo_label.setStyleSheet(f"color: {Colors.ACCENT.name()}; background: transparent;")
        logo_label.setFixedWidth(30)
        
        title_label = QLabel("TENRA")
        title_label.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title_label.setStyleSheet(f"color: {Colors.TEXT.name()}; background: transparent;")
        
        version_label = QLabel("v5")
        version_label.setFont(QFont("Segoe UI", 9))
        version_label.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; background: transparent;")
        
        # Status dot
        self.status_dot = QLabel("●")
        self.status_dot.setFont(QFont("Segoe UI", 8))
        self.status_dot.setStyleSheet(f"color: {Colors.ACCENT.name()}; background: transparent;")
        
        status_text = QLabel("Aktif")
        status_text.setFont(QFont("Segoe UI", 9))
        status_text.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; background: transparent;")
        
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
        
        # === CHAT AREA ===
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 5px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,0.1); border-radius: 2px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(16, 16, 16, 16)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch()
        
        self.scroll_area.setWidget(self.chat_container)
        
        # Welcome message
        self._add_message("Merhaba. Ben <b>Tenra</b>. Bilgisayarınızı yönetebilir, dosya işlemleri yapabilir, web'de arama yapabilirim. Bir şey sorun veya bir görev verin.", is_user=False)
        
        # === INPUT AREA ===
        input_frame = QFrame()
        input_frame.setStyleSheet("QFrame { background: rgba(0,0,0,0.3); border-top: 1px solid rgba(255,255,255,0.06); border-radius: 0; border-bottom-left-radius: 16px; border-bottom-right-radius: 16px; }")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 10, 12, 10)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ne yapayım?")
        self.input_field.setFont(QFont("Segoe UI", 10))
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
                padding: 10px 14px;
                color: {Colors.TEXT.name()};
            }}
            QLineEdit:focus {{
                border-color: rgba(94, 235, 216, 0.3);
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
                border-radius: 10px;
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
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        
        # Assemble
        container_layout.addWidget(header)
        container_layout.addWidget(self.scroll_area, 1)
        container_layout.addWidget(input_frame)
        
        main_layout.addWidget(self.container)
        
        # Shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 10)
        self.container.setGraphicsEffect(shadow)
    
    def _add_message(self, text: str, is_user: bool = False, is_tool: bool = False):
        bubble = MessageBubble(text, is_user, is_tool)
        # Insert before the stretch
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        
        # Scroll to bottom
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))
    
    def _send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        
        self._add_message(text, is_user=True)
        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.status_dot.setStyleSheet("color: #ff6644; background: transparent;")
        
        # Arkaplanda LLM çalıştır
        self._worker = LLMWorker(text)
        self._worker.tool_executed.connect(self._on_tool_executed)
        self._worker.response_ready.connect(self._on_response)
        self._worker.start()
    
    def _on_tool_executed(self, func_name: str, result: str):
        self._add_message(f"⚡ <b>{func_name}</b> — {result}", is_tool=True)
    
    def _on_response(self, message: str, func_info: str):
        self._add_message(message)
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input_field.setFocus()
        self.status_dot.setStyleSheet(f"color: {Colors.ACCENT.name()}; background: transparent;")
    
    # Window dragging
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 52:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
    
    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
    
    def mouseReleaseEvent(self, event):
        self._drag_pos = None
    
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
                from core.llm import preload_models
                preload_models()
            except Exception as e:
                print(f"[Tenra] Model preload hatası: {e}")
        
        Thread(target=preload, daemon=True).start()
        
        print("[Tenra] Floating widget aktif. Logoya tiklayarak sohbeti acin.")
        print("[Tenra] ESC ile sohbeti kapatin.")
        
        sys.exit(self.app.exec())


if __name__ == "__main__":
    tenra = TenraApp()
    tenra.run()
