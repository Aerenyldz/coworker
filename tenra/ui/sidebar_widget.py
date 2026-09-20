"""Tenra 2.0 — Sol Kenar Çubuğu (Sidebar Widget)

Projeler (Workspaces) ve Sohbetler (Conversations) listesini yönetir.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QCursor
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QSizePolicy,
)

from tenra.ui.colors import Colors
from tenra.core.workspace_manager import WorkspaceManager


class SidebarWidget(QFrame):
    """Projeleri ve sohbet oturumlarını listeleyen sol kenar çubuğu."""

    workspace_changed = Signal(str, str)  # ws_id, ws_path
    conversation_changed = Signal(str)    # conv_id
    new_chat_requested = Signal()

    def __init__(self, workspace_manager: WorkspaceManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.wm = workspace_manager
        self.setFixedWidth(240)
        self.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_CARD.name()};
                border-right: 1px solid {Colors.BORDER.name()};
                border-top-left-radius: 14px;
                border-bottom-left-radius: 14px;
            }}
        """)

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 14, 10, 14)
        main_layout.setSpacing(12)

        # ── 1. PROJELER BAŞLIĞI & EKLEME BUTONU ───────────────
        proj_hdr = QHBoxLayout()
        proj_lbl = QLabel("📁 PROJELER")
        proj_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
        proj_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; border: none; background: transparent;")

        self.add_proj_btn = QPushButton("＋")
        self.add_proj_btn.setToolTip("Klasör / Proje Seç")
        self.add_proj_btn.setFixedSize(24, 24)
        self.add_proj_btn.setCursor(Qt.PointingHandCursor)
        self.add_proj_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_CARD2.name()};
                color: {Colors.TEXT.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT.name()};
                color: #000;
                border-color: {Colors.ACCENT.name()};
            }}
        """)
        self.add_proj_btn.clicked.connect(self._on_add_project_clicked)

        proj_hdr.addWidget(proj_lbl)
        proj_hdr.addStretch()
        proj_hdr.addWidget(self.add_proj_btn)
        main_layout.addLayout(proj_hdr)

        # Projeler Scroll Listesi
        self.proj_scroll = QScrollArea()
        self.proj_scroll.setWidgetResizable(True)
        self.proj_scroll.setFixedHeight(170)
        self.proj_scroll.setStyleSheet(self._scroll_style())

        self.proj_container = QWidget()
        self.proj_container.setStyleSheet("background: transparent; border: none;")
        self.proj_layout = QVBoxLayout(self.proj_container)
        self.proj_layout.setContentsMargins(0, 0, 0, 0)
        self.proj_layout.setSpacing(4)
        self.proj_layout.addStretch()

        self.proj_scroll.setWidget(self.proj_container)
        main_layout.addWidget(self.proj_scroll)

        # ── 2. AYIRICI ÇİZGİ ──────────────────────────────────
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.BORDER.name()}; border: none;")
        main_layout.addWidget(sep)

        # ── 3. SOHBETLER BAŞLIĞI & YENİ SOHBET BUTONU ─────────
        chat_hdr = QHBoxLayout()
        chat_lbl = QLabel("💬 SOHBETLER")
        chat_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
        chat_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED.name()}; border: none; background: transparent;")

        self.new_chat_btn = QPushButton("＋")
        self.new_chat_btn.setToolTip("Yeni Sohbet Başlat")
        self.new_chat_btn.setFixedSize(24, 24)
        self.new_chat_btn.setCursor(Qt.PointingHandCursor)
        self.new_chat_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_CARD2.name()};
                color: {Colors.TEXT.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT.name()};
                color: #000;
                border-color: {Colors.ACCENT.name()};
            }}
        """)
        self.new_chat_btn.clicked.connect(self._on_new_chat_clicked)

        chat_hdr.addWidget(chat_lbl)
        chat_hdr.addStretch()
        chat_hdr.addWidget(self.new_chat_btn)
        main_layout.addLayout(chat_hdr)

        # Sohbetler Scroll Listesi
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet(self._scroll_style())

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: transparent; border: none;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_layout.setSpacing(4)
        self.chat_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_container)
        main_layout.addWidget(self.chat_scroll, 1)

    def _scroll_style(self) -> str:
        return f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                width: 4px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.BORDER_LIGHT.name()};
                border-radius: 2px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """

    def refresh(self):
        """Projeleri ve sohbetleri yeniden yükler."""
        self._refresh_projects()
        self._refresh_conversations()

    def _refresh_projects(self):
        # Önceki butonları temizle (stretch hariç)
        while self.proj_layout.count() > 1:
            item = self.proj_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        workspaces = self.wm.get_workspaces()
        active_ws = self.wm.get_active_workspace()
        active_id = active_ws.get("id")

        for ws in workspaces:
            is_active = (ws["id"] == active_id)
            row = QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background: {Colors.BG_CARD2.name() if is_active else "transparent"};
                    border: 1px solid {Colors.ACCENT.name() if is_active else Colors.BORDER.name()};
                    border-left: 3px solid {Colors.ACCENT.name() if is_active else Colors.BORDER.name()};
                    border-radius: 6px;
                    padding: 4px 6px;
                }}
                QFrame:hover {{
                    background: {Colors.BG_CARD2.name()};
                    border-color: {Colors.ACCENT.name()};
                }}
            """)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(6, 4, 6, 4)
            rl.setSpacing(6)

            icon = "🖥️" if ws["id"] == "ws-desktop" else "📦"
            lbl = QLabel(f"{icon} {ws['name']}")
            lbl.setFont(QFont("Segoe UI", 9, QFont.Bold if is_active else QFont.Normal))
            lbl.setStyleSheet(f"color: {Colors.TEXT.name() if is_active else Colors.TEXT_MUTED.name()}; border: none; background: transparent;")
            lbl.setToolTip(ws.get("path", ""))

            # Tıklama davranışı
            row.setCursor(Qt.PointingHandCursor)
            row.mousePressEvent = lambda e, w=ws: self._on_select_project(w["id"])

            rl.addWidget(lbl, 1)

            # Silme butonu (sadece özel projeler için)
            if ws["id"] not in ("ws-desktop", "ws-coworker"):
                del_btn = QPushButton("✕")
                del_btn.setFixedSize(16, 16)
                del_btn.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {Colors.TEXT_DIM.name()}; border: none; font-size: 10px; }}
                    QPushButton:hover {{ color: {Colors.ACCENT_RED.name()}; }}
                """)
                del_btn.clicked.connect(lambda _, wid=ws["id"]: self._on_remove_project(wid))
                rl.addWidget(del_btn)

            self.proj_layout.insertWidget(self.proj_layout.count() - 1, row)

    def _refresh_conversations(self):
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        active_ws = self.wm.get_active_workspace()
        active_ws_id = active_ws.get("id")
        active_conv = self.wm.get_active_conversation()
        active_conv_id = active_conv.get("id") if active_conv else None

        # Aktif projeye ait sohbetler
        proj_convs = self.wm.get_conversations(workspace_id=active_ws_id)
        # Bağımsız sohbetler
        independent_convs = self.wm.get_conversations(only_independent=True)

        if proj_convs:
            sec_lbl = QLabel(f"• {active_ws['name']} Sohbetleri")
            sec_lbl.setFont(QFont("Segoe UI", 8, QFont.Bold))
            sec_lbl.setStyleSheet(f"color: {Colors.ACCENT.name()}; border: none; background: transparent; margin-top: 4px;")
            self.chat_layout.insertWidget(self.chat_layout.count() - 1, sec_lbl)

            for c in proj_convs:
                self._add_conversation_row(c, active_conv_id)

        if independent_convs:
            sec_lbl = QLabel("• Genel / Bağımsız")
            sec_lbl.setFont(QFont("Segoe UI", 8, QFont.Bold))
            sec_lbl.setStyleSheet(f"color: {Colors.TEXT_DIM.name()}; border: none; background: transparent; margin-top: 8px;")
            self.chat_layout.insertWidget(self.chat_layout.count() - 1, sec_lbl)

            for c in independent_convs:
                self._add_conversation_row(c, active_conv_id)

    def _add_conversation_row(self, conv: dict, active_conv_id: Optional[str]):
        is_active = (conv["id"] == active_conv_id)
        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_CARD2.name() if is_active else "transparent"};
                border: 1px solid {Colors.BORDER_LIGHT.name() if is_active else "transparent"};
                border-radius: 6px;
                padding: 4px 6px;
            }}
            QFrame:hover {{
                background: {Colors.BG_CARD2.name()};
            }}
        """)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(6, 4, 4, 4)
        rl.setSpacing(4)

        title = conv.get("title", "Sohbet")
        lbl = QLabel(title)
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setStyleSheet(f"color: {Colors.TEXT.name() if is_active else Colors.TEXT_MUTED.name()}; border: none; background: transparent;")
        lbl.setToolTip(title)

        row.setCursor(Qt.PointingHandCursor)
        row.mousePressEvent = lambda e, cid=conv["id"]: self._on_select_conversation(cid)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(16, 16)
        del_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.TEXT_DIM.name()}; border: none; font-size: 10px; }}
            QPushButton:hover {{ color: {Colors.ACCENT_RED.name()}; }}
        """)
        del_btn.clicked.connect(lambda _, cid=conv["id"]: self._on_delete_conversation(cid))

        rl.addWidget(lbl, 1)
        rl.addWidget(del_btn)

        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)

    # ── EVENT HANDLERS ────────────────────────────────────

    def _on_select_project(self, ws_id: str):
        if self.wm.set_active_workspace(ws_id):
            active_ws = self.wm.get_active_workspace()
            self.refresh()
            self.workspace_changed.emit(ws_id, active_ws.get("path", ""))

    def _on_select_conversation(self, conv_id: str):
        if self.wm.set_active_conversation(conv_id):
            self.refresh()
            self.conversation_changed.emit(conv_id)

    def _on_add_project_clicked(self):
        """Masaüstünden veya diskten proje klasörü seçtirir."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Çalışmak İstediğiniz Proje Klasörünü Seçin",
            str(Path.home() / "OneDrive" / "Desktop")
        )
        if folder:
            try:
                new_ws = self.wm.add_workspace(folder)
                self.refresh()
                self.workspace_changed.emit(new_ws["id"], new_ws["path"])
            except Exception as e:
                QMessageBox.warning(self, "Hata", f"Proje eklenemedi: {e}")

    def _on_remove_project(self, ws_id: str):
        self.wm.remove_workspace(ws_id)
        active_ws = self.wm.get_active_workspace()
        self.refresh()
        self.workspace_changed.emit(active_ws["id"], active_ws["path"])

    def _on_new_chat_clicked(self):
        active_ws = self.wm.get_active_workspace()
        ws_id = active_ws.get("id") if active_ws.get("id") != "ws-desktop" else None
        new_conv = self.wm.create_conversation("Yeni Sohbet", workspace_id=ws_id)
        self.refresh()
        self.conversation_changed.emit(new_conv["id"])
        self.new_chat_requested.emit()

    def _on_delete_conversation(self, conv_id: str):
        self.wm.delete_conversation(conv_id)
        active_conv = self.wm.get_active_conversation()
        self.refresh()
        if active_conv:
            self.conversation_changed.emit(active_conv["id"])
