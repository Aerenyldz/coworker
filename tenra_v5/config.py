"""
Tenra V5 — Merkezi Ayarlar
"""

import os

# --- Model Configuration ---
RESPONDER_MODEL = "qwen2.5:7b"  # Ollama'dan çekilecek model
OLLAMA_URL = "http://localhost:11434/api"
LOCAL_ROUTER_PATH = os.path.join(os.path.dirname(__file__), "merged_model")
HF_ROUTER_REPO = "nlouis/pocket-ai-router"  # Yedek router repo
MAX_HISTORY = 20

# --- Runtime Flags ---
SKIP_ROUTER_ON_ERROR = True  # Router hata verirse direkt Ollama kullan
ROUTER_TIMEOUT = 30  # Router max çalışma süresi (saniye)

# --- Tenra Identity ---
APP_NAME = "Tenra"
APP_VERSION = "5.0"
WAKE_WORD = "tenra"

# --- TTS Configuration ---
TTS_VOICE_MODEL = "en_GB-northern_english_male-medium"
TTS_MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx"
TTS_CONFIG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx.json"

# --- STT Configuration ---
REALTIMESTT_MODEL = "base"
WAKE_WORD_SENSITIVITY = 0.4
WAKE_WORD_CONFIRMATION_COUNT = 1
STT_SAMPLE_RATE = 16000
STT_CHUNK_SIZE = 4096
STT_RECORD_TIMEOUT = 5.0

# --- Voice Assistant ---
VOICE_ASSISTANT_ENABLED = True
QWEN_TIMEOUT_SECONDS = 300
QWEN_KEEP_ALIVE = "30m"

# --- Paths ---
import os
USER_HOME = os.path.expanduser("~")
DESKTOP_PATH = os.path.join(USER_HOME, "OneDrive", "Desktop")

# --- Console Colors ---
GRAY = "\033[90m"
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
