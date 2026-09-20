import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class OllamaBackend:
    def __init__(self, base_url, default_model):
        self.base_url = base_url.rstrip('/')
        self.default_model = default_model
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        self.session.mount('http://', HTTPAdapter(max_retries=retries))

    def chat(self, messages, tools=None, model=None, temperature=0.3, num_predict=2048, num_ctx=4096):
        url = f"{self.base_url}/chat"
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "num_ctx": num_ctx
            }
        }
        if tools:
            payload["tools"] = tools

        try:
            response = self.session.post(url, json=payload, timeout=120)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error("Ollama chat timeout (120s)")
            return {"error": "Timeout", "message": "Ollama chat request timed out."}
        except requests.exceptions.ConnectionError:
            logger.error("Ollama chat connection error")
            return {"error": "ConnectionError", "message": "Could not connect to Ollama."}
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama chat HTTP error: {e}")
            return {"error": "RequestException", "message": str(e)}

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
