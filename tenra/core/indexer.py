"""Tenra 2.0 — Code Repository Map & AST Indexer

- Python: yerel ast modülü
- JS/TS/TSX/HTML/CSS: Tree-sitter (yoksa regex fallback)
- Sembol + kısa kod parçaları SQLite-vec'e indekslenir (anlamsal kod arama)
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any


IGNORED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    "dist", "build", ".next", ".nuxt", "vendor", ".gemini",
    ".idea", ".vscode", "data", "target", "coverage", ".pytest_cache",
    "_archive_v1", "archive", "archives"
}

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css",
    ".json", ".sql", ".md", ".sh", ".ps1"
}


# ── Tree-sitter lazy loaders ─────────────────────────────────

_TS_PARSERS: Dict[str, Any] = {}
_TS_AVAILABLE: Optional[bool] = None


def _tree_sitter_available() -> bool:
    global _TS_AVAILABLE
    if _TS_AVAILABLE is not None:
        return _TS_AVAILABLE
    try:
        from tree_sitter import Language, Parser  # noqa: F401
        import tree_sitter_javascript  # noqa: F401
        import tree_sitter_typescript  # noqa: F401
        import tree_sitter_html  # noqa: F401
        import tree_sitter_css  # noqa: F401
        _TS_AVAILABLE = True
    except Exception:
        _TS_AVAILABLE = False
    return _TS_AVAILABLE


def _get_parser(lang_key: str):
    """lang_key: js | ts | tsx | html | css"""
    if lang_key in _TS_PARSERS:
        return _TS_PARSERS[lang_key]
    if not _tree_sitter_available():
        return None

    from tree_sitter import Language, Parser
    import tree_sitter_javascript as tsjs
    import tree_sitter_typescript as tsts
    import tree_sitter_html as tshtml
    import tree_sitter_css as tscss

    mapping = {
        "js": tsjs.language,
        "ts": tsts.language_typescript,
        "tsx": tsts.language_tsx,
        "html": tshtml.language,
        "css": tscss.language,
    }
    factory = mapping.get(lang_key)
    if not factory:
        return None
    parser = Parser(Language(factory()))
    _TS_PARSERS[lang_key] = parser
    return parser


def _node_text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


class CodeIndexer:
    def __init__(self, index_dir: Path, vector_db_path: Path = None):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._vector_db_path = vector_db_path
        self._vector = None

    def _get_vector(self):
        if self._vector is None and self._vector_db_path is not None:
            try:
                from .vector_store import VectorStore
                self._vector = VectorStore(self._vector_db_path)
            except Exception:
                self._vector = None
        return self._vector

    def _get_cache_path(self, workspace_path: str) -> Path:
        norm_path = str(Path(workspace_path).resolve()).lower()
        path_hash = hashlib.md5(norm_path.encode("utf-8")).hexdigest()
        return self.index_dir / f"idx_{path_hash}.json"

    def _load_cache(self, cache_file: Path) -> dict:
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"files": {}}

    def _save_cache(self, cache_file: Path, data: dict):
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── Python ───────────────────────────────────────────────

    def parse_python_file(self, content: str) -> List[str]:
        symbols: List[str] = []
        try:
            tree = ast.parse(content)
        except Exception:
            for match in re.finditer(r"^(?:def|class)\s+([a-zA-Z0-9_]+)", content, re.MULTILINE):
                symbols.append(match.group(0))
            return symbols

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases = [ast.unparse(b) for b in node.bases]
                base_str = f"({', '.join(bases)})" if bases else ""
                doc = ast.get_docstring(node)
                doc_str = f"  # {doc.splitlines()[0]}" if doc else ""
                symbols.append(f"class {node.name}{base_str}:{doc_str}")
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        prefix = "async def " if isinstance(item, ast.AsyncFunctionDef) else "def "
                        args = [a.arg for a in item.args.args if a.arg != "self"]
                        args_str = ", ".join(args[:4]) + (", ..." if len(args) > 4 else "")
                        symbols.append(f"    {prefix}{item.name}({args_str})")

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
                args = [a.arg for a in node.args.args]
                args_str = ", ".join(args[:4]) + (", ..." if len(args) > 4 else "")
                doc = ast.get_docstring(node)
                doc_str = f"  # {doc.splitlines()[0]}" if doc else ""
                symbols.append(f"{prefix}{node.name}({args_str}){doc_str}")

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        symbols.append(f"{target.id} = ...")

        return symbols

    # ── JS / TS via Tree-sitter ──────────────────────────────

    def parse_js_ts_file(self, content: str, ext: str = ".js") -> List[str]:
        lang = "tsx" if ext in (".tsx", ".jsx") else ("ts" if ext in (".ts",) else "js")
        parser = _get_parser(lang)
        if parser is None and lang == "tsx":
            parser = _get_parser("js")
        if parser is None:
            return self._parse_js_ts_regex(content)

        source = content.encode("utf-8")
        try:
            tree = parser.parse(source)
        except Exception:
            return self._parse_js_ts_regex(content)

        symbols: List[str] = []
        seen = set()

        interesting = {
            "function_declaration",
            "generator_function_declaration",
            "class_declaration",
            "method_definition",
            "public_field_definition",
            "interface_declaration",
            "type_alias_declaration",
            "enum_declaration",
            "export_statement",
            "lexical_declaration",
            "variable_declaration",
            "arrow_function",
        }

        for node in _walk(tree.root_node):
            if node.type not in interesting:
                continue

            if node.type in ("function_declaration", "generator_function_declaration"):
                name = None
                params = ""
                for ch in node.children:
                    if ch.type == "identifier" and name is None:
                        name = _node_text(source, ch)
                    elif ch.type in ("formal_parameters", "parameters"):
                        params = _node_text(source, ch)
                if name:
                    line = f"function {name}{params[:40]}"
                    if line not in seen:
                        seen.add(line)
                        symbols.append(line)

            elif node.type == "class_declaration":
                name = None
                heritage = ""
                for ch in node.children:
                    if ch.type == "type_identifier" or ch.type == "identifier":
                        if name is None:
                            name = _node_text(source, ch)
                    elif ch.type == "class_heritage":
                        heritage = " " + _node_text(source, ch)[:40]
                if name:
                    line = f"class {name}{heritage}"
                    if line not in seen:
                        seen.add(line)
                        symbols.append(line)

            elif node.type == "method_definition":
                name = None
                params = ""
                for ch in node.children:
                    if ch.type in ("property_identifier", "identifier", "private_property_identifier") and name is None:
                        name = _node_text(source, ch)
                    elif ch.type in ("formal_parameters", "parameters"):
                        params = _node_text(source, ch)
                if name and name not in ("constructor",):
                    line = f"  method {name}{params[:30]}"
                    if line not in seen:
                        seen.add(line)
                        symbols.append(line)
                elif name == "constructor":
                    line = f"  constructor{params[:30]}"
                    if line not in seen:
                        seen.add(line)
                        symbols.append(line)

            elif node.type in ("interface_declaration", "type_alias_declaration", "enum_declaration"):
                name = None
                for ch in node.children:
                    if ch.type in ("type_identifier", "identifier"):
                        name = _node_text(source, ch)
                        break
                kind = {
                    "interface_declaration": "interface",
                    "type_alias_declaration": "type",
                    "enum_declaration": "enum",
                }[node.type]
                if name:
                    line = f"{kind} {name}"
                    if line not in seen:
                        seen.add(line)
                        symbols.append(line)

            elif node.type in ("lexical_declaration", "variable_declaration"):
                # const Foo = (...) =>  /  const Foo = function
                text = _node_text(source, node)
                m = re.search(
                    r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?(?:\(|function)",
                    text,
                )
                if m:
                    line = f"const {m.group(1)} = ..."
                    if line not in seen:
                        seen.add(line)
                        symbols.append(line)

        return symbols[:40] if symbols else self._parse_js_ts_regex(content)

    def _parse_js_ts_regex(self, content: str) -> List[str]:
        symbols: List[str] = []
        for m in re.finditer(r"(?:export\s+(?:default\s+)?)?function\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)", content):
            symbols.append(f"function {m.group(1)}({m.group(2)[:30]})")
        for m in re.finditer(r"(?:export\s+)?(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>", content):
            symbols.append(f"const {m.group(1)} = ({m.group(2)[:30]}) =>")
        for m in re.finditer(r"(?:export\s+)?class\s+([a-zA-Z0-9_$]+)", content):
            symbols.append(f"class {m.group(1)}")
        for m in re.finditer(r"(?:export\s+)?(?:interface|type)\s+([a-zA-Z0-9_$]+)", content):
            symbols.append(f"interface/type {m.group(1)}")
        return symbols[:15]

    # ── HTML / CSS via Tree-sitter ───────────────────────────

    def parse_html_file(self, content: str) -> List[str]:
        parser = _get_parser("html")
        if parser is None:
            return self._parse_html_regex(content)

        source = content.encode("utf-8")
        try:
            tree = parser.parse(source)
        except Exception:
            return self._parse_html_regex(content)

        symbols: List[str] = []
        seen = set()
        for node in _walk(tree.root_node):
            if node.type == "element":
                tag = None
                el_id = None
                classes = []
                for ch in node.children:
                    if ch.type == "start_tag":
                        for sch in ch.children:
                            if sch.type == "tag_name" and tag is None:
                                tag = _node_text(source, sch)
                            elif sch.type == "attribute":
                                attr = _node_text(source, sch)
                                id_m = re.search(r'id\s*=\s*["\']([^"\']+)["\']', attr, re.I)
                                if id_m:
                                    el_id = id_m.group(1)
                                cls_m = re.search(r'class\s*=\s*["\']([^"\']+)["\']', attr, re.I)
                                if cls_m:
                                    classes = cls_m.group(1).split()[:3]
                if tag in ("script", "style", "meta", "link", "br", "hr"):
                    continue
                if el_id:
                    line = f"<{tag} id={el_id}>"
                elif classes:
                    line = f"<{tag} class={'.'.join(classes)}>"
                elif tag in ("header", "nav", "main", "footer", "section", "article", "form", "title"):
                    line = f"<{tag}>"
                else:
                    continue
                if line not in seen:
                    seen.add(line)
                    symbols.append(line)
            elif node.type == "text":
                # title text handled via element
                pass

        # title özel
        title_m = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
        if title_m:
            symbols.insert(0, f"<title>: {title_m.group(1).strip()[:60]}")

        return symbols[:20] if symbols else self._parse_html_regex(content)

    def _parse_html_regex(self, content: str) -> List[str]:
        symbols: List[str] = []
        title_m = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
        if title_m:
            symbols.append(f"<title>: {title_m.group(1).strip()}")
        for m in re.finditer(r'<[a-z]+[^>]+id=["\']([a-zA-Z0-9_-]+)["\']', content, re.IGNORECASE):
            symbols.append(f"#{m.group(1)}")
        return symbols[:10]

    def parse_css_file(self, content: str) -> List[str]:
        parser = _get_parser("css")
        if parser is None:
            return self._parse_css_regex(content)

        source = content.encode("utf-8")
        try:
            tree = parser.parse(source)
        except Exception:
            return self._parse_css_regex(content)

        symbols: List[str] = []
        seen = set()
        for node in _walk(tree.root_node):
            if node.type == "rule_set":
                for ch in node.children:
                    if ch.type == "selectors":
                        sel = _node_text(source, ch).strip()
                        if sel and sel not in seen:
                            seen.add(sel)
                            symbols.append(sel[:80])
                        break
        return symbols[:25] if symbols else self._parse_css_regex(content)

    def _parse_css_regex(self, content: str) -> List[str]:
        symbols = []
        for m in re.finditer(r"^([.#]?[a-zA-Z0-9_-][^{]*)\{", content, re.MULTILINE):
            symbols.append(m.group(1).strip()[:80])
        return symbols[:15]

    # ── Unified parse ────────────────────────────────────────

    def parse_file(self, file_path: Path) -> List[str]:
        ext = file_path.suffix.lower()
        try:
            if file_path.stat().st_size > 500 * 1024:
                return [f"[Büyük Dosya: {file_path.stat().st_size // 1024} KB]"]

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if ext == ".py":
                return self.parse_python_file(content)
            elif ext in (".js", ".jsx", ".ts", ".tsx"):
                return self.parse_js_ts_file(content, ext)
            elif ext == ".html":
                return self.parse_html_file(content)
            elif ext == ".css":
                return self.parse_css_file(content)
            elif ext == ".json":
                if file_path.name == "package.json":
                    try:
                        data = json.loads(content)
                        deps = list(data.get("dependencies", {}).keys())[:5]
                        scripts = list(data.get("scripts", {}).keys())[:5]
                        return [f"name: {data.get('name')}", f"scripts: {scripts}", f"deps: {deps}"]
                    except Exception:
                        pass
                return []
            elif ext == ".md":
                headers = re.findall(r"^#{1,3}\s+(.*)", content, re.MULTILINE)
                return [f"# {h.strip()}" for h in headers[:8]]
        except Exception:
            pass
        return []

    def _index_symbols_to_vector(self, workspace_path: str, rel_path: str, symbols: List[str]):
        """Değişen dosya sembollerini anlamsal koda yaz."""
        if getattr(self, "_vector_budget", 0) <= 0:
            return
        vec = self._get_vector()
        if vec is None or not symbols:
            return
        ws = Path(workspace_path).resolve().name.lower()
        chunk = f"{rel_path}\n" + "\n".join(symbols[:12])
        try:
            row_id = vec.upsert(
                kind="code",
                text=chunk[:1500],
                workspace=ws,
                meta={"path": rel_path, "symbol_count": len(symbols)},
                dedupe_key=f"code:{ws}:{rel_path}",
            )
            if row_id is None:
                # Embedder down/hung → kalan kotayı yakma
                self._vector_budget = 0
            else:
                self._vector_budget -= 1
        except Exception:
            self._vector_budget = 0

    def index_workspace(self, workspace_path: str, max_files: int = 300) -> dict:
        ws = Path(workspace_path).resolve()
        if not ws.exists() or not ws.is_dir():
            return {}

        cache_file = self._get_cache_path(str(ws))
        cache = self._load_cache(cache_file)
        cached_files = cache.get("files", {})

        current_files: Dict[str, Any] = {}
        files_count = 0
        # İlk taramada Ollama'yı kilitlememek için yeni vektör upsert kotası
        self._vector_budget = 40

        for root, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

            for file in files:
                if files_count >= max_files:
                    break

                ext = Path(file).suffix.lower()
                if ext not in SUPPORTED_EXTENSIONS or file.startswith("."):
                    continue

                full_path = Path(root) / file
                rel_path = str(full_path.relative_to(ws)).replace("\\", "/")

                try:
                    mtime = full_path.stat().st_mtime
                    if rel_path in cached_files and cached_files[rel_path].get("mtime") == mtime:
                        current_files[rel_path] = cached_files[rel_path]
                    else:
                        symbols = self.parse_file(full_path)
                        current_files[rel_path] = {
                            "mtime": mtime,
                            "symbols": symbols,
                            "parser": "tree-sitter" if (
                                ext in (".js", ".jsx", ".ts", ".tsx", ".html", ".css")
                                and _tree_sitter_available()
                            ) else "native",
                        }
                        self._index_symbols_to_vector(str(ws), rel_path, symbols)
                    files_count += 1
                except Exception:
                    continue

            if files_count >= max_files:
                break

        cache["files"] = current_files
        cache["tree_sitter"] = _tree_sitter_available()
        self._save_cache(cache_file, cache)
        return current_files

    def get_repo_map(self, workspace_path: str, max_chars: int = 5000, query: str = None) -> str:
        """AST/Tree-sitter sembol haritası + isteğe bağlı anlamsal kod eşleşmeleri."""
        try:
            ws = Path(workspace_path).resolve()
            files_dict = self.index_workspace(str(ws))
            if not files_dict:
                return ""

            lines: List[str] = []
            ws_name = ws.name or "workspace"
            engine = "Tree-sitter+AST" if _tree_sitter_available() else "AST+regex"
            lines.append(f"📦 PROJE KOD HARİTASI ({ws_name}) [{engine}]:")

            # Anlamsal kod parçacıkları (query varsa)
            if query:
                vec = self._get_vector()
                if vec is not None:
                    try:
                        hits = vec.search(query, top_k=3, kind="code", workspace=ws_name.lower())
                        if hits:
                            lines.append("🔎 Anlamsal Kod Eşleşmeleri:")
                            for h in hits:
                                path = (h.get("meta") or {}).get("path", "")
                                preview = h.get("text", "").replace("\n", " | ")[:120]
                                lines.append(f"  • [{h.get('score', 0):.2f}] {path or preview}")
                    except Exception:
                        pass

            total_chars = sum(len(x) + 2 for x in lines)
            for rel_path, info in sorted(files_dict.items()):
                symbols = info.get("symbols", [])
                if not symbols:
                    file_header = f"• {rel_path}"
                    if total_chars + len(file_header) + 2 > max_chars:
                        break
                    lines.append(file_header)
                    total_chars += len(file_header) + 2
                    continue

                file_header = f"• {rel_path}:"
                lines.append(file_header)
                total_chars += len(file_header) + 2

                for sym in symbols[:10]:
                    sym_line = f"    {sym}"
                    if total_chars + len(sym_line) + 2 > max_chars:
                        lines.append("    ...")
                        total_chars += 7
                        break
                    lines.append(sym_line)
                    total_chars += len(sym_line) + 2

                if total_chars >= max_chars:
                    lines.append("  [... diğer dosyalar önbellekte ...]")
                    break

            return "\n".join(lines)
        except Exception as e:
            return f"[Repo-Map Hatası: {e}]"

    def close(self):
        if self._vector is not None:
            try:
                self._vector.close()
            except Exception:
                pass
            self._vector = None
