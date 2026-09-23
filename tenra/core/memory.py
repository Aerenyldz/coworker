"""Tenra 2.0 — Persistent Episodic & Semantic Memory System

JSON (preferences/projects/episodes) + SQLite-vec anlamsal arama.
Kullanıcı sorgusuna en yakın 3 geçmiş deneyim / kod parçacığı prompt'a enjekte edilir.
"""

from __future__ import annotations

import json
import os
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class MemoryStore:
    def __init__(self, memory_file: Path, vector_db_path: Path = None):
        self.memory_file = Path(memory_file)
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = self._load()
        self._vector = None
        self._vector_db_path = vector_db_path
        self._migrated = False

    def _get_vector(self):
        if self._vector is None and self._vector_db_path is not None:
            try:
                from .vector_store import VectorStore
                self._vector = VectorStore(self._vector_db_path)
                if not self._migrated:
                    self._migrate_episodes_to_vector()
                    self._migrated = True
            except Exception:
                self._vector = None
        return self._vector

    def _default_data(self) -> Dict[str, Any]:
        return {
            "preferences": [
                "Windows PowerShell ve Windows dosya yolları kullanılıyor.",
                "Kullanıcı Türkçe yanıtları ve doğrudan çözümleri tercih ediyor.",
                "Kod yazımında temiz, modüler ve güvenli mimari hedefleniyor.",
                "Tehlikeli komutlarda ve kod değişikliklerinde onay kartları gösterilir."
            ],
            "projects": {
                "coworker": {
                    "description": "Antigravity tarzı otonom masaüstü geliştirici asistanı Tenra 2.0.",
                    "stack": "Python 3.11, PySide6, Ollama Qwen3:8b, SpeechRecognition",
                    "notes": [
                        "Proje çekirdeği tenra/ paketinde yer alır.",
                        "4 temel araç: shell, file, web, screen.",
                        "Diff onay ve güvenlik sandbox motoru tenra/core/executor.py içinde çalışır."
                    ]
                }
            },
            "episodes": [
                {
                    "date": datetime.date.today().isoformat(),
                    "workspace": "coworker",
                    "query": "Güvenlik sandbox ve diff önizleme kartları",
                    "summary": "Tehlikeli komut önleme ve unified diff onay kartları sisteme entegre edildi."
                }
            ]
        }

    def _load(self) -> Dict[str, Any]:
        if self.memory_file.exists():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    defaults = self._default_data()
                    for k, v in defaults.items():
                        if k not in data:
                            data[k] = v
                    return data
            except Exception:
                pass

        defaults = self._default_data()
        self._save(defaults)
        return defaults

    def _save(self, data: Optional[Dict[str, Any]] = None):
        if data is not None:
            self.data = data
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _migrate_episodes_to_vector(self):
        """Mevcut JSON episode'larını vektör DB'ye bir kez aktar."""
        vec = self._vector
        if vec is None:
            return
        try:
            if vec.count("episode") > 0:
                return
            for ep in self.data.get("episodes", []):
                text = f"{ep.get('query', '')}: {ep.get('summary', '')}".strip()
                if not text or text == ":":
                    continue
                dedupe = f"episode:{ep.get('date','')}:{ep.get('query','')[:40]}"
                vec.upsert(
                    kind="episode",
                    text=text,
                    workspace=ep.get("workspace", ""),
                    meta={"date": ep.get("date"), "source": "json_migrate"},
                    dedupe_key=dedupe,
                )
        except Exception:
            pass

    def add_preference(self, pref: str):
        pref = pref.strip()
        if pref and pref not in self.data["preferences"]:
            self.data["preferences"].append(pref)
            self._save()

    def add_project_note(self, workspace_name: str, note: str):
        ws_key = workspace_name.lower().strip()
        if ws_key not in self.data["projects"]:
            self.data["projects"][ws_key] = {
                "description": "",
                "stack": "",
                "notes": []
            }
        notes = self.data["projects"][ws_key].setdefault("notes", [])
        if note not in notes:
            notes.append(note)
            self._save()

    def set_project_info(self, workspace_name: str, description: str = "", stack: str = ""):
        ws_key = workspace_name.lower().strip()
        if ws_key not in self.data["projects"]:
            self.data["projects"][ws_key] = {"notes": []}
        if description:
            self.data["projects"][ws_key]["description"] = description
        if stack:
            self.data["projects"][ws_key]["stack"] = stack
        self._save()

    def add_episode(self, workspace_name: str, query: str, summary: str):
        episode = {
            "date": datetime.date.today().isoformat(),
            "workspace": workspace_name,
            "query": query[:80],
            "summary": summary[:120]
        }
        self.data.setdefault("episodes", []).append(episode)
        # JSON'da son 100 kayıt (vektör DB uzun vadeli arşiv)
        if len(self.data["episodes"]) > 100:
            self.data["episodes"] = self.data["episodes"][-100:]
        self._save()

        # Anlamsal indeks
        vec = self._get_vector()
        if vec is not None:
            try:
                text = f"{episode['query']}: {episode['summary']}"
                dedupe = f"episode:{episode['date']}:{episode['query'][:40]}"
                vec.upsert(
                    kind="episode",
                    text=text,
                    workspace=workspace_name,
                    meta={"date": episode["date"], "source": "auto_learn"},
                    dedupe_key=dedupe,
                )
            except Exception:
                pass

    def get_memory_summary(
        self,
        workspace_path: str,
        max_chars: int = 2000,
        query: str = None,
    ) -> str:
        """Sistem prompt'u için çalışma alanına özel + anlamsal hafıza özeti."""
        lines: List[str] = []
        lines.append("🧠 KALICI HAFIZA VE ÖĞRENİLENLER:")

        prefs = self.data.get("preferences", [])
        if prefs:
            lines.append("📌 Genel Tercihler:")
            for p in prefs[:4]:
                lines.append(f"  • {p}")

        ws_name = Path(workspace_path).resolve().name.lower()
        projects = self.data.get("projects", {})
        proj_data = projects.get(ws_name)
        if proj_data:
            lines.append(f"📌 Proje Notları ({ws_name}):")
            if proj_data.get("description"):
                lines.append(f"  • Tanım: {proj_data['description']}")
            if proj_data.get("stack"):
                lines.append(f"  • Teknoloji: {proj_data['stack']}")
            for note in proj_data.get("notes", [])[:5]:
                lines.append(f"  • {note}")

        # Anlamsal RAG: sorguya en yakın 3 episode (+ kod parçası)
        semantic_added = False
        vec = self._get_vector()
        if vec is not None and query:
            try:
                hits = vec.search(query, top_k=3, workspace=ws_name)
                if hits:
                    lines.append("📌 Anlamsal Hafıza (sorguna en yakın deneyimler):")
                    for h in hits:
                        score = h.get("score", 0)
                        kind = h.get("kind", "episode")
                        tag = "kod" if kind == "code" else "deneyim"
                        lines.append(f"  • [{tag} · {score:.2f}] {h.get('text', '')[:160]}")
                    semantic_added = True
            except Exception:
                pass

        if not semantic_added:
            episodes = self.data.get("episodes", [])
            if episodes:
                lines.append("📌 Son Hafıza Kayıtları (Önceki Görevler):")
                for ep in reversed(episodes[-4:]):
                    ws_tag = f"[{ep.get('workspace', '')}] " if ep.get('workspace') else ""
                    lines.append(f"  • {ws_tag}{ep.get('query')}: {ep.get('summary')}")

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n  [... eski hafıza kayıtları arşivlendi ...]"
        return result

    def auto_learn_from_agent_run(self, workspace_path: str, user_input: str, tool_results: list, reply: str):
        """Ajanın çalıştırdığı araçlardan otomatik öğrenme çıkarır ve hafızaya yazar."""
        if not tool_results:
            return

        ws_name = Path(workspace_path).resolve().name
        actions_taken = []

        for tr in tool_results:
            name = tr.get("name", "")
            args = tr.get("args", {})

            if name == "file":
                action = args.get("action", "")
                p = args.get("path", "")
                filename = Path(p).name if p else ""
                if action in ("write", "patch", "create"):
                    actions_taken.append(f"{filename} güncellendi/yazıldı")
                elif action in ("delete", "trash"):
                    actions_taken.append(f"{filename} silindi")
            elif name == "shell":
                cmd = args.get("command", "")
                if len(cmd) > 30:
                    cmd = cmd[:30] + "..."
                actions_taken.append(f"Komut: {cmd}")

        if actions_taken:
            summary = ", ".join(actions_taken[:3])
            self.add_episode(ws_name, user_input, summary)

    def close(self):
        if self._vector is not None:
            try:
                self._vector.close()
            except Exception:
                pass
            self._vector = None
