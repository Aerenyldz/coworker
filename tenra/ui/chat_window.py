import re
import os
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QPoint, QSize, QTimer, Signal, QThread, QPropertyAnimation, QEasingCurve, QRect, QUrl
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel, QScrollArea, QFrame, QGraphicsDropShadowEffect, QSizePolicy, QSizeGrip, QTextBrowser, QFileDialog, QProgressBar
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QLinearGradient, QIcon, QPixmap, QCursor, QKeyEvent, QGuiApplication, QScreen, QDesktopServices

from tenra.ui.colors import Colors
from tenra.ui.markdown import markdown_to_html, make_tool_card_html, make_terminal_card_html, make_diff_card_html, make_multi_diff_card_html
from tenra.ui.snipping import SnippingWidget, ClickableLabel
from tenra.ui.sidebar_widget import SidebarWidget
from tenra.core.workspace_manager import WorkspaceManager
from tenra.config import MAIN_MODEL, VISION_MODEL, DESKTOP_PATH, TTS_ENABLED, TTS_AUTO_SPEAK, UNCENSORED_MODEL

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
                params = dict(self.params or {})
                params.setdefault("action", "delete")
                result = self.executor.execute("file", params)
                ok = bool(result.get("success")) and not result.get("error")
                self.action_finished.emit(
                    "file",
                    result.get("message", "İşlem tamamlandı." if ok else "Silme başarısız."),
                )
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
    token_received         = Signal(str)                 # streaming content delta
    stream_reset           = Signal()                    # tool call → clear stream bubble

    def __init__(self, user_input: str, screenshot_path: str | None = None,
                 chat_history: list = None, rpa_mode: bool = False, uncensored: bool = False,
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
                success = bool(sc_result.get("success")) and not sc_result.get("error")
                self.tool_executed.emit(sc_name, msg, success)
                self.response_ready.emit(msg, sc_name)
                return

            # Vision zenginleştirmesi varsa history'deki son user mesajını güncelle
            # (çift user turn / çakışan bağlamı önler)
            history_for_agent = list(self.chat_history)
            if input_text != self.user_input:
                if history_for_agent and history_for_agent[-1].get("role") == "user":
                    history_for_agent[-1] = {
                        **history_for_agent[-1],
                        "content": input_text,
                    }
                else:
                    history_for_agent.append({"role": "user", "content": input_text})

            # Hermes otonom araç döngüsü
            agent_result = run_agent_loop(
                input_text, executor,
                chat_history=history_for_agent,
                on_token=lambda t: self.token_received.emit(t),
                on_stream_reset=lambda: self.stream_reset.emit(),
                uncensored=self.uncensored,
            )

            if not agent_result.get("ok"):
                self.response_ready.emit(f"⚠ {agent_result.get('error', 'Bilinmeyen hata')}", "")
                return

            self.last_prompt_eval = agent_result.get("prompt_eval_count")

            # Araç sonuçlarını emit et
            for tool_call in agent_result.get("tool_results", []):
                name = tool_call.get("name", "tool")
                result = tool_call.get("result", {})
                success = bool(result.get("success")) and not result.get("error")
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
        self.uncensored_mode = False
        self._active_model_label = "qwen3:8b"
        self._last_batch_id = None
        self._last_speakable = ""
        self._stream_buffer = ""
        self._stream_dirty = False
        self._pre_stream_html = None
        self._stream_started = False
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        # Yumuşak/bulanık kenar yok — opak panel, keskin çerçeve
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._build_ui()
        self._position_window()
        self._render_active_conversation()

        # Stream UI flush (Cursor tarzı akıcı yazım — 40ms batch)
        self._stream_flush_timer = QTimer(self)
        self._stream_flush_timer.setInterval(40)
        self._stream_flush_timer.timeout.connect(self._flush_stream_ui)

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
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Ana panel — gölge/yuvarlak yok (yumuşak kenar hissi kalksın)
        self.container = QFrame()
        self.container.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_PANEL.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 0;
            }}
        """)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── 1. CUSTOM HEADER ────────────────────────────
        self._build_header(container_layout)

        # ── 2. SOL SİDEBAR + ORTA SOHBET (+ isteğe bağlı sağ log) ──
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = SidebarWidget(self.wm)
        self.sidebar.workspace_changed.connect(self._on_workspace_changed)
        self.sidebar.conversation_changed.connect(self._on_conversation_changed)
        self.sidebar.new_chat_requested.connect(self._on_new_chat_requested)
        body_layout.addWidget(self.sidebar)

        left_panel = QFrame()
        left_panel.setStyleSheet("background: transparent; border: none;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Breadcrumb satırı
        self.breadcrumb = QLabel()
        self.breadcrumb.setFont(QFont("Segoe UI", 11))
        self.breadcrumb.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_MUTED.name()};
                background: transparent;
                border: none;
                padding: 12px 24px 4px 24px;
            }}
        """)
        self._update_breadcrumb()
        left_layout.addWidget(self.breadcrumb)

        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(False)
        self.chat_display.setOpenLinks(False)
        self.chat_display.anchorClicked.connect(self._on_anchor_clicked)
        self.chat_display.setStyleSheet(f"""
            QTextBrowser {{
                background: transparent;
                border: none;
                padding: 8px 28px 16px 28px;
                color: {Colors.TEXT.name()};
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 14px;
                selection-background-color: {Colors.ACCENT_DIM.name()};
            }}
            QScrollBar:vertical {{
                width: 6px;
                background: transparent;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.BORDER.name()};
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
                background: {Colors.TEXT_MUTED.name()};
            }}
        """)
        self.loading_bar.hide()

        self.tool_label = QLabel()
        self.tool_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_MUTED.name()};
                font-size: 12px;
                font-family: 'Segoe UI', sans-serif;
                padding: 4px 28px;
                background: transparent;
            }}
        """)
        self.tool_label.hide()

        self.stream_preview = None
        self._stream_buffer = ""

        self._build_preview_bar(left_layout)

        left_layout.addWidget(self.chat_display, 1)
        left_layout.addWidget(self.loading_bar)
        left_layout.addWidget(self.tool_label)
        left_layout.addWidget(self.preview_frame)
        self._build_input_bar(left_layout)

        # Sağ log — varsayılan gizli (Antigravity gibi temiz orta alan)
        self.right_panel = QFrame()
        self.right_panel.setFixedWidth(280)
        self.right_panel.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_CARD.name()};
                border-left: 1px solid {Colors.BORDER.name()};
                border-bottom-right-radius: 0;
            }}
        """)
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        console_hdr = QHBoxLayout()
        con_lbl = QLabel("Aktivite")
        con_lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        con_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; border: none; background: transparent;")
        clear_con_btn = QPushButton("Temizle")
        clear_con_btn.setFixedHeight(22)
        clear_con_btn.setCursor(Qt.PointingHandCursor)
        clear_con_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_DIM.name()};
                border: none;
                font-size: 11px;
            }}
            QPushButton:hover {{ color: {Colors.TEXT.name()}; }}
        """)
        clear_con_btn.clicked.connect(self._clear_console)
        console_hdr.addWidget(con_lbl)
        console_hdr.addStretch()
        console_hdr.addWidget(clear_con_btn)
        right_layout.addLayout(console_hdr)

        self.console_display = QTextBrowser()
        self.console_display.setStyleSheet(f"""
            QTextBrowser {{
                background: {Colors.TERMINAL_BG.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
                padding: 8px;
                color: {Colors.TEXT_MUTED.name()};
                font-family: Consolas, monospace;
                font-size: 11px;
            }}
        """)
        self.console_display.setHtml(
            f"<span style='color:{Colors.TEXT_DIM.name()};'>Araç ve komut izleri burada.</span>"
        )
        right_layout.addWidget(self.console_display, 1)

        btn_clear = QPushButton("Sohbeti temizle")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet(self._action_btn_style())
        btn_clear.clicked.connect(self._clear_chat_history)
        right_layout.addWidget(btn_clear)

        self.right_panel.hide()  # Antigravity: sağ panel yok / kapalı

        body_layout.addWidget(left_panel, 1)
        body_layout.addWidget(self.right_panel)
        container_layout.addWidget(body_widget, 1)

        outer.addWidget(self.container)

    def _update_breadcrumb(self):
        ws = (self.active_workspace or {}).get("name", "Masaüstü")
        conv = ""
        if self.active_conversation:
            conv = self.active_conversation.get("title", "Sohbet")
        if conv:
            self.breadcrumb.setText(f"{ws}  /  {conv}")
        else:
            self.breadcrumb.setText(ws)

    def _toggle_activity_panel(self):
        if self.right_panel.isVisible():
            self.right_panel.hide()
            self.activity_btn.setToolTip("Aktivite panelini aç")
        else:
            self.right_panel.show()
            self.activity_btn.setToolTip("Aktivite panelini gizle")

    def _render_active_conversation(self):
        """Aktif sohbetin mesajlarını ekrana çizer veya karşılama mesajını gösterir."""
        self._update_breadcrumb()
        self.chat_display.setHtml("<html><body style='background:transparent;margin:0;padding:0;'></body></html>")
        if not self.chat_history:
            ws_title = self.active_workspace.get("name", "Masaüstü")
            self._add_assistant_message(
                f"Merhaba — **{ws_title}** üzerindeyim.\n\n"
                f"Bu sohbet yalnızca bu projeye ait. Yeni sohbet açarsan bağlam sıfırlanır.\n\n"
                f"Ne yapmak istersin?"
            )
            self._update_context_badge()
            return

        for msg in self.chat_history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user":
                self._add_user_message(content)
            elif role == "assistant":
                self._add_assistant_message(content)
        self._update_context_badge()

    def _on_workspace_changed(self, ws_id: str, ws_path: str):
        """Proje değişince o projenin sohbet bağlamına geç."""
        self.active_workspace = self.wm.get_active_workspace()
        self.active_conversation = self.wm.get_active_conversation()
        self.chat_history = (
            list(self.active_conversation.get("messages", []))
            if self.active_conversation else []
        )
        self.project_badge.setText(self.active_workspace.get("name", "Masaüstü"))
        self.project_badge.setToolTip(self.active_workspace.get("path", ""))
        self._render_active_conversation()
        self._append_console(
            f"Proje bağlamı: {self.active_workspace.get('name')} "
            f"/ {(self.active_conversation or {}).get('title', 'Sohbet')}",
            "info",
        )

    def _on_conversation_changed(self, conv_id: str):
        """Sohbet değişince geçmişi yükle (proje bağlamı izole)."""
        self.active_workspace = self.wm.get_active_workspace()
        self.active_conversation = self.wm.get_active_conversation()
        self.chat_history = (
            list(self.active_conversation.get("messages", []))
            if self.active_conversation else []
        )
        self.project_badge.setText(self.active_workspace.get("name", "Masaüstü"))
        self._render_active_conversation()
        title = (
            self.active_conversation.get("title", "Sohbet")
            if self.active_conversation else "Yeni Sohbet"
        )
        self._append_console(f"Sohbet bağlamı: {title}", "info")

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
                color: {Colors.TEXT.name()};
                border-color: {Colors.TEXT_MUTED.name()};
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
        self._update_context_badge()
        self._append_console("Sohbet belleği temizlendi.", "info")

    def _quick_prompt(self, text: str):
        self.input_field.setText(text)
        self._send_message()

    def _build_header(self, layout):
        header = QFrame()
        header.setFixedHeight(48)
        header.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_HEADER.name()};
                border-bottom: 1px solid {Colors.BORDER.name()};
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
            }}
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 12, 0)
        hl.setSpacing(8)

        title = QLabel("Tenra")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet(f"color: {Colors.TEXT.name()}; background: transparent; border: none;")

        ws_name = self.active_workspace.get("name", "Masaüstü")
        self.project_badge = QLabel(ws_name)
        self.project_badge.setFont(QFont("Segoe UI", 9))
        self.project_badge.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_MUTED.name()};
                background: {Colors.BG_CARD2.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 8px;
                padding: 3px 10px;
            }}
        """)
        self.project_badge.setToolTip(self.active_workspace.get("path", ""))

        self.model_label = QLabel("qwen3:8b")
        self.model_label.setFont(QFont("Segoe UI", 9))
        self.model_label.setStyleSheet(f"color: {Colors.TEXT_DIM.name()}; background: transparent; border: none;")

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {Colors.ACCENT_GREEN.name()}; font-size: 8px; background: transparent; border: none;")

        self.status_text = QLabel("Hazır")
        self.status_text.setFont(QFont("Segoe UI", 9))
        self.status_text.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; background: transparent; border: none;")

        self.activity_btn = QPushButton("☰")
        self.activity_btn.setFixedSize(28, 28)
        self.activity_btn.setToolTip("Aktivite panelini aç")
        self.activity_btn.setCursor(Qt.PointingHandCursor)
        self.activity_btn.setStyleSheet("""
            QPushButton { color: #8c8c91; background: transparent; border: none; border-radius: 8px; font-size: 14px; }
            QPushButton:hover { background: rgba(255,255,255,0.06); color: #e8e8e8; }
        """)
        self.activity_btn.clicked.connect(self._toggle_activity_panel)

        self.hack_btn = QPushButton("🔓")
        self.hack_btn.setFixedSize(28, 28)
        self.hack_btn.setToolTip(f"Hack / Sansürsüz Mod (kapalı) → {UNCENSORED_MODEL or 'model yok'}")
        self.hack_btn.setStyleSheet(self._hack_style(False))
        self.hack_btn.clicked.connect(self._toggle_uncensored)

        self.undo_btn = QPushButton("↩")
        self.undo_btn.setFixedSize(28, 28)
        self.undo_btn.setToolTip("Son kod değişikliğini geri al")
        self.undo_btn.setStyleSheet("""
            QPushButton { color: #8c8c91; background: transparent; border: none; border-radius: 8px; font-size: 13px; }
            QPushButton:hover { background: rgba(255,255,255,0.06); color: #e8e8e8; }
        """)
        self.undo_btn.clicked.connect(self._undo_last_change)

        self.pin_btn = QPushButton("📌")
        self.pin_btn.setFixedSize(28, 28)
        self.pin_btn.setToolTip("Pencereyi en üste sabitle")
        self.pin_btn.setStyleSheet(self._pin_style(False))
        self.pin_btn.clicked.connect(self._toggle_pin)

        min_btn = QPushButton("─")
        min_btn.setFixedSize(28, 28)
        min_btn.setStyleSheet("""
            QPushButton { color: #8c8c91; background: transparent; border: none; border-radius: 8px; font-size: 12px; }
            QPushButton:hover { background: rgba(255,255,255,0.06); color: #e8e8e8; }
        """)
        min_btn.clicked.connect(self.showMinimized)

        self.max_btn = QPushButton("□")
        self.max_btn.setFixedSize(28, 28)
        self.max_btn.setToolTip("Tam ekran / geri al")
        self.max_btn.setStyleSheet("""
            QPushButton { color: #8c8c91; background: transparent; border: none; border-radius: 8px; font-size: 12px; }
            QPushButton:hover { background: rgba(255,255,255,0.06); color: #e8e8e8; }
        """)
        self.max_btn.clicked.connect(self._toggle_maximize)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet("""
            QPushButton { color: #8c8c91; background: transparent; border: none; border-radius: 8px; }
            QPushButton:hover { background: rgba(220, 100, 95, 0.25); color: #dc645f; }
        """)
        close_btn.clicked.connect(self.hide)

        hl.addWidget(title)
        hl.addWidget(self.project_badge)
        hl.addWidget(self.model_label)
        hl.addStretch()
        hl.addWidget(self.status_dot)
        hl.addWidget(self.status_text)
        hl.addSpacing(6)
        hl.addWidget(self.activity_btn)
        hl.addWidget(self.hack_btn)
        hl.addWidget(self.undo_btn)
        hl.addWidget(self.pin_btn)
        hl.addWidget(min_btn)
        hl.addWidget(self.max_btn)
        hl.addWidget(close_btn)

        layout.addWidget(header)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.max_btn.setText("□")
        else:
            self.showMaximized()
            self.max_btn.setText("❐")

    def _pin_style(self, pinned: bool) -> str:
        color = Colors.ACCENT.name() if pinned else "#7d8590"
        bg = "rgba(0, 217, 255, 0.15)" if pinned else "transparent"
        return f"""
            QPushButton {{ color: {color}; background: {bg}; border: none; border-radius: 13px; font-size: 11px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.1); }}
        """

    def _hack_style(self, on: bool) -> str:
        color = "#ff6b6b" if on else "#7d8590"
        bg = "rgba(255, 107, 107, 0.18)" if on else "transparent"
        return f"""
            QPushButton {{ color: {color}; background: {bg}; border: none; border-radius: 13px; font-size: 12px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.1); }}
        """

    def _toggle_uncensored(self):
        if not self.uncensored_mode:
            # Açmadan önce modelin kurulu olduğunu doğrula
            try:
                from tenra.plugins._hermes_slot import resolve_uncensored_model
                resolved = resolve_uncensored_model()
            except Exception as e:
                resolved = None
                self._append_console(f"Model kontrolü başarısız: {e}", "error")
            if not resolved:
                msg = (
                    "⚠ Sansürsüz model Ollama'da bulunamadı.\n"
                    "Kurulum: `ollama pull uandinotai/dolphin-uncensored` "
                    "veya `ollama pull hermes3:8b`"
                )
                self._add_assistant_message(msg)
                self._append_console("Hack modu açılamadı: model yok.", "error")
                return
            self.uncensored_mode = True
            self.hack_btn.setStyleSheet(self._hack_style(True))
            short = resolved.split("/")[-1][:18]
            self._active_model_label = short
            self.hack_btn.setToolTip(f"Hack Modu AÇIK → {resolved}")
            self.model_label.setText(short)
            if hasattr(self, "_model_chip"):
                self._model_chip.setText(short)
            self._append_console(f"Hack/Sansürsüz mod açıldı: {resolved}", "info")
        else:
            self.uncensored_mode = False
            self.hack_btn.setStyleSheet(self._hack_style(False))
            self._active_model_label = "qwen3:8b"
            self.hack_btn.setToolTip(f"Hack / Sansürsüz Mod (kapalı) → {UNCENSORED_MODEL or 'model yok'}")
            self.model_label.setText("qwen3:8b")
            if hasattr(self, "_model_chip"):
                self._model_chip.setText("qwen3:8b")
            self._append_console("Hack modu kapatıldı (qwen3:8b).", "info")

    def _undo_last_change(self):
        try:
            from tenra.core.executor import TenraExecutor
            ws_path = self.active_workspace.get("path") if self.active_workspace else None
            ex = TenraExecutor(workspace_path=ws_path)
            if self._last_batch_id:
                result = ex.undo_batch(self._last_batch_id)
                self._last_batch_id = None
            else:
                result = ex.undo_last_change()
            ok = result.get("success")
            msg = result.get("message", "Undo")
            self._add_tool_card("Undo", msg, bool(ok))
            self._append_console(msg, "success" if ok else "error")
        except Exception as e:
            self._add_tool_card("Undo", str(e), False)

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
                border-bottom-left-radius: 0;
            }}
        """)
        outer = QVBoxLayout(input_frame)
        outer.setContentsMargins(20, 12, 20, 16)
        outer.setSpacing(0)

        # Antigravity tarzı tek pill input
        pill = QFrame()
        pill.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_INPUT.name()};
                border: 1px solid {Colors.BORDER_LIGHT.name()};
                border-radius: 22px;
            }}
        """)
        il = QHBoxLayout(pill)
        il.setContentsMargins(8, 6, 8, 6)
        il.setSpacing(6)

        self.capture_btn = QPushButton("+")
        self.capture_btn.setFixedSize(32, 32)
        self.capture_btn.setToolTip("Ekran görüntüsü / ek")
        self.capture_btn.setCursor(Qt.PointingHandCursor)
        self.capture_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_MUTED.name()};
                border: none;
                border-radius: 16px;
                font-size: 16px;
            }}
            QPushButton:hover {{ background: {Colors.BG_CARD2.name()}; color: {Colors.TEXT.name()}; }}
        """)
        self.capture_btn.clicked.connect(self._capture_screenshot)

        self.attach_btn = QPushButton("📎")
        self.attach_btn.setFixedSize(32, 32)
        self.attach_btn.setToolTip("Fotoğraf yükle")
        self.attach_btn.setCursor(Qt.PointingHandCursor)
        self.attach_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_MUTED.name()};
                border: none;
                border-radius: 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background: {Colors.BG_CARD2.name()}; color: {Colors.TEXT.name()}; }}
        """)
        self.attach_btn.clicked.connect(self._select_image)

        self.voice_btn = QPushButton("🎙️")
        self.voice_btn.setFixedSize(32, 32)
        self.voice_btn.setToolTip("Sesle konuş / dikte")
        self.voice_btn.setStyleSheet(self._voice_btn_style(False))
        self.voice_btn.clicked.connect(self._toggle_voice_listening)

        self.speak_btn = QPushButton("🔊")
        self.speak_btn.setFixedSize(32, 32)
        self.speak_btn.setToolTip("Son cevabı Türkçe oku")
        self.speak_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_MUTED.name()};
                border: none;
                border-radius: 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background: {Colors.BG_CARD2.name()}; color: {Colors.TEXT.name()}; }}
        """)
        self.speak_btn.clicked.connect(self._toggle_speak_last)
        self._speaking = False

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Bir şey sor…  @ mention,  / komut")
        self.input_field.setFont(QFont("Segoe UI", 12))
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                padding: 6px 8px;
                color: {Colors.TEXT.name()};
            }}
            QLineEdit::placeholder {{ color: {Colors.TEXT_DIM.name()}; }}
        """)
        self.input_field.returnPressed.connect(self._send_message)

        self.send_btn = QPushButton("↑")
        self.send_btn.setFixedSize(34, 34)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.TEXT.name()};
                color: #111;
                border: none;
                border-radius: 17px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #fff; }}
            QPushButton:disabled {{ background: {Colors.BORDER.name()}; color: {Colors.TEXT_DIM.name()}; }}
        """)
        self.send_btn.clicked.connect(self._send_message)

        il.addWidget(self.capture_btn)
        il.addWidget(self.attach_btn)
        il.addWidget(self.input_field, 1)
        il.addWidget(self.voice_btn)
        il.addWidget(self.speak_btn)
        il.addWidget(self.send_btn)

        # Model + bağlam kullanımı (sağ alt — Cursor tarzı)
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(12, 6, 12, 0)
        model_chip = QLabel()
        self._model_chip = model_chip
        model_chip.setText(self._active_model_label)
        model_chip.setStyleSheet(
            f"color: {Colors.TEXT_DIM.name()}; font-size: 11px; border: none; background: transparent;"
        )
        self.context_badge = QLabel("0% bağlam")
        self.context_badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.context_badge.setStyleSheet(
            f"color: {Colors.TEXT_DIM.name()}; font-size: 11px; border: none; background: transparent;"
        )
        self.context_badge.setToolTip("Bu sohbetin bağlam penceresi kullanımı")
        meta_row.addWidget(model_chip)
        meta_row.addStretch()
        meta_row.addWidget(self.context_badge)

        outer.addWidget(pill)
        outer.addLayout(meta_row)
        layout.addWidget(input_frame)
        self._update_context_badge()

    def _update_context_badge(self, prompt_eval_count: int | None = None):
        """Sağ alt bağlam % — aktif sohbet geçmişine göre."""
        if not hasattr(self, "context_badge"):
            return
        try:
            from tenra.core.context_usage import estimate_context_usage, context_badge_color
            ws = self.active_workspace or {}
            info = estimate_context_usage(
                self.chat_history,
                workspace_path=ws.get("path"),
                workspace_name=ws.get("name"),
                prompt_eval_count=prompt_eval_count,
            )
            color = context_badge_color(info["percent"])
            self.context_badge.setText(f"{info['percent']}% · {info['detail']}")
            self.context_badge.setToolTip(info["tooltip"])
            self.context_badge.setStyleSheet(
                f"color: {color}; font-size: 11px; border: none; background: transparent;"
            )
        except Exception:
            self.context_badge.setText("?— bağlam")

    # ── MESSAGE RENDERING ──────────────────────────

    def _add_user_message(self, text: str):
        import html as html_mod
        safe = html_mod.escape(text).replace("\n", "<br>")
        # Tablo hücresi → balon metin kadar genişler (tam satır çizgisi yok)
        html = (
            f'<table cellspacing="0" cellpadding="0" style="margin:14px 0 8px 0;border-collapse:collapse;">'
            f'<tr><td style="background:{Colors.BG_CARD2.name()};'
            f'border:1px solid {Colors.BORDER.name()};border-radius:12px;'
            f'padding:10px 14px;color:{Colors.TEXT.name()};'
            f'font-family:Segoe UI,system-ui;font-size:14px;line-height:1.5;">'
            f'{safe}</td></tr></table>'
        )
        self.chat_display.append(html)
        self._scroll_bottom()

    def _add_assistant_message(self, text: str):
        body = markdown_to_html(text)
        speak_link = ""
        if TTS_ENABLED and text and not text.startswith("⚠") and not text.startswith("Hata"):
            speak_link = (
                f'<div style="margin-top:8px;">'
                f'<a href="action://speak" title="Türkçe oku" '
                f'style="color:{Colors.TEXT_DIM.name()};text-decoration:none;font-size:12px;">🔊 Dinle</a>'
                f'</div>'
            )
            self._last_speakable = text
        html = (
            f'<div style="margin:8px 0 20px 0;padding:4px 2px;">'
            f'<div style="color:{Colors.TEXT.name()};font-family:Segoe UI,system-ui;'
            f'font-size:14.5px;line-height:1.65;">{body}</div>'
            f'{speak_link}'
            f'</div>'
        )
        self.chat_display.append(html)
        self._scroll_bottom()

    def _stream_bubble_html(self, preview: str) -> str:
        import html as html_mod
        safe = html_mod.escape(preview).replace("\n", "<br>")
        return (
            f'<div style="margin:8px 0 20px 0;padding:4px 2px;">'
            f'<div style="color:{Colors.TEXT.name()};font-family:Segoe UI,system-ui;'
            f'font-size:14.5px;line-height:1.65;">'
            f'{safe}<span style="color:{Colors.TEXT_MUTED.name()};">▍</span></div>'
            f'</div>'
        )

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

        # Görsel + metin: yine metin kadar balon (tam genişlik yok)
        self._add_html(
            f'<table cellspacing="0" cellpadding="0" style="margin:14px 0 8px 0;border-collapse:collapse;">'
            f'<tr><td style="background:{Colors.BG_CARD2.name()};'
            f'border:1px solid {Colors.BORDER.name()};border-radius:12px;'
            f'padding:10px 14px;color:{Colors.TEXT.name()};'
            f'font-family:Segoe UI,system-ui;font-size:14px;line-height:1.5;">'
            f'{display_html}</td></tr></table>'
        )
        self.input_field.clear()
        self._set_busy(True)

        self._append_console(f"Kullanıcı: {text if text else '[Görsel Gönderildi]'}", "user")
        self.chat_history.append({"role": "user", "content": text})
        self._update_context_badge()
        if self.active_conversation:
            self.wm.save_conversation_messages(self.active_conversation["id"], self.chat_history)
            self.sidebar.refresh()

        uncensored = self.uncensored_mode
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
        self._worker.token_received.connect(self._on_token_received)
        self._worker.stream_reset.connect(self._on_stream_reset)
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
        if hasattr(self, "speak_btn"):
            self.speak_btn.setEnabled(not busy)
        self.preview_close_btn.setEnabled(not busy)
        if busy:
            self.loading_bar.show()
            self.status_dot.setStyleSheet(f"color: {Colors.ACCENT_YELLOW.name()}; font-size: 8px; background: transparent; border: none;")
            self.status_text.setText("Çalışıyor")
        else:
            self.loading_bar.hide()
            self.tool_label.hide()
            self._on_stream_reset()
            self.status_dot.setStyleSheet(f"color: {Colors.ACCENT_GREEN.name()}; font-size: 8px; background: transparent; border: none;")
            self.status_text.setText("Hazır")
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
        self.model_label.setText(f"{self._active_model_label} · {func_name}")
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

    def _on_token_received(self, token: str):
        """Ollama stream delta → sohbet içinde canlı daktilo."""
        if not token:
            return
        if not self._stream_started:
            # Snapshot: tool kartları vb. korunur, üzerine stream balonu yazılır
            self._pre_stream_html = self.chat_display.toHtml()
            self._stream_started = True
            if not self._stream_flush_timer.isActive():
                self._stream_flush_timer.start()
        self._stream_buffer += token
        self._stream_dirty = True
        self.status_text.setText("Yazıyor")
        self.status_dot.setStyleSheet(
            f"color: {Colors.ACCENT.name()}; font-size: 8px; background: transparent; border: none;"
        )

    def _flush_stream_ui(self):
        """40ms'de bir stream balonunu yenile (akıcı, seyrek değil)."""
        if not self._stream_dirty or not self._stream_started:
            return
        self._stream_dirty = False
        preview = self._stream_buffer
        if len(preview) > 6000:
            preview = "…\n" + preview[-5600:]
        base = self._pre_stream_html or ""
        # Qt toHtml body'sini koruyup sonuna stream eklemek için setHtml
        # En güvenlisi: öncesi + stream balonu
        try:
            # toHtml tam belge döner; stream balonunu body sonuna eklemek için
            # basit yol: ön HTML'i tut, üzerine append benzeri birleştir
            if "</body>" in base.lower():
                # case-insensitive split
                idx = base.lower().rfind("</body>")
                combined = base[:idx] + self._stream_bubble_html(preview) + base[idx:]
            else:
                combined = base + self._stream_bubble_html(preview)
            # Scroll konumunu koru / alta yapış
            bar = self.chat_display.verticalScrollBar()
            at_bottom = bar.value() >= bar.maximum() - 40
            self.chat_display.setHtml(combined)
            if at_bottom:
                bar.setValue(bar.maximum())
        except Exception:
            pass

    def _on_stream_reset(self):
        """Araç çağrısı / bitiş: yarım stream metnini temizle."""
        self._stream_flush_timer.stop()
        self._stream_dirty = False
        was_streaming = self._stream_started
        self._stream_buffer = ""
        self._stream_started = False
        if was_streaming and self._pre_stream_html is not None:
            try:
                self.chat_display.setHtml(self._pre_stream_html)
            except Exception:
                pass
        self._pre_stream_html = None

    def _on_response(self, message: str, func_info: str):
        # Stream temizliği _set_busy(False) içinde (tek kaynak)
        self._set_busy(False)
        self.model_label.setText(self._active_model_label)
        if hasattr(self, "_model_chip"):
            self._model_chip.setText(self._active_model_label)

        pec = None
        if hasattr(self, "_worker") and self._worker is not None:
            pec = getattr(self._worker, "last_prompt_eval", None)

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
        self._update_context_badge(prompt_eval_count=pec)
        self._append_console("Cevap hazırlandı ve iletildi.", "info")

        # Son batch uygulandıysa undo linki göster
        if self._last_batch_id:
            self._add_html(
                f'<div style="margin:4px 0 10px 0;">'
                f'<a href="action://undo_batch?id={self._last_batch_id}" '
                f'style="color:{Colors.ACCENT.name()};font-size:12px;">↩ Bu değişiklik paketini geri al</a>'
                f'</div>'
            )

        # Otomatik TTS kapalı — yalnızca TTS_AUTO_SPEAK True ise (varsayılan False)
        if TTS_AUTO_SPEAK and TTS_ENABLED and message and not message.startswith("⚠") and not message.startswith("Hata"):
            plain = message.strip()
            if len(plain) <= 280 and "```" not in plain:
                try:
                    from tenra.voice.tts import speak
                    speak(plain)
                except Exception:
                    pass

    def _on_tool_approval_requested(self, func_name: str, params_str: str):
        import html as html_mod
        import json
        
        params = {}
        try:
            params = json.loads(params_str)
        except Exception:
            params = {"raw": params_str}

        # Case 0: Çoklu dosya diff paketi
        if func_name == "diff_batch" and params.get("files"):
            files = params.get("files") or []
            if files:
                count = params.get("count", len(files))
                batch_id = params.get("batch_id", "")
                self._pending_batch_id = batch_id
                multi = make_multi_diff_card_html(files)
                html = (
                    f'<div style="background:{Colors.BG_CARD.name()};border:1px solid {Colors.ACCENT.name()};'
                    f'border-radius:10px;padding:14px;margin:10px 0;">'
                    f'<div style="color:{Colors.ACCENT.name()};font-weight:bold;font-size:13px;margin-bottom:8px;">'
                    f'📦 Çoklu Dosya Diff Paketi ({count} dosya)</div>'
                    f'<div style="margin-bottom:12px;">{multi}</div>'
                    f'<div>'
                    f'<a href="action://approve_tool" style="background:{Colors.ACCENT_GREEN.name()};color:#000;padding:7px 18px;'
                    f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;margin-right:10px;">✓ Paketi Onayla ve Uygula</a>'
                    f'<a href="action://deny_tool" style="background:{Colors.ACCENT_RED.name()};color:#fff;padding:7px 18px;'
                    f'text-decoration:none;border-radius:6px;font-weight:bold;font-size:12px;">✕ Paketi Reddet</a>'
                    f'</div>'
                    f'</div>'
                )
                self._add_html(html)
                self._append_console(f"📦 Diff paketi onayı: {count} dosya", "info")
                return

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
                if getattr(self, "_pending_batch_id", None):
                    self._last_batch_id = self._pending_batch_id
                    self._pending_batch_id = None
                self._add_tool_card("Onay", "İzin verildi, devam ediliyor...", True)
                self._append_console("Kullanıcı eyleme izin verdi.", "success")
            return

        if url_str == "action://deny_tool":
            if hasattr(self, "_worker") and self._worker and self._worker.isRunning():
                self._worker.tool_approval_result = False
                self._pending_batch_id = None
                self._add_tool_card("Onay", "İşlem reddedildi.", False)
                self._append_console("Kullanıcı eylemi reddetti.", "error")
                # Busy'yi burada açma — worker hâlâ çalışıyor; _on_response temizler
            return

        if url_str == "action://undo_last":
            self._undo_last_change()
            return

        if url_str.startswith("action://undo_batch"):
            # action://undo_batch?id=xxx or action://undo_batch/xxx
            batch_id = ""
            if "?" in url_str:
                batch_id = url_str.split("id=")[-1]
            elif "/" in url_str:
                batch_id = url_str.rstrip("/").split("/")[-1]
            if batch_id and batch_id != "undo_batch":
                self._last_batch_id = batch_id
            self._undo_last_change()
            return

        if url_str == "action://approve_pending":
            self._handle_pending_confirmation(True)
            return

        if url_str == "action://deny_pending":
            self._handle_pending_confirmation(False)
            return

        if url_str == "action://speak":
            self._speak_text(self._last_speakable)
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
    def _plain_for_speech(self, text: str) -> str:
        """Markdown/kod bloklarını ses için sadeleştir."""
        if not text:
            return ""
        plain = re.sub(r"```[\s\S]*?```", " ", text)
        plain = re.sub(r"`([^`]+)`", r"\1", plain)
        plain = re.sub(r"[#*_>\[\]()]+", " ", plain)
        plain = re.sub(r"\s+", " ", plain).strip()
        return plain[:800]

    def _speak_text(self, text: str):
        if not TTS_ENABLED:
            self._append_console("TTS kapalı.", "info")
            return
        plain = self._plain_for_speech(text)
        if not plain:
            self._append_console("Okunacak metin yok.", "info")
            return
        try:
            from tenra.voice.tts import get_synthesizer, speak, stop_speaking
            synth = get_synthesizer()
            if not synth.available:
                self._append_console(
                    "Yerel Türkçe TTS yok. data/piper altına onnx koy "
                    "veya ileride ses klonunu bağla.",
                    "error",
                )
                return
            if self._speaking:
                stop_speaking()
                self._speaking = False
                self.speak_btn.setText("🔊")
                return
            ok = speak(plain)
            if ok:
                self._speaking = True
                self.speak_btn.setText("⏹")
                # Konuşma bitince ikonu geri al (kabaca süre)
                delay_ms = min(120_000, max(3000, len(plain) * 80))
                QTimer.singleShot(delay_ms, self._reset_speak_btn)
                self._append_console(f"TTS ({synth.backend_name}): okunuyor…", "info")
            else:
                self._append_console("TTS başlatılamadı.", "error")
        except Exception as e:
            self._append_console(f"TTS hata: {e}", "error")

    def _reset_speak_btn(self):
        self._speaking = False
        if hasattr(self, "speak_btn"):
            self.speak_btn.setText("🔊")

    def _toggle_speak_last(self):
        """Input bar hoparlör: son cevabı oku / durdur."""
        if self._speaking:
            try:
                from tenra.voice.tts import stop_speaking
                stop_speaking()
            except Exception:
                pass
            self._reset_speak_btn()
            return
        self._speak_text(self._last_speakable)

    def _voice_btn_style(self, listening: bool) -> str:
        if listening:
            return f"""
                QPushButton {{
                    background: {Colors.ACCENT_RED.name()};
                    color: #ffffff;
                    border: none;
                    border-radius: 16px;
                    font-size: 13px;
                }}
                QPushButton:hover {{ background: #e0706a; }}
            """
        return f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_MUTED.name()};
                border: none;
                border-radius: 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background: {Colors.BG_CARD2.name()}; color: {Colors.TEXT.name()}; }}
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


