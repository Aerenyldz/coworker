"""Tenra 2.0 — Ollama embedding client (nomic-embed-text)."""

from __future__ import annotations

import logging
from typing import List, Optional

import requests

from ..config import OLLAMA_URL, EMBED_MODEL

logger = logging.getLogger(__name__)

# nomic-embed-text default dimensionality
EMBED_DIM = 768


class EmbeddingClient:
    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = (base_url or OLLAMA_URL).rstrip("/")
        self.model = model or EMBED_MODEL
        self._session = requests.Session()

    def embed(self, text: str, timeout: int = 60) -> Optional[List[float]]:
        """Tek metin → 768-d vektör. Başarısızsa None."""
        text = (text or "").strip()
        if not text:
            return None
        # Embedding için uzun metni kırp (nomic ~8192 token; güvenli sınır)
        if len(text) > 6000:
            text = text[:6000]

        url = f"{self.base_url}/embeddings"
        try:
            resp = self._session.post(
                url,
                json={"model": self.model, "prompt": text},
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            emb = data.get("embedding")
            if isinstance(emb, list) and emb:
                return [float(x) for x in emb]
            # bazı sürümler embeddings: [[...]]
            embs = data.get("embeddings")
            if isinstance(embs, list) and embs and isinstance(embs[0], list):
                return [float(x) for x in embs[0]]
        except Exception as e:
            logger.debug(f"embed failed: {e}")
        return None

    def embed_batch(self, texts: List[str], timeout: int = 60) -> List[Optional[List[float]]]:
        return [self.embed(t, timeout=timeout) for t in texts]
