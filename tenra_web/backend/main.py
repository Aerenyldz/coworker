import webview
import threading
import uvicorn
import time
from server import app

# This flag is used to track whether the window has closed
window_closed = False

def start_server():
    """Run FastAPI. The server stays alive until the main thread exists or we stop it."""
    # uvicorn doesn't natively have a gentle stop without keeping ref to the server,
    # but when the main process (webview) exits, daemon thread will terminate.
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

if __name__ == '__main__':
    # Start the web server in a background daemon thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Wait a tiny bit allowing uvicorn to bind the port
    time.sleep(1.0)
    
    # Create the webview window pointing to our local server
    # We remove the background to make it look clean if supported
    window = webview.create_window(
        'Tenra - AI Asistan', 
        'http://127.0.0.1:8000', 
        width=950, 
        height=800,
        text_select=True,
        background_color='#0a0a0a'
    )
    
    # Start the pywebview main loop. Once closed, script exits.
    webview.start()
