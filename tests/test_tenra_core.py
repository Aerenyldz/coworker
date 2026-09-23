"""Tenra 2.0 — pytest regresyon süiti (Faz 1–3 çekirdek kontrolleri)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ── Faz 1 ────────────────────────────────────────────────────

def test_think_mode_hybrid():
    from tenra.core.agent import should_enable_think
    assert should_enable_think("/think mimari", 0, False) is True
    assert should_enable_think("/think mimari", 1, True) is False
    assert should_enable_think("Python nedir?", 0, False) is True
    assert should_enable_think("listele", 0, False) is False


def test_shell_security_blocks_encoded():
    from tenra.core.executor import TenraExecutor
    ex = TenraExecutor()
    r = ex.execute("shell", {"command": "powershell -EncodedCommand SQBFAFgA"})
    assert r.get("error") is True
    assert "engellendi" in r.get("message", "").lower() or "encoded" in r.get("message", "").lower()


def test_shell_safe_commands_not_blocked():
    from tenra.core.executor import TenraExecutor
    ex = TenraExecutor()
    for cmd in ("Get-ChildItem", "git status", "echo hello", "npm install"):
        obf, _ = ex._is_obfuscated_command(cmd)
        dang, _ = ex._is_dangerous_command(cmd)
        assert not obf and not dang, cmd


def test_stream_assemble_mock():
    from tenra.core.llm_backend import OllamaBackend

    ndjson = [
        '{"message":{"role":"assistant","content":"Mer"},"done":false}',
        '{"message":{"role":"assistant","content":"haba"},"done":true}',
    ]

    class FakeResp:
        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            yield from ndjson

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    backend = OllamaBackend("http://localhost:11434/api", "qwen3:8b")
    tokens = []
    fake = MagicMock()
    fake.post.return_value = FakeResp()
    backend.session = fake
    result = backend.chat(messages=[{"role": "user", "content": "x"}], on_token=tokens.append)
    assert "".join(tokens) == "Merhaba"
    assert result["message"]["content"] == "Merhaba"


# ── Faz 2 ────────────────────────────────────────────────────

def test_tree_sitter_js_symbols():
    from tenra.core.indexer import CodeIndexer, _tree_sitter_available
    if not _tree_sitter_available():
        pytest.skip("tree-sitter yok")
    idx = CodeIndexer(Path(tempfile.mkdtemp()))
    js = "export function greet(name) { return name; }\nexport class Widget {}"
    syms = " ".join(idx.parse_js_ts_file(js, ".js"))
    assert "greet" in syms and "Widget" in syms


def test_vector_search_semantic(tmp_path):
    from tenra.core.embeddings import EmbeddingClient, EMBED_DIM
    from tenra.core.vector_store import VectorStore

    client = EmbeddingClient()
    emb = client.embed("güvenlik sandbox testi")
    if emb is None:
        pytest.skip("Ollama/embed yok")
    assert len(emb) == EMBED_DIM

    store = VectorStore(tmp_path / "v.db", embedder=client)
    try:
        store.upsert("episode", "Güvenlik sandbox ve diff onay", workspace="t", dedupe_key="a")
        store.upsert("episode", "Token streaming eklendi", workspace="t", dedupe_key="b")
        hits = store.search("encoded powershell engelle", top_k=2, workspace="t")
        assert hits
    finally:
        store.close()


# ── Faz 3 ────────────────────────────────────────────────────

def test_batch_diff_and_undo(tmp_path):
    from tenra.core.executor import TenraExecutor
    from tenra.core.change_journal import ChangeJournal

    (tmp_path / "a.py").write_text("A0", encoding="utf-8")
    (tmp_path / "b.py").write_text("B0", encoding="utf-8")
    ex = TenraExecutor(workspace_path=str(tmp_path))
    ex.approval_callback = lambda n, p: True
    ex.journal = ChangeJournal(tmp_path / "j.json")
    ex.begin_diff_batch()
    ex.execute("file", {"action": "write", "path": "a.py", "content": "A1"})
    ex.execute("file", {"action": "write", "path": "b.py", "content": "B1"})
    flush = ex.flush_diff_batch()
    assert flush.get("success")
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "A1"
    undo = ex.undo_batch(flush["batch_id"])
    assert undo.get("success")
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "A0"


def test_hermes_model_resolve():
    from tenra.plugins._hermes_slot import resolve_uncensored_model, is_uncensored_request
    assert is_uncensored_request("/hack test") is True
    assert is_uncensored_request("dosya oku") is False
    model = resolve_uncensored_model()
    assert model is not None
    assert "dolphin" in model.lower() or "hermes" in model.lower()


def test_create_outside_workspace_blocked(tmp_path):
    import os
    from tenra.core.executor import TenraExecutor
    from tenra.core.change_journal import ChangeJournal

    ex = TenraExecutor(workspace_path=str(tmp_path))
    ex.journal = ChangeJournal(tmp_path / "j.json")
    bad = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp", "tenra_pytest_block.txt")
    r = ex.execute("file", {"action": "create", "path": bad, "content": "x"})
    assert r.get("error") is True


def test_tool_success_semantics():
    def ok(result):
        return bool(result.get("success")) and not result.get("error")
    assert ok({"success": True}) is True
    assert ok({"error": True}) is False
    assert ok({}) is False


# ── Faz 4 ────────────────────────────────────────────────────

def test_tray_controller_construct(qt_optional):
    from tenra.ui.tray import TrayController, _make_tray_icon
    icon = _make_tray_icon()
    assert not icon.isNull()
    tray = TrayController()
    assert tray.tray is not None


@pytest.fixture
def qt_optional():
    """QApplication yoksa oluştur (offscreen)."""
    import os
    import sys
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
