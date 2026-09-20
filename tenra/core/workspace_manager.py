"""Tenra 2.0 — Proje ve Sohbet (Workspace & Conversation) Yöneticisi

Antigravity benzeri çalışma alanı yönetimi:
- Projeler (Masaüstü, Coworker, Özel Klasörler)
- Sohbetler (Projeye bağlı veya bağımsız genel sohbetler)
- Kalıcı JSON tabanlı veri saklama (data/workspaces.json)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tenra.config import DESKTOP_PATH


class WorkspaceManager:
    """Projeleri ve sohbet oturumlarını yöneten ve kalıcı saklayan sınıf."""

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
            "conversations": []
        }
        self.load()

    def load(self) -> None:
        """Verileri dosyadan oku veya varsayılanları oluştur."""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"[WorkspaceManager] Yükleme hatası, sıfırlanıyor: {e}")
                self._init_defaults()
        else:
            self._init_defaults()

        # Doğrulama: Varsayılan projeler var mı?
        ws_ids = {ws["id"] for ws in self.data.get("workspaces", [])}
        if "ws-desktop" not in ws_ids:
            self.data.setdefault("workspaces", []).insert(0, {
                "id": "ws-desktop",
                "name": "Masaüstü",
                "path": DESKTOP_PATH,
                "created_at": datetime.now().isoformat()
            })

        # Coworker projesini kontrol et
        coworker_path = str(Path(__file__).resolve().parent.parent.parent)
        if not any(ws.get("path") == coworker_path for ws in self.data["workspaces"]):
            self.data["workspaces"].append({
                "id": "ws-coworker",
                "name": "Coworker (Tenra 2.0)",
                "path": coworker_path,
                "created_at": datetime.now().isoformat()
            })

        if not self.data.get("conversations"):
            self.create_conversation("Genel Sohbet", workspace_id=None)

        self.save()

    def _init_defaults(self) -> None:
        """İlk kurulum varsayılan projelerini ve sohbetini oluşturur."""
        coworker_path = str(Path(__file__).resolve().parent.parent.parent)
        self.data = {
            "active_workspace_id": "ws-desktop",
            "active_conversation_id": "conv-default",
            "workspaces": [
                {
                    "id": "ws-desktop",
                    "name": "Masaüstü",
                    "path": DESKTOP_PATH,
                    "created_at": datetime.now().isoformat()
                },
                {
                    "id": "ws-coworker",
                    "name": "Coworker (Tenra 2.0)",
                    "path": coworker_path,
                    "created_at": datetime.now().isoformat()
                }
            ],
            "conversations": [
                {
                    "id": "conv-default",
                    "title": "Genel Sohbet",
                    "workspace_id": None,
                    "messages": [],
                    "updated_at": datetime.now().isoformat()
                }
            ]
        }

    def save(self) -> None:
        """Mevcut durumu JSON dosyasına kaydeder."""
        try:
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WorkspaceManager] Kaydetme hatası: {e}")

    # ── PROJE (WORKSPACE) İŞLEMLERİ ─────────────────────────

    def get_workspaces(self) -> List[Dict[str, Any]]:
        """Tüm kayıtlı projeleri döner."""
        return self.data.get("workspaces", [])

    def get_active_workspace(self) -> Dict[str, Any]:
        """Şu an seçili olan projeyi döner."""
        active_id = self.data.get("active_workspace_id", "ws-desktop")
        for ws in self.data.get("workspaces", []):
            if ws["id"] == active_id:
                return ws
        # Bulunamazsa ilkini veya masaüstünü dön
        if self.data.get("workspaces"):
            return self.data["workspaces"][0]
        return {"id": "ws-desktop", "name": "Masaüstü", "path": DESKTOP_PATH}

    def set_active_workspace(self, workspace_id: str) -> bool:
        """Aktif projeyi değiştirir."""
        for ws in self.data.get("workspaces", []):
            if ws["id"] == workspace_id:
                self.data["active_workspace_id"] = workspace_id
                self.save()
                return True
        return False

    def add_workspace(self, path: str, name: Optional[str] = None) -> Dict[str, Any]:
        """Yeni bir proje klasörü ekler."""
        p = Path(path).resolve()
        if not p.exists() or not p.is_dir():
            raise ValueError(f"Geçersiz klasör yolu: {path}")

        norm_path = str(p)
        # Zaten varsa olanı döndür
        for ws in self.data.get("workspaces", []):
            if ws.get("path") == norm_path:
                self.data["active_workspace_id"] = ws["id"]
                self.save()
                return ws

        ws_id = f"ws-{uuid.uuid4().hex[:8]}"
        ws_name = name or p.name or "Yeni Proje"
        new_ws = {
            "id": ws_id,
            "name": ws_name,
            "path": norm_path,
            "created_at": datetime.now().isoformat()
        }
        self.data.setdefault("workspaces", []).append(new_ws)
        self.data["active_workspace_id"] = ws_id
        self.save()
        return new_ws

    def remove_workspace(self, workspace_id: str) -> bool:
        """Projeyi listeden kaldırır (klasörü silmez, sadece takipten çıkarır)."""
        if workspace_id == "ws-desktop":
            return False # Masaüstü silinemez

        self.data["workspaces"] = [
            ws for ws in self.data.get("workspaces", []) if ws["id"] != workspace_id
        ]
        if self.data.get("active_workspace_id") == workspace_id:
            self.data["active_workspace_id"] = "ws-desktop"
        self.save()
        return True

    # ── SOHBET (CONVERSATION) İŞLEMLERİ ───────────────────────

    def get_conversations(self, workspace_id: Optional[str] = None, only_independent: bool = False) -> List[Dict[str, Any]]:
        """Sohbetleri listeler.
        - only_independent=True ise bir projeye bağlı olmayanları döner.
        - workspace_id belirtilmişse o projeye ait olanları döner.
        - İkisi de yoksa tümünü döner.
        """
        all_convs = self.data.get("conversations", [])
        if only_independent:
            return [c for c in all_convs if not c.get("workspace_id")]
        if workspace_id:
            return [c for c in all_convs if c.get("workspace_id") == workspace_id]
        return all_convs

    def get_active_conversation(self) -> Optional[Dict[str, Any]]:
        """Şu an aktif sohbeti döner."""
        active_id = self.data.get("active_conversation_id")
        for c in self.data.get("conversations", []):
            if c["id"] == active_id:
                return c
        # Yoksa ilkini dön
        if self.data.get("conversations"):
            return self.data["conversations"][0]
        return None

    def set_active_conversation(self, conversation_id: str) -> bool:
        """Aktif sohbeti değiştirir."""
        for c in self.data.get("conversations", []):
            if c["id"] == conversation_id:
                self.data["active_conversation_id"] = conversation_id
                self.save()
                return True
        return False

    def create_conversation(self, title: str = "Yeni Sohbet", workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Yeni bir sohbet oluşturur."""
        conv_id = f"conv-{uuid.uuid4().hex[:8]}"
        new_conv = {
            "id": conv_id,
            "title": title,
            "workspace_id": workspace_id,
            "messages": [],
            "updated_at": datetime.now().isoformat()
        }
        self.data.setdefault("conversations", []).insert(0, new_conv)
        self.data["active_conversation_id"] = conv_id
        self.save()
        return new_conv

    def save_conversation_messages(self, conversation_id: str, messages: List[Dict[str, Any]], title: Optional[str] = None) -> bool:
        """Sohbetin mesaj geçmişini kaydeder."""
        for c in self.data.get("conversations", []):
            if c["id"] == conversation_id:
                c["messages"] = messages
                c["updated_at"] = datetime.now().isoformat()
                if title:
                    c["title"] = title
                elif c.get("title") == "Yeni Sohbet" and messages:
                    # İlk kullanıcı mesajından başlık türet
                    first_user_msg = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
                    if first_user_msg:
                        c["title"] = first_user_msg[:24].strip() + ("..." if len(first_user_msg) > 24 else "")
                self.save()
                return True
        return False

    def delete_conversation(self, conversation_id: str) -> bool:
        """Sohbeti siler."""
        self.data["conversations"] = [
            c for c in self.data.get("conversations", []) if c["id"] != conversation_id
        ]
        if self.data.get("active_conversation_id") == conversation_id:
            if self.data.get("conversations"):
                self.data["active_conversation_id"] = self.data["conversations"][0]["id"]
            else:
                self.create_conversation("Genel Sohbet", workspace_id=None)
        self.save()
        return True
