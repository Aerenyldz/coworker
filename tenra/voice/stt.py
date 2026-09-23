"""Tenra 2.0 — Ses Tanıma (Speech-to-Text)

Öncelik: faster-whisper (çevrimdışı) → Google Web Speech (online yedek).
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger("TenraVoice")

_whisper_model = None


def _get_whisper(model_size: str = "tiny"):
    """Lazy-load faster-whisper model (tiny ≈ 75MB, base ≈ 150MB)."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    try:
        from faster_whisper import WhisperModel
        # CPU int8 — RTX varsa cuda dener
        device = "cpu"
        compute = "int8"
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                compute = "float16"
        except Exception:
            pass
        _whisper_model = WhisperModel(model_size, device=device, compute_type=compute)
        logger.info(f"faster-whisper loaded: {model_size} on {device}")
        return _whisper_model
    except Exception as e:
        logger.debug(f"faster-whisper unavailable: {e}")
        return None


def transcribe_wav_whisper(wav_path: str, language: str = "tr") -> Optional[str]:
    model = _get_whisper(os.environ.get("TENRA_WHISPER_MODEL", "tiny"))
    if model is None:
        return None
    try:
        segments, _info = model.transcribe(wav_path, language=language or "tr", beam_size=1)
        parts = [seg.text.strip() for seg in segments if seg.text]
        text = " ".join(parts).strip()
        return text or None
    except Exception as e:
        logger.debug(f"whisper transcribe failed: {e}")
        return None


class VoiceListenerThread(QThread):
    """Arka planda mikrofonu dinleyip Türkçe metin üreten QThread."""

    listening_started = Signal()
    listening_finished = Signal()
    text_recognized = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, language: str = "tr-TR", parent=None, prefer_offline: bool = True):
        super().__init__(parent)
        self.language = language
        self.prefer_offline = prefer_offline
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            import speech_recognition as sr
        except ImportError:
            self.error_occurred.emit("SpeechRecognition kütüphanesi kurulu değil.")
            return

        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 1.0

        try:
            with sr.Microphone() as source:
                if self._is_cancelled:
                    return

                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self.listening_started.emit()
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=15)

            if self._is_cancelled:
                return

            text = ""
            whisper_lang = "tr" if self.language.lower().startswith("tr") else self.language.split("-")[0]

            # 1) Offline Whisper
            if self.prefer_offline:
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                        tmp_path = tmp.name
                        tmp.write(audio.get_wav_data())
                    try:
                        text = transcribe_wav_whisper(tmp_path, language=whisper_lang) or ""
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug(f"whisper path failed: {e}")

            # 2) Google online fallback
            if not text:
                try:
                    text = recognizer.recognize_google(audio, language=self.language)
                    text = text.strip() if text else ""
                except sr.RequestError as e:
                    if not text:
                        self.error_occurred.emit(
                            f"Çevrimdışı Whisper yok ve Google'a ulaşılamadı: {e}"
                        )
                        return
                except sr.UnknownValueError:
                    pass

            if text:
                self.text_recognized.emit(text)
            else:
                self.error_occurred.emit("Söylenenler anlaşılamadı. Lütfen tekrar deneyin.")

        except sr.WaitTimeoutError:
            self.error_occurred.emit("Zaman aşımı: Ses algılanamadı.")
        except Exception as e:
            self.error_occurred.emit(f"Mikrofon hatası: {e}")
        finally:
            self.listening_finished.emit()
