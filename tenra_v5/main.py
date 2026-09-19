"""
Tenra V7 — Antigravity Tarzı Agent Studio
Carbon/Slate tema, terminal kartları, araç kartları, custom header.
"""

import sys
import os
import re
import warnings
from datetime import datetime
from pathlib import Path
warnings.simplefilter("ignore")

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["QT_LOGGING_RULES"] = "qt.qpa.window=false"

from PySide6.QtCore import (
    Qt, QPoint, QSize, QTimer, Signal, QThread,
    QPropertyAnimation, QEasingCurve, QRect, QUrl
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QGraphicsDropShadowEffect, QSizePolicy, QSizeGrip, QTextBrowser,
    QFileDialog, QProgressBar
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient,
    QIcon, QPixmap, QCursor, QKeyEvent, QGuiApplication, QScreen,
    QDesktopServices
)


# ═══════════════════════════════════════════════
# CARBON / SLATE RENK PALETİ (Antigravity Tarzı)
# ═══════════════════════════════════════════════
class Colors:
    # Ana arka planlar
    BG_DARK    = QColor(13, 13, 13)       # #0d0d0d — neredeyse siyah
    BG_PANEL   = QColor(16, 19, 24)       # #101318 — koyu grafit
    BG_CARD    = QColor(22, 27, 34)       # #161b22 — kart arka planı
    BG_CARD2   = QColor(30, 35, 44)       # #1e232c — hafif açık kart
    BG_INPUT   = QColor(21, 25, 32)       # #151920 — input alanı
    BG_HEADER  = QColor(18, 21, 28)       # #12151c — header

    # Vurgu renkleri
    ACCENT       = QColor(0, 212, 255)    # #00d4ff — neon cyan (ana)
    ACCENT_DIM   = QColor(0, 212, 255, 40)
    ACCENT_GREEN = QColor(63, 185, 80)    # #3fb950 — başarı
    ACCENT_RED   = QColor(248, 81, 73)    # #f85149 — hata
    ACCENT_YELLOW= QColor(210, 153, 34)   # #d29922 — uyarı
    ACCENT_PURPLE= QColor(188, 140, 255)  # #bc8cff — araç
    ACCENT_BLUE  = QColor(79, 140, 201)   # #4f8cc9 — link

    # Metin
    TEXT         = QColor(230, 237, 243)  # #e6edf3
    TEXT_MUTED   = QColor(125, 133, 144)  # #7d8590
    TEXT_DIM     = QColor(72, 80, 92)     # #48505c

    # Kenarlıklar
    BORDER       = QColor(48, 54, 61)     # #30363d
    BORDER_LIGHT = QColor(63, 70, 80)     # #3f4650

    # Özel
    TERMINAL_BG  = QColor(10, 12, 16)     # #0a0c10 — terminal arka plan
    DIFF_ADD_BG  = QColor(20, 60, 30)     # koyu yeşil diff satırı
    DIFF_DEL_BG  = QColor(60, 20, 20)     # koyu kırmızı diff satırı
    USER_BG      = QColor(0, 212, 255, 18)


# ═══════════════════════════════════════════════
# MARKDOWN → HTML (Antigravity tarzı kod blokları)
# ═══════════════════════════════════════════════
def markdown_to_html(text: str) -> str:
    import html as html_mod
    import re

    escaped = html_mod.escape(text)

    code_blocks = []
    def save_code_block(match):
        lang = match.group(1) or ""
        code = match.group(2)
        lang_label = f'<span style="color:#7d8590;font-size:10px;float:right;">{html_mod.escape(lang)}</span>' if lang else ""
        ph = f"___CODEBLOCK_{len(code_blocks)}___"
        block = (
            f'<div style="background:{Colors.TERMINAL_BG.name()};border:1px solid {Colors.BORDER.name()};'
            f'border-radius:8px;margin:10px 0;overflow:hidden;">'
            f'<div style="padding:6px 14px 4px;border-bottom:1px solid {Colors.BORDER.name()};'
            f'background:{Colors.BG_CARD.name()};">{lang_label}'
            f'<span style="color:{Colors.ACCENT_PURPLE.name()};font-size:10px;font-family:Consolas;">&#x25CF; kod</span>'
            f'</div>'
            f'<pre style="font-family:Consolas,monospace;font-size:12px;color:#c9d1d9;'
            f'padding:12px 16px;margin:0;white-space:pre-wrap;">{code.strip()}</pre>'
            f'</div>'
        )
        code_blocks.append(block)
        return ph

    processed = re.sub(r"```([a-zA-Z0-9_-]*)\n(.*?)\n```", save_code_block, escaped, flags=re.DOTALL)

    inline_codes = []
    def save_inline(match):
        code = match.group(1)
        ph = f"___INLINE_{len(inline_codes)}___"
        inline_codes.append(
            f'<code style="font-family:Consolas,monospace;background:{Colors.BG_CARD2.name()};'
            f'color:{Colors.ACCENT_PURPLE.name()};padding:2px 6px;border-radius:4px;font-size:12px;">'
            f'{code}</code>'
        )
        return ph

    processed = re.sub(r"`([^`\n]+)`", save_inline, processed)
    processed = re.sub(r"\*\*([^\*]+)\*\*", r"<b>\1</b>", processed)
    processed = re.sub(r"\*([^\*]+)\*", r"<i>\1</i>", processed)

    lines = processed.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)[-\*]\s+(.+)$", line)
        if m:
            lines[i] = f'{m.group(1)}<span style="color:{Colors.ACCENT.name()};">▸</span> {m.group(2)}'
    processed = "\n".join(lines)

    processed = processed.replace("\n", "<br>")

    for idx, block in enumerate(code_blocks):
        processed = processed.replace(f"___CODEBLOCK_{idx}___", block)
    for idx, code in enumerate(inline_codes):
        processed = processed.replace(f"___INLINE_{idx}___", code)

    return processed


def make_tool_card_html(func_name: str, result: str, success: bool = True) -> str:
    """Araç çalıştırma kartı HTML'i üretir."""
    icons = {
        "web_search": "🔍", "browse_website": "🌐", "run_command": "⚡",
        "create_file": "📄", "write_file": "📝", "patch": "🔧",
        "read_file": "📖", "delete_file": "🗑", "move_to_trash": "🗑",
        "execute_python": "🐍", "open_app": "🚀", "open_url": "🔗",
        "search_files": "🔎", "list_directory": "📁", "list_desktop": "🖥",
        "create_folder": "📁", "get_system_info": "💻",
    }
    icon = icons.get(func_name, "⚙️")
    status_color = Colors.ACCENT_GREEN.name() if success else Colors.ACCENT_RED.name()
    status_icon = "✓" if success else "✗"
    border_color = Colors.ACCENT_GREEN.name() if success else Colors.ACCENT_RED.name()

    import html as html_mod
    safe_result = html_mod.escape(str(result))

    return (
        f'<div style="background:{Colors.BG_CARD.name()};border:1px solid {Colors.BORDER.name()};'
        f'border-left:3px solid {border_color};border-radius:8px;padding:10px 14px;margin:6px 0;">'
        f'<div style="display:flex;align-items:center;margin-bottom:4px;">'
        f'<span style="font-size:13px;margin-right:8px;">{icon}</span>'
        f'<span style="color:{Colors.ACCENT_PURPLE.name()};font-family:Consolas;font-size:12px;font-weight:bold;">{func_name}</span>'
        f'<span style="margin-left:auto;color:{status_color};font-size:11px;font-weight:bold;">{status_icon}</span>'
        f'</div>'
        f'<div style="color:{Colors.TEXT_MUTED.name()};font-size:12px;font-family:Consolas;">{safe_result[:300]}</div>'
        f'</div>'
    )


