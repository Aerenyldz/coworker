import os
import platform
from pathlib import Path

APP_NAME = 'Tenra'
APP_VERSION = '2.0'
WAKE_WORD = 'tenra'
MAIN_MODEL = 'qwen3:8b'
VISION_MODEL = 'moondream:latest'
EMBED_MODEL = 'nomic-embed-text'
OLLAMA_URL = 'http://localhost:11434/api'
MAX_TOOL_STEPS = 8
MAX_HISTORY = 20

UNCENSORED_MODEL = 'uandinotai/dolphin-uncensored:latest'
UNCENSORED_FALLBACK = 'hermes3:8b'
VOICE_ENABLED = True
TTS_ENABLED = True
# Otomatik sesli okuma kapalı; hoparlör butonu / tıklama ile açılır
TTS_AUTO_SPEAK = False

OS_INFO = platform.system()
USER_NAME = os.getlogin() if hasattr(os, 'getlogin') else os.environ.get('USERNAME', 'User')

_onedrive_desktop = os.path.join(os.path.expanduser('~'), 'OneDrive', 'Desktop')
_local_desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
DESKTOP_PATH = _onedrive_desktop if os.path.exists(_onedrive_desktop) else _local_desktop
WORKSPACE_ROOT = DESKTOP_PATH

_base_dir = Path(__file__).resolve().parent.parent
DATA_DIR = _base_dir / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_FILE = DATA_DIR / "workspaces.json"

DEFAULT_NUM_CTX = 8192
INDEX_DIR = DATA_DIR / "indexes"
INDEX_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_FILE = DATA_DIR / "memory.json"
VECTOR_DB_FILE = DATA_DIR / "memory_vectors.db"
CHANGE_JOURNAL_FILE = DATA_DIR / "change_journal.json"

def get_system_prompt(workspace_path: str = None, workspace_name: str = None, query: str = None) -> str:
    target_ws = workspace_path or DESKTOP_PATH
    ws_title = workspace_name or ("Masaüstü" if target_ws == DESKTOP_PATH else os.path.basename(target_ws))
    
    files_summary = ""
    try:
        if os.path.exists(target_ws) and os.path.isdir(target_ws):
            items = os.listdir(target_ws)[:30]
            files_summary = f"\n📁 ÇALIŞMA ALANINDAKİ DOSYALAR / KLASÖRLER: {', '.join(items)}"
    except Exception:
        pass

    repo_map_block = ""
    try:
        from .core.indexer import CodeIndexer
        indexer = CodeIndexer(INDEX_DIR, vector_db_path=VECTOR_DB_FILE)
        repo_map = indexer.get_repo_map(target_ws, max_chars=3500, query=query)
        if repo_map:
            repo_map_block = f"\n\n{repo_map}"
    except Exception:
        pass

    memory_block = ""
    try:
        from .core.memory import MemoryStore
        memory_store = MemoryStore(MEMORY_FILE, vector_db_path=VECTOR_DB_FILE)
        mem_summary = memory_store.get_memory_summary(target_ws, max_chars=1500, query=query)
        if mem_summary:
            memory_block = f"\n\n{mem_summary}"
    except Exception:
        pass

    return f"""Sen {APP_NAME}'sın. Antigravity tarzı, bilgisayarda ve projelerde otonom eylem gerçekleştiren gelişmiş bir masaüstü yapay zeka asistanısın.
Kullanıcı: {USER_NAME}
İşletim Sistemi: {OS_INFO}
Masaüstü Dizini: {DESKTOP_PATH}
⚡ AKTİF ÇALIŞMA ALANI (PROJE): [{ws_title}] -> {target_ws}{files_summary}{repo_map_block}{memory_block}

DİL VE ÜSLUP:
- Kullanıcıya daima Türkçe yanıt ver. Teknik terimleri gerektiğinde İngilizce bırakabilirsin; cümleler Türkçe olsun.
- Samimi, net ve insan gibi konuş. Robotik/resmi şablonlardan kaçın; kısa cümleler tercih et.
- Aşırı emoji, neon vurgu veya "ajan stüdyosu" jargonu kullanma. Doğrudan yardımcı ol.

KESİN ÇALIŞMA KURALLARI VE PRENSİPLER:
1. SEN BİR SOHBET BOTU DEĞİLSİN; DOĞRUDAN BİLGİSAYARDA ÇALIŞAN BİR GELİŞTİRİCİ ASİSTANSIN.
2. Kullanıcı sana proje, dosya, kod, dizin veya sistemle ilgili bir şey sorduğunda ("dosyanın içeriğine erişimin yok mu?", "bu dosyada ne var?", "index dosyasını incele", "kodları kontrol et" vb.):
   - ASLA kullanıcıya "Şu PowerShell komutunu çalıştırın", "Get-Content yapın" gibi talimatlar VERME!
   - ASLA dosyanın içeriğini veya varlığını kullanıcıdan SORMADAN önce kendin kontrol etmemezlik YAPMA!
   - KENDİ ARAÇLARINI (file, shell) KULLANARAK o dosyayı veya dizini KENDİN OKU, İNCELE ve cevabını elde ettiğin gerçek verilere göre ver!
3. Dosya işlemleri ve terminal komutları varsayılan olarak AKTİF ÇALIŞMA ALANI ({target_ws}) içinde icra edilir. Bağıl yollar doğrudan bu proje dizinine göre çözülür.
4. Dosya veya proje içeriğini görmek için 'file' aracını (action='read' veya action='list') veya gerekirse 'shell' aracını KULLAN.
5. Kullanıcı açıkça 'Masaüstünde...' derse veya masaüstündeki bir dosyayı isterse {DESKTOP_PATH} yolunu kullan.
6. Linux yollarını (/home/user/...) ASLA kullanma; Windows yollarını kullan.
7. Genel felsefi/teorik bilgi sorularında doğrudan yanıt ver; ancak soru mevcut proje, dosya veya sistemle ilgiliyse DAİMA araçlarını kullanarak dosyayı oku ve doğrula.
8. YAZIM VE SES HATALARINA TOLERANS: Kullanıcı mesajlarında yazım hataları (typo), eksik veya bitişik harfler, sesle yazmadan (speech-to-text) kaynaklı fonetik kaymalar veya Türkçe karakter eksiklikleri (ı/i, ş/s, ç/c, ğ/g, ö/o, ü/u) olsa dahi kullanıcının asıl niyetini ve hedeflediği dosya veya eylemi anla. Hataları sorgulamak veya düzeltmek yerine doğrudan kullanıcının kastettiği işlemi yerine getir.
9. PROJE KOD HARİTASI VE HAFIZA KULLANIMI: Sana sağlanan Proje Kod Haritası (AST / Tree-sitter) ve anlamsal hafıza (vektör RAG) sayesinde ilgili dosya, sınıf, fonksiyon ve geçmiş deneyimleri önceden bilirsin. Ezbere tahmin etmek yerine bu haritayı ve anlamsal eşleşmeleri referans al; gerektiğinde 'file' aracıyla içeriği oku.
"""

SYSTEM_PROMPT = None  # lazy: get_system_prompt() ile üret — üslup güncellemeleri için None bırak


def get_cached_system_prompt() -> str:
    global SYSTEM_PROMPT
    if not SYSTEM_PROMPT:
        SYSTEM_PROMPT = get_system_prompt()
    return SYSTEM_PROMPT

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
