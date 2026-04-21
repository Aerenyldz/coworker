#!/usr/bin/env python
"""
Tenra V5 setup checker.
Validates Python environment, dependencies, Ollama access and model files.
"""

import os
import sys


def main() -> int:
    all_ok = True

    print("=" * 60)
    print("TENRA V5 - SETUP CHECK")
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
        ("torch", "torch"),
        ("transformers", "transformers"),
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
    try:
        import requests

        response = requests.get("http://localhost:11434/api/tags", timeout=3)
        if response.status_code == 200:
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            print("  [OK] Ollama is running")
            print(f"       Installed models: {', '.join(models) if models else 'none'}")
        else:
            print(f"  [ERR] Ollama returned status {response.status_code}")
            all_ok = False
    except Exception as err:
        print(f"  [ERR] Ollama check failed: {err}")
        print("       Solution: run 'ollama serve' in a terminal")
        all_ok = False

    print()

    # 4) Local router model files
    print("Model files:")
    model_path = os.path.join(os.path.dirname(__file__), "tenra_v5", "merged_model")
    if os.path.exists(model_path):
        files = os.listdir(model_path)
        preview = ", ".join(files[:3])
        suffix = "..." if len(files) > 3 else ""
        print(f"  [OK] {model_path} exists")
        print(f"       Files: {preview}{suffix}")
    else:
        print(f"  [ERR] Missing folder: {model_path}")
        all_ok = False

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

