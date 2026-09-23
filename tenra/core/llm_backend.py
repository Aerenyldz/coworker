import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from ..config import DEFAULT_NUM_CTX

logger = logging.getLogger(__name__)

class OllamaBackend:
    def __init__(self, base_url, default_model):
        self.base_url = base_url.rstrip('/')
        self.default_model = default_model
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        self.session.mount('http://', HTTPAdapter(max_retries=retries))

    def chat(self, messages, tools=None, model=None, temperature=0.3, num_predict=2048,
             num_ctx=None, think=False, on_token=None):
        """Ollama /api/chat.

        on_token verilirse SSE streaming açılır; her content delta için çağrılır.
        Dönüş her zaman tek bir (birleştirilmiş) chat yanıt dict'idir.
        """
        if num_ctx is None:
            num_ctx = DEFAULT_NUM_CTX
        url = f"{self.base_url}/chat"
        use_stream = callable(on_token)
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": use_stream,
            "think": think,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "num_ctx": num_ctx
            }
        }
        if tools:
            payload["tools"] = tools

        try:
            if use_stream:
                return self._chat_stream(url, payload, on_token)
            response = self.session.post(url, json=payload, timeout=180)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error("Ollama chat timeout (180s)")
            return {"error": "Timeout", "message": "Ollama yanıt vermedi (zaman aşımı)."}
        except requests.exceptions.ConnectionError:
            logger.error("Ollama chat connection error")
            return {"error": "ConnectionError", "message": "Ollama'ya bağlanılamadı. Ollama çalışıyor mu?"}
        except requests.exceptions.RequestException as e:
            err_body = ""
            status = None
            if hasattr(e, "response") and e.response is not None:
                status = getattr(e.response, "status_code", None)
                try:
                    err_body = (e.response.text or "").strip()
                except Exception:
                    pass
            # Model yok / think desteklenmiyor gibi yaygın hataları Türkçeleştir
            low = (err_body or str(e)).lower()
            if "not found" in low or status == 404:
                model_name = (model or self.default_model) or "?"
                msg = (
                    f"Model bulunamadı: {model_name}. "
                    f"Ollama'da yüklü mü kontrol et (ör. ollama pull {model_name})."
                )
            elif "does not support thinking" in low or "think" in low and "support" in low:
                msg = "Bu model düşünme (think) modunu desteklemiyor."
            else:
                msg = f"Ollama hatası: {err_body or str(e)}"
            logger.error(f"Ollama chat HTTP error: {e} | {err_body}")
            return {"error": "RequestException", "message": msg}

    def _chat_stream(self, url, payload, on_token):
        """NDJSON/SSE stream birleştirir; tool_calls son chunk'tan korunur."""
        content_parts = []
        thinking_parts = []
        role = "assistant"
        tool_calls = None
        final_meta = {}

        with self.session.post(url, json=payload, timeout=180, stream=True) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                if isinstance(raw_line, bytes):
                    line = raw_line.decode("utf-8", errors="replace").strip()
                else:
                    line = str(raw_line).strip()
                if line.startswith("data:"):
                    line = line[5:].strip()
                if not line or line == "[DONE]":
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if chunk.get("error"):
                    err = chunk["error"]
                    msg = err if isinstance(err, str) else str(err)
                    return {"error": "StreamError", "message": msg}

                msg = chunk.get("message") or {}
                if msg.get("role"):
                    role = msg["role"]

                delta = msg.get("content") or ""
                if delta:
                    content_parts.append(delta)
                    try:
                        on_token(delta)
                    except Exception as cb_err:
                        logger.debug(f"on_token callback error: {cb_err}")

                think_delta = msg.get("thinking") or ""
                if think_delta:
                    thinking_parts.append(think_delta)

                if msg.get("tool_calls"):
                    tool_calls = msg["tool_calls"]

                if chunk.get("done"):
                    final_meta = {
                        k: chunk[k]
                        for k in ("total_duration", "load_duration", "prompt_eval_count",
                                  "eval_count", "eval_duration", "created_at", "model")
                        if k in chunk
                    }

        assembled = {
            "message": {
                "role": role,
                "content": "".join(content_parts),
            },
            "done": True,
            **final_meta,
        }
        if thinking_parts:
            assembled["message"]["thinking"] = "".join(thinking_parts)
        if tool_calls:
            assembled["message"]["tool_calls"] = tool_calls
        return assembled

    def generate(self, prompt, model=None, images=None, temperature=0.1):
        url = f"{self.base_url}/generate"
        payload = {
            "model": model or self.default_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        if images:
            payload["images"] = images

        try:
            response = self.session.post(url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.exceptions.Timeout:
            logger.error("Ollama generate timeout (60s)")
            return "Error: Timeout generating response."
        except requests.exceptions.ConnectionError:
            logger.error("Ollama generate connection error")
            return "Error: Could not connect to Ollama."
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama generate HTTP error: {e}")
            return f"Error: {str(e)}"

    def list_models(self):
        url = f"{self.base_url}/tags"
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return [model.get("name") for model in data.get("models", [])]
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return []

    def health_check(self):
        try:
            return bool(self.list_models())
        except Exception:
            return False

    def preload_model(self, model):
        url = f"{self.base_url}/generate"
        payload = {
            "model": model,
            "keep_alive": "5m"
        }
        try:
            self.session.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.debug(f"Failed to preload model {model}: {e}")
