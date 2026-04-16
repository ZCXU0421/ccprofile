#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build script - Package ccprofile into a PyInstaller onedir distribution."""

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


def check_certifi():
    try:
        import certifi  # noqa: F401
    except ImportError:
        print("Installing certifi...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "certifi"])


def build():
    check_pyinstaller()
    check_certifi()

    if DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--clean",
        "--name", "ccprofile",
        "--hidden-import", "cryptography",
        "--hidden-import", "cryptography.fernet",
        "--hidden-import", "cryptography.hazmat.primitives.ciphers",
        "--hidden-import", "cryptography.hazmat.primitives",
        "--hidden-import", "cryptography.hazmat.backends",
        "--hidden-import", "certifi",
        "--collect-data", "certifi",
        "--hidden-import", "ccprofile_app",
        "--collect-submodules", "ccprofile_app",
        "ccprofile.py",
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=ROOT)

    exe_name = "ccprofile.exe" if sys.platform == "win32" else "ccprofile"
    bundle_dir = DIST / "ccprofile"
    exe = bundle_dir / exe_name
    if exe.exists():
        total_size = sum(p.stat().st_size for p in bundle_dir.rglob("*") if p.is_file())
        size_mb = total_size / (1024 * 1024)
        print(f"\nBuild succeeded: {bundle_dir} ({size_mb:.1f} MB)")
        print(f"Executable: {exe}")
    else:
        print("\nError: Build artifact not found.")
        sys.exit(1)


if __name__ == "__main__":
    build()
