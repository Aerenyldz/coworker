from PySide6.QtGui import QColor

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
