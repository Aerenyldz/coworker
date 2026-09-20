"""Tenra 2.0 — Ses Tanıma (Speech-to-Text) Modülü.

Mikrofon üzerinden Türkçe konuşmayı dinler ve metne dönüştürür.
"""

from __future__ import annotations

import logging
from typing import Optional
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger("TenraVoice")


class VoiceListenerThread(QThread):
    """Arka planda mikrofonu dinleyip Türkçe metin üreten QThread iş parçacığı."""

    listening_started = Signal()
    listening_finished = Signal()
    text_recognized = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, language: str = "tr-TR", parent=None):
        super().__init__(parent)
        self.language = language
        self._is_cancelled = False

    def cancel(self):
        """Dinlemeyi iptal eder."""
        self._is_cancelled = True

    def run(self):
        try:
            import speech_recognition as sr
        except ImportError:
            self.error_occurred.emit("SpeechRecognition kütüphanesi kurulu değil.")
            return

        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 1.0  # Konuşma arası bekleme toleransı

        try:
            with sr.Microphone() as source:
                if self._is_cancelled:
                    return

                # Ortam gürültüsünü hızlıca kalibre et (0.5 sn)
                recognizer.adjust_for_ambient_noise(source, duration=0.5)

                self.listening_started.emit()

                # Dinleme (maksimum 8 sn başlangıç bekleme, 15 sn konuşma süresi)
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=15)

            if self._is_cancelled:
                return

            # Google Web Speech API ile Türkçe transkripsiyon
            text = recognizer.recognize_google(audio, language=self.language)
            text = text.strip() if text else ""

            if text:
                self.text_recognized.emit(text)
            else:
                self.error_occurred.emit("Ses algılanamadı.")

        except sr.WaitTimeoutError:
            self.error_occurred.emit("Zaman aşımı: Ses algılanamadı.")
        except sr.UnknownValueError:
            self.error_occurred.emit("Söylenenler anlaşılamadı. Lütfen tekrar deneyin.")
        except sr.RequestError as e:
            self.error_occurred.emit(f"Ses tanıma servisine ulaşılamadı: {e}")
        except Exception as e:
            self.error_occurred.emit(f"Mikrofon hatası: {e}")
        finally:
            self.listening_finished.emit()
