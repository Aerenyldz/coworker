import os
import subprocess
import difflib
import json
import re
import shutil
import glob
from pathlib import Path

class TenraExecutor:
    def __init__(self, workspace_path: str = None):
        from ..config import DESKTOP_PATH
        self.desktop_path = DESKTOP_PATH
        self.workspace_path = str(Path(workspace_path).resolve()) if workspace_path else self.desktop_path
        self.workspace_name = os.path.basename(self.workspace_path) if self.workspace_path != self.desktop_path else "Masaüstü"
        self.user_home = os.path.expanduser('~')
        self.approval_callback = None
        self.tool_start_callback = None
        
    def _get_path(self, path_str):
        if not path_str:
            return self.workspace_path
        path_str = str(path_str).strip()
        norm = path_str.replace('\\', '/')
        if norm.startswith('~/Desktop/'):
            path_str = os.path.join(self.desktop_path, norm[10:])
        elif '/Desktop/' in norm:
            idx = norm.find('/Desktop/')
            path_str = os.path.join(self.desktop_path, norm[idx + 9:])
        p = Path(path_str)
        if not p.is_absolute():
            p = Path(self.workspace_path) / p
        return str(p)

    def execute(self, tool_name, params):
        synonyms = {
            "cmd": "shell", "powershell": "shell", "run": "shell",
            "dosya": "file", "dosyaislemleri": "file",
            "tarayici": "web", "internet": "web", "browser": "web",
            "ekran": "screen", "goruntu": "screen"
        }
        tool_name = tool_name.lower().strip()
        tool_name = synonyms.get(tool_name, tool_name)
        
        valid_tools = ["shell", "file", "web", "screen"]
        if tool_name not in valid_tools:
            matches = difflib.get_close_matches(tool_name, valid_tools, n=1, cutoff=0.5)
            if matches:
                tool_name = matches[0]
            else:
                return {"error": True, "message": f"Tool '{tool_name}' not found."}
                
        try:
            if tool_name == "shell":
                return self._tool_shell(**params)
            elif tool_name == "file":
                return self._tool_file(**params)
            elif tool_name == "web":
                return self._tool_web(**params)
            elif tool_name == "screen":
                return self._tool_screen(**params)
        except Exception as e:
            return {"error": True, "message": f"Execution failed: {str(e)}"}
            
    def _tool_shell(self, command, timeout=30):
        try:
            cwd = self.workspace_path if os.path.isdir(self.workspace_path) else self.desktop_path
            result = subprocess.run(['powershell', '-Command', command], 
                                    cwd=cwd,
                                    capture_output=True, text=True, timeout=timeout)
            stdout = result.stdout[:3000]
            if len(result.stdout) > 3000:
                stdout += "\n...[TRUNCATED]"
            stderr = result.stderr[:1000]
            return {
                "success": result.returncode == 0,
                "message": "Command executed",
                "data": {
                    "command": command,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": result.returncode
                }
            }
        except subprocess.TimeoutExpired:
            return {"error": True, "message": "Command timed out."}
        except Exception as e:
            return {"error": True, "message": str(e)}

    def _tool_file(self, action, path="", content=None, old_string=None, new_string=None, pattern=None, **kwargs):
        full_path = self._get_path(path)
        
        if action == "read":
            if not os.path.exists(full_path):
                # 1. Uzantı eklemeyi dene (.html, .js, .py, .json, .txt, .css, .md vb.)
                resolved = None
                for ext in [".html", ".js", ".py", ".json", ".txt", ".css", ".md", ".jsx", ".tsx", ".ts"]:
                    candidate = full_path + ext
                    if os.path.exists(candidate) and os.path.isfile(candidate):
                        resolved = candidate
                        break
                # 2. Üst dizinde veya workspace_path içinde yakın eşleşme ara
                if not resolved:
                    dir_to_search = os.path.dirname(full_path) if os.path.dirname(full_path) and os.path.exists(os.path.dirname(full_path)) else self.workspace_path
                    if os.path.exists(dir_to_search):
                        files = [f for f in os.listdir(dir_to_search) if os.path.isfile(os.path.join(dir_to_search, f))]
                        target_name = os.path.basename(full_path)

                        # Fonetik / yaygın Türkçe yazım eşleştirmesi (örn. indeks -> index)
                        tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
                        norm_target = target_name.translate(tr_map).lower().replace("indeks", "index")

                        # Doğrudan veya normalize eşleşme
                        for f in files:
                            norm_f = f.translate(tr_map).lower()
                            if norm_target == norm_f or norm_f.startswith(norm_target):
                                resolved = os.path.join(dir_to_search, f)
                                break

                        # Difflib yakın eşleştirme
                        if not resolved:
                            matches = difflib.get_close_matches(target_name, files, n=1, cutoff=0.5)
                            if matches:
                                resolved = os.path.join(dir_to_search, matches[0])
                            else:
                                # Normalize difflib
                                norm_files = [f.translate(tr_map).lower() for f in files]
                                norm_matches = difflib.get_close_matches(norm_target, norm_files, n=1, cutoff=0.45)
                                if norm_matches:
                                    idx = norm_files.index(norm_matches[0])
                                    resolved = os.path.join(dir_to_search, files[idx])

                if resolved and os.path.exists(resolved):
                    full_path = resolved
                else:
                    return {"error": True, "message": f"Dosya bulunamadı: '{path}'"}

            # Eğer seçilen yol klasörse okumak yerine listele
            if os.path.isdir(full_path):
                items = os.listdir(full_path)
                data = [{"name": i, "is_dir": os.path.isdir(os.path.join(full_path, i))} for i in items]
                return {"success": True, "message": f"'{path}' bir klasör. İçindeki dosyalar listelendi.", "items": data}

            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            offset = kwargs.get('offset', 0)
            limit = kwargs.get('limit', 1000)
            chunk = lines[offset:offset+limit]
            text = "".join(f"{i+offset+1}: {line}" for i, line in enumerate(chunk))
            return {"success": True, "content": text, "total_lines": len(lines), "path": full_path}
            
        elif action == "write":
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content or "")
            return {"success": True, "message": f"File written: {full_path}"}
            
        elif action == "patch":
            if not os.path.exists(full_path):
                return {"error": True, "message": "File not found."}
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                data = f.read()
            data_norm = data.replace('\r\n', '\n')
            old_norm = (old_string or "").replace('\r\n', '\n')
            if old_norm in data_norm:
                data_norm = data_norm.replace(old_norm, (new_string or ""))
            else:
                return {"error": True, "message": "Target string not found for patch."}
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(data_norm)
            return {"success": True, "message": "File patched successfully."}
            
        elif action == "create":
            if os.path.exists(full_path):
                return {"error": True, "message": "File already exists."}
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content or "")
            return {"success": True, "message": "File created."}
            
        elif action == "delete":
            if not os.path.exists(full_path):
                # Fuzzy matching fallback
                dir_path = os.path.dirname(full_path)
                if os.path.exists(dir_path):
                    files = os.listdir(dir_path)
                    matches = difflib.get_close_matches(os.path.basename(full_path), files, n=1, cutoff=0.6)
                    if matches:
                        full_path = os.path.join(dir_path, matches[0])
            if os.path.exists(full_path):
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                else:
                    os.remove(full_path)
                return {"success": True, "message": "Deleted permanently."}
            return {"error": True, "message": "File not found."}
            
        elif action == "trash":
            try:
                import send2trash
                if os.path.exists(full_path):
                    send2trash.send2trash(full_path)
                    return {"success": True, "message": "Moved to recycle bin."}
                return {"error": True, "message": "File not found."}
            except ImportError:
                return {"error": True, "message": "send2trash not installed."}
                
        elif action == "rename":
            new_path = self._get_path(kwargs.get("new_name", ""))
            if os.path.exists(full_path):
                os.rename(full_path, new_path)
                return {"success": True, "message": f"Renamed to {new_path}"}
            return {"error": True, "message": "Source not found."}
            
        elif action == "find":
            results = []
            for root, _, files in os.walk(self.user_home):
                for f in files:
                    if pattern and pattern.lower() in f.lower():
                        results.append(os.path.join(root, f))
            return {"success": True, "results": results[:50]}
            
        elif action == "search":
            results = []
            if os.path.isdir(full_path):
                for f in glob.glob(os.path.join(full_path, '**', '*.*'), recursive=True):
                    try:
                        with open(f, 'r', encoding='utf-8') as file:
                            content_str = file.read()
                            if pattern and re.search(pattern, content_str):
                                results.append(f)
                    except:
                        pass
            return {"success": True, "results": results[:50]}
            
        elif action == "list":
            if not os.path.exists(full_path):
                if os.path.exists(self.workspace_path):
                    full_path = self.workspace_path
            if os.path.isdir(full_path):
                items = os.listdir(full_path)
                data = [{"name": i, "is_dir": os.path.isdir(os.path.join(full_path, i))} for i in items]
                return {"success": True, "items": data, "directory": full_path}
            return {"error": True, "message": f"Dizin bulunamadı: {full_path}"}
            
        return {"error": True, "message": "Unknown action."}

    def _tool_web(self, action, query=None, url=None, **kwargs):
        if action == "search":
            try:
                try:
                    from ddgs import DDGS
                except ImportError:
                    from duckduckgo_search import DDGS
                results = list(DDGS().text(query, max_results=5))
                return {"success": True, "results": results}
            except Exception as e:
                return {"error": True, "message": str(e)}
        elif action == "browse":
            try:
                import requests
                from bs4 import BeautifulSoup
                resp = requests.get(url, timeout=10)
                soup = BeautifulSoup(resp.content, 'html.parser')
                text = soup.get_text(separator=' ', strip=True)
                return {"success": True, "content": text[:8000]}
            except Exception as e:
                return {"error": True, "message": str(e)}
        elif action == "open":
            import webbrowser
            webbrowser.open(url)
            return {"success": True, "message": f"Opened {url} in browser."}
        return {"error": True, "message": "Unknown action."}

    def _tool_screen(self, action, x=None, y=None, text=None, **kwargs):
        try:
            import pyautogui
        except ImportError:
            return {"error": True, "message": "pyautogui not installed."}
            
        if action == "click":
            pyautogui.click(x=x, y=y)
            return {"success": True, "message": "Clicked."}
        elif action == "click_text":
            try:
                import pytesseract
                import cv2
                import numpy as np
                img = pyautogui.screenshot()
                img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                data = pytesseract.image_to_data(img_cv, output_type=pytesseract.Output.DICT)
                for i in range(len(data['text'])):
                    if text.lower() in data['text'][i].lower():
                        x = data['left'][i] + data['width'][i] // 2
                        y = data['top'][i] + data['height'][i] // 2
                        pyautogui.click(x=x, y=y)
                        return {"success": True, "message": f"Clicked text '{text}'."}
                return {"error": True, "message": "Text not found on screen."}
            except Exception as e:
                return {"error": True, "message": f"OCR failed: {str(e)}"}
        elif action == "type":
            pyautogui.write(text, interval=0.01)
            if kwargs.get('enter', False):
                pyautogui.press('enter')
            return {"success": True, "message": "Typed text."}
        elif action == "hotkey":
            keys = kwargs.get("keys", [])
            pyautogui.hotkey(*keys)
            return {"success": True, "message": "Hotkey pressed."}
        elif action == "screenshot":
            path = os.path.join(self.desktop_path, 'screenshot.png')
            pyautogui.screenshot(path)
            return {"success": True, "path": path}
        return {"error": True, "message": "Unknown action."}

    def get_tool_schemas(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "shell",
                    "description": "PowerShell komutları çalıştırır. Sistem bilgisi alma, script çalıştırma, windows araçlarını kullanma.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Çalıştırılacak powershell komutu"},
                            "timeout": {"type": "integer", "description": "Zaman aşımı (saniye)"}
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "file",
                    "description": "Dosya işlemleri: okuma (read), yazma (write), düzenleme (patch), silme (delete, trash), arama (find, search), listeleme (list).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["read", "write", "patch", "create", "delete", "trash", "rename", "find", "search", "list"]},
                            "path": {"type": "string", "description": "Dosya veya dizin yolu"},
                            "content": {"type": "string", "description": "Dosyaya yazılacak içerik"},
                            "old_string": {"type": "string", "description": "Değiştirilecek eski metin (patch için)"},
                            "new_string": {"type": "string", "description": "Yeni metin (patch için)"},
                            "pattern": {"type": "string", "description": "Arama kelimesi veya regex deseni"}
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "web",
                    "description": "Web işlemleri: arama (search), sayfa okuma (browse), tarayıcıda açma (open).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["search", "browse", "open"]},
                            "query": {"type": "string", "description": "Arama sorgusu"},
                            "url": {"type": "string", "description": "Açılacak veya okunacak URL"}
                        },
                        "required": ["action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "screen",
                    "description": "Ekran etkileşimi: tıklama (click, click_text), yazma (type), kısayol (hotkey), ekran görüntüsü alma (screenshot).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["click", "click_text", "type", "hotkey", "screenshot"]},
                            "text": {"type": "string", "description": "Tıklanacak veya yazılacak metin"},
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "keys": {"type": "array", "items": {"type": "string"}, "description": "Kısayol tuşları örn: ['ctrl', 'c']"},
                            "enter": {"type": "boolean", "description": "Yazdıktan sonra Enter'a bas"}
                        },
                        "required": ["action"]
                    }
                }
            }
        ]
