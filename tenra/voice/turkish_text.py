"""Türkçe metin normalizasyonu — TTS için ASCII → ç/ğ/ı/ö/ş/ü."""

from __future__ import annotations

import logging
import unicodedata
from typing import Optional

logger = logging.getLogger("TenraTTS")

_TR_LETTERS = set("çÇğĞıİöÖşŞüÜ")
_ASCII_CANDIDATES = set("cgiosuCGIOSU")  # deasciify adayları

_deasciifier_cls = None
_deasciifier_tried = False


def _load_deasciifier():
    global _deasciifier_cls, _deasciifier_tried
    if _deasciifier_tried:
        return _deasciifier_cls
    _deasciifier_tried = True
    try:
        from turkish.deasciifier import Deasciifier
        _deasciifier_cls = Deasciifier
    except Exception as e:
        logger.debug(f"turkish-deasciifier yok: {e}")
        _deasciifier_cls = None
    return _deasciifier_cls


def turkish_lower(text: str) -> str:
    """Türkçe büyük/küçük harf (I→ı, İ→i)."""
    return text.replace("I", "ı").replace("İ", "i").lower()


def needs_deasciify(text: str) -> bool:
    """Metinde Türkçe harf yoksa ve ASCII adayları varsa deasciify gerekir."""
    if not text:
        return False
    has_tr = any(ch in _TR_LETTERS for ch in text)
    has_ascii_cand = any(ch in _ASCII_CANDIDATES for ch in text)
    # Zaten bol Türkçe harf varsa dokunma (yanlış düzeltme riski)
    if has_tr:
        # Kısmi ASCII karışımı: yine deasciify faydalı (dogru → doğru)
        return has_ascii_cand and sum(1 for c in text if c in _TR_LETTERS) < max(3, len(text) // 20)
    return has_ascii_cand


def normalize_for_speech(text: str) -> str:
    """TTS öncesi: Unicode NFC + Türkçe deasciify (calisiyorum → çalışıyorum)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text.strip())
    cls = _load_deasciifier()
    if cls is None:
        return text
    try:
        # Deasciifier her zaman güvenli: mevcut ç/ğ/ı korunur, ASCII düzeltilir
        return cls(text).convert_to_turkish()
    except Exception as e:
        logger.debug(f"deasciify failed: {e}")
        return text
