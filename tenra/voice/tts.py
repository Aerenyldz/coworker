"""Tenra 2.0 — Text-to-Speech (yalnızca yerel / offline).

Öncelik:
1) Yerel Türkçe Piper modeli (data/piper/...)
2) Windows SAPI — yalnızca Türkçe ses kuruluysa

İnternet TTS (edge-tts vb.) yok. İleride özel ses klonu buraya bağlanacak.
"""

from __future__ import annotations

import logging
import os
import threading
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger("TenraTTS")

_REPO_PIPER = Path(__file__).resolve().parent.parent.parent / "data" / "piper"


def _find_piper_model() -> Optional[Path]:
    """Yalnızca Türkçe Piper modelini dener (İngilizce / online yok)."""
    env = os.environ.get("PIPER_MODEL", "").strip()
    if env and Path(env).exists():
        return Path(env)

    candidates = [
        _REPO_PIPER / "tr_TR-dfki-medium.onnx",
        Path.home() / "piper" / "tr_TR-dfki-medium.onnx",
        Path.home() / "piper" / "tr_TR-fettah-medium.onnx",
        # İleride kullanıcı ses klonu: data/piper/custom.onnx veya PIPER_MODEL
        _REPO_PIPER / "custom.onnx",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _pick_turkish_sapi_voice(engine) -> bool:
    """pyttsx3 içinde Türkçe ses varsa seçer. True = bulundu."""
    try:
        for voice in engine.getProperty("voices") or []:
            name = (getattr(voice, "name", "") or "").lower()
            vid = (getattr(voice, "id", "") or "").lower()
            culture = ""
            try:
                culture = str(getattr(voice, "languages", [""])[0] or "").lower()
            except Exception:
                pass
            if any(
                tip in name or tip in vid or tip in culture
                for tip in ("turkish", "turk", "tr-tr", "tr_tr", "tr\\")
            ):
                engine.setProperty("voice", voice.id)
                return True
    except Exception:
        pass
    return False


class SpeechSynthesizer:
    """Yerel TTS: Türkçe Piper → (opsiyonel) Türkçe SAPI."""

    def __init__(self):
        self._engine = None
        self._piper_voice = None
        self._backend = None
        self._lock = threading.Lock()
        self._stop_flag = threading.Event()
        self._init_backend()

    def _init_backend(self):
        model_path = _find_piper_model()
        if model_path is not None:
            try:
                from piper import PiperVoice
                self._piper_voice = PiperVoice.load(str(model_path))
                self._backend = "piper"
                logger.info(f"TTS backend: piper ({model_path.name})")
                return
            except Exception as e:
                logger.debug(f"piper load failed: {e}")

        # Türkçe SAPI varsa (nadiren kurulu)
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            if _pick_turkish_sapi_voice(engine):
                self._engine = engine
                self._backend = "pyttsx3"
                logger.info("TTS backend: pyttsx3 (Türkçe)")
                return
            try:
                engine.stop()
            except Exception:
                pass
            logger.warning("Yerel Türkçe TTS yok (Piper model / TR SAPI).")
        except Exception as e:
            logger.debug(f"pyttsx3 unavailable: {e}")

        self._backend = None

    @property
    def available(self) -> bool:
        return self._backend is not None

    @property
    def backend_name(self) -> str:
        return self._backend or "none"

    def stop(self):
        self._stop_flag.set()
        try:
            if self._backend == "pyttsx3" and self._engine is not None:
                self._engine.stop()
        except Exception:
            pass

    def speak(self, text: str, block: bool = False) -> bool:
        text = (text or "").strip()
        if not text or not self._backend:
            return False
        try:
            from .turkish_text import normalize_for_speech
            text = normalize_for_speech(text)
        except Exception:
            pass
        if len(text) > 800:
            text = text[:800] + "..."

        self._stop_flag.clear()

        def _run():
            with self._lock:
                if self._stop_flag.is_set():
                    return
                try:
                    if self._backend == "piper" and self._piper_voice is not None:
                        self._speak_piper(text)
                    elif self._backend == "pyttsx3" and self._engine is not None:
                        self._engine.say(text)
                        self._engine.runAndWait()
                except Exception as e:
                    logger.debug(f"TTS speak error: {e}")

        if block:
            _run()
        else:
            threading.Thread(target=_run, daemon=True).start()
        return True

    def _speak_piper(self, text: str):
        import tempfile
        import winsound

        with tempfile.TemporaryDirectory() as td:
            wav_path = Path(td) / "out.wav"
            with wave.open(str(wav_path), "wb") as wav_file:
                self._piper_voice.synthesize_wav(text, wav_file)
            if not self._stop_flag.is_set():
                winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)


_default_synth: Optional[SpeechSynthesizer] = None


def get_synthesizer() -> SpeechSynthesizer:
    global _default_synth
    if _default_synth is None:
        _default_synth = SpeechSynthesizer()
    return _default_synth


def speak(text: str, block: bool = False) -> bool:
    return get_synthesizer().speak(text, block=block)


def stop_speaking() -> None:
    get_synthesizer().stop()
