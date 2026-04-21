"""Helpers for keeping the responder model warm in Ollama."""

import threading
import time

import requests

from config import OLLAMA_URL, QWEN_KEEP_ALIVE, QWEN_TIMEOUT_SECONDS, RESPONDER_MODEL
from core.model_manager import unload_model

_state_lock = threading.Lock()
_last_used_ts = 0.0


def ensure_qwen_loaded() -> bool:
    """Ensure responder model is loaded in Ollama memory."""
    try:
        response = requests.post(
            f"{OLLAMA_URL}/generate",
            json={
                "model": RESPONDER_MODEL,
                "prompt": "",
                "stream": False,
                "keep_alive": QWEN_KEEP_ALIVE,
                "options": {"num_predict": 0},
            },
            timeout=20,
        )
        if response.status_code != 200:
            return False
        mark_qwen_used()
        return True
    except Exception:
        return False


def mark_qwen_used() -> None:
    """Record last model usage time."""
    with _state_lock:
        global _last_used_ts
        _last_used_ts = time.time()


def unload_qwen(force: bool = False) -> None:
    """Unload responder model when idle long enough or by force."""
    with _state_lock:
        now = time.time()
        idle_for = now - _last_used_ts if _last_used_ts else now

    if force or idle_for >= QWEN_TIMEOUT_SECONDS:
        unload_model(RESPONDER_MODEL)
