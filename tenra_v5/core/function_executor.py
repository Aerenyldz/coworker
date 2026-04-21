"""
Tenra Function Executor — ADA Pattern + Tenra System Control
Dosya yönetimi, uygulama açma, sistem komutları, web arama vb.
"""

import os
import glob
import subprocess
import webbrowser
from datetime import datetime, timedelta
from typing import Dict, Any
from dataclasses import dataclass
import threading
import time


@dataclass
class ActiveTimer:
    """Aktif geri sayım zamanlayıcısı."""
    label: str
    duration_seconds: int
    start_time: float

    @property
    def remaining_seconds(self) -> int:
        elapsed = time.time() - self.start_time
        return max(0, int(self.duration_seconds - elapsed))

    @property
    def is_expired(self) -> bool:
        return self.remaining_seconds <= 0

    def format_remaining(self) -> str:
        secs = self.remaining_seconds
        mins, secs = divmod(secs, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours}sa {mins}dk {secs}sn"
        elif mins:
            return f"{mins}dk {secs}sn"
        return f"{secs}sn"


class TenraFunctionExecutor:
    """Tenra V5 — Tüm fonksiyonları çalıştıran merkezi motor."""

    def __init__(self):
        from config import DESKTOP_PATH, USER_HOME
        self.desktop_path = DESKTOP_PATH
        self.user_home = USER_HOME
        
        self.task_manager = None
        self.calendar_manager = None
        self.weather_manager = None
        
        self.active_timers: Dict[str, ActiveTimer] = {}
        self._timer_lock = threading.Lock()
        self.smart_lights: Dict[str, Dict[str, Any]] = {}
        
        self.approval_callback = None # (func_name: str, params: dict) -> bool
        
        self._init_managers()

    def _init_managers(self):
        try:
            from core.tasks import TaskManager
            self.task_manager = TaskManager()
        except Exception as e:
            print(f"[Tenra] TaskManager init failed: {e}")

        try:
            from core.calendar_manager import CalendarManager
            self.calendar_manager = CalendarManager()
        except Exception as e:
            print(f"[Tenra] CalendarManager init failed: {e}")

        try:
            from core.weather import WeatherManager
            self.weather_manager = WeatherManager()
        except Exception as e:
            print(f"[Tenra] WeatherManager init failed: {e}")

    def execute(self, func_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fonksiyon çalıştır ve yapılandırılmış sonuç döndür."""
        import difflib
        
        # 1. Aşama: Eş Anlamlılar (Synonyms) Toleransı
        synonyms = {
            "make_dir": "create_folder", "mkdir": "create_folder",
            "remove_file": "delete_file", "del_file": "delete_file", "rm": "delete_file",
            "open_website": "open_url", "visit_url": "open_url", "visit": "open_url",
            "browse": "browse_website", "read_website": "browse_website",
            "run": "open_app", "start_app": "open_app", "execute": "run_command",
            "search": "web_search", "find": "find_file", "google": "web_search",
            "create_text": "create_file", "new_file": "create_file",
            "type": "type_text", "write": "type_text"
        }
        
        if func_name in synonyms:
            func_name = synonyms[func_name]
            
        handler_map = {
            "read_file": self._read_file, "write_file": self._write_file, "patch": self._patch_file,
            "search_files": self._search_files, "create_folder": self._create_folder,
            "create_file": self._create_file, "find_file": self._find_file, "delete_file": self._delete_file,
            "move_to_trash": self._move_to_trash, "rename_file": self._rename_file,
            "list_directory": self._list_directory, "run_command": self._run_command,
            "open_app": self._open_app, "open_url": self._open_url, "list_desktop": self._list_desktop,
            "click_screen": self._click_screen, "type_text": self._type_text, "press_hotkey": self._press_hotkey,
            "execute_python": self._execute_python, "browse_website": self._browse_website,
            "control_light": self._control_light, "set_timer": self._set_timer, "set_alarm": self._set_alarm,
            "create_calendar_event": self._create_calendar_event, "add_task": self._add_task,
            "web_search": self._web_search, "get_system_info": self._get_system_info
        }
        
        # 2. Aşama: Fuzzy Matching (Esnek Yazım Toleransı)
        if func_name not in handler_map:
            matches = difflib.get_close_matches(func_name, handler_map.keys(), n=1, cutoff=0.75)
            if matches:
                print(f"[Tenra Fuzzy Intent] '{func_name}' komutu anlaşılamadı, '{matches[0]}' olarak kabul edildi.")
                func_name = matches[0]

        risky_functions = {
            "write_file", "patch", "delete_file", "move_to_trash", 
            "rename_file", "run_command", "create_file", "create_folder",
            "send_email", "open_app", "open_url", "click_screen", "type_text", "press_hotkey",
            "execute_python"
        }
        
        if func_name in risky_functions and self.approval_callback:
            approved = self.approval_callback(func_name, params)
            if not approved:
                return {"status": "error", "message": f"Kullanıcı eylemi reddetti: {func_name}"}
                
        try:
            handler = handler_map.get(func_name)
            
            if handler:
                if getattr(self, 'tool_start_callback', None):
                    self.tool_start_callback(func_name)
                return handler(params)
            return {"success": False, "message": f"Bilinmeyen fonksiyon: {func_name}", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Hata: {str(e)}", "data": None}

    # ═══════════════════════════════════════════════
    # TENRA SİSTEM FONKSİYONLARI VE AGENT ARAÇLARI
    # ═══════════════════════════════════════════════

    def _execute_python(self, params: Dict) -> Dict:
        """Python kodunu bellekte çalıştırır."""
        code = params.get("code", "")
        if not code:
            return {"success": False, "message": "Çalıştırılacak kod belirtilmedi.", "data": None}
        
        import sys, io, traceback
        old_stdout = sys.stdout
        redirected_output = sys.stdout = io.StringIO()
        
        try:
            exec_globals = {}
            exec(code, exec_globals)
            output = redirected_output.getvalue()
            return {"success": True, "message": output if output else "Kod başarıyla çalıştı (Çıktı yok).", "data": {"output": output}}
        except Exception:
            err = traceback.format_exc()
            return {"success": False, "message": f"Python Hatası:\n{err}", "data": None}
        finally:
            sys.stdout = old_stdout

    def _browse_website(self, params: Dict) -> Dict:
        """Verilen URL'deki web sayfasını okur ve metin olarak döndürür."""
        url = params.get("url", "")
        if not url:
            return {"success": False, "message": "URL belirtilmedi", "data": None}
            
        try:
            import requests
            from bs4 import BeautifulSoup
            
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, "html.parser")
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.extract()
                
            text = soup.get_text(separator="\n", strip=True)
            if len(text) > 8000:
                text = text[:8000] + "\n...[METİN KESİLDİ, SADECE İLK 8000 KARAKTER GETİRİLDİ]..."
                
            return {"success": True, "message": f"{url} sayfası başarıyla okundu:\n\n{text}", "data": None}
        except ImportError:
            return {"success": False, "message": "'beautifulsoup4' paketi eksik. pip install beautifulsoup4", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Web sayfası okuma hatası: {e}", "data": None}

    def _click_screen(self, params: Dict) -> Dict:
        """PyAutoGUI ile ekranda koordinata tıklar."""
        try:
            import pyautogui
            x = params.get("x")
            y = params.get("y")
            if x is not None and y is not None:
                pyautogui.click(int(x), int(y))
                return {"success": True, "message": f"({x}, {y}) koordinatına tıklandı.", "data": None}
            return {"success": False, "message": "x ve y koordinatları gerekli.", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Mouse tıklama hatası: {e}", "data": None}

    def _type_text(self, params: Dict) -> Dict:
        """Klavyeden metin yazar."""
        try:
            import pyautogui
            text = params.get("text", "")
            press_enter = params.get("press_enter", False)
            pyautogui.write(text, interval=0.01)
            if press_enter:
                pyautogui.press('enter')
            return {"success": True, "message": f"Metin yazıldı: {text}", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Klavye yazma hatası: {e}", "data": None}
            
    def _press_hotkey(self, params: Dict) -> Dict:
        """Kısayol tuşu gönderir (örn: ctrl, c)."""
        try:
            import pyautogui
            keys = params.get("keys", [])
            if isinstance(keys, str):
                keys = [keys]
            pyautogui.hotkey(*keys)
            return {"success": True, "message": f"Kısayol tuşlandı: {'+'.join(keys)}", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Kısayol hatası: {e}", "data": None}

    def _run_command(self, params: Dict) -> Dict:
        """PowerShell komutu çalıştır."""
        command = params.get("command", "")
        if not command:
            return {"success": False, "message": "Komut belirtilmedi", "data": None}
        try:
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True, text=True, timeout=60
            )
            output = result.stdout.strip() or result.stderr.strip() or "(Çıktı yok)"
            # Truncate very long output
            if len(output) > 2000:
                output = output[:2000] + "\n... (çıktı kısaltıldı)"
            return {"success": result.returncode == 0, "message": output, "data": {"command": command, "return_code": result.returncode}}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Komut zaman aşımına uğradı (60sn)", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Komut hatası: {e}", "data": None}

    def _find_file(self, params: Dict) -> Dict:
        """Dosya ara."""
        filename = params.get("filename", "")
        if not filename:
            return {"success": False, "message": "Dosya adı belirtilmedi", "data": None}
        
        results = glob.glob(f"{self.user_home}/**/*{filename}*", recursive=True)[:10]
        if results:
            return {
                "success": True,
                "message": f"{len(results)} dosya bulundu:\n" + "\n".join(results[:5]),
                "data": {"files": results}
            }
        return {"success": True, "message": f"'{filename}' bulunamadı", "data": None}

    def _create_folder(self, params: Dict) -> Dict:
        """Klasör oluştur."""
        path = str(params.get("path", "")).strip()
        if not path:
            path = str(params.get("name", "")).strip()
        if not path:
            return {"success": False, "message": "Klasör yolu belirtilmedi", "data": None}

        if not os.path.isabs(path):
            path = os.path.join(self.desktop_path, path)

        try:
            os.makedirs(path, exist_ok=True)
            return {"success": True, "message": f"Klasör oluşturuldu: {path}", "data": {"path": path}}
        except Exception as e:
            return {"success": False, "message": f"Klasör oluşturma hatası: {e}", "data": None}

    def _create_file(self, params: Dict) -> Dict:
        """Dosya oluştur."""
        path = params.get("path", "")
        content = params.get("content", "")
        
        if not path:
            return {"success": False, "message": "Dosya yolu belirtilmedi", "data": None}
        
        # Eğer sadece dosya adı verilmişse masaüstüne oluştur
        if not os.path.isabs(path):
            path = os.path.join(self.desktop_path, path)
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        
        return {"success": True, "message": f"Dosya oluşturuldu: {path}", "data": {"path": path}}

    def _delete_file(self, params: Dict) -> Dict:
        """Dosya sil (kalıcı)."""
        path = params.get("path", "")
        if not path:
            return {"success": False, "message": "Dosya yolu belirtilmedi", "data": None}
        if not os.path.isabs(path):
            path = os.path.join(self.desktop_path, path)
        
        if not os.path.exists(path):
            parent_dir = os.path.dirname(path)
            base_name = os.path.basename(path)
            if os.path.exists(parent_dir):
                import difflib
                files = os.listdir(parent_dir)
                # Tam isim aramasi
                matches = difflib.get_close_matches(base_name, files, n=1, cutoff=0.45)
                if matches:
                    path = os.path.join(parent_dir, matches[0])
                else:
                    # Uzantisiz isim aramasi
                    files_no_ext = {os.path.splitext(f)[0]: f for f in files}
                    matches_no_ext = difflib.get_close_matches(base_name, list(files_no_ext.keys()), n=1, cutoff=0.45)
                    if matches_no_ext:
                        path = os.path.join(parent_dir, files_no_ext[matches_no_ext[0]])

        if os.path.exists(path):
            if os.path.isdir(path):
                import shutil
                shutil.rmtree(path)
            else:
                os.remove(path)
            return {"success": True, "message": f"Silindi: {path}", "data": None}
        return {"success": False, "message": f"Dosya bulunamadı: {path}", "data": None}

    def _move_to_trash(self, params: Dict) -> Dict:
        """Dosyayı geri dönüşüme (çöp kutusuna) taşı."""
        path = params.get("path", "")
        if not path:
            return {"success": False, "message": "Dosya yolu belirtilmedi", "data": None}
        if not os.path.isabs(path):
            path = os.path.join(self.desktop_path, path)
        
        if not os.path.exists(path):
            parent_dir = os.path.dirname(path)
            base_name = os.path.basename(path)
            if os.path.exists(parent_dir):
                import difflib
                files = os.listdir(parent_dir)
                matches = difflib.get_close_matches(base_name, files, n=1, cutoff=0.45)
                if matches:
                    path = os.path.join(parent_dir, matches[0])
                else:
                    files_no_ext = {os.path.splitext(f)[0]: f for f in files}
                    matches_no_ext = difflib.get_close_matches(base_name, list(files_no_ext.keys()), n=1, cutoff=0.45)
                    if matches_no_ext:
                        path = os.path.join(parent_dir, files_no_ext[matches_no_ext[0]])

        if not os.path.exists(path):
            return {"success": False, "message": f"Dosya bulunamadı: {path}", "data": None}
        
        try:
            from send2trash import send2trash
            send2trash(path)
            return {"success": True, "message": f"Çöp kutusuna taşındı: {path}", "data": None}
        except ImportError:
            return {"success": False, "message": "send2trash paketi kurulu değil. 'pip install send2trash' çalıştırın.", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Çöpe taşıma hatası: {e}", "data": None}

    def _read_file(self, params: Dict) -> Dict:
        """Dosya içeriğini satır numaralarıyla oku (Hermes Agent uyumlu).
        
        Parametreler:
            path: Dosya yolu
            offset: Başlangıç satır numarası (1-indexed, varsayılan: 1)
            limit: Okunacak max satır sayısı (varsayılan: 200)
        """
        path = params.get("path", "")
        offset = max(1, int(params.get("offset", 1)))
        limit = min(2000, max(1, int(params.get("limit", 200))))
        
        if not path:
            return {"success": False, "message": "Dosya yolu belirtilmedi", "data": None}
        if not os.path.isabs(path):
            path = os.path.join(self.desktop_path, path)
        if not os.path.exists(path):
            return {"success": False, "message": f"Dosya bulunamadı: {path}", "data": None}
        if os.path.isdir(path):
            return {"success": False, "message": f"Bu bir klasör, dosya değil: {path}", "data": None}
        
        try:
            file_size = os.path.getsize(path)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            
            total_lines = len(all_lines)
            start_idx = offset - 1  # 0-indexed
            end_idx = min(start_idx + limit, total_lines)
            
            # Satır numaralı format (Hermes Agent tarzı)
            numbered_lines = []
            for i in range(start_idx, end_idx):
                line_num = i + 1
                line_content = all_lines[i].rstrip('\n\r')
                numbered_lines.append(f"{line_num}|{line_content}")
            
            content = "\n".join(numbered_lines)
            truncated = end_idx < total_lines
            
            msg = f"Dosya okundu: {os.path.basename(path)} ({total_lines} satır, {file_size} byte)"
            if truncated:
                msg += f"\n[Gösterilen: satır {offset}-{end_idx} / {total_lines}. Devamı için offset={end_idx+1} kullan]"
            
            return {
                "success": True,
                "message": f"{msg}\n\n{content}",
                "data": {
                    "path": path,
                    "total_lines": total_lines,
                    "file_size": file_size,
                    "offset": offset,
                    "limit": limit,
                    "truncated": truncated,
                    "content": content,
                }
            }
        except Exception as e:
            return {"success": False, "message": f"Dosya okuma hatası: {e}", "data": None}

    def _write_file(self, params: Dict) -> Dict:
        """Dosyanın tüm içeriğini yaz (overwrite). Hermes Agent write_file uyumlu.
        
        Dosya yoksa oluşturur, varsa üzerine yazar.
        """
        path = params.get("path", "")
        content = params.get("content", "")
        
        if not path:
            return {"success": False, "message": "Dosya yolu belirtilmedi", "data": None}
        if not os.path.isabs(path):
            path = os.path.join(self.desktop_path, path)
        
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            
            line_count = content.count('\n') + (1 if content and not content.endswith('\n') else 0)
            return {
                "success": True,
                "message": f"Dosya yazıldı: {path} ({line_count} satır, {len(content)} karakter)",
                "data": {"path": path, "lines_written": line_count, "chars": len(content)}
            }
        except Exception as e:
            return {"success": False, "message": f"Dosya yazma hatası: {e}", "data": None}

    def _patch_file(self, params: Dict) -> Dict:
        """Dosyada hedefli find-and-replace düzenleme. Hermes Agent patch uyumlu.
        
        Parametreler:
            path: Düzenlenecek dosya yolu
            old_string: Bulunacak metin
            new_string: Yerine konacak metin (boş string = silme)
            replace_all: True ise tüm eşleşmeleri değiştirir (varsayılan: False)
        """
        path = params.get("path", "")
        old_string = params.get("old_string", "")
        new_string = params.get("new_string", "")
        replace_all = params.get("replace_all", False)
        
        if not path:
            return {"success": False, "message": "Dosya yolu belirtilmedi", "data": None}
        if not old_string:
            return {"success": False, "message": "old_string belirtilmedi — neyi değiştirmek istediğinizi belirtin", "data": None}
        if not os.path.isabs(path):
            path = os.path.join(self.desktop_path, path)
        if not os.path.exists(path):
            return {"success": False, "message": f"Dosya bulunamadı: {path}", "data": None}
        
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                original = f.read()
            
            count = original.count(old_string)
            if count == 0:
                # Fuzzy arama — büyük/küçük harf farksız dene
                import re
                pattern = re.escape(old_string)
                matches = re.findall(pattern, original, flags=re.IGNORECASE)
                if matches:
                    return {
                        "success": False,
                        "message": f"Tam eşleşme bulunamadı. Büyük/küçük harf farkıyla {len(matches)} benzer eşleşme var. Dosyayı read_file ile okuyup doğru metni gönderin.",
                        "data": None
                    }
                return {
                    "success": False,
                    "message": f"'{old_string[:80]}...' dosyada bulunamadı. Dosyayı read_file ile okuyup mevcut içeriği kontrol edin.",
                    "data": None
                }
            
            if count > 1 and not replace_all:
                return {
                    "success": False,
                    "message": f"'{old_string[:60]}...' dosyada {count} kez geçiyor. Benzersizlik için daha fazla bağlam ekleyin veya replace_all=true kullanın.",
                    "data": None
                }
            
            if replace_all:
                new_content = original.replace(old_string, new_string)
                replaced_count = count
            else:
                new_content = original.replace(old_string, new_string, 1)
                replaced_count = 1
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            return {
                "success": True,
                "message": f"Dosya düzenlendi: {path} ({replaced_count} değişiklik yapıldı)",
                "data": {"path": path, "replacements": replaced_count}
            }
        except Exception as e:
            return {"success": False, "message": f"Patch hatası: {e}", "data": None}

    def _search_files(self, params: Dict) -> Dict:
        """Dosya içinde arama veya dosya adı arama. Hermes Agent search_files uyumlu.
        
        Parametreler:
            pattern: Aranacak regex/glob deseni
            target: 'content' (dosya içi) veya 'files' (dosya adı)
            path: Aranacak dizin (varsayılan: masaüstü)
            file_glob: Dosya türü filtresi (örn: '*.py')
            limit: Maksimum sonuç (varsayılan: 30)
        """
        import re as regex_module
        import fnmatch
        
        pattern = params.get("pattern", "")
        target = params.get("target", "content")
        search_path = params.get("path", self.desktop_path)
        file_glob = params.get("file_glob", None)
        limit = min(100, int(params.get("limit", 30)))
        
        if not pattern:
            return {"success": False, "message": "Arama deseni belirtilmedi", "data": None}
        
        if not os.path.isabs(search_path):
            search_path = os.path.join(self.desktop_path, search_path)
        
        if not os.path.exists(search_path):
            return {"success": False, "message": f"Arama dizini bulunamadı: {search_path}", "data": None}
        
        results = []
        
        try:
            if target == "files":
                # Dosya adı araması (glob)
                for root, dirs, files in os.walk(search_path):
                    # Gizli dizinleri atla
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for fname in files:
                        if fnmatch.fnmatch(fname, pattern) or fnmatch.fnmatch(fname.lower(), pattern.lower()):
                            full_path = os.path.join(root, fname)
                            try:
                                stat = os.stat(full_path)
                                results.append({
                                    "path": full_path,
                                    "size": stat.st_size,
                                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                                })
                            except OSError:
                                results.append({"path": full_path})
                        if len(results) >= limit:
                            break
                    if len(results) >= limit:
                        break
                
                msg = f"'{pattern}' ile eşleşen {len(results)} dosya bulundu"
                return {"success": True, "message": msg, "data": {"matches": results, "total": len(results)}}
            
            else:
                # İçerik araması (regex)
                try:
                    compiled = regex_module.compile(pattern, regex_module.IGNORECASE)
                except regex_module.error:
                    # Geçersiz regex ise literal arama yap
                    compiled = regex_module.compile(regex_module.escape(pattern), regex_module.IGNORECASE)
                
                binary_exts = {'.exe', '.dll', '.bin', '.gguf', '.safetensors', '.pyc', '.pyo',
                               '.zip', '.rar', '.7z', '.tar', '.gz', '.jpg', '.png', '.gif',
                               '.mp4', '.mp3', '.wav', '.pdf', '.doc', '.docx', '.xls', '.xlsx'}
                
                if os.path.isfile(search_path):
                    files_to_search = [search_path]
                else:
                    files_to_search = []
                    for root, dirs, fnames in os.walk(search_path):
                        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__' and d != 'node_modules']
                        for fname in fnames:
                            ext = os.path.splitext(fname)[1].lower()
                            if ext in binary_exts:
                                continue
                            if file_glob and not fnmatch.fnmatch(fname, file_glob):
                                continue
                            files_to_search.append(os.path.join(root, fname))
                
                for fpath in files_to_search:
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            for line_num, line in enumerate(f, 1):
                                if compiled.search(line):
                                    results.append({
                                        "file": fpath,
                                        "line": line_num,
                                        "content": line.rstrip()[:200],
                                    })
                                    if len(results) >= limit:
                                        break
                    except (OSError, UnicodeDecodeError):
                        continue
                    if len(results) >= limit:
                        break
                
                msg = f"'{pattern}' için {len(results)} eşleşme bulundu"
                if len(results) >= limit:
                    msg += f" (limit: {limit}, daha fazla sonuç olabilir)"
                return {"success": True, "message": msg, "data": {"matches": results, "total": len(results)}}
                
        except Exception as e:
            return {"success": False, "message": f"Arama hatası: {e}", "data": None}

    def _list_directory(self, params: Dict) -> Dict:
        """Bir dizinin içeriğini listele (ls/dir karşılığı)."""
        path = params.get("path", self.desktop_path)
        if not os.path.isabs(path):
            path = os.path.join(self.desktop_path, path)
        
        if not os.path.exists(path):
            return {"success": False, "message": f"Dizin bulunamadı: {path}", "data": None}
        if not os.path.isdir(path):
            return {"success": False, "message": f"Bu bir dosya, dizin değil: {path}", "data": None}
        
        try:
            items = []
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                is_dir = os.path.isdir(full)
                try:
                    stat = os.stat(full)
                    items.append({
                        "name": name,
                        "type": "directory" if is_dir else "file",
                        "size": stat.st_size if not is_dir else None,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    })
                except OSError:
                    items.append({"name": name, "type": "directory" if is_dir else "file"})
            
            dirs = [i for i in items if i["type"] == "directory"]
            files = [i for i in items if i["type"] == "file"]
            
            msg = f"{path}\n{len(dirs)} klasör, {len(files)} dosya:\n"
            for d in dirs:
                msg += f"  📁 {d['name']}/\n"
            for f in files:
                size_str = f"  ({f['size']} B)" if f.get('size') is not None else ""
                msg += f"  📄 {f['name']}{size_str}\n"
            
            return {"success": True, "message": msg.strip(), "data": {"path": path, "items": items}}
        except Exception as e:
            return {"success": False, "message": f"Dizin listeleme hatası: {e}", "data": None}

    def _rename_file(self, params: Dict) -> Dict:
        """Dosya veya klasör adını değiştir."""
        old_path = params.get("path", "") or params.get("old_path", "")
        new_name = params.get("new_name", "") or params.get("name", "")
        if not old_path or not new_name:
            return {"success": False, "message": "Eski yol ve yeni ad belirtilmedi", "data": None}
        if not os.path.isabs(old_path):
            old_path = os.path.join(self.desktop_path, old_path)
        if not os.path.exists(old_path):
            return {"success": False, "message": f"Dosya bulunamadı: {old_path}", "data": None}
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        try:
            os.rename(old_path, new_path)
            return {"success": True, "message": f"Yeniden adlandırıldı: {old_path} → {new_path}", "data": {"old": old_path, "new": new_path}}
        except Exception as e:
            return {"success": False, "message": f"Yeniden adlandırma hatası: {e}", "data": None}

    def _open_app(self, params: Dict) -> Dict:
        """Uygulama aç (Başlat menüsünden arayarak)."""
        name = params.get("name", "")
        if not name:
            return {"success": False, "message": "Uygulama adı belirtilmedi", "data": None}
        
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.press('win')
            time.sleep(0.5)
            pyautogui.write(name, interval=0.03)
            time.sleep(0.8)
            pyautogui.press('enter')
            return {"success": True, "message": f"Uygulama açılıyor: {name}", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Uygulama açma hatası: {e}", "data": None}

    def _open_url(self, params: Dict) -> Dict:
        """Web sitesi aç."""
        url = params.get("url", "")
        if not url:
            return {"success": False, "message": "URL belirtilmedi", "data": None}
        if not url.startswith("http"):
            url = "https://" + url
        webbrowser.open(url)
        return {"success": True, "message": f"Tarayıcıda açıldı: {url}", "data": None}

    def _list_desktop(self, params: Dict) -> Dict:
        """Masaüstü dosyalarını listele."""
        try:
            items = os.listdir(self.desktop_path)
            files = [f for f in items if os.path.isfile(os.path.join(self.desktop_path, f))]
            dirs = [d for d in items if os.path.isdir(os.path.join(self.desktop_path, d))]
            
            msg = f"Masaüstünde {len(files)} dosya, {len(dirs)} klasör var:\n"
            if dirs:
                msg += "📁 Klasörler: " + ", ".join(dirs[:10]) + "\n"
            if files:
                msg += "📄 Dosyalar: " + ", ".join(files[:15])
            
            return {"success": True, "message": msg, "data": {"files": files, "dirs": dirs}}
        except Exception as e:
            return {"success": False, "message": f"Masaüstü listelenemedi: {e}", "data": None}

    # ═══════════════════════════════════════════════
    # ADA FONKSİYONLARI (KORUNDU)
    # ═══════════════════════════════════════════════

    def _control_light(self, params: Dict) -> Dict:
        action = str(params.get("action", "toggle")).lower().strip()
        device = str(params.get("device_name", "varsayilan")).strip() or "varsayilan"
        brightness = params.get("brightness")
        color = str(params.get("color", "")).strip() or None

        state = self.smart_lights.get(device, {"name": device, "is_on": False, "brightness": 100, "color": None})

        if action == "on":
            state["is_on"] = True
        elif action == "off":
            state["is_on"] = False
        elif action == "toggle":
            state["is_on"] = not state["is_on"]
        elif action == "dim":
            state["is_on"] = True
            if isinstance(brightness, int):
                state["brightness"] = max(0, min(100, brightness))
        else:
            return {"success": False, "message": f"Desteklenmeyen ışık aksiyonu: {action}", "data": None}

        if isinstance(brightness, int):
            state["brightness"] = max(0, min(100, brightness))
        if color:
            state["color"] = color

        self.smart_lights[device] = state

        on_off = "açık" if state["is_on"] else "kapalı"
        msg = f"Işık güncellendi: {device} -> {on_off}, parlaklık %{state['brightness']}"
        if state.get("color"):
            msg += f", renk {state['color']}"

        return {"success": True, "message": msg, "data": state}

    def _set_timer(self, params: Dict) -> Dict:
        duration_str = params.get("duration", "")
        label = params.get("label", "Zamanlayıcı")
        seconds = self._parse_duration(duration_str)
        if seconds <= 0:
            return {"success": False, "message": f"Geçersiz süre: {duration_str}", "data": None}
        timer = ActiveTimer(label=label, duration_seconds=seconds, start_time=time.time())
        with self._timer_lock:
            self.active_timers[label] = timer
        return {"success": True, "message": f"⏱️ '{label}' zamanlayıcısı {duration_str} için kuruldu", "data": {"label": label, "seconds": seconds}}

    def _parse_duration(self, duration_str: str) -> int:
        import re
        duration_str = duration_str.lower().strip()
        total = 0
        for pattern, mult in [(r'(\d+)\s*(?:sa|ho?u?r)', 3600), (r'(\d+)\s*(?:dk|da?k?|mi?n)', 60), (r'(\d+)\s*(?:sn|sa?n?|se?c)', 1)]:
            m = re.search(pattern, duration_str)
            if m:
                total += int(m.group(1)) * mult
        if total == 0:
            nums = re.findall(r'\d+', duration_str)
            if nums:
                total = int(nums[0]) * 60
        return total

    def _create_calendar_event(self, params: Dict) -> Dict:
        title = params.get("title", "Etkinlik")
        date = params.get("date", "today")
        time_str = self._normalize_time(params.get("time", "09:00"))
        if not self.calendar_manager:
            return {"success": False, "message": "Takvim yöneticisi yüklenemedi", "data": None}
        event_date = self._parse_date(date)
        start_dt = f"{event_date} {time_str}:00"
        try:
            start = datetime.strptime(start_dt, "%Y-%m-%d %H:%M:%S")
            end = start + timedelta(minutes=60)
            end_dt = end.strftime("%Y-%m-%d %H:%M:%S")
        except:
            end_dt = start_dt
        event = self.calendar_manager.add_event(title, start_dt, end_dt)
        if event:
            return {"success": True, "message": f"📅 '{title}' etkinliği oluşturuldu ({date})", "data": event}
        return {"success": False, "message": "Etkinlik oluşturulamadı", "data": None}

    def _set_alarm(self, params: Dict) -> Dict:
        time_str = str(params.get("time", "")).strip()
        label = str(params.get("label", "Alarm")).strip() or "Alarm"
        if not time_str:
            return {"success": False, "message": "Alarm zamanı belirtilmedi", "data": None}
        if not self.task_manager:
            return {"success": False, "message": "Alarm yöneticisi yüklenemedi", "data": None}

        alarm_id = self.task_manager.add_alarm(time_str, label)
        if alarm_id:
            return {
                "success": True,
                "message": f"⏰ Alarm kuruldu: {time_str} ({label})",
                "data": {"id": alarm_id, "time": time_str, "label": label},
            }
        return {"success": False, "message": "Alarm oluşturulamadı", "data": None}

    def _parse_date(self, date_str: str) -> str:
        date_str = date_str.lower().strip()
        today = datetime.now()
        if date_str in ("today", "bugün", ""):
            return today.strftime("%Y-%m-%d")
        elif date_str in ("tomorrow", "yarın"):
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return today.strftime("%Y-%m-%d")

    def _normalize_time(self, time_value: Any) -> str:
        raw = str(time_value or "").strip().lower()
        if not raw:
            return "09:00"

        compact = raw.replace(" ", "").replace(".", ":")
        for fmt in ("%H:%M", "%H", "%I%p", "%I:%M%p"):
            try:
                parsed = datetime.strptime(compact, fmt)
                return parsed.strftime("%H:%M")
            except ValueError:
                continue

        import re

        match = re.search(r"(\d{1,2})(?::(\d{2}))?", compact)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            if "pm" in compact and hour < 12:
                hour += 12
            if "am" in compact and hour == 12:
                hour = 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return f"{hour:02d}:{minute:02d}"

        return "09:00"

    def _add_task(self, params: Dict) -> Dict:
        text = params.get("text", "")
        if not text:
            return {"success": False, "message": "Görev metni yok", "data": None}
        if not self.task_manager:
            return {"success": False, "message": "Görev yöneticisi yüklenemedi", "data": None}
        task = self.task_manager.add_task(text)
        if task:
            return {"success": True, "message": f"✅ Görev eklendi: {text}", "data": task}
        return {"success": False, "message": "Görev eklenemedi", "data": None}

    def _web_search(self, params: Dict) -> Dict:
        query = params.get("query", "")
        if not query:
            return {"success": False, "message": "Arama sorgusu yok", "data": None}
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if results:
                formatted = [{"title": r.get("title", ""), "body": r.get("body", "")[:200], "url": r.get("href", "")} for r in results[:3]]
                return {"success": True, "message": f"🔍 '{query}' için {len(results)} sonuç bulundu", "data": {"query": query, "results": formatted}}
            return {"success": True, "message": f"'{query}' için sonuç bulunamadı", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Arama hatası: {e}", "data": None}

    def _get_system_info(self, params=None) -> Dict:
        info = {
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timers": [],
            "alarms": [],
            "calendar_today": [],
            "tasks": [],
            "weather": None,
            "smart_devices": [],
            "news": [],
            "desktop_files": len(os.listdir(self.desktop_path)) if os.path.exists(self.desktop_path) else 0
        }
        with self._timer_lock:
            for label, timer in list(self.active_timers.items()):
                if timer.is_expired:
                    del self.active_timers[label]
                else:
                    info["timers"].append({"label": timer.label, "remaining": timer.format_remaining()})
        if self.task_manager:
            try:
                tasks = self.task_manager.get_tasks()
                info["tasks"] = [{"text": t["text"], "completed": t["completed"]} for t in tasks]
            except:
                pass
            try:
                alarms = self.task_manager.get_alarms()
                info["alarms"] = [{"time": a.get("time"), "label": a.get("label")} for a in alarms]
            except:
                pass
        if self.calendar_manager:
            try:
                today = datetime.now().strftime("%Y-%m-%d")
                events = self.calendar_manager.get_events(today)
                info["calendar_today"] = [{"title": e["title"], "time": e["start_time"]} for e in events]
            except:
                pass
        if self.weather_manager:
            try:
                weather = self.weather_manager.get_weather()
                if weather:
                    info["weather"] = weather
            except:
                pass

        info["smart_devices"] = list(self.smart_lights.values())
        return {"success": True, "message": "Sistem bilgisi alındı", "data": info}


# Singleton
executor = TenraFunctionExecutor()
