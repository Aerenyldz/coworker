"""Tenra 2.0 — Change Journal (Rollback / Undo)

Uygulanan dosya değişikliklerinin önceki içeriğini saklar.
Kullanıcı tek tıkla son (veya paket) değişikliği geri alabilir.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class ChangeJournal:
    """Son N dosya değişikliğini diskte tutar."""

    def __init__(self, journal_path: Path, max_entries: int = 50):
        self.journal_path = Path(journal_path)
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self._entries: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if self.journal_path.exists():
            try:
                with open(self.journal_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception:
                pass
        return []

    def _save(self):
        try:
            with open(self.journal_path, "w", encoding="utf-8") as f:
                json.dump(self._entries[-self.max_entries:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def record(
        self,
        path: str,
        before: str,
        after: str,
        action: str = "write",
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        entry = {
            "id": f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}_{Path(path).name}",
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "path": str(path),
            "filename": Path(path).name,
            "action": action,
            "before": before,
            "after": after,
            "batch_id": batch_id,
            "undone": False,
        }
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]
        self._save()
        return entry

    def peek_last(self) -> Optional[Dict[str, Any]]:
        for entry in reversed(self._entries):
            if not entry.get("undone"):
                return entry
        return None

    def undo_last(self) -> Dict[str, Any]:
        """Son uygulanmış değişikliği geri alır (before içeriğini yazar)."""
        entry = self.peek_last()
        if not entry:
            return {"success": False, "message": "Geri alınacak değişiklik yok."}

        path = entry["path"]
        before = entry.get("before", "")
        try:
            p = Path(path)
            if before == "" and entry.get("action") == "create":
                if p.exists():
                    p.unlink()
                entry["undone"] = True
                self._save()
                return {
                    "success": True,
                    "message": f"Oluşturma geri alındı (silindi): {entry['filename']}",
                    "entry": entry,
                }

            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(before)
            entry["undone"] = True
            self._save()
            return {
                "success": True,
                "message": f"Geri alındı: {entry['filename']}",
                "entry": entry,
                "path": path,
            }
        except Exception as e:
            return {"success": False, "message": f"Geri alma başarısız: {e}"}

    def undo_batch(self, batch_id: str) -> Dict[str, Any]:
        """Aynı batch_id'deki tüm değişiklikleri ters sırada geri al."""
        if not batch_id:
            return {"success": False, "message": "batch_id gerekli."}
        targets = [
            e for e in self._entries
            if e.get("batch_id") == batch_id and not e.get("undone")
        ]
        if not targets:
            return {"success": False, "message": "Bu paket için geri alınacak kayıt yok."}

        results = []
        for entry in reversed(targets):
            # Temporarily mark as last by undoing this specific entry
            path = entry["path"]
            before = entry.get("before", "")
            try:
                p = Path(path)
                if before == "" and entry.get("action") == "create" and p.exists():
                    p.unlink()
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(before)
                entry["undone"] = True
                results.append(entry["filename"])
            except Exception as e:
                return {"success": False, "message": f"{entry['filename']} geri alınamadı: {e}", "undone": results}

        self._save()
        return {
            "success": True,
            "message": f"Paket geri alındı ({len(results)} dosya): {', '.join(results)}",
            "files": results,
            "batch_id": batch_id,
        }

    def recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        active = [e for e in self._entries if not e.get("undone")]
        return list(reversed(active[-limit:]))
