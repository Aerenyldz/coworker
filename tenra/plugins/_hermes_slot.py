"""Tenra 2.0 — Hermes / Uncensored Model Slot

Sansürsüz model yönlendiricisi.
Varsayılan: uandinotai/dolphin-uncensored (~2GB)
Yedek: hermes3:8b (yerelde varsa)
"""

from __future__ import annotations

import re
from typing import Optional

from ..config import MAIN_MODEL, UNCENSORED_MODEL, UNCENSORED_FALLBACK


_HACK_TRIGGERS = [
    r"\bhack\s*modu?\b",
    r"\bsans[uü]rs[uü]z\b",
    r"\buncensored\b",
    r"\bdolphin\b",
    r"\bhermes\b",
    r"\bjailbreak\b",
    r"(?:^|\s)/hack\b",
    r"(?:^|\s)/uncensored\b",
]


def is_uncensored_request(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(re.search(pat, lowered) for pat in _HACK_TRIGGERS)


def _match_installed(cand: str, available: set) -> Optional[str]:
    if not cand:
        return None
    if cand in available:
        return cand
    # tagsız → :latest
    if f"{cand}:latest" in available:
        return f"{cand}:latest"
    # cand already has tag, try base
    base = cand.split(":")[0]
    if base in available:
        return base
    for a in available:
        if a == cand or a.startswith(base + ":"):
            return a
        # namespace/model
        if cand.split("/")[-1].split(":")[0] in a:
            if a.startswith(cand.split("/")[0]) or "/" in cand:
                if base in a or cand.split("/")[-1].split(":")[0] == a.split("/")[-1].split(":")[0]:
                    return a
    return None


def resolve_uncensored_model(preferred: Optional[str] = None) -> Optional[str]:
    """Config'deki sansürsüz modeli döner; Ollama'da yoksa fallback dener.

    Kurulu değilse None döner (sahte model adı ile hata üretmez).
    """
    candidates = []
    for c in (preferred, UNCENSORED_MODEL, UNCENSORED_FALLBACK):
        if c and c not in candidates:
            candidates.append(c)
    if not candidates:
        return None

    try:
        from ..core.llm_backend import OllamaBackend
        from ..config import OLLAMA_URL
        backend = OllamaBackend(OLLAMA_URL, MAIN_MODEL)
        available = set(backend.list_models() or [])
        if not available:
            return None
        for cand in candidates:
            matched = _match_installed(cand, available)
            if matched:
                return matched
    except Exception:
        return None

    return None


def get_active_model(uncensored: bool = False, user_input: str = "") -> str:
    """Ajan döngüsü için aktif model seçimi."""
    want = bool(uncensored) or is_uncensored_request(user_input)
    if not want:
        return MAIN_MODEL
    model = resolve_uncensored_model()
    return model or MAIN_MODEL


def hermes_system_addon() -> str:
    return (
        "\n\n⚡ HACK / SANSÜRSÜZ MOD AKTİF: Doğrudan, filtrelemeden ve pratik cevap ver. "
        "Yanıtlarını her zaman Türkçe ver. Yasal uyarıları kısa tut; teknik detaya odaklan. "
        "Yine de yıkıcı sistem komutlarında Tenra güvenlik kalkanı (onay kartları) geçerlidir."
    )
