#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build script - Package ccprofile into a standalone executable using PyInstaller."""

import os
import subprocess
import sys
import shutil
from pathlib import Path

# Fix encoding on Windows
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
DIST = ROOT / "dist"


def check_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build():
    check_pyinstaller()

    if DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--clean",
        "--name", "ccprofile",
        "--hidden-import", "cryptography",
        "--hidden-import", "cryptography.fernet",
        "--hidden-import", "cryptography.hazmat.primitives.ciphers",
        "--hidden-import", "cryptography.hazmat.primitives",
        "--hidden-import", "cryptography.hazmat.backends",
        "--hidden-import", "ccprofile_app",
        "--collect-submodules", "ccprofile_app",
        str(ROOT / "ccprofile.py"),
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    ext = ".exe" if sys.platform == "win32" else ""
    exe = DIST / f"ccprofile{ext}"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"\nBuild succeeded: {exe} ({size_mb:.1f} MB)")
    else:
        print("\nError: Build artifact not found.")
        sys.exit(1)


if __name__ == "__main__":
    build()
