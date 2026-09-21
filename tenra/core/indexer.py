"""Tenra 2.0 — Code Repository Map & AST Indexer

Cursor ve Aider mimarisinden esinlenilmiştir:
- Çalışma alanındaki (workspace) kod dosyalarını tarar (Python AST, JS/TS, HTML, CSS, JSON).
- Fonksiyon, sınıf, metot, API ve bileşen imzalarını (signatures) kompakt bir haritaya dönüştürür.
- Sonuçları disk üzerinde (data/indexes/<hash>.json) mtime bazlı önbelleğe alır.
- LLM context'ine tüm projeyi 1.5k-2k token gibi optimize bir boyutta harita olarak sunar.
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


class CodeIndexer:
    def __init__(self, index_dir: Path):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

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

    def parse_python_file(self, content: str) -> List[str]:
        """Python AST ile sınıf ve fonksiyon imzalarını çıkarır."""
        symbols: List[str] = []
        try:
            tree = ast.parse(content)
        except Exception:
            # AST parse başarısızsa regex fallback
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

                # Metotlar
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
                # Önemli büyük harfli sabitler (örn. APP_NAME, CONFIG)
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        symbols.append(f"{target.id} = ...")

        return symbols

    def parse_js_ts_file(self, content: str) -> List[str]:
        """JavaScript / TypeScript dosyalarından fonksiyon ve sınıfları çıkarır."""
        symbols: List[str] = []
        # function f(...)
        for m in re.finditer(r"(?:export\s+(?:default\s+)?)?function\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)", content):
            symbols.append(f"function {m.group(1)}({m.group(2)[:30]})")
        # const/let f = (...) =>
        for m in re.finditer(r"(?:export\s+)?(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>", content):
            symbols.append(f"const {m.group(1)} = ({m.group(2)[:30]}) =>")
        # class Foo
        for m in re.finditer(r"(?:export\s+)?class\s+([a-zA-Z0-9_$]+)", content):
            symbols.append(f"class {m.group(1)}")
        # interface / type (TypeScript)
        for m in re.finditer(r"(?:export\s+)?(?:interface|type)\s+([a-zA-Z0-9_$]+)", content):
            symbols.append(f"interface/type {m.group(1)}")
        return symbols[:15]

    def parse_html_file(self, content: str) -> List[str]:
        """HTML dosyasının başlık ve ana blok yapılarını çıkarır."""
        symbols: List[str] = []
        title_m = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
        if title_m:
            symbols.append(f"<title>: {title_m.group(1).strip()}")
        # Ana taşıyıcı ID'ler
        for m in re.finditer(r'<[a-z]+[^>]+id=["\']([a-zA-Z0-9_-]+)["\']', content, re.IGNORECASE):
            symbols.append(f"#{m.group(1)}")
        return symbols[:10]

    def parse_file(self, file_path: Path) -> List[str]:
        """Dosya uzantısına göre sembolleri ayrıştırır."""
        ext = file_path.suffix.lower()
        try:
            # 500KB'dan büyük dosyaları atla (performans)
            if file_path.stat().st_size > 500 * 1024:
                return [f"[Büyük Dosya: {file_path.stat().st_size // 1024} KB]"]

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if ext == ".py":
                return self.parse_python_file(content)
            elif ext in (".js", ".jsx", ".ts", ".tsx"):
                return self.parse_js_ts_file(content)
            elif ext == ".html":
                return self.parse_html_file(content)
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

    def index_workspace(self, workspace_path: str, max_files: int = 300) -> dict:
        """Çalışma alanındaki tüm geçerli dosyaları tarar ve önbelleği günceller."""
        ws = Path(workspace_path).resolve()
        if not ws.exists() or not ws.is_dir():
            return {}

        cache_file = self._get_cache_path(str(ws))
        cache = self._load_cache(cache_file)
        cached_files = cache.get("files", {})

        current_files: Dict[str, Any] = {}
        files_count = 0

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
                            "symbols": symbols
                        }
                    files_count += 1
                except Exception:
                    continue

            if files_count >= max_files:
                break

        cache["files"] = current_files
        self._save_cache(cache_file, cache)
        return current_files

    def get_repo_map(self, workspace_path: str, max_chars: int = 5000) -> str:
        """Tüm projenin AST sembol haritasını kompakt metin olarak üretir."""
        try:
            ws = Path(workspace_path).resolve()
            files_dict = self.index_workspace(str(ws))
            if not files_dict:
                return ""

            lines: List[str] = []
            ws_name = ws.name or "workspace"
            lines.append(f"📦 PROJE KOD HARİTASI ({ws_name}):")

            total_chars = len(lines[0])
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

                for sym in symbols[:10]:  # dosya başına max 10 ana sembol
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
