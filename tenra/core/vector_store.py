"""Tenra 2.0 — SQLite-vec anlamsal vektör deposu.

Episodik hafıza ve kod parçacıklarını nomic-embed-text (768-d) ile indeksler.
sqlite-vec yüklenemezse aynı SQLite şemasında Python cosine fallback kullanır.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .embeddings import EMBED_DIM, EmbeddingClient

logger = logging.getLogger(__name__)


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


class VectorStore:
    """Yerel anlamsal indeks: episode + code snippet."""

    def __init__(self, db_path: Path, embedder: EmbeddingClient = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or EmbeddingClient()
        self._use_vec = False
        self._conn = self._connect()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        self._use_vec = False
        try:
            import sqlite_vec
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            self._use_vec = True
        except Exception as e:
            logger.debug(f"sqlite-vec unavailable, cosine fallback: {e}")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                workspace TEXT,
                text TEXT NOT NULL,
                meta_json TEXT,
                embedding_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_kind_ws ON items(kind, workspace)"
        )

        if self._use_vec:
            try:
                conn.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_items "
                    f"USING vec0(embedding float[{EMBED_DIM}])"
                )
            except Exception as e:
                logger.debug(f"vec0 create failed, cosine fallback: {e}")
                self._use_vec = False

        conn.commit()
        return conn

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def _serialize_vec(self, embedding: List[float]) -> bytes:
        import sqlite_vec
        return sqlite_vec.serialize_float32(embedding)

    def upsert(
        self,
        kind: str,
        text: str,
        workspace: str = "",
        meta: Optional[Dict[str, Any]] = None,
        dedupe_key: Optional[str] = None,
    ) -> Optional[int]:
        """Metni embed edip kaydet. dedupe_key meta içinde eşleşirse günceller."""
        text = (text or "").strip()
        if not text:
            return None

        embedding = self.embedder.embed(text)
        if not embedding:
            return None

        # Boyut hizala + L2 normalize (sqlite-vec L2 mesafesi için)
        if len(embedding) != EMBED_DIM:
            if len(embedding) > EMBED_DIM:
                embedding = embedding[:EMBED_DIM]
            else:
                embedding = embedding + [0.0] * (EMBED_DIM - len(embedding))
        norm = math.sqrt(sum(x * x for x in embedding)) or 1.0
        embedding = [x / norm for x in embedding]

        meta = dict(meta or {})
        if dedupe_key:
            meta["dedupe_key"] = dedupe_key
            existing = self._find_by_dedupe(kind, workspace, dedupe_key)
            if existing is not None:
                self._update_row(existing, text, meta, embedding)
                return existing

        created = datetime.datetime.now().isoformat(timespec="seconds")
        cur = self._conn.execute(
            """
            INSERT INTO items(kind, workspace, text, meta_json, embedding_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                kind,
                (workspace or "").lower(),
                text,
                json.dumps(meta, ensure_ascii=False),
                json.dumps(embedding),
                created,
            ),
        )
        row_id = int(cur.lastrowid)

        if self._use_vec:
            try:
                self._conn.execute(
                    "INSERT INTO vec_items(rowid, embedding) VALUES (?, ?)",
                    (row_id, self._serialize_vec(embedding)),
                )
            except Exception as e:
                logger.debug(f"vec insert failed: {e}")

        self._conn.commit()
        return row_id

    def _find_by_dedupe(self, kind: str, workspace: str, dedupe_key: str) -> Optional[int]:
        ws = (workspace or "").lower()
        rows = self._conn.execute(
            "SELECT id, meta_json FROM items WHERE kind = ? AND workspace = ?",
            (kind, ws),
        ).fetchall()
        for row in rows:
            try:
                meta = json.loads(row["meta_json"] or "{}")
            except Exception:
                meta = {}
            if meta.get("dedupe_key") == dedupe_key:
                return int(row["id"])
        return None

    def _update_row(self, row_id: int, text: str, meta: Dict[str, Any], embedding: List[float]):
        self._conn.execute(
            """
            UPDATE items
            SET text = ?, meta_json = ?, embedding_json = ?, created_at = ?
            WHERE id = ?
            """,
            (
                text,
                json.dumps(meta, ensure_ascii=False),
                json.dumps(embedding),
                datetime.datetime.now().isoformat(timespec="seconds"),
                row_id,
            ),
        )
        if self._use_vec:
            try:
                self._conn.execute("DELETE FROM vec_items WHERE rowid = ?", (row_id,))
                self._conn.execute(
                    "INSERT INTO vec_items(rowid, embedding) VALUES (?, ?)",
                    (row_id, self._serialize_vec(embedding)),
                )
            except Exception as e:
                logger.debug(f"vec update failed: {e}")
        self._conn.commit()

    def search(
        self,
        query: str,
        top_k: int = 3,
        kind: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Anlamsal arama — en yakın top_k kayıt."""
        query = (query or "").strip()
        if not query:
            return []

        q_emb = self.embedder.embed(query)
        if not q_emb:
            return []
        if len(q_emb) != EMBED_DIM:
            if len(q_emb) > EMBED_DIM:
                q_emb = q_emb[:EMBED_DIM]
            else:
                q_emb = q_emb + [0.0] * (EMBED_DIM - len(q_emb))
        qn = math.sqrt(sum(x * x for x in q_emb)) or 1.0
        q_emb = [x / qn for x in q_emb]

        if self._use_vec:
            try:
                return self._search_vec(q_emb, top_k, kind, workspace)
            except Exception as e:
                logger.debug(f"vec search failed, cosine fallback: {e}")

        return self._search_cosine(q_emb, top_k, kind, workspace)

    def _search_vec(
        self,
        q_emb: List[float],
        top_k: int,
        kind: Optional[str],
        workspace: Optional[str],
    ) -> List[Dict[str, Any]]:
        # Adayları geniş tut, sonra kind/workspace filtrele
        fetch_n = max(top_k * 8, 24)
        rows = self._conn.execute(
            """
            SELECT rowid, distance
            FROM vec_items
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
            """,
            (self._serialize_vec(q_emb), fetch_n),
        ).fetchall()

        results: List[Dict[str, Any]] = []
        ws = (workspace or "").lower() if workspace else None
        for row in rows:
            item = self._conn.execute(
                "SELECT * FROM items WHERE id = ?", (row["rowid"],)
            ).fetchone()
            if not item:
                continue
            if kind and item["kind"] != kind:
                continue
            if ws and (item["workspace"] or "") != ws and item["kind"] == "code":
                # code: workspace zorunlu filtre; episode'da daha esnek
                continue
            if ws and item["kind"] == "episode" and (item["workspace"] or "") not in ("", ws):
                # episode: aynı workspace veya genel
                if (item["workspace"] or "") != ws:
                    continue
            try:
                meta = json.loads(item["meta_json"] or "{}")
            except Exception:
                meta = {}
            # L2 distance on unit vectors ≈ √(2-2cos); map to [0,1] similarity
            dist = float(row["distance"])
            score = max(0.0, 1.0 - (dist * dist) / 2.0)
            results.append({
                "id": item["id"],
                "kind": item["kind"],
                "workspace": item["workspace"],
                "text": item["text"],
                "meta": meta,
                "score": score,
                "distance": dist,
                "created_at": item["created_at"],
            })
            if len(results) >= top_k:
                break
        return results

    def _search_cosine(
        self,
        q_emb: List[float],
        top_k: int,
        kind: Optional[str],
        workspace: Optional[str],
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM items WHERE 1=1"
        params: List[Any] = []
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if workspace:
            sql += " AND (workspace = ? OR workspace = '' OR workspace IS NULL)"
            params.append(workspace.lower())

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for item in self._conn.execute(sql, params).fetchall():
            try:
                emb = json.loads(item["embedding_json"] or "[]")
            except Exception:
                continue
            score = _cosine(q_emb, emb)
            if score < 0:
                continue
            try:
                meta = json.loads(item["meta_json"] or "{}")
            except Exception:
                meta = {}
            scored.append((score, {
                "id": item["id"],
                "kind": item["kind"],
                "workspace": item["workspace"],
                "text": item["text"],
                "meta": meta,
                "score": score,
                "created_at": item["created_at"],
            }))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def count(self, kind: Optional[str] = None) -> int:
        if kind:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM items WHERE kind = ?", (kind,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()
        return int(row["c"] if row else 0)
