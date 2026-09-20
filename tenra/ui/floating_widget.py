from PySide6.QtCore import Qt, QPoint, QRect, Signal, QTimer
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QLinearGradient, QFont, QCursor
from PySide6.QtWidgets import QWidget, QApplication
from tenra.ui.colors import Colors

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
