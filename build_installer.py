"""Build script for SBpy Setup Installer (SBpy_Setup.exe).
Compiles the Graphical Installer Wizard into a single standalone Setup.exe.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Fix Windows console UTF-8 encoding
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def build_setup_installer():
    project_root = Path(__file__).resolve().parent
    ico_path = project_root / "assets" / "icon.ico"
    version_file = project_root / "version_info.txt"
    sbpy_exe = project_root / "dist" / "sbpy.exe"
    assets_dir = project_root / "assets"

    if not sbpy_exe.exists():
        print("[!] dist/sbpy.exe missing. Building sbpy.exe first...")
        subprocess.run([sys.executable, "build_exe.py"], cwd=project_root, check=True)

    print("=" * 60)
    print("  Building Graphical Setup Wizard: SBpy_Setup.exe")
    print("=" * 60)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name=SBpy_Setup",
        "--onefile",
        "--windowed",
        f"--icon={ico_path}",
        f"--add-data={sbpy_exe}{os.pathsep}dist",
        f"--add-data={assets_dir}{os.pathsep}assets",
        "--hidden-import=tkinter",
        "--hidden-import=tkinter.ttk",
        "--hidden-import=tkinter.filedialog",
        "--hidden-import=tkinter.messagebox",
        str(project_root / "installer_gui.py"),
    ]

    print("[*] Running PyInstaller for Setup Wizard...")
    res = subprocess.run(cmd, cwd=project_root)
    if res.returncode != 0:
        raise RuntimeError(f"PyInstaller failed with exit code {res.returncode}")

    setup_exe = project_root / "dist" / "SBpy_Setup.exe"
    if not setup_exe.exists():
        raise FileNotFoundError(f"Setup executable not found at {setup_exe}")

    print(f"\n[+] SUCCESS! Graphical Setup Wizard created:")
    print(f"    {setup_exe} ({setup_exe.stat().st_size:,} bytes)")
    return setup_exe


if __name__ == "__main__":
    build_setup_installer()
