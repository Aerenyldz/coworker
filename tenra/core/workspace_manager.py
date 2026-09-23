"""Tenra 2.0 — Proje ve Sohbet yöneticisi (proje başına izole bağlam)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tenra.config import DESKTOP_PATH


class WorkspaceManager:
    """Her projenin kendi sohbetleri / bağlamı vardır (Antigravity / Cursor modeli)."""

    def __init__(self, storage_file: Optional[Path | str] = None):
        if storage_file is None:
            data_dir = Path(__file__).resolve().parent.parent.parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.storage_file = data_dir / "workspaces.json"
        else:
            self.storage_file = Path(storage_file)

        self.data: Dict[str, Any] = {
            "active_workspace_id": "ws-desktop",
            "active_conversation_id": "conv-default",
            "workspaces": [],
            "conversations": [],
        }
        self.load()

    def load(self) -> None:
        if self.storage_file.exists():
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"[WorkspaceManager] Yükleme hatası, sıfırlanıyor: {e}")
                self._init_defaults()
        else:
            self._init_defaults()

        ws_ids = {ws["id"] for ws in self.data.get("workspaces", [])}
        if "ws-desktop" not in ws_ids:
            self.data.setdefault("workspaces", []).insert(0, {
                "id": "ws-desktop",
                "name": "Masaüstü",
                "path": DESKTOP_PATH,
                "created_at": datetime.now().isoformat(),
            })
            ws_ids.add("ws-desktop")

        coworker_path = str(Path(__file__).resolve().parent.parent.parent)
        if not any(ws.get("path") == coworker_path for ws in self.data["workspaces"]):
            self.data["workspaces"].append({
                "id": "ws-coworker",
                "name": "Coworker (Tenra 2.0)",
                "path": coworker_path,
                "created_at": datetime.now().isoformat(),
            })

        # Eski bağımsız sohbetleri Masaüstü'ne bağla (proje bağlamı zorunlu)
        for c in self.data.get("conversations", []):
            wid = c.get("workspace_id")
            if not wid or wid not in {w["id"] for w in self.data.get("workspaces", [])}:
                c["workspace_id"] = "ws-desktop"

        if not self.data.get("conversations"):
            self.create_conversation("Genel Sohbet", workspace_id="ws-desktop")

        # Aktif sohbet aktif projeye ait değilse düzelt
        self._sync_active_conversation_to_workspace()
        self.save()

    def _init_defaults(self) -> None:
        coworker_path = str(Path(__file__).resolve().parent.parent.parent)
        self.data = {
            "active_workspace_id": "ws-desktop",
            "active_conversation_id": "conv-default",
            "workspaces": [
                {
                    "id": "ws-desktop",
                    "name": "Masaüstü",
                    "path": DESKTOP_PATH,
                    "created_at": datetime.now().isoformat(),
                },
                {
                    "id": "ws-coworker",
                    "name": "Coworker (Tenra 2.0)",
                    "path": coworker_path,
                    "created_at": datetime.now().isoformat(),
                },
            ],
            "conversations": [
                {
                    "id": "conv-default",
                    "title": "Genel Sohbet",
                    "workspace_id": "ws-desktop",
                    "messages": [],
                    "updated_at": datetime.now().isoformat(),
                }
            ],
        }

    def save(self) -> None:
        try:
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WorkspaceManager] Kaydetme hatası: {e}")

    def _sort_convs(self, convs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            convs,
            key=lambda c: c.get("updated_at") or c.get("created_at") or "",
            reverse=True,
        )

    def _sync_active_conversation_to_workspace(self) -> None:
        """Aktif sohbet, aktif projeye ait değilse o projenin son sohbetine geç."""
        ws = self.get_active_workspace()
        ws_id = ws["id"]
        active = self.get_active_conversation()
        if active and active.get("workspace_id") == ws_id:
            return
        convs = self.get_conversations(workspace_id=ws_id)
        if convs:
            self.data["active_conversation_id"] = convs[0]["id"]
        else:
            new_c = self.create_conversation("Genel Sohbet", workspace_id=ws_id)
            self.data["active_conversation_id"] = new_c["id"]

    # ── PROJE ─────────────────────────────────────────────

    def get_workspaces(self) -> List[Dict[str, Any]]:
        return self.data.get("workspaces", [])

    def get_active_workspace(self) -> Dict[str, Any]:
        active_id = self.data.get("active_workspace_id", "ws-desktop")
        for ws in self.data.get("workspaces", []):
            if ws["id"] == active_id:
                return ws
        if self.data.get("workspaces"):
            return self.data["workspaces"][0]
        return {"id": "ws-desktop", "name": "Masaüstü", "path": DESKTOP_PATH}

    def set_active_workspace(self, workspace_id: str) -> bool:
        """Projeyi seçer ve o projenin sohbet bağlamına geçer."""
        for ws in self.data.get("workspaces", []):
            if ws["id"] == workspace_id:
                self.data["active_workspace_id"] = workspace_id
                self._sync_active_conversation_to_workspace()
                self.save()
                return True
        return False

    def add_workspace(self, path: str, name: Optional[str] = None) -> Dict[str, Any]:
        p = Path(path).resolve()
        if not p.exists() or not p.is_dir():
            raise ValueError(f"Geçersiz klasör yolu: {path}")

        norm_path = str(p)
        for ws in self.data.get("workspaces", []):
            if ws.get("path") == norm_path:
                self.set_active_workspace(ws["id"])
                return ws

        ws_id = f"ws-{uuid.uuid4().hex[:8]}"
        new_ws = {
            "id": ws_id,
            "name": name or p.name or "Yeni Proje",
            "path": norm_path,
            "created_at": datetime.now().isoformat(),
        }
        self.data.setdefault("workspaces", []).append(new_ws)
        self.data["active_workspace_id"] = ws_id
        # Yeni projede boş sohbet bağlamı
        self.create_conversation("Genel Sohbet", workspace_id=ws_id)
        self.save()
        return new_ws

    def remove_workspace(self, workspace_id: str) -> bool:
        if workspace_id == "ws-desktop":
            return False

        # Proje sohbetlerini de sil (bağlam izolasyonu)
        self.data["conversations"] = [
            c for c in self.data.get("conversations", [])
            if c.get("workspace_id") != workspace_id
        ]
        self.data["workspaces"] = [
            ws for ws in self.data.get("workspaces", []) if ws["id"] != workspace_id
        ]
        if self.data.get("active_workspace_id") == workspace_id:
            self.data["active_workspace_id"] = "ws-desktop"
        self._sync_active_conversation_to_workspace()
        self.save()
        return True

    # ── SOHBET ────────────────────────────────────────────

    def get_conversations(
        self,
        workspace_id: Optional[str] = None,
        only_independent: bool = False,
    ) -> List[Dict[str, Any]]:
        all_convs = self.data.get("conversations", [])
        if only_independent:
            # Geriye dönük: artık bağımsız yok; boş liste
            return []
        if workspace_id:
            return self._sort_convs(
                [c for c in all_convs if c.get("workspace_id") == workspace_id]
            )
        return self._sort_convs(all_convs)

    def get_active_conversation(self) -> Optional[Dict[str, Any]]:
        active_id = self.data.get("active_conversation_id")
        for c in self.data.get("conversations", []):
            if c["id"] == active_id:
                return c
        if self.data.get("conversations"):
            return self.data["conversations"][0]
        return None

    def set_active_conversation(self, conversation_id: str) -> bool:
        for c in self.data.get("conversations", []):
            if c["id"] == conversation_id:
                self.data["active_conversation_id"] = conversation_id
                # Sohbet başka projedeyse projeyi de ona çek
                wid = c.get("workspace_id")
                if wid:
                    self.data["active_workspace_id"] = wid
                self.save()
                return True
        return False

    def create_conversation(
        self, title: str = "Yeni Sohbet", workspace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not workspace_id:
            workspace_id = self.get_active_workspace()["id"]
        conv_id = f"conv-{uuid.uuid4().hex[:8]}"
        new_conv = {
            "id": conv_id,
            "title": title,
            "workspace_id": workspace_id,
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self.data.setdefault("conversations", []).insert(0, new_conv)
        self.data["active_conversation_id"] = conv_id
        self.data["active_workspace_id"] = workspace_id
        self.save()
        return new_conv

    def save_conversation_messages(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        title: Optional[str] = None,
    ) -> bool:
        for c in self.data.get("conversations", []):
            if c["id"] == conversation_id:
                c["messages"] = messages
                c["updated_at"] = datetime.now().isoformat()
                if title:
                    c["title"] = title
                elif c.get("title") in ("Yeni Sohbet", "Genel Sohbet") and messages:
                    first_user_msg = next(
                        (m.get("content", "") for m in messages if m.get("role") == "user"),
                        "",
                    )
                    if first_user_msg:
                        c["title"] = first_user_msg[:24].strip() + (
                            "..." if len(first_user_msg) > 24 else ""
                        )
                self.save()
                return True
        return False

    def delete_conversation(self, conversation_id: str) -> bool:
        target = next(
            (c for c in self.data.get("conversations", []) if c["id"] == conversation_id),
            None,
        )
        ws_id = (target or {}).get("workspace_id") or self.get_active_workspace()["id"]

        self.data["conversations"] = [
            c for c in self.data.get("conversations", []) if c["id"] != conversation_id
        ]
        if self.data.get("active_conversation_id") == conversation_id:
            siblings = self.get_conversations(workspace_id=ws_id)
            if siblings:
                self.data["active_conversation_id"] = siblings[0]["id"]
            else:
                self.create_conversation("Genel Sohbet", workspace_id=ws_id)
        self.save()
        return True