def make_terminal_card_html(command: str, stdout: str, stderr: str, exit_code: int) -> str:
    """Terminal komutu çıktısı için özel kart."""
    import html as html_mod
    safe_cmd = html_mod.escape(command)
    safe_out = html_mod.escape(stdout[:2000]) if stdout else ""
    safe_err = html_mod.escape(stderr[:500]) if stderr else ""
    exit_ok = exit_code == 0
    exit_color = Colors.ACCENT_GREEN.name() if exit_ok else Colors.ACCENT_RED.name()
    exit_icon = "✓" if exit_ok else "✗"

    output_html = ""
    if safe_out:
        output_html += f'<pre style="color:#c9d1d9;margin:0;padding:0;white-space:pre-wrap;font-size:11px;">{safe_out}</pre>'
    if safe_err:
        output_html += f'<pre style="color:{Colors.ACCENT_RED.name()};margin:0;padding:0;white-space:pre-wrap;font-size:11px;">{safe_err}</pre>'
    if not safe_out and not safe_err:
        output_html = f'<span style="color:{Colors.TEXT_DIM.name()};font-size:11px;">(çıktı yok)</span>'

    return (
        f'<div style="background:{Colors.TERMINAL_BG.name()};border:1px solid {Colors.BORDER.name()};'
        f'border-radius:8px;margin:8px 0;overflow:hidden;">'
        # Terminal header bar
        f'<div style="padding:7px 14px;background:{Colors.BG_CARD.name()};border-bottom:1px solid {Colors.BORDER.name()};'
        f'display:flex;align-items:center;">'
        f'<span style="color:{Colors.TEXT_DIM.name()};font-family:Consolas;font-size:10px;">⚡ Terminal</span>'
        f'<span style="margin-left:10px;color:{Colors.ACCENT.name()};font-family:Consolas;font-size:11px;">$ {safe_cmd}</span>'
        f'<span style="margin-left:auto;color:{exit_color};font-size:11px;font-weight:bold;">exit {exit_code} {exit_icon}</span>'
        f'</div>'
        # Output body
        f'<div style="padding:10px 14px;max-height:200px;overflow-y:auto;">{output_html}</div>'
        f'</div>'
    )


def make_diff_card_html(filename: str, diff_text: str) -> str:
    """Dosya değişikliği için diff kartı."""
    import html as html_mod
    lines = diff_text.split("\n")
    rows = ""
    adds = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    dels = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))

    for line in lines[:40]:
        safe = html_mod.escape(line)
        if line.startswith("+") and not line.startswith("+++"):
            rows += f'<div style="background:{Colors.DIFF_ADD_BG.name()};color:{Colors.ACCENT_GREEN.name()};font-family:Consolas;font-size:11px;padding:1px 10px;">{safe}</div>'
        elif line.startswith("-") and not line.startswith("---"):
            rows += f'<div style="background:{Colors.DIFF_DEL_BG.name()};color:{Colors.ACCENT_RED.name()};font-family:Consolas;font-size:11px;padding:1px 10px;">{safe}</div>'
        elif line.startswith("@@"):
            rows += f'<div style="color:{Colors.ACCENT_BLUE.name()};font-family:Consolas;font-size:10px;padding:1px 10px;">{safe}</div>'
        else:
            rows += f'<div style="color:{Colors.TEXT_MUTED.name()};font-family:Consolas;font-size:11px;padding:1px 10px;">{safe}</div>'

    safe_fname = html_mod.escape(filename)
    return (
        f'<div style="background:{Colors.BG_CARD.name()};border:1px solid {Colors.BORDER.name()};'
        f'border-radius:8px;margin:8px 0;overflow:hidden;">'
        f'<div style="padding:7px 14px;background:{Colors.BG_CARD2.name()};border-bottom:1px solid {Colors.BORDER.name()};">'
        f'<span style="color:#e6edf3;font-family:Consolas;font-size:11px;">📄 {safe_fname}</span>'
        f'<span style="margin-left:12px;color:{Colors.ACCENT_GREEN.name()};font-size:10px;">+{adds}</span>'
        f'<span style="margin-left:6px;color:{Colors.ACCENT_RED.name()};font-size:10px;">-{dels}</span>'
        f'</div>'
        f'<div>{rows}</div>'
        f'</div>'
    )


# ═══════════════════════════════════════════════
# FLOATING WIDGET — Ekranda Yüzen Pill (Redesign)
# ═══════════════════════════════════════════════
class FloatingWidget(QWidget):
    """Ekranda her zaman üstte duran, sürüklenebilir Tenra logosu."""
    clicked = Signal()
    close_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(78, 40)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 100, screen.height() - 120)

        self._drag_pos = None
        self._hover = False
        self._close_hover = False
        self._pulse = 0.0
        self._pulse_dir = 1

        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._tick)
        self._pulse_timer.start(40)

    def _tick(self):
        self._pulse += 0.03 * self._pulse_dir
        if self._pulse >= 1.0:
            self._pulse_dir = -1
        elif self._pulse <= 0.0:
            self._pulse_dir = 1
        self.update()

    def _get_close_rect(self) -> QRect:
        return QRect(54, 10, 18, 20)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Glow aura
        if self._hover:
            glow = QColor(0, 212, 255, int(40 * self._pulse))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(0, 0, 78, 40, 20, 20)

        # Pill şekli
        grad = QLinearGradient(0, 0, 78, 40)
        grad.setColorAt(0, QColor(22, 27, 34))
        grad.setColorAt(1, QColor(16, 19, 24))
        p.setBrush(QBrush(grad))
        border_alpha = int(120 + 100 * self._pulse)
        p.setPen(QPen(QColor(0, 212, 255, border_alpha), 1.5))
        p.drawRoundedRect(2, 2, 74, 36, 18, 18)

        # Durum noktası (aktif = yeşil)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(63, 185, 80, int(200 + 55 * self._pulse)))
        p.drawEllipse(10, 15, 7, 7)

        # "T" yazısı
        p.setPen(QPen(QColor(0, 212, 255)))
        font = QFont("Consolas", 13, QFont.Bold)
        p.setFont(font)
        p.drawText(QRect(20, 2, 30, 36), Qt.AlignCenter, "T")

        # Hover durumunda X kapatma butonu
        if self._hover:
            close_rect = self._get_close_rect()
            if self._close_hover:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(248, 81, 73, 180))
                p.drawEllipse(close_rect.center(), 8, 8)
                p.setPen(QPen(QColor(255, 255, 255)))
            else:
                p.setPen(QPen(QColor(125, 133, 144)))
            
            font_x = QFont("Segoe UI", 10, QFont.Bold)
            p.setFont(font_x)
            p.drawText(close_rect, Qt.AlignCenter, "✕")

    def enterEvent(self, event):
        self._hover = True
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self._close_hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            if self._hover and self._get_close_rect().contains(pos):
                self.close_requested.emit()
                return
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        was_close = self._close_hover
        self._close_hover = self._get_close_rect().contains(pos)
        if was_close != self._close_hover:
            self.update()

        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._drag_pos:
                moved = (event.globalPosition().toPoint() - self.frameGeometry().topLeft() - self._drag_pos).manhattanLength()
                if moved < 6:
                    pos = event.position().toPoint()
                    if self._get_close_rect().contains(pos):
                        self.close_requested.emit()
                    else:
                        self.clicked.emit()
            self._drag_pos = None


