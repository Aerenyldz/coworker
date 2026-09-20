from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QCursor, QPixmap
from PySide6.QtWidgets import QWidget, QApplication, QLabel

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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.closed.emit()
            self.close()

class ClickableLabel(QLabel):
    clicked = Signal()
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
