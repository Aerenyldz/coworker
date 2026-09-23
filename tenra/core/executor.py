import os
import subprocess
import difflib
import json
import re
import shutil
import glob
import uuid
from pathlib import Path

class TenraExecutor:
    def __init__(self, workspace_path: str = None):
        from ..config import DESKTOP_PATH, CHANGE_JOURNAL_FILE
        self.desktop_path = DESKTOP_PATH
        self.workspace_path = str(Path(workspace_path).resolve()) if workspace_path else self.desktop_path
        self.workspace_name = os.path.basename(self.workspace_path) if self.workspace_path != self.desktop_path else "Masaüstü"
        self.user_home = os.path.expanduser('~')
        self.approval_callback = None
        self.tool_start_callback = None
        # Multi-file diff batching
        self._batch_mode = False
        self._batch_id = None
        self._batch_items = []
        # Rollback journal
        try:
            from .change_journal import ChangeJournal
            self.journal = ChangeJournal(CHANGE_JOURNAL_FILE)
        except Exception:
            self.journal = None

    def begin_diff_batch(self):
        """Birden fazla file write/patch için tek onay paketi başlat."""
        self._batch_mode = True
        self._batch_id = uuid.uuid4().hex[:10]
        self._batch_items = []

    def flush_diff_batch(self) -> dict:
        """Birikmiş değişiklikleri tek kartta onaylatıp uygular."""
        items = list(self._batch_items)
        batch_id = self._batch_id
        self._batch_mode = False
        self._batch_id = None
        self._batch_items = []

        if not items:
            return {"success": True, "message": "Boş diff paketi.", "applied": []}

        # Tek onay
        if self.approval_callback:
            approved = self.approval_callback("diff_batch", {
                "batch_id": batch_id,
                "files": [
                    {
                        "path": it["path"],
                        "filename": it["filename"],
                        "diff": it["diff"],
                        "action": it["action"],
                    }
                    for it in items
                ],
                "count": len(items),
                "warning": f"{len(items)} dosyada değişiklik paketi",
            })
            if not approved:
                return {
                    "error": True,
                    "message": f"Kullanıcı {len(items)} dosyalık değişiklik paketini reddetti.",
                    "batch_id": batch_id,
                }

        applied = []
        for it in items:
            try:
                parent = os.path.dirname(it["path"])
                if parent:
                    try:
                        os.makedirs(parent, exist_ok=True)
                    except OSError:
                        pass
                with open(it["path"], "w", encoding="utf-8") as f:
                    f.write(it["after"])
                if self.journal is not None:
                    self.journal.record(
                        path=it["path"],
                        before=it["before"],
                        after=it["after"],
                        action=it["action"],
                        batch_id=batch_id,
                    )
                applied.append(it["filename"])
            except Exception as e:
                return {
                    "error": True,
                    "message": f"Paket uygularken hata ({it['filename']}): {e}",
                    "applied": applied,
                    "batch_id": batch_id,
                }

        return {
            "success": True,
            "message": f"Paket uygulandı ({len(applied)} dosya): {', '.join(applied)}",
            "applied": applied,
            "batch_id": batch_id,
            "undo_hint": "Geri almak için Undo / action://undo_batch",
        }

    def cancel_diff_batch(self):
        self._batch_mode = False
        self._batch_id = None
        self._batch_items = []

    def undo_last_change(self) -> dict:
        if self.journal is None:
            return {"error": True, "message": "Change journal yok."}
        return self.journal.undo_last()

    def undo_batch(self, batch_id: str) -> dict:
        if self.journal is None:
            return {"error": True, "message": "Change journal yok."}
        return self.journal.undo_batch(batch_id)

    def _queue_or_apply_change(self, full_path, before, after, diff_text, action, approval_name):
        """Batch modunda kuyruğa al; değilse tekil onay + uygula + journal."""
        filename = os.path.basename(full_path)

        if self._batch_mode:
            self._batch_items.append({
                "path": full_path,
                "filename": filename,
                "before": before,
                "after": after,
                "diff": diff_text,
                "action": action,
            })
            return {
                "success": True,
                "message": f"Pakete eklendi: {filename}",
                "batched": True,
                "batch_id": self._batch_id,
                "diff": diff_text,
            }

        if self.approval_callback and (diff_text or "").strip():
            approved = self.approval_callback(approval_name, {
                "path": full_path,
                "filename": filename,
                "diff": diff_text,
                "action": action,
            })
            if not approved:
                return {"error": True, "message": "Kullanıcı dosya değişikliğini reddetti."}

        parent = os.path.dirname(full_path)
        if parent:
            try:
                os.makedirs(parent, exist_ok=True)
            except OSError:
                pass
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(after)

        if self.journal is not None:
            self.journal.record(
                path=full_path,
                before=before,
                after=after,
                action=action,
                batch_id=None,
            )

        return {
            "success": True,
            "message": f"Dosya güncellendi ({filename})",
            "diff": diff_text,
            "path": full_path,
        }
        
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

    def _is_safe_path(self, full_path: str) -> tuple[bool, str]:
        """Bir dosya yolunun sistem dizinleri veya çalışma alanı dışında olup olmadığını denetler."""
        try:
            target = Path(full_path).resolve()
            ws = Path(self.workspace_path).resolve()
            dt = Path(self.desktop_path).resolve()

            # Yasaklı Windows sistem alanları
            sys_root = Path(os.environ.get("SystemRoot", "C:\\Windows")).resolve()
            prog_files = Path(os.environ.get("ProgramFiles", "C:\\Program Files")).resolve()
            prog_files_x86 = Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")).resolve()

            for restricted in (sys_root, prog_files, prog_files_x86):
                if target == restricted or restricted in target.parents:
                    return False, f"Sistem dizinine müdahale engellendi ({restricted.name})"

            # Sürücü kök dizini kontrolü (C:\, D:\ gibi yerlere doğrudan yazma/silme)
            if str(target) in ("C:\\", "D:\\", "E:\\", "c:\\", "d:\\", "e:\\"):
                return False, "Sürücü kök dizinine doğrudan müdahale engellendi."

            # Çalışma alanı veya Masaüstü içindeyse güvenli
            if target == ws or ws in target.parents or target == dt or dt in target.parents:
                return True, "Güvenli çalışma alanı"

            # Farklı bir kullanıcı veya sistem diziniyse onay gerekir
            return False, f"Çalışma alanı dışındaki dizine erişim ({target})"
        except Exception as e:
            return False, f"Yol doğrulama hatası: {e}"

    def _is_obfuscated_command(self, command: str) -> tuple[bool, str]:
        """Encoded/obfuscated PowerShell — onay bile istenmez, sert blok."""
        cmd = command.strip()
        cmd_l = cmd.lower()

        obfuscation_patterns = [
            (r"(?i)-encodedcommand\b", "EncodedCommand (base64) gizleme"),
            (r"(?i)-enc\b", "EncodedCommand kısa formu (-enc)"),
            (r"(?i)-ec\b\s+[A-Za-z0-9+/=]{16,}", "EncodedCommand (-ec) payload"),
            (r"(?i)\bfrombase64string\b", "Base64 decode ile komut çalıştırma"),
            (r"(?i)\bconvert\s*::\s*frombase64string\b", "Convert::FromBase64String obfuscation"),
            (r"(?i)\biex\b\s*\(.*\+", "iex + string birleştirme obfuscation"),
            (r"(?i)\binvoke-expression\b\s*\(.*\+", "Invoke-Expression + birleştirme"),
            (r"(?i)\biex\b\s*\(?\s*\[", "iex + tip dönüşümü obfuscation"),
            (r"(?i)\binvoke-expression\b\s*\(?\s*\[", "Invoke-Expression + tip dönüşümü"),
            (r"(?i)\biex\s*\(\s*\$\w+", "iex ile değişken üzerinden yürütme"),
            (r"(?i)\binvoke-expression\s*\(\s*\$\w+", "Invoke-Expression değişken yürütme"),
            (r"(?i)\bdownloadstring\b.*\b(iex|invoke-expression)\b", "Remote DownloadString + iex"),
            (r"(?i)\b(iex|invoke-expression)\b.*\bdownloadstring\b", "iex + DownloadString"),
            (r"(?i)\bdownloadfile\b.*\b(iex|invoke-expression|start-process)\b", "DownloadFile + yürütme"),
            (r"(?i)\$\w+\s*\+\s*\$\w+.*\b(iex|invoke-expression)\b", "Ortam/değişken parçalama + iex"),
            (r"(?i)-command\s+[\"'].*;\s*(iex|invoke-expression)\b", "Nested -Command + iex"),
        ]

        for pattern, desc in obfuscation_patterns:
            if re.search(pattern, cmd):
                return True, desc

        # -e / -encoded ile uzun base64 benzeri tek argüman
        if re.search(r"(?i)(?:^|\s)-(?:e|encodedcommand|enc|ec)\s+([A-Za-z0-9+/=]{40,})", cmd):
            return True, "Uzun base64 encoded PowerShell payload"

        # powershell.exe -EncodedCommand zinciri (cmd içinden çağrı)
        if "powershell" in cmd_l and re.search(r"(?i)-(?:encodedcommand|enc|ec)\b", cmd):
            return True, "İç içe powershell EncodedCommand"

        return False, ""

    def _is_dangerous_command(self, command: str) -> tuple[bool, str]:
        """PowerShell komutunun yıkıcı/tehlikeli olup olmadığını denetler."""
        cmd = command.strip().lower()

        dangerous_patterns = [
            (r"\brm\s+-[rRfF]", "Özyinelemeli (recursive) dosya silme"),
            (r"\bremove-item\b.*-recurse", "Özyinelemeli PowerShell dosya silme"),
            (r"\bdel\s+/[sS]", "Tüm alt dizinleri silme"),
            (r"\bformat-volume\b|\bformat\s+[a-zA-Z]:", "Disk formatlama komutu"),
            (r"\bdiskpart\b", "Disk bölümleme komutu"),
            (r"\bstop-computer\b|\brestart-computer\b|\bshutdown\b", "Bilgisayarı kapatma/yeniden başlatma"),
            (r"\breg\s+(delete|add)\b", "Windows Kayıt Defteri (Registry) müdahalesi"),
            (r"\bset-executionpolicy\b", "PowerShell güvenlik ilkesini değiştirme"),
            (r"\bnet\s+user\b", "Kullanıcı hesabı oluşturma/değiştirme"),
            (r"\bgit\s+push\b.*--force", "Git zorla gönderme (force push)"),
            (r"\bgit\s+reset\b.*--hard", "Git tüm yerel değişiklikleri geri alma (hard reset)"),
            # Shell üzerinden gizli dosya yazma (diff kartını baypas etme)
            (r"\bset-content\b", "Shell ile dosya üzerine yazma (Set-Content)"),
            (r"\badd-content\b", "Shell ile dosyaya ekleme (Add-Content)"),
            (r"\bout-file\b", "Shell ile dosya yazma (Out-File)"),
            (r"\bnew-item\b.*-itemtype\s+file", "Shell ile yeni dosya oluşturma"),
            (r"\bni\b.*-itemtype\s+file", "Shell ile yeni dosya oluşturma (ni)"),
            (r"[>\|]{1,2}\s*[\"']?[^\"'\s]+\.(py|js|ts|tsx|jsx|html|css|json|ps1|bat|cmd|vbs)",
             "Shell yönlendirme ile dosya yazma"),
            (r"\bstart-process\b.*-verb\s+runas", "Yönetici yetkisiyle süreç başlatma"),
            (r"\bbypass\b.*executionpolicy|\bexecutionpolicy\b.*bypass", "ExecutionPolicy bypass"),
        ]

        for pattern, desc in dangerous_patterns:
            if re.search(pattern, cmd):
                return True, desc

        return False, ""

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

        if self.tool_start_callback:
            try:
                self.tool_start_callback(tool_name)
            except Exception:
                pass

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
            timeout = int(timeout) if timeout is not None else 30
        except (TypeError, ValueError):
            timeout = 30
        timeout = max(1, min(timeout, 300))

        # 1) Obfuscation: sert blok (onay kartı bile yok — opaque payload güvenilmez)
        is_obfuscated, obf_reason = self._is_obfuscated_command(command)
        if is_obfuscated:
            return {
                "error": True,
                "message": (
                    f"Güvenlik kalkanı: Gizlenmiş/encoded PowerShell komutu engellendi "
                    f"({obf_reason}). Açık metin komut kullanın."
                ),
            }

        # 2) Yıkıcı / dosya-yazan komutlar: Human-in-the-loop onayı
        is_dangerous, reason = self._is_dangerous_command(command)
        if is_dangerous:
            if self.approval_callback:
                allowed = self.approval_callback("shell", {
                    "command": command,
                    "warning": f"Yüksek riskli komut tespit edildi: {reason}"
                })
                if not allowed:
                    return {"error": True, "message": f"İşlem kullanıcı tarafından reddedildi ({reason})."}
            else:
                return {"error": True, "message": f"Güvenlik kalkanı: Bu riskli komut kullanıcı onayı olmadan çalıştırılamaz ({reason})."}

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
            is_safe, reason = self._is_safe_path(full_path)
            if not is_safe:
                if self.approval_callback:
                    allowed = self.approval_callback("path_security", {
                        "path": full_path,
                        "warning": reason
                    })
                    if not allowed:
                        return {"error": True, "message": f"İşlem reddedildi: {reason}"}
                else:
                    return {"error": True, "message": f"Güvenlik kalkanı: {reason}"}

            before = ""
            if os.path.exists(full_path):
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        before = f.read()
                except Exception:
                    before = ""

            after = content or ""
            old_lines = before.replace('\r\n', '\n').splitlines(keepends=True)
            new_lines = after.replace('\r\n', '\n').splitlines(keepends=True)
            diff_lines = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"a/{os.path.basename(full_path)}",
                tofile=f"b/{os.path.basename(full_path)}",
                n=3
            ))
            diff_text = "".join(diff_lines)
            write_action = "write" if before else "create"
            return self._queue_or_apply_change(
                full_path, before, after, diff_text, write_action, "diff_write"
            )
            
        elif action == "patch":
            if not os.path.exists(full_path):
                return {"error": True, "message": "File not found."}

            is_safe, reason = self._is_safe_path(full_path)
            if not is_safe:
                if self.approval_callback:
                    allowed = self.approval_callback("path_security", {
                        "path": full_path,
                        "warning": reason
                    })
                    if not allowed:
                        return {"error": True, "message": f"İşlem reddedildi: {reason}"}
                else:
                    return {"error": True, "message": f"Güvenlik kalkanı: {reason}"}

            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                data = f.read()
            data_norm = data.replace('\r\n', '\n')
            old_norm = (old_string or "").replace('\r\n', '\n')
            new_norm = (new_string or "").replace('\r\n', '\n')
            if old_norm in data_norm:
                patched_data = data_norm.replace(old_norm, new_norm)
            else:
                return {"error": True, "message": "Target string not found for patch."}

            old_lines = data_norm.splitlines(keepends=True)
            new_lines = patched_data.splitlines(keepends=True)
            diff_lines = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"a/{os.path.basename(full_path)}",
                tofile=f"b/{os.path.basename(full_path)}",
                n=3
            ))
            diff_text = "".join(diff_lines)
            return self._queue_or_apply_change(
                full_path, data_norm, patched_data, diff_text, "patch", "diff_patch"
            )
            
        elif action == "create":
            if os.path.exists(full_path):
                return {"error": True, "message": "File already exists."}

            is_safe, reason = self._is_safe_path(full_path)
            if not is_safe:
                if self.approval_callback:
                    allowed = self.approval_callback("path_security", {
                        "path": full_path,
                        "warning": reason
                    })
                    if not allowed:
                        return {"error": True, "message": f"İşlem reddedildi: {reason}"}
                else:
                    return {"error": True, "message": f"Güvenlik kalkanı: {reason}"}

            after = content or ""
            diff_lines = list(difflib.unified_diff(
                [],
                after.replace('\r\n', '\n').splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(full_path)}",
                tofile=f"b/{os.path.basename(full_path)}",
                n=3
            ))
            return self._queue_or_apply_change(
                full_path, "", after, "".join(diff_lines), "create", "diff_write"
            )
            
        elif action in ("delete", "trash"):
            if not os.path.exists(full_path):
                # Fuzzy matching fallback
                dir_path = os.path.dirname(full_path)
                if os.path.exists(dir_path):
                    files = os.listdir(dir_path)
                    matches = difflib.get_close_matches(os.path.basename(full_path), files, n=1, cutoff=0.6)
                    if matches:
                        full_path = os.path.join(dir_path, matches[0])
            if not os.path.exists(full_path):
                return {"error": True, "message": "File not found."}

            # Silme işlemi için zorunlu kullanıcı onayı
            if self.approval_callback:
                approved = self.approval_callback("delete", {
                    "path": full_path,
                    "filename": os.path.basename(full_path),
                    "is_dir": os.path.isdir(full_path),
                    "warning": f"'{os.path.basename(full_path)}' {'klasörü' if os.path.isdir(full_path) else 'dosyası'} çöp kutusuna taşınacak!"
                })
                if not approved:
                    return {"error": True, "message": "Kullanıcı silme işlemini onaylamadı."}

            try:
                import send2trash
                send2trash.send2trash(full_path)
                return {"success": True, "message": f"'{os.path.basename(full_path)}' güvenli şekilde çöp kutusuna taşındı."}
            except Exception:
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                else:
                    os.remove(full_path)
                return {"success": True, "message": f"'{os.path.basename(full_path)}' silindi."}
                
        elif action == "rename":
            new_path = self._get_path(kwargs.get("new_name", ""))
            is_safe, reason = self._is_safe_path(full_path)
            if not is_safe:
                if self.approval_callback:
                    allowed = self.approval_callback("path_security", {
                        "path": full_path,
                        "warning": reason
                    })
                    if not allowed:
                        return {"error": True, "message": f"İşlem reddedildi: {reason}"}
                else:
                    return {"error": True, "message": f"Güvenlik kalkanı: {reason}"}
            is_safe_new, reason_new = self._is_safe_path(new_path)
            if not is_safe_new:
                if self.approval_callback:
                    allowed = self.approval_callback("path_security", {
                        "path": new_path,
                        "warning": reason_new
                    })
                    if not allowed:
                        return {"error": True, "message": f"İşlem reddedildi: {reason_new}"}
                else:
                    return {"error": True, "message": f"Güvenlik kalkanı: {reason_new}"}
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
