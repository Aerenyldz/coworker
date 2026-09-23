from PySide6.QtGui import QColor

class Colors:
    # Antigravity tarzı soft dark
    BG_DARK    = QColor(15, 15, 15)       # #0f0f0f
    BG_PANEL   = QColor(18, 18, 18)       # #121212
    BG_CARD    = QColor(24, 24, 24)       # #181818
    BG_CARD2   = QColor(36, 36, 36)       # #242424 — hover / aktif
    BG_INPUT   = QColor(28, 28, 28)       # #1c1c1c
    BG_HEADER  = QColor(18, 18, 18)       # #121212
    BG_SIDEBAR = QColor(20, 20, 20)       # #141414

    # Vurgu — neon cyan yerine yumuşak beyaz/mavi-gri
    ACCENT       = QColor(210, 210, 215)  # soft light
    ACCENT_DIM   = QColor(255, 255, 255, 18)
    ACCENT_GREEN = QColor(110, 180, 120)
    ACCENT_RED   = QColor(220, 100, 95)
    ACCENT_YELLOW= QColor(200, 160, 80)
    ACCENT_PURPLE= QColor(180, 160, 200)
    ACCENT_BLUE  = QColor(140, 170, 210)

    # Metin
    TEXT         = QColor(232, 232, 232)  # #e8e8e8
    TEXT_MUTED   = QColor(140, 140, 145)  # #8c8c91
    TEXT_DIM     = QColor(90, 90, 95)     # #5a5a5f

    # Kenarlıklar
    BORDER       = QColor(42, 42, 45)     # #2a2a2d
    BORDER_LIGHT = QColor(55, 55, 60)     # #37373c

    # Özel
    TERMINAL_BG  = QColor(12, 12, 12)
    DIFF_ADD_BG  = QColor(20, 50, 28)
    DIFF_DEL_BG  = QColor(55, 22, 22)
    USER_BG      = QColor(255, 255, 255, 12)
    CODE_FG      = QColor(180, 150, 150)  # sakin inline code