# ═══════════════════════════════════════════════
# SNIPPING TOOL — DPI & Multi-Monitor Fix
# ═══════════════════════════════════════════════
class SnippingWidget(QWidget):
    screenshot_taken = Signal(QPixmap)
    closed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setCursor(Qt.CrossCursor)

        cursor_pos = QCursor.pos()
        active_screen = QApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
        screen_geo = active_screen.geometry()
        self.setGeometry(screen_geo)

        dpr = active_screen.devicePixelRatio()
        self.original_pixmap = active_screen.grabWindow(0)
        self._dpr = dpr

        self.begin = QPoint()
        self.end = QPoint()
        self.is_drawing = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.original_pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 130))

        if not self.begin.isNull() and not self.end.isNull():
            rect = QRect(self.begin, self.end).normalized()
            p.setCompositionMode(QPainter.CompositionMode_Clear)
            p.fillRect(rect, Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.setPen(QPen(QColor(0, 212, 255), 2))
            p.drawRect(rect)
            size_text = f"{rect.width()} × {rect.height()}"
            p.setPen(QPen(QColor(255, 255, 255, 200)))
            font = p.font()
            font.setPointSize(10)
            p.setFont(font)
            text_y = rect.y() - 6 if rect.y() > 20 else rect.bottom() + 16
            p.drawText(rect.x() + 4, text_y, size_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.begin = event.position().toPoint()
            self.end = self.begin
            self.is_drawing = True
            self.update()
        elif event.button() == Qt.RightButton:
            self.closed.emit()
            self.close()

    def mouseMoveEvent(self, event):
        if self.is_drawing:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.end = event.position().toPoint()
            self.is_drawing = False
            rect = QRect(self.begin, self.end).normalized()
            if rect.width() > 10 and rect.height() > 10:
                dpr = self._dpr
                phys = QRect(int(rect.x() * dpr), int(rect.y() * dpr),
                             int(rect.width() * dpr), int(rect.height() * dpr))
                cropped = self.original_pixmap.copy(phys)
                cropped.setDevicePixelRatio(1.0)
                self.screenshot_taken.emit(cropped)
            else:
                self.closed.emit()
            self.close()

    def keyPressEvent(self, event):  # Tek tanım — bug düzeltildi
        if event.key() == Qt.Key_Escape:
            self.closed.emit()
            self.close()


# ═══════════════════════════════════════════════
# CLICKABLE LABEL
# ═══════════════════════════════════════════════
class ClickableLabel(QLabel):
    clicked = Signal()
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════
# SIMPLE ACTION WORKER
# ═══════════════════════════════════════════════
class SimpleActionWorker(QThread):
    action_finished = Signal(str, str)

    def __init__(self, action_type, executor, params):
        super().__init__()
        self.action_type = action_type
        self.executor = executor
        self.params = params

    def run(self):
        try:
            if self.action_type == "delete":
                result = self.executor.execute("move_to_trash", self.params)
                self.action_finished.emit("move_to_trash", result.get("message", "İşlem tamamlandı."))
        except Exception as e:
            self.action_finished.emit("Hata", str(e))


# ═══════════════════════════════════════════════
# LLM WORKER THREAD
# ═══════════════════════════════════════════════
class LLMWorker(QThread):
    response_ready         = Signal(str, str)
    tool_executed          = Signal(str, str, bool)  # name, result, success
    tool_approval_requested= Signal(str, str)
    tool_started           = Signal(str)
    terminal_output        = Signal(str, str, str, int)  # cmd, stdout, stderr, exit_code

    def __init__(self, user_input: str, screenshot_path: str | None = None,
                 chat_history: list = None, rpa_mode: bool = False, uncensored: bool = True):
        super().__init__()
        self.rpa_mode = rpa_mode
        self.uncensored = uncensored
        self.user_input = user_input
        self.raw_user_input = user_input
        self.screenshot_path = screenshot_path
        self.chat_history = chat_history or []
        self.tool_approval_result = None

    def _wait_for_approval(self, func_name: str, params: dict) -> bool:
        import json, time
        self.tool_approval_result = None
        self.tool_approval_requested.emit(func_name, json.dumps(params, ensure_ascii=False, indent=2))
        while self.tool_approval_result is None:
            time.sleep(0.1)
        return self.tool_approval_result

    def _extract_quoted_name(self, text: str) -> str:
        match = re.search(r"[\"']([^\"']{2,120})[\"']", text)
        if match:
            return match.group(1).strip()
        m = re.search(r"(?:adli|adında|isimli)\s+([\w\-\. ]{2,80})", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return ""

    def _extract_delete_target(self, text: str) -> str:
        patterns = [
            r"(?:masaustunde|masaüstünde)\s+(.+?)\s+(?:dosyasini|dosyasını|dosyayi|dosyayı|klasoru|klasörü)?\s*sil",
            r"(.+?)\s+(?:dosyasini|dosyasını|dosyayi|dosyayı|klasoru|klasörü)?\s*sil$",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip(" .,:;")
                val = re.sub(r"^(bir|su|şu|o)\s+", "", val, flags=re.IGNORECASE)
                if val:
                    return val
        return ""

    def _run_direct_shortcut(self, executor):
        """Sadece %100 kesin eşleşmeler — gerisi Hermes'e."""
        lower = self.raw_user_input.lower()
        text = self.raw_user_input.strip()

        # URL aç
        if any(word in lower for word in ("ac", "aç", "open")) and "http" in lower:
            url_match = re.search(r"https?://\S+", text, re.IGNORECASE)
            if url_match:
                return "open_url", executor.execute("open_url", {"url": url_match.group(0)})

        # Masaüstü listele
        if "masa" in lower and "liste" in lower:
            return "list_desktop", executor.execute("list_desktop", {})

        # Doğrudan terminal komutu (komut: prefix)
        if lower.startswith("komut:") or lower.startswith("powershell:"):
            raw_cmd = text.split(":", 1)[1].strip() if ":" in text else ""
            if raw_cmd:
                return "run_command", executor.execute("run_command", {"command": raw_cmd})

        return None

    def run(self):
        try:
            from core.function_executor import executor
            executor.approval_callback = self._wait_for_approval
            executor.tool_start_callback = lambda f: self.tool_started.emit(f)

            # Uncensored mod
            executor.uncensored_mode = bool(self.uncensored)

            from core.hermes_agent import (
                run_hermes_tool_loop,
                should_analyze_screenshot,
                get_screenshot_text,
            )

            # Ekran görüntüsü varsa OCR ile zenginleştir — BUG DÜZELTİLDİ
            input_text = self.user_input
            if should_analyze_screenshot(self.user_input, self.screenshot_path):
                self.tool_started.emit("Ekran Analizi")
                extracted_text = get_screenshot_text(self.screenshot_path, self.user_input)
                if extracted_text:
                    effective_q = self.user_input.strip() or "Bu görselde ne var? Detaylı açıkla."
                    input_text = (
                        f"Göz (Vision) modülüm bu fotoğrafı okudu ve şu metinleri/verileri çıkardı:\n\n"
                        f"━━━ GÖRSEL METNİ ━━━\n{extracted_text}\n━━━━━━━━━━━━━━━━━━━\n\n"
                        f"Kullanıcının sorusu/isteği: '{effective_q}'\n\n"
                        f"Türkçe yanıt ver, samimi ve doğrudan konuş."
                    )
                else:
                    self.response_ready.emit("⚠ Görselden metin çıkarılamadı.", "")
                    return
                # input_text screenshot context'ini korur — üzerine yazılmıyor

            # Hızlı kısayollar (sadece %100 kesin)
            shortcut = self._run_direct_shortcut(executor)
            if shortcut:
                sc_name, sc_result = shortcut
                msg = sc_result.get("message", "İşlem tamamlandı.")
                success = sc_result.get("success", True)
                self.tool_executed.emit(sc_name, msg, success)
                self.response_ready.emit(msg, sc_name)
                return

            # Hermes otonom araç döngüsü
            agent_result = run_hermes_tool_loop(
                input_text, executor,
                chat_history=self.chat_history,
                uncensored=self.uncensored
            )

            if not agent_result.get("ok"):
                self.response_ready.emit(f"⚠ {agent_result.get('error', 'Bilinmeyen hata')}", "")
                return

            # Araç sonuçlarını emit et
            for tool_call in agent_result.get("tool_results", []):
                name = tool_call.get("name", "tool")
                result = tool_call.get("result", {})
                success = result.get("success", True)
                msg = result.get("message", "İşlem tamamlandı")

                # Terminal çıktısı özel signal
                if name == "run_command" and isinstance(result.get("data"), dict):
                    d = result["data"]
                    self.terminal_output.emit(
                        d.get("command", ""),
                        d.get("stdout", ""),
                        d.get("stderr", ""),
                        d.get("exit_code", 0)
                    )
                else:
                    self.tool_executed.emit(name, msg, success)

            reply = (agent_result.get("reply") or "").strip()
            self.response_ready.emit(reply or "İşlem tamamlandı.", "")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.response_ready.emit(f"Hata: {str(e)[:300]}", "")


# ═══════════════════════════════════════════════
# CHAT WINDOW — Antigravity Agent Studio Arayüzü
# ═══════════════════════════════════════════════
# ═══════════════════════════════════════════════
# CHAT WINDOW — Antigravity Agent Studio Arayüzü (Yatay / Landscape)
# ═══════════════════════════════════════════════
class ChatWindow(QMainWindow):
    """Tenra V7 — Antigravity tarzı Yatay Agent Studio penceresi."""

    def __init__(self):
        super().__init__()
        self.chat_history = []
        self.rpa_mode = True
        self.uncensored_active = True
        self._pending_action = None
        self.latest_screenshot_path = None
        self._drag_pos = None
        self._worker = None
        self._active_tool = None

        self.setWindowTitle("Tenra — Agent Studio")
        self.setMinimumSize(920, 560)
        self.resize(1060, 640)

        # Tam frameless custom pencere
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._build_ui()
        self._position_window()

    def _position_window(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(
            max(20, (screen.width() - self.width()) // 2),
            max(20, (screen.height() - self.height()) // 2)
        )

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(0)

        # Ana kart wrapper
        self.container = QFrame()
        self.container.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_PANEL.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 14px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 8)
        self.container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── 1. CUSTOM HEADER ────────────────────────────
        self._build_header(container_layout)

        # ── 2. YATAY İKİ BÖLMELİ GÖVDE ───────────────────
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # ── SOL PANEL: SOHBET & AGENT AKIŞI ─────────────
        left_panel = QFrame()
        left_panel.setStyleSheet("background: transparent; border: none;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(False)
        self.chat_display.setOpenLinks(False)
        self.chat_display.anchorClicked.connect(self._on_anchor_clicked)
        self.chat_display.setStyleSheet(f"""
            QTextBrowser {{
                background: transparent;
                border: none;
                padding: 14px 12px;
                color: {Colors.TEXT.name()};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                selection-background-color: {Colors.ACCENT_DIM.name()};
            }}
            QScrollBar:vertical {{
                width: 6px;
                background: transparent;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.BORDER_LIGHT.name()};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.chat_display.setHtml(
            f"<html><body style='background:transparent;margin:0;padding:0;'></body></html>"
        )

        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setFixedHeight(2)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setStyleSheet(f"""
            QProgressBar {{
                background: transparent;
                border: none;
                border-radius: 0;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {Colors.ACCENT.name()},
                    stop:0.5 {Colors.ACCENT_PURPLE.name()},
                    stop:1 {Colors.ACCENT.name()});
            }}
        """)
        self.loading_bar.hide()

        self.tool_label = QLabel()
        self.tool_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.ACCENT.name()};
                font-size: 11px;
                font-family: Consolas, monospace;
                padding: 4px 16px;
                background: transparent;
            }}
        """)
        self.tool_label.hide()

        self._build_preview_bar(left_layout)

        left_layout.addWidget(self.chat_display, 1)
        left_layout.addWidget(self.loading_bar)
        left_layout.addWidget(self.tool_label)
        left_layout.addWidget(self.preview_frame)
        self._build_input_bar(left_layout)

        # ── SAĞ PANEL: ANTIGRAVITY WORKSPACE & CANLI KONSOL ──
        right_panel = QFrame()
        right_panel.setFixedWidth(360)
        right_panel.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_CARD.name()};
                border-left: 1px solid {Colors.BORDER.name()};
                border-bottom-right-radius: 14px;
            }}
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        # Sağ Header: Console başlığı
        console_hdr = QHBoxLayout()
        con_lbl = QLabel("⚡ AGENT WORKSPACE")
        con_lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        con_lbl.setStyleSheet(f"color: {Colors.ACCENT.name()}; border: none; background: transparent;")

        clear_con_btn = QPushButton("🧹")
        clear_con_btn.setToolTip("Konsolu Temizle")
        clear_con_btn.setFixedSize(24, 24)
        clear_con_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_MUTED.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {Colors.BG_CARD2.name()}; color: {Colors.TEXT.name()}; }}
        """)
        clear_con_btn.clicked.connect(self._clear_console)

        console_hdr.addWidget(con_lbl)
        console_hdr.addStretch()
        console_hdr.addWidget(clear_con_btn)
        right_layout.addLayout(console_hdr)

        # Sistem & Model Durum Kartı
        from config import RESPONDER_MODEL, VISION_MODEL, DESKTOP_PATH
        status_box = QFrame()
        status_box.setStyleSheet(f"""
            QFrame {{
                background: {Colors.TERMINAL_BG.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
                padding: 4px;
            }}
        """)
        sb_layout = QVBoxLayout(status_box)
        sb_layout.setContentsMargins(8, 6, 8, 6)
        sb_layout.setSpacing(3)

        sb_m = QLabel(f"🧠 Model: <b>{RESPONDER_MODEL}</b>")
        sb_m.setStyleSheet(f"color: {Colors.TEXT.name()}; font-size: 11px; font-family: Consolas; border: none;")
        sb_v = QLabel(f"👁 Vision: <b>{VISION_MODEL}</b>")
        sb_v.setStyleSheet(f"color: {Colors.ACCENT_PURPLE.name()}; font-size: 11px; font-family: Consolas; border: none;")
        sb_d = QLabel(f"📂 Desktop: {DESKTOP_PATH[:32]}...")
        sb_d.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; font-size: 10px; font-family: Consolas; border: none;")

        sb_layout.addWidget(sb_m)
        sb_layout.addWidget(sb_v)
        sb_layout.addWidget(sb_d)
        right_layout.addWidget(status_box)

        # Canlı Terminal / Event Log Konsolu
        con_title = QLabel("Canlı Komut & Olay Konsolu:")
        con_title.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; font-size: 10px; font-family: Segoe UI; border: none;")
        right_layout.addWidget(con_title)

        self.console_display = QTextBrowser()
        self.console_display.setStyleSheet(f"""
            QTextBrowser {{
                background: {Colors.TERMINAL_BG.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
                padding: 8px;
                color: #c9d1d9;
                font-family: Consolas, monospace;
                font-size: 11px;
            }}
            QScrollBar:vertical {{
                width: 5px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.BORDER.name()};
                border-radius: 2px;
            }}
        """)
        self.console_display.setHtml(
            f"<span style='color:{Colors.TEXT_DIM.name()};'>[Tenra V7 Antigravity Studio başlatıldı. Canlı komut ve araç akışı burada listelenir.]</span><br>"
        )
        right_layout.addWidget(self.console_display, 1)

        # Hızlı İşlem Düğmeleri
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(6)

        btn_desktop = QPushButton("🖥 Masaüstü")
        btn_desktop.setStyleSheet(self._action_btn_style())
        btn_desktop.clicked.connect(lambda: self._quick_prompt("Masaüstündeki dosyaları listele"))

        btn_sys = QPushButton("⚙ Sistem")
        btn_sys.setStyleSheet(self._action_btn_style())
        btn_sys.clicked.connect(lambda: self._quick_prompt("Sistem durumunu ve özetini göster"))

        btn_clear = QPushButton("🗑 Sohbeti Sil")
        btn_clear.setStyleSheet(self._action_btn_style())
        btn_clear.clicked.connect(self._clear_chat_history)

        actions_layout.addWidget(btn_desktop)
        actions_layout.addWidget(btn_sys)
        actions_layout.addWidget(btn_clear)
        right_layout.addLayout(actions_layout)

        # Birleştir
        body_layout.addWidget(left_panel, 1)
        body_layout.addWidget(right_panel)
        container_layout.addWidget(body_widget, 1)

        outer.addWidget(self.container)

        # Welcome message
        self._add_assistant_message(
            "**Tenra V7 — Antigravity Studio** hazır.\n\n"
            "• **Görsel & OCR Modülü:** `moondream:latest` aktif — ekran görüntüsü ve sipariş kodlarını doğrudan okur.\n"
            "• **Çıktı Sınırı:** Genişletildi — uzun teknik analizler artık kesilmeden tamamlanır.\n"
            "• **Yatay Çalışma Alanı:** Sol panelde sohbet, sağ panelde canlı terminal ve araç konsolu aktiftir."
        )

    def _action_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: {Colors.BG_CARD2.name()};
                color: {Colors.TEXT.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {Colors.BORDER.name()};
                color: {Colors.ACCENT.name()};
                border-color: {Colors.ACCENT.name()};
            }}
        """

    def _append_console(self, text: str, tag: str = "info"):
        import html as html_mod
        colors = {
            "info": Colors.TEXT_MUTED.name(),
            "cmd": Colors.ACCENT.name(),
            "success": Colors.ACCENT_GREEN.name(),
            "error": Colors.ACCENT_RED.name(),
            "tool": Colors.ACCENT_PURPLE.name(),
            "user": Colors.TEXT.name()
        }
        color = colors.get(tag, "#c9d1d9")
        safe = html_mod.escape(text).replace("\n", "<br>")
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"<div style='margin-bottom:4px;'><span style='color:{Colors.TEXT_DIM.name()};'>[{timestamp}]</span> <span style='color:{color};'>{safe}</span></div>"
        self.console_display.append(entry)
        QTimer.singleShot(40, lambda: self.console_display.verticalScrollBar().setValue(
            self.console_display.verticalScrollBar().maximum()
        ))

    def _clear_console(self):
        self.console_display.setHtml(f"<span style='color:{Colors.TEXT_DIM.name()};'>[Konsol temizlendi]</span><br>")

    def _clear_chat_history(self):
        self.chat_history.clear()
        self.chat_display.setHtml("<html><body style='background:transparent;margin:0;padding:0;'></body></html>")
        self._add_assistant_message("Sohbet geçmişi ve bellek temizlendi. Yeni bir görev verebilirsiniz.")
        self._append_console("Sohbet belleği temizlendi.", "info")

    def _quick_prompt(self, text: str):
        self.input_field.setText(text)
        self._send_message()

    def _build_header(self, layout):
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_HEADER.name()};
                border-bottom: 1px solid {Colors.BORDER.name()};
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }}
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 12, 0)
        hl.setSpacing(10)

        # Logo dot + title
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {Colors.ACCENT.name()}; font-size: 10px; background: transparent; border: none;")
        title = QLabel("TENRA")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet(f"color: {Colors.TEXT.name()}; background: transparent; border: none;")
        ver = QLabel("v7 · Antigravity Studio")
        ver.setFont(QFont("Segoe UI", 9))
        ver.setStyleSheet(f"color: {Colors.TEXT_DIM.name()}; background: transparent; border: none; margin-top: 3px;")

        sep = QLabel("·")
        sep.setStyleSheet(f"color: {Colors.TEXT_DIM.name()}; background: transparent; border: none;")

        # Active model label
        self.model_label = QLabel("hermes3:8b")
        self.model_label.setFont(QFont("Consolas", 9))
        self.model_label.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; background: transparent; border: none;")

        # Status dot
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {Colors.ACCENT_GREEN.name()}; font-size: 8px; background: transparent; border: none;")

        self.status_text = QLabel("Aktif")
        self.status_text.setFont(QFont("Segoe UI", 9))
        self.status_text.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; background: transparent; border: none;")

        # Window buttons
        min_btn = QPushButton("─")
        min_btn.setFixedSize(26, 26)
        min_btn.setStyleSheet("""
            QPushButton { color: #7d8590; background: transparent; border: none; border-radius: 13px; font-size: 12px; }
            QPushButton:hover { background: rgba(255,255,255,0.1); color: #e6edf3; }
        """)
        min_btn.clicked.connect(self.showMinimized)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setStyleSheet("""
            QPushButton { color: #7d8590; background: transparent; border: none; border-radius: 13px; }
            QPushButton:hover { background: rgba(248, 81, 73, 0.3); color: #f85149; }
        """)
        close_btn.clicked.connect(self.hide)

        hl.addWidget(dot)
        hl.addWidget(title)
        hl.addWidget(ver)
        hl.addWidget(sep)
        hl.addWidget(self.model_label)
        hl.addStretch()
        hl.addWidget(self.status_dot)
        hl.addWidget(self.status_text)
        hl.addSpacing(8)
        hl.addWidget(min_btn)
        hl.addWidget(close_btn)

        layout.addWidget(header)

    def _build_preview_bar(self, layout):
        self.preview_frame = QFrame()
        self.preview_frame.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_CARD.name()};
                border-top: 1px solid {Colors.BORDER.name()};
            }}
        """)
        self.preview_frame.hide()

        pl = QHBoxLayout(self.preview_frame)
        pl.setContentsMargins(12, 6, 12, 6)
        pl.setSpacing(10)

        self.preview_img = ClickableLabel()
        self.preview_img.setFixedSize(60, 40)
        self.preview_img.setStyleSheet(f"background: {Colors.BG_DARK.name()}; border-radius: 4px; border: 1px solid {Colors.BORDER.name()};")
        self.preview_img.setCursor(Qt.PointingHandCursor)
        self.preview_img.clicked.connect(self._open_preview_image)

        icon_lbl = QLabel("📷")
        icon_lbl.setStyleSheet("background: transparent; border: none;")

        txt = QLabel("Ekran görüntüsü eklendi")
        txt.setStyleSheet(f"color: {Colors.ACCENT.name()}; font-size: 11px; background: transparent; border: none;")
        txt.setFont(QFont("Segoe UI", 9))

        self.preview_close_btn = QPushButton("✕")
        self.preview_close_btn.setFixedSize(20, 20)
        self.preview_close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED.name()}; border: none; }}
            QPushButton:hover {{ color: {Colors.ACCENT_RED.name()}; }}
        """)
        self.preview_close_btn.clicked.connect(self._clear_screenshot)

        pl.addWidget(self.preview_img)
        pl.addWidget(icon_lbl)
        pl.addWidget(txt)
        pl.addStretch()
        pl.addWidget(self.preview_close_btn)

    def _build_input_bar(self, layout):
        input_frame = QFrame()
        input_frame.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_HEADER.name()};
                border-top: 1px solid {Colors.BORDER.name()};
                border-bottom-left-radius: 14px;
            }}
        """)
        il = QHBoxLayout(input_frame)
        il.setContentsMargins(12, 10, 12, 10)
        il.setSpacing(8)

        self.capture_btn = QPushButton("📷")
        self.capture_btn.setFixedSize(36, 36)
        self.capture_btn.setToolTip("Ekran görüntüsü al")
        self.capture_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_CARD.name()};
                color: {Colors.TEXT_MUTED.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 10px;
                font-size: 14px;
            }}
            QPushButton:hover {{ background: {Colors.BG_CARD2.name()}; color: {Colors.TEXT.name()}; border-color: {Colors.BORDER_LIGHT.name()}; }}
            QPushButton:disabled {{ opacity: 0.4; }}
        """)
        self.capture_btn.clicked.connect(self._capture_screenshot)

        self.attach_btn = QPushButton("📎")
        self.attach_btn.setFixedSize(36, 36)
        self.attach_btn.setToolTip("Fotoğraf yükle")
        self.attach_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_CARD.name()};
                color: {Colors.TEXT_MUTED.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 10px;
                font-size: 14px;
            }}
            QPushButton:hover {{ background: {Colors.BG_CARD2.name()}; color: {Colors.TEXT.name()}; border-color: {Colors.BORDER_LIGHT.name()}; }}
        """)
        self.attach_btn.clicked.connect(self._select_image)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Bir şey sor veya görev ver...")
        self.input_field.setFont(QFont("Segoe UI", 11))
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.BG_INPUT.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 10px;
                padding: 9px 18px;
                color: {Colors.TEXT.name()};
            }}
            QLineEdit:focus {{
                border-color: {Colors.ACCENT.name()};
                background: {Colors.BG_CARD.name()};
            }}
            QLineEdit::placeholder {{ color: {Colors.TEXT_DIM.name()}; }}
        """)
        self.input_field.returnPressed.connect(self._send_message)

        self.send_btn = QPushButton("↑")
        self.send_btn.setFixedSize(36, 36)
        self.send_btn.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT.name()};
                color: #000;
                border: none;
                border-radius: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #33deff; }}
            QPushButton:disabled {{ background: {Colors.BORDER.name()}; color: {Colors.TEXT_DIM.name()}; }}
        """)
        self.send_btn.clicked.connect(self._send_message)

        il.addWidget(self.capture_btn)
        il.addWidget(self.attach_btn)
        il.addWidget(self.input_field)
        il.addWidget(self.send_btn)

        layout.addWidget(input_frame)

    # ── MESSAGE RENDERING ──────────────────────────

    def _add_user_message(self, text: str):
        import html as html_mod
        safe = html_mod.escape(text).replace("\n", "<br>")
        html = (
            f'<div style="display:flex;justify-content:flex-end;margin:10px 0;">'
            f'<div style="max-width:85%;background:{Colors.BG_CARD2.name()};'
            f'border:1px solid {Colors.BORDER.name()};border-left:3px solid {Colors.ACCENT.name()};'
            f'border-radius:10px;padding:10px 16px;color:{Colors.TEXT.name()};'
            f'font-family:Segoe UI,Arial;font-size:13px;">{safe}</div>'
            f'</div>'
        )
        self.chat_display.append(html)
        self._scroll_bottom()

    def _add_assistant_message(self, text: str):
        body = markdown_to_html(text)
        html = (
            f'<div style="margin:10px 0;padding-right:40px;">'
            f'<div style="display:inline-flex;align-items:center;gap:6px;margin-bottom:6px;">'
            f'<span style="color:{Colors.ACCENT.name()};font-size:9px;">●</span>'
            f'<span style="color:{Colors.TEXT_DIM.name()};font-size:10px;font-family:Consolas;">Tenra</span>'
            f'</div>'
            f'<div style="color:{Colors.TEXT.name()};font-family:Segoe UI,Arial;font-size:13px;line-height:1.6;">{body}</div>'
            f'</div>'
        )
        self.chat_display.append(html)
        self._scroll_bottom()

    def _add_tool_card(self, func_name: str, result: str, success: bool = True):
        html = make_tool_card_html(func_name, result, success)
        self.chat_display.append(html)
        self._scroll_bottom()

    def _add_terminal_card(self, command: str, stdout: str, stderr: str, exit_code: int):
        html = make_terminal_card_html(command, stdout, stderr, exit_code)
        self.chat_display.append(html)
        self._scroll_bottom()

    def _add_html(self, html: str):
        self.chat_display.append(html)
        self._scroll_bottom()

    def _scroll_bottom(self):
        QTimer.singleShot(60, lambda: self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        ))

    # ── SCREENSHOT ─────────────────────────────────

    def _capture_screenshot(self):
        self.hide()
        QTimer.singleShot(250, self._perform_screenshot_capture)

    def _perform_screenshot_capture(self):
        try:
            self.snipping_widget = SnippingWidget()
            self.snipping_widget.screenshot_taken.connect(self._on_screenshot_taken)
            self.snipping_widget.closed.connect(self._on_snipping_closed)
            self.snipping_widget.show()
        except Exception as err:
            self.show()
            self._add_tool_card("Snipping", str(err), False)

    def _on_snipping_closed(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_screenshot_taken(self, pixmap: QPixmap):
        self.show()
        self.raise_()
        self.activateWindow()
        if pixmap.isNull():
            self._add_tool_card("Ekran Görüntüsü", "Seçili alan alınamadı.", False)
            return
        base_dir = Path(__file__).resolve().parent / "data" / "screenshots"
        base_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = base_dir / f"screen_{stamp}.png"
        if not pixmap.save(str(file_path), "PNG"):
            self._add_tool_card("Ekran Görüntüsü", "Dosyaya yazılamadı.", False)
            return
        self.latest_screenshot_path = str(file_path)
        preview = pixmap.scaled(60, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_img.setPixmap(preview)
        self.preview_frame.show()
        self.input_field.setFocus()
        self._append_console(f"Ekran görüntüsü alındı: {file_path.name}", "info")

    def _select_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Fotoğraf Seç", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            self.latest_screenshot_path = file_path
            pixmap = QPixmap(file_path).scaled(60, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_img.setPixmap(pixmap)
            self.preview_frame.show()
            self.input_field.setFocus()
            self._append_console(f"Görsel seçildi: {os.path.basename(file_path)}", "info")

    def _open_preview_image(self):
        if self.latest_screenshot_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.latest_screenshot_path))

    def _clear_screenshot(self):
        self.latest_screenshot_path = None
        self.preview_frame.hide()
        self.input_field.setFocus()

    # ── SEND MESSAGE ───────────────────────────────

    def _send_message(self):
        text = self.input_field.text().strip()
        if not text and not self.latest_screenshot_path:
            return

        normalized = text.lower().strip()
        if normalized in {"evet", "eet", "evt", "yes", "onay", "tamam"} and self._pending_action:
            self._add_user_message(text)
            self._handle_pending_confirmation(True)
            self.input_field.clear()
            self.input_field.setFocus()
            return
        if normalized in {"hayir", "hayır", "iptal", "vazgec", "vazgeç", "no"} and self._pending_action:
            self._add_user_message(text)
            self._handle_pending_confirmation(False)
            self.input_field.clear()
            self.input_field.setFocus()
            return

        display_html = ""
        if self.latest_screenshot_path:
            img_uri = f"file:///{self.latest_screenshot_path.replace(chr(92), '/')}"
            display_html = f"<a href='{img_uri}'><img src='{img_uri}' width='240' style='border-radius:8px;margin-bottom:6px;'></a><br>"
        if text:
            import html as html_mod
            display_html += html_mod.escape(text).replace("\n", "<br>")

        self._add_html(
            f'<div style="display:flex;justify-content:flex-end;margin:10px 0;">'
            f'<div style="max-width:85%;background:{Colors.BG_CARD2.name()};'
            f'border:1px solid {Colors.BORDER.name()};border-left:3px solid {Colors.ACCENT.name()};'
            f'border-radius:10px;padding:10px 16px;color:{Colors.TEXT.name()};'
            f'font-family:Segoe UI,Arial;font-size:13px;">{display_html}</div>'
            f'</div>'
        )
        self.input_field.clear()
        self._set_busy(True)

        self._append_console(f"Kullanıcı: {text if text else '[Görsel Gönderildi]'}", "user")
        self.chat_history.append({"role": "user", "content": text})

        uncensored = self.uncensored_active
        self._worker = LLMWorker(
            text,
            screenshot_path=self.latest_screenshot_path,
            chat_history=list(self.chat_history),
            rpa_mode=self.rpa_mode,
            uncensored=uncensored
        )
        self._worker.response_ready.connect(self._on_response)
        self._worker.tool_executed.connect(self._on_tool_executed)
        self._worker.tool_approval_requested.connect(self._on_tool_approval_requested)
        self._worker.tool_started.connect(self._on_tool_started)
        self._worker.terminal_output.connect(self._on_terminal_output)
        self._worker.start()

        self.preview_frame.hide()
        self.latest_screenshot_path = None

    # ── SIGNALS ────────────────────────────────────

    def _set_busy(self, busy: bool):
        self.input_field.setEnabled(not busy)
        self.send_btn.setEnabled(not busy)
        self.capture_btn.setEnabled(not busy)
        self.preview_close_btn.setEnabled(not busy)
        if busy:
            self.loading_bar.show()
            self.status_dot.setStyleSheet(f"color: {Colors.ACCENT_YELLOW.name()}; font-size: 8px; background: transparent; border: none;")
            self.status_text.setText("Çalışıyor")
        else:
            self.loading_bar.hide()
            self.tool_label.hide()
            self.status_dot.setStyleSheet(f"color: {Colors.ACCENT_GREEN.name()}; font-size: 8px; background: transparent; border: none;")
            self.status_text.setText("Aktif")
            self.input_field.setFocus()

    def _on_tool_started(self, func_name: str):
        labels = {
            "web_search": "🔍 İnternette araştırıyor",
            "browse_website": "🌐 Web sitesini okuyor",
            "run_command": "⚡ Komut çalıştırıyor",
            "execute_python": "🐍 Python çalıştırıyor",
            "read_file": "📖 Dosya okuyor",
            "patch": "🔧 Kod güncelliyor",
            "search_files": "🔎 Dosya tarıyor",
            "click_screen": "🖱 Ekrana tıklıyor",
            "open_app": "🚀 Uygulama açıyor",
            "Ekran Analizi": "👁 Görsel analiz yapıyor",
        }
        label = labels.get(func_name, f"⚙ {func_name} çalışıyor")
        self.tool_label.setText(label + "...")
        self.tool_label.show()
        self.model_label.setText(f"hermes3:8b · {func_name}")
        self._append_console(f"⚙ Başlatılıyor: {func_name}", "tool")

    def _on_tool_executed(self, func_name: str, result: str, success: bool):
        self._add_tool_card(func_name, result, success)
        status_txt = "✓" if success else "✗"
        self._append_console(f"{status_txt} {func_name}: {result[:120]}", "success" if success else "error")

    def _on_terminal_output(self, command: str, stdout: str, stderr: str, exit_code: int):
        self._add_terminal_card(command, stdout, stderr, exit_code)
        self._append_console(f"$ {command} (exit {exit_code})", "cmd")
        if stdout:
            self._append_console(stdout[:300], "info")
        if stderr:
            self._append_console(stderr[:200], "error")

    def _on_response(self, message: str, func_info: str):
        self._set_busy(False)
        self.model_label.setText("hermes3:8b")

        if isinstance(message, str) and message.startswith("__CONFIRM_DELETE__"):
            target = message.replace("__CONFIRM_DELETE__", "", 1)
            from core.function_executor import executor
            self._request_delete_confirmation(target, executor)
            return

        self.chat_history.append({"role": "assistant", "content": message})
        self._add_assistant_message(message)
        self._append_console("Cevap hazırlandı ve iletildi.", "info")

    def _on_tool_approval_requested(self, func_name: str, params_str: str):
        import html as html_mod
        safe_params = html_mod.escape(params_str)
        html = (
            f'<div style="background:{Colors.BG_CARD.name()};border:1px solid {Colors.ACCENT_RED.name()};'
            f'border-radius:10px;padding:14px;margin:10px 0;">'
            f'<div style="color:{Colors.ACCENT_RED.name()};font-weight:bold;margin-bottom:8px;">⚠ Onay Gerekiyor: {func_name}</div>'
            f'<pre style="color:{Colors.TEXT_MUTED.name()};font-size:11px;font-family:Consolas;margin:0 0 12px;">{safe_params}</pre>'
            f'<a href="action://approve_tool" style="background:{Colors.ACCENT_GREEN.name()};color:#000;padding:6px 16px;'
            f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;margin-right:10px;">✓ İzin Ver</a>'
            f'<a href="action://deny_tool" style="background:{Colors.ACCENT_RED.name()};color:#fff;padding:6px 16px;'
            f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;">✕ Reddet</a>'
            f'</div>'
        )
        self._add_html(html)
        self._append_console(f"⚠ Kullanıcı onayı bekleniyor: {func_name}", "error")

    def _on_anchor_clicked(self, url):
        url_str = url if isinstance(url, str) else url.toString()

        if url_str == "action://approve_tool":
            if hasattr(self, "_worker") and self._worker and self._worker.isRunning():
                self._worker.tool_approval_result = True
                self._add_tool_card("Onay", "İzin verildi, devam ediliyor...", True)
                self._append_console("Kullanıcı eyleme izin verdi.", "success")
            return

        if url_str == "action://deny_tool":
            if hasattr(self, "_worker") and self._worker and self._worker.isRunning():
                self._worker.tool_approval_result = False
                self._add_tool_card("Onay", "İşlem reddedildi.", False)
                self._append_console("Kullanıcı eylemi reddetti.", "error")
                self._set_busy(False)
            return

        if url_str == "action://approve_pending":
            self._handle_pending_confirmation(True)
            return

        if url_str == "action://deny_pending":
            self._handle_pending_confirmation(False)
            return

        QDesktopServices.openUrl(QUrl(url_str))

    def _request_delete_confirmation(self, target: str, executor):
        import html as html_mod
        safe_target = html_mod.escape(target)
        self._pending_action = {"type": "delete", "executor": executor, "params": {"path": target}}
        html = (
            f'<div style="background:{Colors.BG_CARD.name()};border:1px solid {Colors.ACCENT_YELLOW.name()};'
            f'border-radius:10px;padding:12px;margin:10px 0;">'
            f'<span style="color:{Colors.ACCENT_YELLOW.name()};">⚠</span> '
            f'<b style="color:{Colors.TEXT.name()};">{safe_target}</b> çöp kutusuna taşınsın mı?<br><br>'
            f'<a href="action://approve_pending" style="background:{Colors.ACCENT_GREEN.name()};color:#000;padding:6px 16px;'
            f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;margin-right:8px;">✓ Evet</a>'
            f'<a href="action://deny_pending" style="background:{Colors.BG_CARD2.name()};color:{Colors.TEXT_MUTED.name()};padding:6px 16px;'
            f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;border:1px solid {Colors.BORDER.name()};">✕ Hayır</a>'
            f'</div>'
        )
        self._add_html(html)
        self._set_busy(False)

    def _handle_pending_confirmation(self, approved: bool):
        pending = getattr(self, "_pending_action", None)
        if not pending:
            return
        if not approved:
            self._pending_action = None
            self._add_tool_card("İptal", "İşlem iptal edildi.", False)
            return
        action_type = pending.get("type")
        executor = pending.get("executor")
        params = pending.get("params", {})
        self._pending_action = None
        if action_type == "delete" and executor:
            self._action_worker = SimpleActionWorker(action_type, executor, params)
            self._action_worker.action_finished.connect(
                lambda fn, msg: self._add_tool_card(fn, msg, True)
            )
            self._action_worker.start()

    # ── WINDOW BEHAVIOR ────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 50:
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

        from threading import Thread
        def preload():
            try:
                import requests
                from config import OLLAMA_URL, RESPONDER_MODEL
                requests.post(
                    f"{OLLAMA_URL}/generate",
                    json={"model": RESPONDER_MODEL, "prompt": "hi", "stream": False,
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


if __name__ == "__main__":
    check_and_install_dependencies()
    tenra = TenraApp()
    tenra.run()
