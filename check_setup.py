#!/usr/bin/env python
"""
Tenra V6 setup checker.
Validates Python environment, dependencies, Ollama access and model files.
"""

import os
import sys


def main() -> int:
    all_ok = True

    print("=" * 60)
    print("TENRA V7 - SETUP CHECK")
    print("=" * 60)
    print()

    # 1) Python version
    print(f"[OK] Python: {sys.version}")
    print()

    # 2) Required packages
    print("Package checks:")
    packages = [
        ("PySide6", "PySide6"),
        ("requests", "requests"),
        ("keyboard", "keyboard"),
        ("pyautogui", "pyautogui"),
    ]

    for pkg_name, import_name in packages:
        try:
            __import__(import_name)
            print(f"  [OK] {pkg_name}")
        except ImportError as err:
            print(f"  [ERR] {pkg_name} - {err}")
            all_ok = False

    print()

    # 3) Ollama connectivity
    print("System checks:")
    ollama_ok = False
    models = []
    try:
        import requests
        import subprocess
        import time

        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                ollama_ok = True
                models = [m["name"] for m in response.json().get("models", [])]
        except Exception:
            pass

        if not ollama_ok:
            print("  [*] Ollama is not running. Attempting to start 'ollama serve' automatically...")
            # Start ollama serve in a background process without a popup command window
            # 0x08000000 is CREATE_NO_WINDOW
            try:
                subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
                
                # Poll for up to 15 seconds
                for i in range(15):
                    time.sleep(1)
                    try:
                        response = requests.get("http://localhost:11434/api/tags", timeout=2)
                        if response.status_code == 200:
                            ollama_ok = True
                            models = [m["name"] for m in response.json().get("models", [])]
                            print("  [OK] Ollama started successfully")
                            break
                    except Exception:
                        pass
            except FileNotFoundError:
                print("  [ERR] Ollama is not installed or not in system PATH.")
                print("        Please download Ollama from https://ollama.com/")
                all_ok = False
            except Exception as e:
                print(f"  [ERR] Failed to start Ollama automatically: {e}")
                all_ok = False

        if ollama_ok:
            print("  [OK] Ollama is running")
            print(f"       Installed models: {', '.join(models) if models else 'none'}")
            
            # Check for vision model
            if not any("vision" in m or "llava" in m for m in models):
                print("  [WARN] A vision model ('llama3.2-vision' or 'llava') is NOT installed!")
                print("         Run 'ollama pull llama3.2-vision' to enable screenshot analysis.")
            else:
                print("  [OK] Vision model is installed.")
        else:
            if all_ok:
                print("  [ERR] Ollama check failed: Could not connect to Ollama after auto-start attempt.")
                print("        Solution: run 'ollama serve' in a terminal")
                all_ok = False
    except Exception as err:
        print(f"  [ERR] Ollama check failed: {err}")
        all_ok = False

    print()

    # 4) Local router model files
    print("Model files:")
    model_path = os.path.join(os.path.dirname(__file__), "tenra_v5", "_dev_archive", "merged_model")
    if os.path.exists(model_path):
        files = os.listdir(model_path)
        preview = ", ".join(files[:3])
        suffix = "..." if len(files) > 3 else ""
        print(f"  [OK] {model_path} exists")
        print(f"       Files: {preview}{suffix}")
    else:
        print(f"  [WARN] Missing folder: {model_path}")
        print("         (Safe to ignore if USE_LOCAL_ROUTER is False in config.py)")

    print()

    print("=" * 60)
    if all_ok:
        print("[OK] READY - You can run run_tenra_v5.bat")
    else:
        print("[ERR] ISSUES FOUND - Review messages above")
    print("=" * 60)

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

