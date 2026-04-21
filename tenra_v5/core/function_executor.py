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
        try:
            handler = {
                # === Tenra Sistem Fonksiyonları ===
                "run_command": self._run_command,
                "find_file": self._find_file,
                "create_file": self._create_file,
                "delete_file": self._delete_file,
                "move_to_trash": self._move_to_trash,
                "open_app": self._open_app,
                "open_url": self._open_url,
                "list_desktop": self._list_desktop,
                # === ADA Fonksiyonları ===
                "control_light": self._control_light,
                "set_timer": self._set_timer,
                "set_alarm": self._set_alarm,
                "create_calendar_event": self._create_calendar_event,
                "add_task": self._add_task,
                "web_search": self._web_search,
                "get_system_info": self._get_system_info,
            }.get(func_name)
            
            if handler:
                return handler(params)
            return {"success": False, "message": f"Bilinmeyen fonksiyon: {func_name}", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Hata: {str(e)}", "data": None}

    # ═══════════════════════════════════════════════
    # TENRA SİSTEM FONKSİYONLARI
    # ═══════════════════════════════════════════════

    def _run_command(self, params: Dict) -> Dict:
        """PowerShell komutu çalıştır."""
        command = params.get("command", "")
        if not command:
            return {"success": False, "message": "Komut belirtilmedi", "data": None}
        try:
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True, text=True, timeout=30
            )
            output = result.stdout.strip() or result.stderr.strip() or "(Çıktı yok)"
            return {"success": True, "message": output, "data": {"command": command}}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Komut zaman aşımına uğradı (30sn)", "data": None}
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
        
        try:
            from send2trash import send2trash
            send2trash(path)
            return {"success": True, "message": f"Çöp kutusuna taşındı: {path}", "data": None}
        except Exception as e:
            return {"success": False, "message": f"Çöpe taşıma hatası: {e}", "data": None}

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
