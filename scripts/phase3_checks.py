"""Phase 3 regression — multi-diff, rollback, hermes slot, voice modules."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tenra.config import UNCENSORED_MODEL, UNCENSORED_FALLBACK, CHANGE_JOURNAL_FILE
from tenra.core.change_journal import ChangeJournal
from tenra.core.executor import TenraExecutor
from tenra.plugins._hermes_slot import (
    get_active_model,
    is_uncensored_request,
    resolve_uncensored_model,
)


def test_hermes_slot_and_model():
    assert is_uncensored_request("/hack anlat") is True
    assert is_uncensored_request("sansürsüz mod aç") is True
    assert is_uncensored_request("dosyayı oku") is False
    assert get_active_model(uncensored=False, user_input="merhaba") == "qwen3:8b"
    model = resolve_uncensored_model()
    assert model is not None
    assert "dolphin" in model.lower() or "hermes" in model.lower()
    print("PASS hermes_slot model=", model)


def test_change_journal_undo():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "demo.txt"
        f.write_text("eski", encoding="utf-8")
        journal = ChangeJournal(root / "journal.json")
        journal.record(str(f), before="eski", after="yeni", action="write")
        f.write_text("yeni", encoding="utf-8")
        result = journal.undo_last()
        assert result["success"] is True
        assert f.read_text(encoding="utf-8") == "eski"
        print("PASS change_journal_undo")


def test_batch_diff_and_undo():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        a = root / "a.py"
        b = root / "b.py"
        a.write_text("A0", encoding="utf-8")
        b.write_text("B0", encoding="utf-8")

        approvals = []

        def approve(name, params):
            approvals.append(name)
            return True

        ex = TenraExecutor(workspace_path=str(root))
        ex.approval_callback = approve
        # Use temp journal
        from tenra.core.change_journal import ChangeJournal
        ex.journal = ChangeJournal(root / "j.json")

        ex.begin_diff_batch()
        r1 = ex.execute("file", {"action": "write", "path": "a.py", "content": "A1"})
        r2 = ex.execute("file", {"action": "write", "path": "b.py", "content": "B1"})
        assert r1.get("batched") and r2.get("batched")
        # Not written yet
        assert a.read_text(encoding="utf-8") == "A0"
        flush = ex.flush_diff_batch()
        assert flush.get("success") is True
        assert a.read_text(encoding="utf-8") == "A1"
        assert b.read_text(encoding="utf-8") == "B1"
        assert "diff_batch" in approvals
        batch_id = flush["batch_id"]
        undo = ex.undo_batch(batch_id)
        assert undo.get("success") is True
        assert a.read_text(encoding="utf-8") == "A0"
        assert b.read_text(encoding="utf-8") == "B0"
        print("PASS batch_diff_and_undo", batch_id)


def test_single_write_still_journals():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        f = root / "solo.txt"
        f.write_text("1", encoding="utf-8")
        ex = TenraExecutor(workspace_path=str(root))
        ex.approval_callback = lambda n, p: True
        from tenra.core.change_journal import ChangeJournal
        ex.journal = ChangeJournal(root / "j.json")
        ex.execute("file", {"action": "write", "path": "solo.txt", "content": "2"})
        assert f.read_text(encoding="utf-8") == "2"
        undo = ex.undo_last_change()
        assert undo.get("success") is True
        assert f.read_text(encoding="utf-8") == "1"
        print("PASS single_write_journal")


def test_voice_modules_import():
    from tenra.voice.stt import VoiceListenerThread, _get_whisper
    from tenra.voice.tts import get_synthesizer, speak
    synth = get_synthesizer()
    print(f"PASS tts_backend={synth.backend_name} available={synth.available}")
    # whisper model load can be slow; just probe import path
    try:
        import faster_whisper  # noqa: F401
        print("PASS faster_whisper_import")
    except Exception as e:
        print("WARN faster_whisper not installed:", e)


def test_multi_diff_html():
    from tenra.ui.markdown import make_multi_diff_card_html
    html = make_multi_diff_card_html([
        {"filename": "a.py", "diff": "--- a\n+++ b\n@@\n-old\n+new\n"},
        {"filename": "b.py", "diff": "--- a\n+++ b\n@@\n-x\n+y\n"},
    ])
    assert "a.py" in html and "b.py" in html
    print("PASS multi_diff_html")


if __name__ == "__main__":
    test_hermes_slot_and_model()
    test_change_journal_undo()
    test_batch_diff_and_undo()
    test_single_write_still_journals()
    test_voice_modules_import()
    test_multi_diff_html()
    print("ALL PHASE3 CHECKS PASSED")
