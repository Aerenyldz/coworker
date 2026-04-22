"""
Tenra V5 — Merkezi Ayarlar
"""

import os

# --- Model Configuration ---
RESPONDER_MODEL = "hermes3:8b"  # Ollama'dan çekilecek model
VISION_MODEL = "llama3.2-vision:latest"  # Ekran analizi ve OCR matematik çözmek için multimodal model
OLLAMA_URL = "http://localhost:11434/api"
LOCAL_ROUTER_PATH = os.path.join(os.path.dirname(__file__), "merged_model")
HF_ROUTER_REPO = "nlouis/pocket-ai-router"  # Yedek router repo

# --- Runtime Flags ---
SKIP_ROUTER_ON_ERROR = True  # Router hata verirse direkt Ollama kullan
ROUTER_TIMEOUT = 30  # Router max çalışma süresi (saniye)
USE_LOCAL_ROUTER = False  # Local FunctionGemma router kullanılsın mı? (False = sadece Hermes)

# --- Enhanced Safety Settings ---
MAX_HISTORY = 20  # Maximum conversation history length
MAX_TOOL_STEPS = 5  # Maximum tool call steps per response

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

# --- Screenshot / Vision ---
VISION_SYSTEM_PROMPT = "Sen sadece bir gözsün. Görevini görseldeki TÜM metinleri, denklemleri, grafikleri ve bilgileri en ince detayına kadar metne (markdown formatında) çevirmektir. Asla soruyu çözmeye çalışma veya yorum yapma. Sadece gördüklerini kusursuzca metne dök."

# --- Browser Session Policy ---
# Antigravity benzeri davranis: web islemlerini mevcut loginli sekme yerine temiz bir profilde ac.
BROWSER_PREFERRED = "chrome"          # auto | edge | chrome | firefox | default
BROWSER_FRESH_SESSION = False        # True ise her open_url cagrisinda yeni/temiz profil
BROWSER_PRIVATE_MODE = False         # Fresh session kapaliysa gizli modla ac
BROWSER_PROFILE_ROOT = os.path.join(os.path.dirname(__file__), "data", "browser_profiles")

# --- Paths ---
USER_HOME = os.path.expanduser("~")
_ONEDRIVE_DESKTOP = os.path.join(USER_HOME, "OneDrive", "Desktop")
_CLASSIC_DESKTOP = os.path.join(USER_HOME, "Desktop")
DESKTOP_PATH = _ONEDRIVE_DESKTOP if os.path.isdir(_ONEDRIVE_DESKTOP) else _CLASSIC_DESKTOP

# --- Console Colors ---
GRAY = "\033[90m"
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"