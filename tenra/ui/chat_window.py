import re
import os
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QPoint, QSize, QTimer, Signal, QThread, QPropertyAnimation, QEasingCurve, QRect, QUrl
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel, QScrollArea, QFrame, QGraphicsDropShadowEffect, QSizePolicy, QSizeGrip, QTextBrowser, QFileDialog, QProgressBar
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QLinearGradient, QIcon, QPixmap, QCursor, QKeyEvent, QGuiApplication, QScreen, QDesktopServices

from tenra.ui.colors import Colors
from tenra.ui.markdown import markdown_to_html, make_tool_card_html, make_terminal_card_html, make_diff_card_html
from tenra.ui.snipping import SnippingWidget, ClickableLabel
from tenra.ui.sidebar_widget import SidebarWidget
from tenra.core.workspace_manager import WorkspaceManager
from tenra.config import MAIN_MODEL, VISION_MODEL, DESKTOP_PATH

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
                 chat_history: list = None, rpa_mode: bool = False, uncensored: bool = True,
                 workspace_path: str = None):
        super().__init__()
        self.rpa_mode = rpa_mode
        self.uncensored = uncensored
        self.user_input = user_input
        self.raw_user_input = user_input
        self.screenshot_path = screenshot_path
        self.chat_history = chat_history or []
        self.workspace_path = workspace_path
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
                return "web", executor.execute("web", {"action": "open", "url": url_match.group(0)})

        # Masaüstü listele
        if "masa" in lower and "liste" in lower:
            return "file", executor.execute("file", {"action": "list"})

        # Doğrudan terminal komutu (komut: prefix)
        if lower.startswith("komut:") or lower.startswith("powershell:"):
            raw_cmd = text.split(":", 1)[1].strip() if ":" in text else ""
            if raw_cmd:
                return "shell", executor.execute("shell", {"command": raw_cmd})

        return None

    def run(self):
        try:
            from tenra.core.executor import TenraExecutor
            executor = TenraExecutor(workspace_path=self.workspace_path)
            executor.approval_callback = self._wait_for_approval
            executor.tool_start_callback = lambda f: self.tool_started.emit(f)

            # Uncensored mod
            

            from tenra.core.agent import (
                run_agent_loop,
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
            agent_result = run_agent_loop(
                input_text, executor,
                chat_history=self.chat_history,
                
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
                if name == "shell" and isinstance(result.get("data"), dict):
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
    """Tenra V2.0 — Agent Studio tarzı Yatay Agent Studio penceresi."""

    def __init__(self):
        super().__init__()
        self.wm = WorkspaceManager()
        self.active_workspace = self.wm.get_active_workspace()
        self.active_conversation = self.wm.get_active_conversation()
        self.chat_history = list(self.active_conversation.get("messages", [])) if self.active_conversation else []
        self.rpa_mode = True
        
        self._pending_action = None
        self.latest_screenshot_path = None
        self._drag_pos = None
        self._worker = None
        self._active_tool = None

        self.setWindowTitle("Tenra — Agent Studio")
        self.setMinimumSize(1000, 600)
        self.resize(1180, 680)

        # Frameless normal pencere (diğer uygulamaların arkasına geçebilir, Alt+Tab yapılabilir)
        self.is_pinned = False
        self._voice_thread = None
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._build_ui()
        self._position_window()
        self._render_active_conversation()

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

        # ── 2. YATAY 3 BÖLMELİ GÖVDE (SOL SİDEBAR, ORTA SOHBET, SAĞ KONSOL) ──
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # ── 2.1 SOL SİDEBAR: PROJELER & SOHBETLER ─────────
        self.sidebar = SidebarWidget(self.wm)
        self.sidebar.workspace_changed.connect(self._on_workspace_changed)
        self.sidebar.conversation_changed.connect(self._on_conversation_changed)
        self.sidebar.new_chat_requested.connect(self._on_new_chat_requested)
        body_layout.addWidget(self.sidebar)

        # ── 2.2 ORTA PANEL: SOHBET & AGENT AKIŞI ──────────
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

        # ── 2.3 SAĞ PANEL: CANLI KOMUT VE LOG AKIŞI ───────
        right_panel = QFrame()
        right_panel.setFixedWidth(300)
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
        con_lbl = QLabel("⚡ CANLI LOG & AKIŞ")
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

        # Canlı Terminal / Event Log Konsolu
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
            f"<span style='color:{Colors.TEXT_DIM.name()};'>[Tenra 2.0 hazır. Canlı komut ve araç akışı burada listelenir.]</span><br>"
        )
        right_layout.addWidget(self.console_display, 1)

        # Sohbeti Temizle Butonu
        btn_clear = QPushButton("🗑 Sohbeti Temizle")
        btn_clear.setStyleSheet(self._action_btn_style())
        btn_clear.clicked.connect(self._clear_chat_history)
        right_layout.addWidget(btn_clear)

        # Birleştir
        body_layout.addWidget(left_panel, 1)
        body_layout.addWidget(right_panel)
        container_layout.addWidget(body_widget, 1)

        outer.addWidget(self.container)

    def _render_active_conversation(self):
        """Aktif sohbetin mesajlarını ekrana çizer veya karşılama mesajını gösterir."""
        self.chat_display.setHtml("<html><body style='background:transparent;margin:0;padding:0;'></body></html>")
        if not self.chat_history:
            ws_title = self.active_workspace.get("name", "Masaüstü")
            ws_path = self.active_workspace.get("path", "")
            self._add_assistant_message(
                f"**Tenra 2.0 hazır.**\n\n"
                f"• **Aktif Proje:** `{ws_title}`\n"
                f"• **Dizin:** `{ws_path}`\n\n"
                f"Sol panelden üzerinde çalışmak istediğiniz projeyi seçebilir veya yeni sohbet açabilirsiniz."
            )
            return

        for msg in self.chat_history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user":
                self._add_user_message(content)
            elif role == "assistant":
                self._add_assistant_message(content)

    def _on_workspace_changed(self, ws_id: str, ws_path: str):
        """Kullanıcı sol panelden projeyi değiştirdiğinde çağrılır."""
        self.active_workspace = self.wm.get_active_workspace()
        self.project_badge.setText(f"📁 {self.active_workspace.get('name', 'Masaüstü')}")
        self.project_badge.setToolTip(self.active_workspace.get("path", ""))
        self._append_console(f"Aktif Proje Değişti: {self.active_workspace.get('name')} ({ws_path})", "info")

    def _on_conversation_changed(self, conv_id: str):
        """Kullanıcı sol panelden sohbet değiştirdiğinde çağrılır."""
        self.active_conversation = self.wm.get_active_conversation()
        self.chat_history = list(self.active_conversation.get("messages", [])) if self.active_conversation else []
        self._render_active_conversation()
        title = self.active_conversation.get("title", "Sohbet") if self.active_conversation else "Yeni Sohbet"
        self._append_console(f"Sohbet Yüklendi: {title}", "info")

    def _on_new_chat_requested(self):
        """Yeni sohbet açıldığında çağrılır."""
        self.active_conversation = self.wm.get_active_conversation()
        self.chat_history = []
        self._render_active_conversation()
        self._append_console("Yeni sohbet oturumu açıldı.", "info")

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
        if self.active_conversation:
            self.wm.save_conversation_messages(self.active_conversation["id"], [])
            self.sidebar.refresh()
        self._render_active_conversation()
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
        ver = QLabel("v2.0 · Agent Studio")
        ver.setFont(QFont("Segoe UI", 9))
        ver.setStyleSheet(f"color: {Colors.TEXT_DIM.name()}; background: transparent; border: none; margin-top: 3px;")

        # Active workspace badge
        ws_name = self.active_workspace.get("name", "Masaüstü")
        self.project_badge = QLabel(f"📁 {ws_name}")
        self.project_badge.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.project_badge.setStyleSheet(f"""
            QLabel {{
                color: {Colors.ACCENT.name()};
                background: {Colors.BG_CARD2.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 6px;
                padding: 2px 8px;
            }}
        """)
        self.project_badge.setToolTip(self.active_workspace.get("path", ""))

        sep = QLabel("·")
        sep.setStyleSheet(f"color: {Colors.TEXT_DIM.name()}; background: transparent; border: none;")

        # Active model label
        self.model_label = QLabel("qwen3:8b")
        self.model_label.setFont(QFont("Consolas", 9))
        self.model_label.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; background: transparent; border: none;")

        # Status dot
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {Colors.ACCENT_GREEN.name()}; font-size: 8px; background: transparent; border: none;")

        self.status_text = QLabel("Aktif")
        self.status_text.setFont(QFont("Segoe UI", 9))
        self.status_text.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; background: transparent; border: none;")

        # Window buttons
        self.pin_btn = QPushButton("📌")
        self.pin_btn.setFixedSize(26, 26)
        self.pin_btn.setToolTip("Pencereyi En Üste Sabitle (Şu an: Normal)")
        self.pin_btn.setStyleSheet(self._pin_style(False))
        self.pin_btn.clicked.connect(self._toggle_pin)

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
        hl.addWidget(self.project_badge)
        hl.addWidget(sep)
        hl.addWidget(self.model_label)
        hl.addStretch()
        hl.addWidget(self.status_dot)
        hl.addWidget(self.status_text)
        hl.addSpacing(8)
        hl.addWidget(self.pin_btn)
        hl.addWidget(min_btn)
        hl.addWidget(close_btn)

        layout.addWidget(header)

    def _pin_style(self, pinned: bool) -> str:
        color = Colors.ACCENT.name() if pinned else "#7d8590"
        bg = "rgba(0, 217, 255, 0.15)" if pinned else "transparent"
        return f"""
            QPushButton {{ color: {color}; background: {bg}; border: none; border-radius: 13px; font-size: 11px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.1); }}
        """

    def _toggle_pin(self):
        self.is_pinned = not self.is_pinned
        flags = self.windowFlags()
        if self.is_pinned:
            flags |= Qt.WindowStaysOnTopHint
            self.pin_btn.setToolTip("Pencere En Üstte Sabitlendi (Tıklayarak normale döndürün)")
            self._append_console("Pencere en üste sabitlendi.", "info")
        else:
            flags &= ~Qt.WindowStaysOnTopHint
            self.pin_btn.setToolTip("Pencere Normal Modda (Tıklayarak sabitleyin)")
            self._append_console("Pencere normal moda alındı (arkaya geçebilir).", "info")
        self.setWindowFlags(flags)
        self.pin_btn.setStyleSheet(self._pin_style(self.is_pinned))
        self.show()

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

        self.voice_btn = QPushButton("🎙️")
        self.voice_btn.setFixedSize(36, 36)
        self.voice_btn.setToolTip("Sesle Konuş / Dikte (Ctrl+M veya F4)")
        self.voice_btn.setStyleSheet(self._voice_btn_style(False))
        self.voice_btn.clicked.connect(self._toggle_voice_listening)

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
        il.addWidget(self.voice_btn)
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
        if self.active_conversation:
            self.wm.save_conversation_messages(self.active_conversation["id"], self.chat_history)
            self.sidebar.refresh()

        uncensored = False
        ws_path = self.active_workspace.get("path") if self.active_workspace else None
        self._worker = LLMWorker(
            text,
            screenshot_path=self.latest_screenshot_path,
            chat_history=list(self.chat_history),
            rpa_mode=self.rpa_mode,
            uncensored=uncensored,
            workspace_path=ws_path
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
        if hasattr(self, "voice_btn"):
            self.voice_btn.setEnabled(not busy)
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
            "web": "🔍 İnternette araştırıyor",
            "browse_website": "🌐 Web sitesini okuyor",
            "shell": "⚡ Komut çalıştırıyor",
            "execute_python": "🐍 Python çalıştırıyor",
            "file": "📄 Dosya işlemi yapıyor",
            "patch": "🔧 Kod güncelliyor",
            "search_files": "🔎 Dosya tarıyor",
            "click_screen": "🖱 Ekrana tıklıyor",
            "open_app": "🚀 Uygulama açıyor",
            "screen": "👁 Görsel analiz yapıyor",
        }
        label = labels.get(func_name, f"⚙ {func_name} çalışıyor")
        self.tool_label.setText(label + "...")
        self.tool_label.show()
        self.model_label.setText(f"qwen3:8b · {func_name}")
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
        self.model_label.setText("qwen3:8b")

        if isinstance(message, str) and message.startswith("__CONFIRM_DELETE__"):
            target = message.replace("__CONFIRM_DELETE__", "", 1)
            from tenra.core.executor import TenraExecutor
            executor = TenraExecutor()
            self._request_delete_confirmation(target, executor)
            return

        self.chat_history.append({"role": "assistant", "content": message})
        if self.active_conversation:
            self.wm.save_conversation_messages(self.active_conversation["id"], self.chat_history)
            self.sidebar.refresh()
        self._add_assistant_message(message)
        self._append_console("Cevap hazırlandı ve iletildi.", "info")

    def _on_tool_approval_requested(self, func_name: str, params_str: str):
        import html as html_mod
        import json
        
        params = {}
        try:
            params = json.loads(params_str)
        except Exception:
            params = {"raw": params_str}

        # Case 1: Kod Diff Önizleme Onayı (patch / write)
        if "diff" in params and params["diff"]:
            filename = params.get("filename", "Dosya")
            diff_text = params["diff"]
            diff_card = make_diff_card_html(filename, diff_text)
            action_name = "Kod Güncellemesi (Patch)" if func_name == "diff_patch" else "Dosya Üzerine Yazma"
            html = (
                f'<div style="background:{Colors.BG_CARD.name()};border:1px solid {Colors.ACCENT.name()};'
                f'border-radius:10px;padding:14px;margin:10px 0;">'
                f'<div style="color:{Colors.ACCENT.name()};font-weight:bold;font-size:13px;margin-bottom:8px;">'
                f'📝 {action_name} Onayı: <code>{html_mod.escape(filename)}</code></div>'
                f'<div style="margin-bottom:12px;">{diff_card}</div>'
                f'<div>'
                f'<a href="action://approve_tool" style="background:{Colors.ACCENT_GREEN.name()};color:#000;padding:7px 18px;'
                f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;margin-right:10px;">✓ Değişiklikleri Onayla ve Uygula</a>'
                f'<a href="action://deny_tool" style="background:{Colors.ACCENT_RED.name()};color:#fff;padding:7px 18px;'
                f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;">✕ Değişiklikleri Reddet</a>'
                f'</div>'
                f'</div>'
            )
            self._add_html(html)
            self._append_console(f"📝 Kod değişikliği onayı bekleniyor: {filename}", "info")
            return

        # Case 2: Dosya Silme / Çöp Kutusu Onayı
        if func_name == "delete":
            filename = params.get("filename", "Dosya")
            warning = params.get("warning", "Dosya silinecek!")
            html = (
                f'<div style="background:{Colors.BG_CARD.name()};border:1px solid {Colors.ACCENT_RED.name()};'
                f'border-radius:10px;padding:14px;margin:10px 0;">'
                f'<div style="color:{Colors.ACCENT_RED.name()};font-weight:bold;font-size:13px;margin-bottom:6px;">'
                f'🗑️ Silme Onayı: <code>{html_mod.escape(filename)}</code></div>'
                f'<div style="color:{Colors.TEXT.name()};font-size:12px;margin-bottom:12px;">{html_mod.escape(warning)}</div>'
                f'<div>'
                f'<a href="action://approve_tool" style="background:{Colors.ACCENT_RED.name()};color:#fff;padding:7px 18px;'
                f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;margin-right:10px;">✓ Çöp Kutusuna Taşı</a>'
                f'<a href="action://deny_tool" style="background:{Colors.BG_CARD2.name()};color:{Colors.TEXT_MUTED.name()};padding:7px 18px;'
                f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;border:1px solid {Colors.BORDER.name()};">✕ İptal Et</a>'
                f'</div>'
                f'</div>'
            )
            self._add_html(html)
            self._append_console(f"🗑️ Silme onayı bekleniyor: {filename}", "error")
            return

        # Case 3: Riskli Shell Komutu Onayı
        if func_name == "shell":
            command = params.get("command", "")
            warning = params.get("warning", "Riskli sistem komutu")
            html = (
                f'<div style="background:{Colors.BG_CARD.name()};border:1px solid {Colors.ACCENT_YELLOW.name()};'
                f'border-radius:10px;padding:14px;margin:10px 0;">'
                f'<div style="color:{Colors.ACCENT_YELLOW.name()};font-weight:bold;font-size:13px;margin-bottom:6px;">'
                f'⚡ Yüksek Riskli Terminal Komutu Onayı</div>'
                f'<div style="color:{Colors.TEXT_MUTED.name()};font-size:12px;margin-bottom:8px;">{html_mod.escape(warning)}</div>'
                f'<pre style="background:{Colors.TERMINAL_BG.name()};color:{Colors.ACCENT_RED.name()};padding:10px 14px;border-radius:6px;font-family:Consolas;font-size:12px;margin:0 0 12px;border:1px solid {Colors.BORDER.name()};">$ {html_mod.escape(command)}</pre>'
                f'<div>'
                f'<a href="action://approve_tool" style="background:{Colors.ACCENT_YELLOW.name()};color:#000;padding:7px 18px;'
                f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;margin-right:10px;">✓ Komutu Çalıştır</a>'
                f'<a href="action://deny_tool" style="background:{Colors.BG_CARD2.name()};color:{Colors.TEXT_MUTED.name()};padding:7px 18px;'
                f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;border:1px solid {Colors.BORDER.name()};">✕ Komutu Reddet</a>'
                f'</div>'
                f'</div>'
            )
            self._add_html(html)
            self._append_console(f"⚠ Riskli komut onayı bekleniyor: {command[:60]}", "error")
            return

        # Case 4: Genel Güvenlik Onayı
        safe_params = html_mod.escape(params_str)
        html = (
            f'<div style="background:{Colors.BG_CARD.name()};border:1px solid {Colors.ACCENT_RED.name()};'
            f'border-radius:10px;padding:14px;margin:10px 0;">'
            f'<div style="color:{Colors.ACCENT_RED.name()};font-weight:bold;margin-bottom:8px;">⚠ Güvenlik Onayı: {func_name}</div>'
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

    # ── SESLİ KONUŞMA (VOICE / STT) ────────────────
    def _voice_btn_style(self, listening: bool) -> str:
        if listening:
            return f"""
                QPushButton {{
                    background: {Colors.ACCENT_RED.name()};
                    color: #ffffff;
                    border: 1px solid {Colors.ACCENT_RED.name()};
                    border-radius: 10px;
                    font-size: 14px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background: #ff4d4d; }}
            """
        return f"""
            QPushButton {{
                background: {Colors.BG_CARD.name()};
                color: {Colors.TEXT_MUTED.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 10px;
                font-size: 14px;
            }}
            QPushButton:hover {{ background: {Colors.BG_CARD2.name()}; color: {Colors.TEXT.name()}; border-color: {Colors.BORDER_LIGHT.name()}; }}
            QPushButton:disabled {{ opacity: 0.4; }}
        """

    def _toggle_voice_listening(self):
        if hasattr(self, "_voice_thread") and self._voice_thread and self._voice_thread.isRunning():
            self._voice_thread.cancel()
            self._voice_thread.wait(600)
            self._on_voice_finished()
            self._append_console("Ses dinleme durduruldu.", "info")
            return

        try:
            from tenra.voice.stt import VoiceListenerThread
            self._voice_thread = VoiceListenerThread(language="tr-TR", parent=self)
            self._voice_thread.listening_started.connect(self._on_voice_started)
            self._voice_thread.listening_finished.connect(self._on_voice_finished)
            self._voice_thread.text_recognized.connect(self._on_voice_recognized)
            self._voice_thread.error_occurred.connect(self._on_voice_error)
            self._voice_thread.start()
        except Exception as e:
            self._append_console(f"Ses modülü başlatılamadı: {e}", "error")

    def _on_voice_started(self):
        self.voice_btn.setStyleSheet(self._voice_btn_style(True))
        self.voice_btn.setText("🔴")
        self.input_field.setPlaceholderText("🔴 Dinleniyor... Şimdi konuşun")
        self._append_console("🎙️ Ses algılayıcı aktif: Dinleniyor...", "info")

    def _on_voice_finished(self):
        self.voice_btn.setStyleSheet(self._voice_btn_style(False))
        self.voice_btn.setText("🎙️")
        self.input_field.setPlaceholderText("Bir şey sor veya görev ver...")

    def _on_voice_recognized(self, text: str):
        if not text:
            return
        curr = self.input_field.text().strip()
        merged = f"{curr} {text}".strip() if curr else text
        self.input_field.setText(merged)
        self.input_field.setFocus()
        self._append_console(f"🎙️ Ses Algılandı: \"{text}\"", "success")

    def _on_voice_error(self, err_msg: str):
        self._append_console(f"⚠ Ses Algılama: {err_msg}", "error")

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
        elif (event.key() == Qt.Key_M and event.modifiers() == Qt.ControlModifier) or event.key() == Qt.Key_F4:
            self._toggle_voice_listening()


