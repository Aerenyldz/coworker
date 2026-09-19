import os
import glob
import subprocess
import pyautogui
import keyboard

# Failsafe ayarı: mouse köşeye çekilirse sistem durur
pyautogui.FAILSAFE = True

def find_file(filename: str) -> str:
    """Searches for a file by name recursively in the user's home directory."""
    try:
        home = os.path.expanduser("~")
        sonuclar = glob.glob(f"{home}/**/*{filename}*", recursive=True)[:5]
        if sonuclar:
            return "Bulunan dosyalar:\n" + "\n".join(sonuclar)
        return f"'{filename}' adında dosya bulunamadı."
    except Exception as e:
        return f"Dosya arama hatası: {str(e)}"

def read_file(filepath: str) -> str:
    """Reads the content of a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Dosya okuma hatası: {str(e)}"

def write_file(filepath: str, content: str) -> str:
    """Writes or overwrites content to a file."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"{filepath} başarıyla kaydedildi/değiştirildi."
    except Exception as e:
        return f"Dosya yazma hatası: {str(e)}"

def open_url(url: str) -> str:
    """Opens a URL in the default web browser.
    Useful when the user asks to open a website, open google, open youtube, etc."""
    try:
        if not url.startswith("http"):
            url = "https://" + url
        os.startfile(url)
        return f"Tarayıcıda açıldı: {url}"
    except Exception as e:
        return f"URL açma hatası: {str(e)}"

def run_command(command: str) -> str:
    """Runs a shell command and returns the output.
    Can run any system command. Be careful of destructive actions."""
    try:
        # User requested full authority. No restriction.
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        return result.stdout or result.stderr or "Komut çalıştırıldı ancak çıktı vermedi."
    except Exception as e:
        return f"Komut hatası: {str(e)}"

def mouse_move(x: int, y: int) -> str:
    """Belirtilen (x, y) koordinatlarına fareyi hareket ettirir."""
    try:
        pyautogui.moveTo(x, y, duration=0.5)
        return f"Mouse {x}, {y} konumuna taşındı."
    except Exception as e:
        return f"Mouse taşıma hatası: {str(e)}"

def mouse_click(button: str = "left") -> str:
    """Bulunduğu yere tıklar (left, right)."""
    try:
        pyautogui.click(button=button)
        return f"Mouse {button} tuşuyla tıklandı."
    except Exception as e:
        return f"Tıklama hatası: {str(e)}"

def keyboard_type(text: str) -> str:
    """Klavyeden metin yazar"""
    try:
        pyautogui.write(text, interval=0.01)
        return f"'{text}' yazıldı."
    except Exception as e:
        return f"Klavye hatası: {str(e)}"

# Register tools
AVAILABLE_TOOLS = {
    "find_file": find_file,
    "read_file": read_file,
    "write_file": write_file,
    "open_url": open_url,
    "run_command": run_command,
    "mouse_move": mouse_move,
    "mouse_click": mouse_click,
    "keyboard_type": keyboard_type,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "find_file",
            "description": "Bilgisayarda dosya/belge arar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Aranacak dosya adı"
                    }
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Belirtilen yoldaki dosyanın içeriğini okur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Okunacak dosyanın tam yolu (ör: C:\\Users\\ahmet\\Desktop\\not.txt)"
                    }
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Belirtilen yoldaki dosyayı değiştirir veya yeni dosya oluşturup içine yazar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Yazılacak dosyanın tam yolu"
                    },
                    "content": {
                        "type": "string",
                        "description": "Dosyanın içine yazılacak tam metin/kod"
                    }
                },
                "required": ["filepath", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Kullanıcı için tarayıcıda bir web sitesini (Google, Youtube vb.) açar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Açılacak url (ör: google.com)"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Terminalde sistem komutlarını çalıştırır. Powershell komutlarını yollayabilirsiniz (Örn: Get-ChildItem, ping, vs).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Çalıştırılacak terminal komutu"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_move",
            "description": "Fareyi ekranın X ve Y koordinatlarına hareket ettirir. (Antigravity yeteneği)",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X ekseni noktası"},
                    "y": {"type": "integer", "description": "Y ekseni noktası"}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_click",
            "description": "Farenin o anki konumuna tıklar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "button": {"type": "string", "enum": ["left", "right"], "description": "Tıklanacak tuş"}
                },
                "required": ["button"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "keyboard_type",
            "description": "Yapay zekanın klavyeyi kullanarak o anki odaklı yere yazı yazmasını sağlar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Yazılacak metin"}
                },
                "required": ["text"]
            }
        }
    }
]
