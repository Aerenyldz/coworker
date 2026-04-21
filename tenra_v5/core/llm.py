"""
Tenra V5 — LLM Arayüzü
Router + Ollama Responder entegrasyonu.
"""

import requests
import threading

from config import (
    RESPONDER_MODEL, OLLAMA_URL, LOCAL_ROUTER_PATH,
    GRAY, RESET, USE_LOCAL_ROUTER
)

http_session = requests.Session()
router = None


def is_router_loaded():
    return router is not None


def should_bypass_router(text):
    return not USE_LOCAL_ROUTER


def route_query(user_input):
    """Router ile kullanıcı isteğini yönlendir."""
    global router

    if not USE_LOCAL_ROUTER:
        return "nonthinking", {"prompt": user_input}

    if not router:
        try:
            from core.router import FunctionGemmaRouter
            router = FunctionGemmaRouter(model_path=LOCAL_ROUTER_PATH, compile_model=False)
        except Exception as e:
            print(f"{GRAY}[Router Init Hatası: {e}]{RESET}")
            return "nonthinking", {"prompt": user_input}

    try:
        (func_name, params), elapsed = router.route_with_timing(user_input)
        print(f"{GRAY}[Router] {func_name} ({elapsed*1000:.0f}ms){RESET}")
        return func_name, params
    except Exception as e:
        print(f"{GRAY}[Router Hatası: {e}]{RESET}")
        return "nonthinking", {"prompt": user_input}


def execute_function(name, params):
    """Eski uyumluluk fonksiyonu."""
    from core.function_executor import executor
    result = executor.execute(name, params)
    return result.get("message", f"Fonksiyon çalıştırıldı: {name}")


def preload_models():
    """Modelleri önceden yükle."""
    global router

    print(f"{GRAY}[Tenra] Modeller yükleniyor...{RESET}")

    threads = []

    def load_router():
        global router
        if not USE_LOCAL_ROUTER:
            print(f"{GRAY}[Router] Local router devre dışı (USE_LOCAL_ROUTER=False){RESET}")
            return
        try:
            from core.router import FunctionGemmaRouter
            router = FunctionGemmaRouter(model_path=LOCAL_ROUTER_PATH, compile_model=False)
        except Exception as e:
            print(f"{GRAY}[Router] Yerel model yüklenemedi: {e}{RESET}")

    def load_responder():
        try:
            print(f"{GRAY}[Tenra] Responder model ({RESPONDER_MODEL}) yükleniyor...{RESET}")
            response = http_session.post(f"{OLLAMA_URL}/generate", json={
                "model": RESPONDER_MODEL,
                "prompt": "merhaba",
                "stream": False,
                "keep_alive": "30m",
                "options": {"num_predict": 1}
            }, timeout=120)
            if response.status_code == 200:
                print(f"{GRAY}[Tenra] Responder model yüklendi.{RESET}")
            else:
                print(f"{GRAY}[Tenra] Responder model yüklenemedi: {response.status_code}{RESET}")
        except Exception as e:
            print(f"{GRAY}[Tenra] Responder preload hatası: {e}{RESET}")

    threads.append(threading.Thread(target=load_router))
    threads.append(threading.Thread(target=load_responder))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"{GRAY}[Tenra] Modeller hazır.{RESET}")
