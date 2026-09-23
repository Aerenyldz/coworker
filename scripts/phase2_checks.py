"""Phase 2 regression checks — RAG + Tree-sitter."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tenra.config import EMBED_MODEL, VECTOR_DB_FILE, INDEX_DIR, MEMORY_FILE
from tenra.core.embeddings import EmbeddingClient, EMBED_DIM
from tenra.core.vector_store import VectorStore
from tenra.core.memory import MemoryStore
from tenra.core.indexer import CodeIndexer, _tree_sitter_available


def test_tree_sitter_js_ts_html():
    assert _tree_sitter_available(), "tree-sitter packages missing"
    idx = CodeIndexer(INDEX_DIR)

    js = '''
export function greet(name) {
  return `hello ${name}`;
}
export class Widget extends Base {
  constructor(props) { super(props); }
  render() { return null; }
}
export const useThing = (x) => x + 1;
'''
    syms = idx.parse_js_ts_file(js, ".js")
    joined = " ".join(syms)
    assert "greet" in joined, syms
    assert "Widget" in joined, syms
    print("PASS tree_sitter_js", syms[:8])

    ts = '''
export interface User { id: string; name: string }
export type ID = string;
export enum Role { Admin, User }
export function loadUser(id: ID): User { return { id, name: "" }; }
'''
    tsyms = idx.parse_js_ts_file(ts, ".ts")
    tjoined = " ".join(tsyms)
    assert "User" in tjoined or "interface" in tjoined, tsyms
    assert "loadUser" in tjoined, tsyms
    print("PASS tree_sitter_ts", tsyms[:8])

    html = '''
<html><head><title>Demo App</title></head>
<body>
  <header id="top"><nav class="main-nav"></nav></header>
  <main id="content"><form id="login-form"></form></main>
  <footer id="foot"></footer>
</body></html>
'''
    hsyms = idx.parse_html_file(html)
    hjoined = " ".join(hsyms)
    assert "Demo" in hjoined or "title" in hjoined.lower(), hsyms
    assert "top" in hjoined or "content" in hjoined or "login" in hjoined, hsyms
    print("PASS tree_sitter_html", hsyms[:8])


def test_embeddings_and_vector_search():
    client = EmbeddingClient()
    emb = client.embed("PowerShell güvenlik sandbox ve diff onay kartı")
    assert emb is not None and len(emb) == EMBED_DIM, f"dim={None if not emb else len(emb)}"
    print(f"PASS embed model={EMBED_MODEL} dim={len(emb)}")

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test_vec.db"
        store = VectorStore(db, embedder=client)
        store.upsert(
            "episode",
            "Güvenlik sandbox ve diff önizleme: tehlikeli komut engellendi",
            workspace="coworker",
            meta={"source": "test"},
            dedupe_key="ep1",
        )
        store.upsert(
            "episode",
            "Token streaming Ollama SSE ile canlı yanıt akışı eklendi",
            workspace="coworker",
            meta={"source": "test"},
            dedupe_key="ep2",
        )
        store.upsert(
            "code",
            "tenra/core/executor.py\n_is_dangerous_command\n_is_obfuscated_command",
            workspace="coworker",
            meta={"path": "tenra/core/executor.py"},
            dedupe_key="code1",
        )
        assert store.count() >= 3
        hits = store.search("encoded powershell komut engelleme", top_k=2, workspace="coworker")
        assert hits, "semantic search returned empty"
        texts = " ".join(h["text"] for h in hits).lower()
        assert "güvenlik" in texts or "sandbox" in texts or "executor" in texts or "dangerous" in texts, hits
        print("PASS vector_search", [(round(h["score"], 3), h["text"][:50]) for h in hits])
        print(f"PASS sqlite_vec_mode={store._use_vec}")
        store.close()


def test_memory_semantic_summary():
    with tempfile.TemporaryDirectory() as td:
        mem_file = Path(td) / "memory.json"
        vec_db = Path(td) / "vec.db"
        store = MemoryStore(mem_file, vector_db_path=vec_db)
        try:
            store.add_episode("demo", "Shell güvenlik sıkılaştırma", "EncodedCommand sert blok eklendi")
            store.add_episode("demo", "UI streaming", "token_received sinyali eklendi")
            summary = store.get_memory_summary(
                str(Path(td) / "demo"),
                max_chars=2000,
                query="powershell encoded command engelle",
            )
            assert "Anlamsal Hafıza" in summary or "Encoded" in summary or "güvenlik" in summary.lower() or "Shell" in summary
            print("PASS memory_semantic_summary snippet:")
            print(summary[:400])
        finally:
            store.close()


def test_indexer_fixture_workspace():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app.ts").write_text(
            "export function bootApp(cfg: Config) { return cfg; }\n"
            "export class AppController { start() {} }\n",
            encoding="utf-8",
        )
        (root / "page.html").write_text(
            "<html><head><title>Fixture</title></head>"
            "<body><main id=\"app-root\"></main></body></html>",
            encoding="utf-8",
        )
        (root / "main.py").write_text(
            "class Runner:\n    def run(self):\n        pass\n\ndef main():\n    Runner().run()\n",
            encoding="utf-8",
        )
        vec_db = root / "vec.db"
        idx = CodeIndexer(root / "indexes", vector_db_path=vec_db)
        try:
            files = idx.index_workspace(str(root), max_files=20)
            assert "app.ts" in files and files["app.ts"]["symbols"]
            assert "page.html" in files
            assert "main.py" in files
            rmap = idx.get_repo_map(str(root), max_chars=3000, query="AppController boot")
            assert "PROJE KOD HARİTASI" in rmap
            assert "AppController" in rmap or "bootApp" in rmap
            print("PASS indexer_fixture")
            print(rmap[:500])
        finally:
            idx.close()


def test_config_prompt_wires_query():
    import inspect
    from tenra.config import get_system_prompt
    sig = inspect.signature(get_system_prompt)
    assert "query" in sig.parameters
    # Smoke: shouldn't crash (may be slow if full coworker index)
    prompt = get_system_prompt(query="hafıza vektör")
    assert "Tenra" in prompt
    print("PASS config_prompt_query len=", len(prompt))


if __name__ == "__main__":
    test_tree_sitter_js_ts_html()
    test_embeddings_and_vector_search()
    test_memory_semantic_summary()
    test_indexer_fixture_workspace()
    test_config_prompt_wires_query()
    print("ALL PHASE2 CHECKS PASSED")
