"""Tenra 2.0 — Windows System Tray (arka plan simgesi)."""

from __future__ import annotations

from PySide6.QtCore import Signal, QObject, Qt
from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QSystemTrayIcon, QMenu


def _make_tray_icon() -> QIcon:
    """Basit Tenra 'T' ikonu (harici dosya gerekmez)."""
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(0, 217, 255))
    p.setPen(QColor(0, 40, 50))
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor(0, 20, 30))
    p.setFont(QFont("Segoe UI", 28, QFont.Bold))
    p.drawText(pm.rect(), int(Qt.AlignCenter), "T")
    p.end()
    return QIcon(pm)


class TrayController(QObject):
    """Sistem tepsisi: göster/gizle, çıkış."""

    show_requested = Signal()
    hide_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tray = QSystemTrayIcon(_make_tray_icon(), parent)
        self.tray.setToolTip("Tenra — Agent Studio (arka plan)")

        menu = QMenu()
        act_show = QAction("Tenra'yı Aç", menu)
        act_hide = QAction("Pencereyi Gizle", menu)
        act_quit = QAction("Çıkış", menu)
        act_show.triggered.connect(self.show_requested.emit)
        act_hide.triggered.connect(self.hide_requested.emit)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_show)
        menu.addAction(act_hide)
        menu.addSeparator()
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_requested.emit()

    def show(self) -> bool:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
            return True
        return False

    def notify(self, title: str, message: str, msec: int = 3000):
        if self.tray.isVisible():
            self.tray.showMessage(title, message, QSystemTrayIcon.Information, msec)
