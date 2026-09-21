"""Tenra 2.0 — Qwen3 Agent (Otonom Araç Döngüsü + Vision Analizi)

Eski hermes_agent.py'nin tam olarak Qwen3 için adapte edilmiş hali.
- Çok adımlı tool calling döngüsü
- Regex fallback'ler (native → markdown JSON → Python syntax → raw JSON)
- Vision analizi (Moondream + Tesseract OCR fallback)
- Akıllı sohbet geçmişi sıkıştırma
- Türkçe bilgi/analiz sorgu tespiti
"""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import getpass
import platform
from typing import Any, Dict, List, Tuple

import requests

from ..config import (
    SYSTEM_PROMPT,
    MAIN_MODEL,
    VISION_MODEL,
    OLLAMA_URL,
    MAX_TOOL_STEPS,
    MAX_HISTORY,
    DESKTOP_PATH,
    APP_VERSION,
    get_system_prompt,
    MEMORY_FILE,
)
from .llm_backend import OllamaBackend
from .memory import MemoryStore


# ═══════════════════════════════════════════════
# TEXT SANITIZATION
# ═══════════════════════════════════════════════

def sanitize_assistant_text(text: str) -> str:
    """Clean known noisy output patterns from model text."""
    if not text:
        return ""

    # Remove thinking tags (Qwen3 /think mode compat)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    cleaned = re.sub(r"<thought>.*?</thought>", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()

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

    # Model bazen {s: "mesaj"} formatı üretiyor
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
# TOOL CALL EXTRACTION (Multi-Fallback)
# ═══════════════════════════════════════════════

