"""Build script for SBpy:
1. Converts assets/icon.jpg to a multi-resolution assets/icon.ico
2. Generates Windows file version resource (version_info.txt)
3. Builds standalone sbpy.exe using PyInstaller
4. Creates a Desktop shortcut with the custom icon
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Fix Windows console UTF-8 encoding for Hebrew / Unicode paths
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_desktop_dir() -> Path:
    """Gets the active Windows Desktop path."""
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        )
        val, _ = winreg.QueryValueEx(key, "Desktop")
        winreg.CloseKey(key)
        expanded = os.path.expandvars(val)
        if os.path.isdir(expanded):
            return Path(expanded)
    except Exception:
        pass
    
    # Fallback to OneDrive Desktop or standard Desktop
    userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    onedrive_desktop = userprofile / "OneDrive - PCMASTER" / "Desktop"
    if onedrive_desktop.is_dir():
        return onedrive_desktop
    onedrive_desktop_std = userprofile / "OneDrive" / "Desktop"
    if onedrive_desktop_std.is_dir():
        return onedrive_desktop_std
    return userprofile / "Desktop"


def generate_ico(project_root: Path) -> Path:
    """Converts icon.jpg to multi-size Windows icon.ico."""
    from PIL import Image

    src_jpg = project_root / "assets" / "icon.jpg"
    out_ico = project_root / "assets" / "icon.ico"

    if not src_jpg.exists():
        src_jpg = project_root / "assets" / "logo.jpg"

    if not src_jpg.exists():
        raise FileNotFoundError(f"Icon source not found in {project_root / 'assets'}")

    print(f"[*] Converting {src_jpg.name} to {out_ico.name} with multiple sizes...")
    img = Image.open(src_jpg).convert("RGBA")
    
    # Windows standard icon sizes
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    img.save(out_ico, format="ICO", sizes=sizes)
    print(f"[+] Created {out_ico} ({out_ico.stat().st_size:,} bytes)")
    return out_ico


def generate_version_info(project_root: Path) -> Path:
    """Creates PyInstaller Windows version info definition file."""
    version_file = project_root / "version_info.txt"
    content = """# UTF-8
