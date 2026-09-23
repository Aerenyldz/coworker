"""Tenra 2.0 — Sol kenar çubuğu: proje → altında sohbetler (bağlam izolasyonu)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QFileDialog,
    QMessageBox,
)

from tenra.ui.colors import Colors
from tenra.core.workspace_manager import WorkspaceManager


def _relative_time(iso_or_ts) -> str:
    if not iso_or_ts:
        return ""
    try:
        if isinstance(iso_or_ts, (int, float)):
            dt = datetime.fromtimestamp(iso_or_ts)
        else:
            s = str(iso_or_ts).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
        delta = datetime.now() - dt
        secs = max(0, int(delta.total_seconds()))
        if secs < 60:
            return "şimdi"
        if secs < 3600:
            return f"{secs // 60}m"
        if secs < 86400:
            return f"{secs // 3600}h"
        days = secs // 86400
        if days < 30:
            return f"{days}d"
        return f"{days // 30}mo"
    except Exception:
        return ""


class SidebarWidget(QFrame):
    """Her projenin altında kendi sohbetleri — Cursor / Antigravity modeli."""

    workspace_changed = Signal(str, str)  # ws_id, ws_path
    conversation_changed = Signal(str)    # conv_id
    new_chat_requested = Signal()

    def __init__(self, workspace_manager: WorkspaceManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.wm = workspace_manager
        self.setFixedWidth(268)
        self.setObjectName("SidebarRoot")
        self.setStyleSheet(f"""
            QFrame#SidebarRoot {{
                background: {Colors.BG_SIDEBAR.name()};
                border-right: 1px solid {Colors.BORDER.name()};
            }}
        """)
        self._expanded: Set[str] = set()
        # Aktif proje açık başlasın
        self._expanded.add(self.wm.get_active_workspace().get("id", "ws-desktop"))
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 14, 12, 12)
        main_layout.setSpacing(10)

        self.new_chat_btn = QPushButton("+  Yeni Sohbet")
        self.new_chat_btn.setCursor(Qt.PointingHandCursor)
        self.new_chat_btn.setFixedHeight(36)
        self.new_chat_btn.setToolTip("Aktif projede yeni sohbet (ayrı bağlam)")
        self.new_chat_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT.name()};
                border: 1px solid {Colors.BORDER_LIGHT.name()};
                border-radius: 18px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {Colors.BG_CARD2.name()};
                border-color: {Colors.TEXT_MUTED.name()};
            }}
        """)
        self.new_chat_btn.clicked.connect(self._on_new_chat_clicked)
        main_layout.addWidget(self.new_chat_btn)

        hist = QLabel("⏱  Sohbet Geçmişi")
        hist.setFont(QFont("Segoe UI", 10))
        hist.setStyleSheet(
            f"color: {Colors.TEXT_MUTED.name()}; border: none; background: transparent; padding: 4px 2px;"
        )
        main_layout.addWidget(hist)

        proj_hdr = QHBoxLayout()
        proj_lbl = QLabel("Projeler")
        proj_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
        proj_lbl.setStyleSheet(
            f"color: {Colors.TEXT_DIM.name()}; border: none; background: transparent;"
        )
        self.add_proj_btn = QPushButton("+")
        self.add_proj_btn.setToolTip("Proje klasörü ekle")
        self.add_proj_btn.setFixedSize(22, 22)
        self.add_proj_btn.setCursor(Qt.PointingHandCursor)
        self.add_proj_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_MUTED.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 6px;
                font-size: 12px;
            }}
            QPushButton:hover {{ color: {Colors.TEXT.name()}; border-color: {Colors.TEXT_MUTED.name()}; }}
        """)
        self.add_proj_btn.clicked.connect(self._on_add_project_clicked)
        proj_hdr.addWidget(proj_lbl)
        proj_hdr.addStretch()
        proj_hdr.addWidget(self.add_proj_btn)
        main_layout.addLayout(proj_hdr)

        self.tree_scroll = QScrollArea()
        self.tree_scroll.setWidgetResizable(True)
        self.tree_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{
                background: {Colors.BORDER.name()};
                border-radius: 2px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.tree_container = QWidget()
        self.tree_container.setStyleSheet("background: transparent; border: none;")
        self.tree_layout = QVBoxLayout(self.tree_container)
        self.tree_layout.setContentsMargins(0, 0, 0, 0)
        self.tree_layout.setSpacing(2)
        self.tree_layout.addStretch()
        self.tree_scroll.setWidget(self.tree_container)
        main_layout.addWidget(self.tree_scroll, 1)

        hint = QLabel("Her sohbet kendi bağlamını taşır")
        hint.setFont(QFont("Segoe UI", 8))
        hint.setStyleSheet(
            f"color: {Colors.TEXT_DIM.name()}; border: none; background: transparent; padding: 4px 2px;"
        )
        main_layout.addWidget(hint)

    def refresh(self):
        while self.tree_layout.count() > 1:
            item = self.tree_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        active_ws = self.wm.get_active_workspace()
        active_ws_id = active_ws.get("id")
        active_conv = self.wm.get_active_conversation()
        active_conv_id = active_conv.get("id") if active_conv else None

        # Aktif proje her zaman açık
        if active_ws_id:
            self._expanded.add(active_ws_id)

        for ws in self.wm.get_workspaces():
            self._add_project_block(ws, active_ws_id, active_conv_id)

    def _add_project_block(self, ws: dict, active_ws_id: str, active_conv_id: Optional[str]):
        ws_id = ws["id"]
        is_active_ws = ws_id == active_ws_id
        expanded = ws_id in self._expanded

        # Proje satırı
        row = QFrame()
        bg = Colors.BG_CARD2.name() if is_active_ws else "transparent"
        row.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: none;
                border-radius: 8px;
            }}
            QFrame:hover {{ background: {Colors.BG_CARD2.name()}; }}
        """)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 7, 6, 7)
        rl.setSpacing(4)

        chev = "▾" if expanded else "▸"
        name = ws["name"]
        if len(name) > 20:
            name = name[:18] + "…"
        lbl = QLabel(f"{chev}  {name}")
        lbl.setFont(QFont("Segoe UI", 10, QFont.DemiBold if is_active_ws else QFont.Normal))
        lbl.setStyleSheet(
            f"color: {Colors.TEXT.name() if is_active_ws else Colors.TEXT_MUTED.name()};"
            f"border: none; background: transparent;"
        )
        lbl.setToolTip(ws.get("path", ""))
        row.setCursor(Qt.PointingHandCursor)

        def _click_project(_e, wid=ws_id):
            if wid in self._expanded and self.wm.get_active_workspace().get("id") == wid:
                self._expanded.discard(wid)
                self.refresh()
                return
            self._expanded.add(wid)
            self._on_select_project(wid)

        row.mousePressEvent = _click_project
        rl.addWidget(lbl, 1)

        if ws_id not in ("ws-desktop", "ws-coworker"):
            del_btn = QPushButton("×")
            del_btn.setFixedSize(18, 18)
            del_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {Colors.TEXT_DIM.name()}; border: none; font-size: 13px; }}
                QPushButton:hover {{ color: {Colors.ACCENT_RED.name()}; }}
            """)
            del_btn.clicked.connect(lambda _, wid=ws_id: self._on_remove_project(wid))
            rl.addWidget(del_btn)

        self.tree_layout.insertWidget(self.tree_layout.count() - 1, row)

        if not expanded:
            return

        # Alt sohbetler (bu projenin bağlamı)
        convs = self.wm.get_conversations(workspace_id=ws_id)
        if not convs:
            empty = QLabel("    henüz sohbet yok")
            empty.setFont(QFont("Segoe UI", 9))
            empty.setStyleSheet(
                f"color: {Colors.TEXT_DIM.name()}; border: none; background: transparent; padding: 4px 8px;"
            )
            self.tree_layout.insertWidget(self.tree_layout.count() - 1, empty)
            return

        for c in convs:
            self._add_conversation_row(c, active_conv_id, indent=True)

    def _add_conversation_row(self, conv: dict, active_conv_id: Optional[str], indent: bool = True):
        is_active = conv["id"] == active_conv_id
        row = QFrame()
        bg = Colors.BG_CARD2.name() if is_active else "transparent"
        row.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: none;
                border-radius: 8px;
            }}
            QFrame:hover {{ background: {Colors.BG_CARD2.name()}; }}
        """)
        rl = QHBoxLayout(row)
        left = 22 if indent else 10
        rl.setContentsMargins(left, 6, 6, 6)
        rl.setSpacing(4)

        title = conv.get("title", "Sohbet")
        display = title if len(title) <= 22 else title[:20] + "…"
        lbl = QLabel(display)
        lbl.setFont(QFont("Segoe UI", 10))
        lbl.setStyleSheet(
            f"color: {Colors.TEXT.name() if is_active else Colors.TEXT_MUTED.name()};"
            f"border: none; background: transparent;"
        )
        lbl.setToolTip(title)

        ago = _relative_time(conv.get("updated_at") or conv.get("created_at"))
        time_lbl = QLabel(ago)
        time_lbl.setFont(QFont("Segoe UI", 9))
        time_lbl.setStyleSheet(
            f"color: {Colors.TEXT_DIM.name()}; border: none; background: transparent;"
        )

        row.setCursor(Qt.PointingHandCursor)
        row.mousePressEvent = lambda e, cid=conv["id"]: self._on_select_conversation(cid)

        del_btn = QPushButton("×")
        del_btn.setFixedSize(18, 18)
        del_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.TEXT_DIM.name()}; border: none; font-size: 13px; }}
            QPushButton:hover {{ color: {Colors.ACCENT_RED.name()}; }}
        """)
        del_btn.clicked.connect(lambda _, cid=conv["id"]: self._on_delete_conversation(cid))

        rl.addWidget(lbl, 1)
        rl.addWidget(time_lbl)
        rl.addWidget(del_btn)
        self.tree_layout.insertWidget(self.tree_layout.count() - 1, row)

    def _on_select_project(self, ws_id: str):
        if self.wm.set_active_workspace(ws_id):
            active_ws = self.wm.get_active_workspace()
            active_conv = self.wm.get_active_conversation()
            self.refresh()
            self.workspace_changed.emit(ws_id, active_ws.get("path", ""))
            if active_conv:
                self.conversation_changed.emit(active_conv["id"])

    def _on_select_conversation(self, conv_id: str):
        if self.wm.set_active_conversation(conv_id):
            self.refresh()
            self.conversation_changed.emit(conv_id)
            # Proje de değişmiş olabilir
            ws = self.wm.get_active_workspace()
            self.workspace_changed.emit(ws["id"], ws.get("path", ""))

    def _on_add_project_clicked(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Proje klasörünü seç",
            str(Path.home() / "OneDrive" / "Desktop"),
        )
        if folder:
            try:
                new_ws = self.wm.add_workspace(folder)
                self._expanded.add(new_ws["id"])
                self.refresh()
                self.workspace_changed.emit(new_ws["id"], new_ws["path"])
                conv = self.wm.get_active_conversation()
                if conv:
                    self.conversation_changed.emit(conv["id"])
            except Exception as e:
                QMessageBox.warning(self, "Hata", f"Proje eklenemedi: {e}")

    def _on_remove_project(self, ws_id: str):
        self.wm.remove_workspace(ws_id)
        self._expanded.discard(ws_id)
        active_ws = self.wm.get_active_workspace()
        self.refresh()
        self.workspace_changed.emit(active_ws["id"], active_ws["path"])
        conv = self.wm.get_active_conversation()
        if conv:
            self.conversation_changed.emit(conv["id"])

    def _on_new_chat_clicked(self):
        active_ws = self.wm.get_active_workspace()
        ws_id = active_ws.get("id")
        new_conv = self.wm.create_conversation("Yeni Sohbet", workspace_id=ws_id)
        self._expanded.add(ws_id)
        self.refresh()
        self.conversation_changed.emit(new_conv["id"])
        self.new_chat_requested.emit()

    def _on_delete_conversation(self, conv_id: str):
        self.wm.delete_conversation(conv_id)
        active_conv = self.wm.get_active_conversation()
        self.refresh()
        if active_conv:
            self.conversation_changed.emit(active_conv["id"])
