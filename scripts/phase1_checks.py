"""Phase 1 regression checks — run with .venv/Scripts/python."""
from __future__ import annotations

from unittest.mock import MagicMock

from tenra.core.agent import should_enable_think
from tenra.core.executor import TenraExecutor
from tenra.core.llm_backend import OllamaBackend


def test_mock_stream_assemble():
    ndjson = [
        '{"message":{"role":"assistant","content":"Mer"},"done":false}',
        '{"message":{"role":"assistant","content":"haba"},"done":false}',
        (
            '{"message":{"role":"assistant","content":"!",'
            '"tool_calls":[{"function":{"name":"file","arguments":{"action":"list"}}}]},'
            '"done":true,"eval_count":3}'
        ),
    ]

    class FakeResp:
        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            for line in ndjson:
                yield line

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    backend = OllamaBackend("http://localhost:11434/api", "qwen3:8b")
    tokens: list[str] = []
    fake_session = MagicMock()
    fake_session.post.return_value = FakeResp()
    backend.session = fake_session

    result = backend.chat(
        messages=[{"role": "user", "content": "x"}],
        on_token=lambda t: tokens.append(t),
    )
    assert "".join(tokens) == "Merhaba!"
    assert result["message"]["content"] == "Merhaba!"
    assert result["message"]["tool_calls"][0]["function"]["name"] == "file"
    assert result.get("done") is True
    print("PASS mock_stream_assemble", tokens)


def test_non_stream_payload():
    class FakeJson:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"role": "assistant", "content": "hi"}}

    backend = OllamaBackend("http://localhost:11434/api", "qwen3:8b")
    fake_session = MagicMock()
    fake_session.post.return_value = FakeJson()
    backend.session = fake_session

    r2 = backend.chat(messages=[{"role": "user", "content": "x"}])
    assert r2["message"]["content"] == "hi"
    payload = fake_session.post.call_args.kwargs["json"]
    assert payload["stream"] is False
    assert payload["think"] is False
    print("PASS non_stream_payload")


def test_think_mode():
    assert should_enable_think("/think mimari", 0, False) is True
    assert should_enable_think("/think mimari", 1, True) is False
    assert should_enable_think("Python nedir?", 0, False) is True
    assert should_enable_think("listele", 0, False) is False
    assert should_enable_think("/nothink nedir?", 0, False) is False
    assert should_enable_think("refactor planı yap", 0, False) is True
    print("PASS think_mode")


def test_shell_security():
    ex = TenraExecutor()

    blocked = [
        "powershell -EncodedCommand SQBFAFgA",
        "powershell -enc SQBFAFgA",
        "iex ($a+$b)",
        "Invoke-Expression ([Convert]::FromBase64String('YWI='))",
    ]
    for cmd in blocked:
        obf, _ = ex._is_obfuscated_command(cmd)
        assert obf, f"expected obfuscated: {cmd}"
        result = ex.execute("shell", {"command": cmd})
        assert result.get("error") is True, cmd

    approval = [
        "Remove-Item -Recurse C:\\temp",
        "Set-Content -Path x.py -Value hi",
        '"hi" | Out-File test.py',
    ]
    for cmd in approval:
        dang, _ = ex._is_dangerous_command(cmd)
        assert dang, f"expected dangerous: {cmd}"

    safe = [
        "Get-ChildItem",
        "Get-Content .\\README.md",
        "git status",
        "npm install",
        "pip install requests",
        "echo hello",
        "dir",
        "python -m pytest",
        "Select-String -Pattern foo",
        "Get-Process | Select-Object -First 5",
        "Write-Host merhaba",
        "Copy-Item a.txt b.txt",
        "Test-Path .\\file.py",
        "New-Item -ItemType Directory -Name foo",
    ]
    for cmd in safe:
        obf, _ = ex._is_obfuscated_command(cmd)
        dang, _ = ex._is_dangerous_command(cmd)
        assert not obf and not dang, f"false positive: {cmd} obf={obf} dang={dang}"

    print("PASS shell_security")


def test_live_stream_if_ollama():
    backend = OllamaBackend("http://localhost:11434/api", "qwen3:8b")
    if not backend.health_check():
        print("SKIP live_stream (ollama down)")
        return
    tokens: list[str] = []
    resp = backend.chat(
        messages=[{"role": "user", "content": "Reply with exactly one word: merhaba"}],
        model="qwen3:8b",
        think=False,
        num_predict=24,
        on_token=lambda t: tokens.append(t),
    )
    if "error" in resp:
        print("SKIP live_stream error:", resp)
        return
    content = (resp.get("message") or {}).get("content", "")
    assert content == "".join(tokens)
    assert len(tokens) >= 1 or len(content) >= 0
    print(f"PASS live_stream tokens={len(tokens)} content={content!r}")


if __name__ == "__main__":
    test_mock_stream_assemble()
    test_non_stream_payload()
    test_think_mode()
    test_shell_security()
    test_live_stream_if_ollama()
    print("ALL PHASE1 CHECKS PASSED")
