"""Hermes-focused tool-calling agent for Tenra V5.

This module handles:
- Building Ollama /api/chat requests with tool schemas
- Executing tool calls returned by the model
- Running a multi-step tool loop (up to MAX_TOOL_STEPS)
- Fallback ROUTE: parsing when model can't produce native tool_calls
- Screenshot analysis via vision-capable models
"""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Dict, List, Tuple

import requests

from config import (
    HERMES_SYSTEM_PROMPT,
    MAX_TOOL_STEPS,
    OLLAMA_URL,
    RESPONDER_MODEL,
    SCREEN_ANALYZER_MODEL,
    USE_LOCAL_ROUTER,
)


# ═══════════════════════════════════════════════
# TOOL SCHEMA DEFINITIONS — Ollama native format
# ═══════════════════════════════════════════════

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "Yeni klasor olusturur. Masaustunde veya belirtilen yolda klasor olusturma isteklerinde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Olusturulacak klasorun yolu veya adi. Ornek: 'Projeler' veya 'C:/Users/ahmet/Desktop/YeniKlasor'"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Yeni dosya olusturur. Masaustunde veya belirtilen yolda dosya olusturma isteklerinde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Dosya yolu veya adi. Ornek: 'notlar.txt'"},
                    "content": {"type": "string", "description": "Dosyanin icerigi. Bos birakilabilir."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_file",
            "description": "Kullanicinin bilgisayarinda dosya arar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Aranacak dosya adi veya parcasi"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Dosyayi veya klasoru kalici olarak siler.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Silinecek dosya veya klasor yolu"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_to_trash",
            "description": "Dosyayi cop kutusuna tasir (geri donusturulabilir silme).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Cop kutusuna tasinacak dosya yolu"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_desktop",
            "description": "Masaustundeki tum dosya ve klasorleri listeler.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Dosya icerigini satir numaralariyla okur. Buyuk dosyalarda offset ve limit ile sayfalanmis okuma yapar. Terminal'de cat/head/tail yerine bunu kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Okunacak dosya yolu"},
                    "offset": {"type": "integer", "description": "Baslangic satir numarasi (1-indexed, varsayilan: 1)", "default": 1},
                    "limit": {"type": "integer", "description": "Okunacak max satir sayisi (varsayilan: 200)", "default": 200},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Bir dosyanin TUM icerigini yazar. Dosya yoksa olusturur, varsa ustune yazar. Hedefli duzenleme icin 'patch' aracini kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Yazilacak dosya yolu"},
                    "content": {"type": "string", "description": "Dosyaya yazilacak tam icerik"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch",
            "description": "Dosyada hedefli bul-ve-degistir duzenleme yapar. Tum dosyayi yeniden yazmak yerine sadece belirli kismi degistirir. sed/awk yerine bunu kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Duzenlenecek dosya yolu"},
                    "old_string": {"type": "string", "description": "Dosyada bulunacak mevcut metin. Benzersiz olmali."},
                    "new_string": {"type": "string", "description": "Yerine konacak yeni metin. Bos string = silme."},
                    "replace_all": {"type": "boolean", "description": "True ise tum eslesmeler degistirilir (varsayilan: false)", "default": False},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Dosya icinde regex araması veya dosya adi araması yapar. grep/find yerine bunu kullan. target='content' dosya icinde, target='files' dosya adinda arar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Aranacak regex deseni (icerik icin) veya glob deseni (dosya adi icin, ornek: '*.py')"},
                    "target": {"type": "string", "description": "'content' dosya ici arama, 'files' dosya adi araması", "default": "content"},
                    "path": {"type": "string", "description": "Aranacak dizin yolu (varsayilan: masaustu)", "default": "."},
                    "file_glob": {"type": "string", "description": "Dosya turu filtresi (ornek: '*.py', '*.txt')"},
                    "limit": {"type": "integer", "description": "Maksimum sonuc sayisi (varsayilan: 30)", "default": 30},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Bir dizinin icerigini listeler (ls/dir karsiligi). Dosya ve klasorleri boyut ve degistirilme tarihiyle gosterir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Listelenecek dizin yolu (varsayilan: masaustu)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_file",
            "description": "Dosya veya klasorun adini degistirir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Yeniden adlandirilacak dosya yolu"},
                    "new_name": {"type": "string", "description": "Yeni dosya adi"},
                },
                "required": ["path", "new_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "PowerShell komutu calistirir. Sistem komutlari, pip install, git komutlari vb. icin kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Calistirilacak PowerShell komutu"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Windows uygulamasi acar. Baslat menusunden arayarak bulur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Acilacak uygulamanin adi. Ornek: 'notepad', 'chrome', 'spotify'"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Verilen URL adresini varsayilan tarayicida acar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Acilacak web adresi. Ornek: 'https://google.com'"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "DuckDuckGo uzerinde web araması yapar ve sonuclari getirir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Aranacak metin"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Sistem durum ozeti getirir: saat, aktif timerlar, alarmlar, gorevler, takvim vb.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_light",
            "description": "Akilli isik cihazlarini kontrol eder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Yapilacak islem: on, off, toggle, dim"},
                    "device_name": {"type": "string", "description": "Cihaz adi"},
                    "brightness": {"type": "integer", "description": "Parlaklik seviyesi 0-100"},
                    "color": {"type": "string", "description": "Renk adi veya hex kodu"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Geri sayim zamanlayicisi kurar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {"type": "string", "description": "Sure. Ornek: '10 dakika', '1 saat', '30 saniye'"},
                    "label": {"type": "string", "description": "Zamanlayici etiketi"},
                },
                "required": ["duration"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "Belirli bir saat icin alarm kurar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time": {"type": "string", "description": "Alarm saati. Ornek: '07:30', '14:00'"},
                    "label": {"type": "string", "description": "Alarm etiketi"},
                },
                "required": ["time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Takvime yeni etkinlik ekler.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Etkinlik basligi"},
                    "date": {"type": "string", "description": "Tarih. Ornek: 'yarin', '2026-04-22'"},
                    "time": {"type": "string", "description": "Saat. Ornek: '15:00'"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Yapilacaklar listesine yeni gorev ekler.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Gorev aciklamasi"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_screen",
            "description": "PyAutoGUI kullanarak bilgisayar ekraninda spesifik bir x, y koordinatina farenin sol tusuyla tiklar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Tiklanacak x koordinati (pixel)."},
                    "y": {"type": "integer", "description": "Tiklanacak y koordinati (pixel)."},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Klavyeden hizli bir sekilde metin yazar ve opsiyonel olarak Enter tusuna basar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Yazilacak metin."},
                    "press_enter": {"type": "boolean", "description": "Metni yazdiktan sonra Enter'a basilsin mi?"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_hotkey",
            "description": "Klavye kisayolu gonderir (Orn: ['ctrl', 'c'] veya ['win', 'd']). Pencereleri kapatmak (alt+f4) veya sekmeleri yonetmek icin kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "array", "items": {"type": "string"}, "description": "Basilacak tuslarin listesi."},
                },
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "Python kodunu dogrudan bellekte (REPL) calistirir ve ciktisini dondurur. Veri analizi, matematik hesaplamalari, grafik uretme veya script calistirma isleri icin kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Calistirilacak gecerli Python kodu."},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_website",
            "description": "Verilen bir URL'ye baglanip web sayfasinin icerigini okur. Arama motoru sonuclarini detayli okumak veya makale/dokuman incelemek icin kullanilir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Okunacak web sitesinin tam URL'si."},
                },
                "required": ["url"],
            },
        },
    },
]