#
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(0, 1, 0, 0),
    prodvers=(0, 1, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', 'Smart Binary'),
            StringStruct('FileDescription', 'SBpy - Python AI Debugger & Optimizer'),
            StringStruct('FileVersion', '0.1.0.0'),
            StringStruct('InternalName', 'sbpy'),
            StringStruct('LegalCopyright', 'Copyright (c) 2026 Smart Binary. All rights reserved.'),
            StringStruct('OriginalFilename', 'sbpy.exe'),
            StringStruct('ProductName', 'SBpy'),
            StringStruct('ProductVersion', '0.1.0.0')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    version_file.write_text(content, encoding="utf-8")
    print(f"[+] Created version info file: {version_file.name}")
    return version_file


def build_executable(project_root: Path, ico_path: Path, version_file: Path) -> Path:
    """Runs PyInstaller to compile sbpy.exe."""
    entry_point = project_root / "sbpy_runner.py"
    assets_dir = project_root / "assets"
    
    work_dir = Path(os.environ.get("TEMP", ".")) / "sbpy_build_work"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        f"--workpath={work_dir}",
        "--name=sbpy",
        "--onefile",
        "--console",
        f"--icon={ico_path}",
        f"--version-file={version_file}",
        f"--add-data={assets_dir}{os.pathsep}assets",
        "--collect-all=sbpy",
        "--hidden-import=sbpy",
        "--hidden-import=sbpy.cli",
        "--hidden-import=sbpy.ui_server",
        "--hidden-import=sbpy.local",
        "--hidden-import=sbpy.local.fixers",
        "--hidden-import=sbpy.local.typo",
        "--hidden-import=sbpy.static",
        "--hidden-import=sbpy.static.checks",
        "--hidden-import=sbpy.shell",
        "--hidden-import=sbpy.shortcuts",
        "--hidden-import=sbpy.gemini",
        "--hidden-import=sbpy.ladder",
        "--hidden-import=sbpy.patcher",
        "--hidden-import=sbpy.git_ops",
        "--hidden-import=sbpy.graph",
        "--hidden-import=sbpy.trace",
        "--hidden-import=sbpy.agent",
        "--hidden-import=sbpy.index",
        "--hidden-import=sbpy.learn",
        "--hidden-import=sbpy.i18n",
        "--hidden-import=sbpy.console",
        "--hidden-import=sbpy.config",
        "--hidden-import=sbpy.budget",
        "--hidden-import=sbpy.cache",
        "--hidden-import=sbpy.context",
        "--hidden-import=sbpy.contextpack",
        "--hidden-import=sbpy.diagrams",
        "--hidden-import=sbpy.diff_viewer",
        "--hidden-import=sbpy.fullinfo",
        "--hidden-import=sbpy.hooks",
        "--hidden-import=sbpy.infer",
        "--hidden-import=sbpy.integrations",
        "--hidden-import=sbpy.knowledge",
        "--hidden-import=sbpy.lsp",
        "--hidden-import=sbpy.magic",
        "--hidden-import=sbpy.migrate",
        "--hidden-import=sbpy.pricing",
        "--hidden-import=sbpy.prompts",
        "--hidden-import=sbpy.providers",
        "--hidden-import=sbpy.redact",
        "--hidden-import=sbpy.render",
        "--hidden-import=sbpy.report",
        "--hidden-import=sbpy.results",
        "--hidden-import=sbpy.rules",
        "--hidden-import=sbpy.scaffold",
        "--hidden-import=sbpy.scancache",
        "--hidden-import=sbpy.search",
        "--hidden-import=sbpy.spinner",
        "--hidden-import=sbpy.suggestions",
        "--hidden-import=sbpy.taint",
        "--hidden-import=sbpy.test_gen",
        "--hidden-import=sbpy.testgen",
        "--hidden-import=sbpy.watcher",
        "--hidden-import=sbpy.cleaner",
        "--hidden-import=sbpy.terminal_alias",
        "--hidden-import=sbpy.updater",
        "--hidden-import=sbpy.keyboard",
        "--hidden-import=sbpy._startup",
        str(entry_point),
    ]

    print("[*] Running PyInstaller compilation...")
    print(f"    Command: {' '.join(cmd[:6])} ...")
    
    result = subprocess.run(cmd, cwd=project_root)
    if result.returncode != 0:
        raise RuntimeError(f"PyInstaller failed with code {result.returncode}")

    exe_path = project_root / "dist" / "sbpy.exe"
    if not exe_path.exists():
        raise FileNotFoundError(f"Expected compiled exe at {exe_path}")

    print(f"[+] Compilation SUCCESSFUL! Binary created: {exe_path} ({exe_path.stat().st_size:,} bytes)")
    return exe_path


def create_desktop_shortcut(exe_path: Path, ico_path: Path, project_root: Path) -> Path:
    """Creates a Windows shortcut (.lnk) on the Desktop using PowerShell."""
    desktop_dir = get_desktop_dir()
    shortcut_path = desktop_dir / "SBpy.lnk"

    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{str(shortcut_path)}')
$Shortcut.TargetPath = '{str(exe_path)}'
$Shortcut.WorkingDirectory = '{str(project_root)}'
$Shortcut.IconLocation = '{str(ico_path)}'
$Shortcut.Description = 'SBpy - Python AI Debugger, Error Fixer & Optimizer'
$Shortcut.Save()
"""
    print(f"[*] Creating Desktop Shortcut at: {shortcut_path} ...")
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[!] Warning: Failed creating desktop shortcut: {res.stderr}")
    else:
        print(f"[+] Desktop Shortcut created successfully: {shortcut_path}")
    return shortcut_path


def main() -> int:
    project_root = Path(__file__).resolve().parent
    print("=" * 60)
    print("  SBpy - Professional EXE Compiler & Shortcut Creator")
    print("=" * 60)
    print(f"Project directory: {project_root}")

    try:
        ico_path = generate_ico(project_root)
        version_file = generate_version_info(project_root)
        exe_path = build_executable(project_root, ico_path, version_file)
        shortcut_path = create_desktop_shortcut(exe_path, ico_path, project_root)

        print("\n" + "=" * 60)
        print("  Build & Setup Completed Successfully!")
        print(f"  EXE Location:      {exe_path}")
        print(f"  Desktop Shortcut:  {shortcut_path}")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n[ERROR] Build failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
