import tkinter as tk
import threading
import time
import ctypes

try:
    # Windows 8.1+
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        # Windows Vista/7
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

_overlay_root = None
_show_req = False

def _run_overlay():
    global _overlay_root
    _overlay_root = tk.Tk()
    _overlay_root.attributes('-topmost', True)
    
    # Make background white and transparent
    _overlay_root.attributes('-transparentcolor', 'white')
    _overlay_root.config(bg='white')
    
    # Make it click-through on Windows
    _overlay_root.wm_attributes("-disabled", True)
    # Remove title bar
    _overlay_root.overrideredirect(True)
    
    # Full screen
    sw = _overlay_root.winfo_screenwidth()
    sh = _overlay_root.winfo_screenheight()
    _overlay_root.geometry(f"{sw}x{sh}+0+0")
    
    # Draw red canvas border
    canvas = tk.Canvas(_overlay_root, width=sw, height=sh, bg='white', highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    
    b = 8  # Border width
    # Draw neon-like red border
    canvas.create_rectangle(b/2, b/2, sw-b/2, sh-b/2, outline='#ff1a1a', width=b)
    
    # Hide by default
    _overlay_root.withdraw()
    
    def check_state():
        if _show_req and _overlay_root.state() != 'normal':
            _overlay_root.deiconify()
        elif not _show_req and _overlay_root.state() == 'normal':
            _overlay_root.withdraw()
        _overlay_root.after(100, check_state)
        
    _overlay_root.after(100, check_state)
    _overlay_root.mainloop()

# Start daemon thread so it's always ready without blocking
_overlay_thread = threading.Thread(target=_run_overlay, daemon=True)
_overlay_thread.start()

def show_red_border():
    global _show_req
    _show_req = True

def hide_red_border():
    global _show_req
    _show_req = False