# ═══════════════════════════════════════════════
# TEXT SANITIZATION
# ═══════════════════════════════════════════════

def sanitize_assistant_text(text: str) -> str:
    """Clean known noisy output patterns from model text."""
    if not text:
        return ""

    # Remove thinking tags (Qwen/DeepSeek compat — harmless for Hermes)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()

    # Remove stray tool call XML that wasn't parsed
    cleaned = re.sub(r"<tool_call>.*?</tool_call>", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()

    # If the entire response is a markdown code block, unwrap it
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    # If entire response is a JSON object with a message/response key, extract it
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            payload = json.loads(cleaned)
            if isinstance(payload, dict):
                for key in ("final", "response", "message", "content", "answer", "reply"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        except Exception:
            pass

    # Bazen model {s: "mesaj"} seklinde sacma sapan formatlar donuyor. Bunu temizleyelim.
    s_match = re.search(r"\{s:\s*[\"'](.*?)[\"']\s*\}", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if s_match:
        cleaned = s_match.group(1).strip()

    return cleaned


# ═══════════════════════════════════════════════
# ARGUMENT COERCION
# ═══════════════════════════════════════════════

def _coerce_arguments(raw_arguments: Any) -> Dict[str, Any]:
    """Normalize tool call arguments to a dict."""
    if isinstance(raw_arguments, dict):
        return raw_arguments

    if isinstance(raw_arguments, str):
        text = raw_arguments.strip()
        if not text:
            return {}

        # Try JSON parse
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        # Try key=value pairs
        pairs = re.findall(r"(\w+)\s*=\s*([^,]+)", text)
        if pairs:
            return {k: v.strip().strip("'\"") for k, v in pairs}

    return {}


# ═══════════════════════════════════════════════
# TOOL CALL EXTRACTION
# ═══════════════════════════════════════════════

def _extract_tool_calls(message: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """Extract tool calls from Ollama response message with intelligent fallbacks."""
    calls: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    
    # 1. Standard Native Tool Calls (Ollama format)
    raw_calls = message.get("tool_calls") or []
    for call in raw_calls:
        if not isinstance(call, dict):
            continue
        function_block = call.get("function") or {}
        name = function_block.get("name") or call.get("name")
        if not name:
            continue
        args = _coerce_arguments(function_block.get("arguments", {}))
        calls.append((name, args, call))
        
    if calls:
        return calls

    # 2. Fallbacks for hallucinatory or raw text outputs
    content = message.get("content", "")
    if not content:
        return calls

    # Fallback A: Markdown JSON Block (e.g. ```json { "name": "...", "arguments": {...} } ```)
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL | re.IGNORECASE)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            if isinstance(parsed, dict) and "name" in parsed:
                name = parsed["name"]
                args = parsed.get("arguments", {})
                pseudo_call = {"function": {"name": name, "arguments": args}}
                calls.append((name, _coerce_arguments(args), pseudo_call))
                return calls
        except Exception:
            pass

    # Fallback B: Python Function Syntax (e.g. delete_file(path="notlar.txt"))
    # Match pattern: func_name(key="val", key2='val2')
    py_matches = re.finditer(r"([a-zA-Z0-9_]+)\((.*?)\)", content)
    for match in py_matches:
        name = match.group(1)
        # Check if this name exists in our TOOL_SCHEMAS
        if any(t["function"]["name"] == name for t in TOOL_SCHEMAS):
            raw_args = match.group(2)
            args_dict = {}
            if raw_args.strip():
                # Extract key="val" or key='val' pairs
                arg_pairs = re.findall(r"([a-zA-Z0-9_]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", raw_args)
                for k, v1, v2 in arg_pairs:
                    args_dict[k] = v1 if v1 else v2
                    
            pseudo_call = {"function": {"name": name, "arguments": args_dict}}
            calls.append((name, _coerce_arguments(args_dict), pseudo_call))
            return calls # Sadece ilk buldugunu dondur

    # Fallback C: Raw JSON Block without markdown ticks (e.g. { "functions": [...] })
    raw_json_match = re.search(r"(\{.*\})", content, flags=re.DOTALL)
    if raw_json_match:
        try:
            parsed = json.loads(raw_json_match.group(1))
            # Senaryo 1: {"functions": [{"name": "...", "arguments": {...}}]}
            if "functions" in parsed and isinstance(parsed["functions"], list):
                for fn in parsed["functions"]:
                    if isinstance(fn, dict) and "name" in fn:
                        name = fn["name"]
                        args = fn.get("arguments", {})
                        pseudo_call = {"function": {"name": name, "arguments": args}}
                        calls.append((name, _coerce_arguments(args), pseudo_call))
                if calls:
                    return calls
            
            # Senaryo 2: {"name": "...", "arguments": {...}}
            elif "name" in parsed:
                name = parsed["name"]
                args = parsed.get("arguments", {})
                pseudo_call = {"function": {"name": name, "arguments": args}}
                calls.append((name, _coerce_arguments(args), pseudo_call))
                return calls
        except Exception:
            pass

    return calls


def _parse_route_directive(text: str) -> Tuple[str, Dict[str, Any]] | None:
    """Parse a ROUTE: directive from assistant text as fallback."""
    route_prefix = "ROUTE:"
    stripped = text.strip()

    # Check for ROUTE: prefix (case insensitive)
    upper = stripped.upper()
    if not upper.startswith(route_prefix):
        return None

    directive = stripped[len(route_prefix):].strip()
    match = re.match(r"([a-zA-Z_][\w]*)\s*(\{.*\})?", directive, flags=re.DOTALL)
    if not match:
        return None

    fn_name = match.group(1)
    raw_json = (match.group(2) or "{}").strip()

    try:
        parsed_args = json.loads(raw_json)
        if not isinstance(parsed_args, dict):
            parsed_args = {}
    except Exception:
        parsed_args = {}

    return fn_name, parsed_args


def _normalize_tool_args(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Fix common model argument quirks."""
    # get_system_info shouldn't have prompt arg
    if name == "get_system_info":
        args.pop("prompt", None)
        return args

    # create_folder: 'name' → 'path' fallback
    if name == "create_folder":
        if not args.get("path") and args.get("name"):
            args["path"] = args["name"]

    # create_file: ensure path exists
    if name == "create_file":
        if not args.get("content"):
            args["content"] = ""

    return args


# ═══════════════════════════════════════════════
# MAIN TOOL LOOP
# ═══════════════════════════════════════════════

def run_hermes_tool_loop(user_input: str, executor: Any, chat_history: list = None) -> Dict[str, Any]:
    """Run a Hermes tool-calling loop.

    1. Optionally try local FunctionGemma router first (if USE_LOCAL_ROUTER=True)
    2. If no local match, use Ollama /api/chat with native tool calling
    3. Handle multi-step tool calling (up to MAX_TOOL_STEPS)
    4. Parse ROUTE: directives as fallback

    Returns:
        {
            "ok": bool,
            "reply": str,
            "tool_results": list,
            "error": str (optional)
        }
    """

    # --- Optional: Local Router Fast Path ---
    if USE_LOCAL_ROUTER:
        try:
            from config import LOCAL_ROUTER_PATH
            if os.path.isdir(LOCAL_ROUTER_PATH):
                from core.llm import route_query
                func_name, params = route_query(user_input)
                if func_name and func_name not in ("thinking", "nonthinking"):
                    result = executor.execute(func_name, params or {})
                    return {
                        "ok": True,
                        "reply": sanitize_assistant_text(result.get("message", "İşlem tamamlandı.")),
                        "tool_results": [{"name": func_name, "args": params or {}, "result": result}],
                    }
        except Exception as e:
            print(f"[Hermes] Local router error (ignored): {e}")

    # --- Ollama Hermes Tool Calling ---
    session = requests.Session()
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": HERMES_SYSTEM_PROMPT},
    ]
    
    if chat_history:
        messages.extend(chat_history)
        # Ensure the current user_input is the last message if not already added
        if not messages or messages[-1].get("content") != user_input:
            messages.append({"role": "user", "content": user_input})
    else:
        messages.append({"role": "user", "content": user_input})

    tool_results: List[Dict[str, Any]] = []

    for step in range(MAX_TOOL_STEPS):
        # Send request to Ollama
        try:
            response = session.post(
                f"{OLLAMA_URL}/chat",
                json={
                    "model": RESPONDER_MODEL,
                    "messages": messages,
                    "tools": TOOL_SCHEMAS,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 512,
                    },
                },
                timeout=120,
            )
        except requests.exceptions.ConnectionError:
            return {
                "ok": False,
                "reply": "",
                "tool_results": tool_results,
                "error": "Ollama sunucusuna bağlanılamadı. 'ollama serve' komutunun çalıştığından emin olun.",
            }
        except Exception as err:
            return {
                "ok": False,
                "reply": "",
                "tool_results": tool_results,
                "error": f"Ollama isteği başarısız: {err}",
            }

        if response.status_code != 200:
            snippet = response.text[:200] if response.text else ""
            return {
                "ok": False,
                "reply": "",
                "tool_results": tool_results,
                "error": f"Ollama HTTP {response.status_code}: {snippet}",
            }

        payload = response.json()
        message = payload.get("message", {}) or {}
        assistant_text = sanitize_assistant_text(message.get("content", ""))
        extracted_calls = _extract_tool_calls(message)

        print(f"[Hermes] Step {step+1}: calls={len(extracted_calls)}, text_len={len(assistant_text)}")

        # --- Case 1: Model returned native tool_calls ---
        if extracted_calls:
            # Add assistant message to history
            messages.append({
                "role": "assistant",
                "content": message.get("content", ""),
                "tool_calls": message.get("tool_calls", []),
            })

            for name, args, _raw in extracted_calls:
                name = (name or "").strip()
                args = _normalize_tool_args(name, args)

                print(f"[Hermes] Executing: {name}({json.dumps(args, ensure_ascii=False)})")
                result = executor.execute(name, args)
                tool_results.append({"name": name, "args": args, "result": result})

                # Add tool result to conversation
                messages.append({
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                })

            # Continue loop — model may want to respond after seeing tool results
            continue

        # --- Case 2: No tool calls — check for ROUTE: fallback ---
        if assistant_text:
            route_parsed = _parse_route_directive(assistant_text)
            if route_parsed:
                fn_name, parsed_args = route_parsed
                parsed_args = _normalize_tool_args(fn_name, parsed_args)

                print(f"[Hermes] ROUTE fallback: {fn_name}({json.dumps(parsed_args, ensure_ascii=False)})")
                result = executor.execute(fn_name, parsed_args)
                tool_results.append({"name": fn_name, "args": parsed_args, "result": result})

                messages.append({"role": "assistant", "content": assistant_text})
                messages.append({
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                })
                continue

        # --- Case 3: Pure text response (no tools needed) ---
        if assistant_text:
            return {"ok": True, "reply": assistant_text, "tool_results": tool_results}

        # --- Case 4: Empty response with previous tool results ---
        if tool_results:
            last_result = tool_results[-1].get("result", {})
            fallback_reply = sanitize_assistant_text(last_result.get("message", ""))
            return {
                "ok": True,
                "reply": fallback_reply or "İşlem tamamlandı.",
                "tool_results": tool_results,
            }

        # --- Case 5: Completely empty response ---
        return {"ok": True, "reply": "Hazırım. Size nasıl yardımcı olabilirim?", "tool_results": []}

    # Loop exhausted — return what we have
    if tool_results:
        last_result = tool_results[-1].get("result", {})
        fallback_reply = sanitize_assistant_text(last_result.get("message", ""))
        return {
            "ok": True,
            "reply": fallback_reply or "İşlem tamamlandı.",
            "tool_results": tool_results,
        }

    return {"ok": True, "reply": "İşlem tamamlandı.", "tool_results": tool_results}


# ═══════════════════════════════════════════════
# SCREENSHOT / VISION ANALYSIS
# ═══════════════════════════════════════════════

def should_analyze_screenshot(user_input: str, screenshot_path: str | None) -> bool:
    """Check if the user's message should trigger screenshot analysis."""
    if not screenshot_path or not os.path.exists(screenshot_path):
        return False

    normalized = user_input.lower()
    hints = (
        "ekran",
        "goruntu",
        "görüntü",
        "gorsel",
        "görsel",
        "resim",
        "ss",
        "screenshot",
        "buna bak",
        "burada",
        "bu ne",
        "bunu analiz",
        "bunu incele",
        "ne görüyorsun",
        "ne goruyorsun",
    )
    return any(hint in normalized for hint in hints)


def analyze_screenshot_question(user_input: str, screenshot_path: str) -> Dict[str, Any]:
    """Analyze a screenshot using a vision-capable model."""
    if not os.path.exists(screenshot_path):
        return {"ok": False, "reply": "", "error": "Ekran görüntüsü dosyası bulunamadı."}

    model_name = SCREEN_ANALYZER_MODEL or RESPONDER_MODEL

    try:
        with open(screenshot_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode("ascii")

        response = requests.post(
            f"{OLLAMA_URL}/chat",
            json={
                "model": model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Sen bir ekran görüntüsü analiz asistanısın. "
                            "Kullanıcının ekranındaki görüntüyü analiz et ve "
                            "sorularını kısa, doğru ve Türkçe olarak yanıtla."
                        ),
                    },
                    {
                        "role": "user",
                        "content": user_input,
                        "images": [encoded_image],
                    },
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=120,
        )

        if response.status_code != 200:
            snippet = response.text[:200] if response.text else ""
            return {
                "ok": False,
                "reply": "",
                "error": f"Görüntü analizi başarısız ({response.status_code}): {snippet}",
            }

        payload = response.json()
        reply = sanitize_assistant_text(payload.get("message", {}).get("content", ""))
        return {"ok": True, "reply": reply or "Görüntü analiz edildi.", "error": ""}

    except requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "reply": "",
            "error": "Ollama sunucusuna bağlanılamadı.",
        }
    except Exception as err:
        return {"ok": False, "reply": "", "error": str(err)}