def _extract_tool_calls(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract tool calls from Ollama response message with intelligent fallbacks."""
    calls: List[Dict[str, Any]] = []

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
        call_id = call.get("id") or function_block.get("id")
        calls.append({"name": name, "arguments": args, "id": call_id})

    if calls:
        return calls

    # 2. Fallbacks for hallucinatory or raw text outputs
    content = message.get("content", "")
    if not content:
        return calls

    # Fallback A: Markdown JSON Block (```json { "name": "...", "arguments": {...} } ```)
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL | re.IGNORECASE)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            if isinstance(parsed, dict) and "name" in parsed:
                name = parsed["name"]
                args = parsed.get("arguments", {})
                calls.append({"name": name, "arguments": _coerce_arguments(args)})
                return calls
        except Exception:
            pass

    # Fallback B: Python Function Syntax (e.g. shell(command="echo test"))
    KNOWN_TOOLS = {"shell", "file", "web", "screen"}
    py_matches = re.finditer(r"([a-zA-Z0-9_]+)\((.*?)\)", content)
    for match in py_matches:
        name = match.group(1)
        if name in KNOWN_TOOLS:
            raw_args = match.group(2)
            args_dict = {}
            if raw_args.strip():
                arg_pairs = re.findall(r"([a-zA-Z0-9_]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", raw_args)
                for k, v1, v2 in arg_pairs:
                    args_dict[k] = v1 if v1 else v2
            calls.append({"name": name, "arguments": _coerce_arguments(args_dict)})
            return calls

    # Fallback C: Raw JSON Block without markdown ticks
    raw_json_match = re.search(r"(\{.*\})", content, flags=re.DOTALL)
    if raw_json_match:
        try:
            parsed = json.loads(raw_json_match.group(1))
            if isinstance(parsed, dict) and "name" in parsed:
                name = parsed["name"]
                args = parsed.get("arguments", {})
                calls.append({"name": name, "arguments": _coerce_arguments(args)})
                return calls
        except Exception:
            pass

    return calls


def _normalize_tool_args(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Fix common model argument quirks."""
    if not isinstance(args, dict):
        return {}

    # file aracı: 'name' → 'path' fallback
    if name == "file":
        if not args.get("path") and args.get("name"):
            args["path"] = args.pop("name")
        if not args.get("path"):
            for alt in ("filename", "file", "target", "folder", "directory", "dir", "filepath"):
                if args.get(alt):
                    args["path"] = args.pop(alt)
                    break
        # Varsayılan action belirleme
        if not args.get("action"):
            if args.get("path"):
                args["action"] = "read"
            else:
                args["action"] = "list"

    return args


# ═══════════════════════════════════════════════
# CHAT HISTORY OPTIMIZATION
# ═══════════════════════════════════════════════

def optimize_chat_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sohbet geçmişindeki uzun metinleri sıkıştırır, eski resimleri temizler."""
    if not history:
        return []

    optimized = copy.deepcopy(history)

    # 1. Base64 Temizliği (eski resimleri sil, sadece son eklenenler kalsın)
    for i in range(len(optimized) - 1):
        if "images" in optimized[i]:
            del optimized[i]["images"]

    # 2. Context Compression (metin sıkıştırma)
    for msg in optimized:
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 1500:
            if "GÖRSEL" in content or "OCR" in content:
                msg["content"] = "[Geçmiş görsel/OCR verisi bellekten temizlendi.]"
            else:
                msg["content"] = content[:500] + "\n...[KISALTILDI]...\n" + content[-300:]

    # 3. Sliding Window
    limit = MAX_HISTORY or 20
    return optimized[-limit:]


# ═══════════════════════════════════════════════
# INFORMATIONAL QUERY DETECTION (Turkish)
# ═══════════════════════════════════════════════

def is_informational_or_analysis_query(text: str) -> bool:
    """Kullanıcının isteğinin bilgi/analiz sorusu mu yoksa eylem mi olduğunu belirler."""
    if not text:
        return True
    lowered = text.lower().strip()

    # Soru / öğrenme / analiz kalıpları
    question_patterns = [
        r'\bnas[iı]\s*l\b', r'\bnedir\b', r'\bne demek\b', r'\bne [iı][sş]e yarar\b',
        r'\bneden\b', r'\bni[cç]in\b', r'\bniye\b', r'\bkimdir\b',
        r'\ba[cç][iı]kla\b', r'\banlat\b', r'\banaliz et\b', r'\by[oö]ntemleri\b',
        r'\bbilgi ver\b', r'\bfark[iı] ne\b', r'\bhangisi\b',
        r'\b[oö][gğ]ret\b', r'\btavsiye\b', r'\b[oö]ner\b',
    ]
    is_q = any(re.search(pat, lowered) for pat in question_patterns) or lowered.endswith('?')

    # Doğrudan işletim sistemi eylemi ve emir kalıpları
    action_patterns = [
        r'\b(uygulamas[iı]n[iı]|program[iı]n[iı]|app)\s+(a[cç]|ba[sş]lat)\b',
        r'^(a[cç]|ba[sş]lat|calistir|çalıştır|sil|yarat|olu[sş]tur)\b',
        r'\b(a[cç]|ba[sş]lat|calistir|çalıştır|sil|yarat|olu[sş]tur)$',
        r'\bkomut:\b', r'\bpowershell:\b', r'\bterminal:\b',
    ]
    is_act = any(re.search(pat, lowered) for pat in action_patterns)

    return is_q and not is_act


# ═══════════════════════════════════════════════
# MAIN AGENT TOOL LOOP
# ═══════════════════════════════════════════════

def _record_run_memory(ws_path: str, user_input: str, tool_results: list, reply: str):
    try:
        store = MemoryStore(MEMORY_FILE)
        store.auto_learn_from_agent_run(ws_path, user_input, tool_results, reply)
    except Exception:
        pass

def run_agent_loop(
    user_input: str,
    executor: Any,
    chat_history: list = None,
) -> Dict[str, Any]:
    """Qwen3 çok adımlı araç çağırma döngüsü."""

    backend = OllamaBackend(OLLAMA_URL, MAIN_MODEL)

    ws_path = getattr(executor, "workspace_path", DESKTOP_PATH)
    ws_name = getattr(executor, "workspace_name", "Masaüstü")
    system_prompt = get_system_prompt(ws_path, ws_name)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]

    if chat_history:
        optimized = optimize_chat_history(chat_history)
        messages.extend(optimized)
        if not messages or messages[-1].get("content") != user_input:
            messages.append({"role": "user", "content": user_input})
    else:
        messages.append({"role": "user", "content": user_input})

    tool_results: List[Dict[str, Any]] = []
    tools = executor.get_tool_schemas()

    for step in range(MAX_TOOL_STEPS):
        response = backend.chat(
            messages=messages,
            tools=tools,
            model=MAIN_MODEL,
            temperature=0.3,
        )

        # Hata kontrolü
        if "error" in response:
            error_msg = response.get("message", str(response.get("error", "Bilinmeyen hata")))
            return {
                "ok": False,
                "reply": "",
                "tool_results": tool_results,
                "error": error_msg,
            }

        message = response.get("message", {}) or {}
        assistant_text = sanitize_assistant_text(message.get("content", ""))
        extracted_calls = _extract_tool_calls(message)

        print(f"[Tenra Agent] Step {step+1}: calls={len(extracted_calls)}, text_len={len(assistant_text)}")

        # --- Case 1: Tool calls found ---
        if extracted_calls:
            # Mesajı geçmişe ekle (model'in cevabı olarak)
            messages.append(message)

            for tc in extracted_calls:
                fn_name = tc["name"]
                fn_args = _normalize_tool_args(fn_name, tc.get("arguments", {}))

                result = executor.execute(fn_name, fn_args)
                tool_results.append({
                    "name": fn_name,
                    "args": fn_args,
                    "result": result,
                })

                tool_msg: Dict[str, Any] = {
                    "role": "tool",
                    "name": fn_name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
                if tc.get("id"):
                    tool_msg["tool_call_id"] = tc["id"]
                messages.append(tool_msg)
            continue

        # --- Case 2: Pure text response (araç gerekmedi) ---
        if assistant_text:
            _record_run_memory(ws_path, user_input, tool_results, assistant_text)
            return {"ok": True, "reply": assistant_text, "tool_results": tool_results}

        # --- Case 3: Boş cevap ama önceki araç sonuçları var ---
        if tool_results:
            last_result = tool_results[-1].get("result", {})
            fallback_reply = sanitize_assistant_text(str(last_result.get("message", "")))
            reply = fallback_reply or "İşlem tamamlandı."
            _record_run_memory(ws_path, user_input, tool_results, reply)
            return {
                "ok": True,
                "reply": reply,
                "tool_results": tool_results,
            }

        # --- Case 4: Tamamen boş cevap ---
        return {"ok": True, "reply": "Hazırım. Size nasıl yardımcı olabilirim?", "tool_results": []}

    # Döngü tükendi
    if tool_results:
        last_result = tool_results[-1].get("result", {})
        fallback_reply = sanitize_assistant_text(str(last_result.get("message", "")))
        reply = fallback_reply or "İşlem tamamlandı."
        _record_run_memory(ws_path, user_input, tool_results, reply)
        return {
            "ok": True,
            "reply": reply,
            "tool_results": tool_results,
        }

    return {"ok": True, "reply": "İşlem tamamlandı.", "tool_results": tool_results}


# ═══════════════════════════════════════════════
# SCREENSHOT / VISION ANALYSIS
# ═══════════════════════════════════════════════

def should_analyze_screenshot(user_input: str, screenshot_path: str | None) -> bool:
    """Ekran görüntüsü analizi gerekli mi?"""
    if not screenshot_path or not os.path.exists(screenshot_path):
        return False
    return True


def get_screenshot_text(screenshot_path: str, user_input: str = "") -> str:
    """Ekran görüntüsünden Vision API (moondream) + Tesseract OCR ile metin çıkarır."""
    if not os.path.exists(screenshot_path):
        return ""

    backend = OllamaBackend(OLLAMA_URL, VISION_MODEL or "moondream:latest")

    # Görseli base64 olarak encode et
    try:
        with open(screenshot_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode("ascii")
    except Exception:
        return ""

    extracted_text = ""

    # 1. Aşama: Vision modeli ile görseli tara
    prompts_to_try = [
        "Describe this image in detail.",
        "Read the text in the image.",
        "Transcribe all visible text, numbers, and labels in this image.",
    ]

    for prompt_text in prompts_to_try:
        try:
            out = backend.generate(
                prompt=prompt_text,
                model=VISION_MODEL or "moondream:latest",
                images=[encoded_image],
                temperature=0.1,
            )
            out = sanitize_assistant_text(out).strip()
            if out and not out.startswith("Error:"):
                extracted_text = out
                break
        except Exception as e:
            print(f"[Tenra Vision] Generate error: {e}")

    # 2. Aşama: Chat endpoint fallback
    if not extracted_text:
        try:
            resp = backend.chat(
                messages=[{
                    "role": "user",
                    "content": "Describe this image and read all visible text.",
                    "images": [encoded_image],
                }],
                model=VISION_MODEL or "moondream:latest",
                temperature=0.1,
            )
            if "error" not in resp:
                extracted_text = sanitize_assistant_text(
                    resp.get("message", {}).get("content", "")
                )
        except Exception as e:
            print(f"[Tenra Vision] Chat fallback error: {e}")

    # 3. Aşama: Tesseract OCR fallback
    if not extracted_text:
        try:
            from PIL import Image
            import pytesseract

            tesseract_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tesseract-OCR", "tesseract.exe"),
            ]
            for p in tesseract_paths:
                if os.path.exists(p):
                    pytesseract.pytesseract.tesseract_cmd = p
                    break

            img = Image.open(screenshot_path)
            try:
                extracted_text = pytesseract.image_to_string(img, lang='eng+tur').strip()
            except Exception:
                extracted_text = pytesseract.image_to_string(img).strip()
        except Exception as e:
            print(f"[Tenra Vision] OCR error: {e}")

    return extracted_text
