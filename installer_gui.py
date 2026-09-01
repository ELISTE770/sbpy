"""SBpy Windows Setup Installer GUI Wizard.
A modern, native graphical installer wizard for SBpy.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Set UTF-8 encoding for console if attached
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_base_dir() -> Path:
    """Returns directory where installer data is located (supports PyInstaller bundle)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore
    return Path(__file__).resolve().parent


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
    
    userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    for cand in [userprofile / "OneDrive - PCMASTER" / "Desktop", userprofile / "OneDrive" / "Desktop", userprofile / "Desktop"]:
        if cand.is_dir():
            return cand
    return userprofile / "Desktop"


def get_start_menu_dir() -> Path:
    """Gets the Programs folder in Start Menu."""
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        p = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if p.is_dir():
            return p
    return Path.home()


def add_to_user_path(directory: str) -> bool:
    """Adds a directory to the User PATH environment variable."""
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE
        )
        try:
            current_path, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current_path = ""
        
        parts = [p.strip() for p in current_path.split(";") if p.strip()]
        norm_dir = os.path.normpath(directory).lower()
        
        for p in parts:
            if os.path.normpath(p).lower() == norm_dir:
                winreg.CloseKey(key)
                return False  # Already in PATH
        
        parts.append(directory)
        new_path = ";".join(parts)
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
        winreg.CloseKey(key)
        
        # Broadcast WM_SETTINGCHANGE so new shells inherit the PATH
        try:
            import ctypes
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002
            result = ctypes.c_long()
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
                SMTO_ABORTIFHUNG, 5000, ctypes.byref(result)
            )
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"Failed to update PATH: {e}", file=sys.stderr)
        return False


def register_uninstaller(install_dir: Path, exe_path: Path, ico_path: Path, version: str = "0.1.0"):
    """Registers SBpy in Windows Add/Remove Programs registry."""
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\SBpy"
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "SBpy - Python AI Debugger")
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "SBpy Project")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(ico_path if ico_path.exists() else exe_path))
        
        uninstaller_path = install_dir / "uninstall.bat"
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller_path}"')
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Registry uninstaller error: {e}", file=sys.stderr)


class SBpyInstallerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SBpy Setup Wizard - התקנת SBpy")
        self.geometry("640x480")
        self.resizable(False, False)
        
        # Center window on screen
        self.update_idletasks()
        w = 640
        h = 480
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.base_dir = get_base_dir()
        self.ico_path = self.base_dir / "assets" / "icon.ico"
        if self.ico_path.exists():
            try:
                self.iconbitmap(str(self.ico_path))
            except Exception:
                pass

        # Variables
        default_install = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "SBpy"
        self.install_dir_var = tk.StringVar(value=str(default_install))
        self.create_desktop_var = tk.BooleanVar(value=True)
        self.create_start_var = tk.BooleanVar(value=True)
        self.add_path_var = tk.BooleanVar(value=True)
        self.launch_after_var = tk.BooleanVar(value=True)

        self.current_step = 0
        self.steps = [
            self.create_welcome_page,
            self.create_directory_page,
            self.create_options_page,
            self.create_install_page,
            self.create_finish_page,
        ]

        self.configure_styles()
        self.create_layout()
        self.show_step(0)

    def configure_styles(self):
        self.configure(bg="#181824")
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        # Custom dark palette
        self.style.configure(".", background="#181824", foreground="#FFFFFF", font=("Segoe UI", 10))
        self.style.configure("TLabel", background="#181824", foreground="#FFFFFF", font=("Segoe UI", 10))
        self.style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), foreground="#58A6FF")
        self.style.configure("SubHeader.TLabel", font=("Segoe UI", 11), foreground="#8B949E")
        self.style.configure("Desc.TLabel", font=("Segoe UI", 10), foreground="#C9D1D9")
        self.style.configure("TCheckbutton", background="#181824", foreground="#E6EDF3", font=("Segoe UI", 10))
        
        self.style.configure(
            "Primary.TButton",
            font=("Segoe UI", 10, "bold"),
            background="#238636",
            foreground="#FFFFFF",
            borderwidth=0,
            padding=8
        )
        self.style.map("Primary.TButton", background=[("active", "#2ea043"), ("disabled", "#30363d")])

        self.style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 10),
            background="#21262d",
            foreground="#C9D1D9",
            borderwidth=1,
            padding=8
        )
        self.style.map("Secondary.TButton", background=[("active", "#30363d")])

        self.style.configure(
            "TProgressbar",
            thickness=16,
            troughcolor="#21262d",
            background="#58A6FF",
            borderwidth=0
        )

    def create_layout(self):
        # Top banner frame
        self.banner_frame = tk.Frame(self, bg="#0d1117", height=70)
        self.banner_frame.pack(fill="x", side="top")

        self.banner_title = tk.Label(
            self.banner_frame,
            text="SBpy Setup Wizard",
            font=("Segoe UI", 14, "bold"),
            bg="#0d1117",
            fg="#58A6FF"
        )
        self.banner_title.pack(side="left", padx=20, pady=12)

        self.banner_sub = tk.Label(
            self.banner_frame,
            text="v0.1.0",
            font=("Segoe UI", 10),
            bg="#0d1117",
            fg="#8B949E"
        )
        self.banner_sub.pack(side="left", pady=15)

        # Content container
        self.container = tk.Frame(self, bg="#181824", padx=25, pady=20)
        self.container.pack(fill="both", expand=True)

        # Bottom navigation bar
        self.bottom_bar = tk.Frame(self, bg="#0d1117", height=55, padx=20, pady=10)
        self.bottom_bar.pack(fill="x", side="bottom")

        self.btn_cancel = ttk.Button(self.bottom_bar, text="ביטול / Cancel", style="Secondary.TButton", command=self.on_cancel)
        self.btn_cancel.pack(side="left")

        self.btn_next = ttk.Button(self.bottom_bar, text="הבא / Next >", style="Primary.TButton", command=self.on_next)
        self.btn_next.pack(side="right", padx=(8, 0))

        self.btn_back = ttk.Button(self.bottom_bar, text="< חזרה / Back", style="Secondary.TButton", command=self.on_back)
        self.btn_back.pack(side="right")

    def show_step(self, step_idx: int):
        self.current_step = step_idx
        for widget in self.container.winfo_children():
            widget.destroy()
        
        self.steps[step_idx]()

        # Update button states
        if step_idx == 0:
            self.btn_back.config(state="disabled")
            self.btn_next.config(text="הבא / Next >", state="normal")
            self.btn_cancel.config(state="normal")
        elif step_idx == 1:
            self.btn_back.config(state="normal")
            self.btn_next.config(text="הבא / Next >", state="normal")
            self.btn_cancel.config(state="normal")
        elif step_idx == 2:
            self.btn_back.config(state="normal")
            self.btn_next.config(text="התקן / Install", state="normal")
            self.btn_cancel.config(state="normal")
        elif step_idx == 3:
            self.btn_back.config(state="disabled")
            self.btn_next.config(state="disabled")
            self.btn_cancel.config(state="disabled")
        elif step_idx == 4:
            self.btn_back.config(state="disabled")
            self.btn_next.config(text="סיום / Finish", state="normal", command=self.on_finish)
            self.btn_cancel.pack_forget()

    def on_next(self):
        if self.current_step == 1:
            dest = self.install_dir_var.get().strip()
            if not dest:
                messagebox.showerror("שגיאה", "אנא בחר תיקיית התקנה תקינה.")
                return
        if self.current_step < len(self.steps) - 1:
            self.show_step(self.current_step + 1)

    def on_back(self):
        if self.current_step > 0:
            self.show_step(self.current_step - 1)

    def on_cancel(self):
        if messagebox.askyesno("יציאה", "האם אתה בטוח שברצונך לבטל את ההתקנה?"):
            self.destroy()

    def on_finish(self):
        if self.launch_after_var.get():
            install_dir = Path(self.install_dir_var.get().strip())
            exe_path = install_dir / "sbpy.exe"
            if exe_path.exists():
                subprocess.Popen([str(exe_path)], cwd=str(install_dir))
        self.destroy()

    # --- Pages ---

    def create_welcome_page(self):
        title = ttk.Label(self.container, text="ברוכים הבאים להתקנת SBpy", style="Header.TLabel")
        title.pack(anchor="w", pady=(0, 6))

        sub = ttk.Label(self.container, text="Python AI Debugger, Error Fixer & Performance Optimizer", style="SubHeader.TLabel")
        sub.pack(anchor="w", pady=(0, 20))

        features_frame = tk.Frame(self.container, bg="#21262d", padx=16, pady=16, relief="flat")
        features_frame.pack(fill="both", expand=True, pady=10)

        items = [
            "⚡ תיקון שגיאות מקומי חכם ב-Python (ללא תלות חיצונית)",
            "🤖 הסלמה ל-Google Gemini AI רק כשבאמת צריך",
            "🌐 ממשק Web Dashboard גרפי מובנה + AI Pair Programmer",
            "🔍 סריקת באגים, אבטחה וביצועים בלחיצה אחת",
            "🚀 תמיכה מלאה בהרצה ישירה משורת הפקודה או משולחן העבודה"
        ]

        for item in items:
            row = tk.Label(features_frame, text=f"✓  {item}", bg="#21262d", fg="#E6EDF3", font=("Segoe UI", 10), anchor="w")
            row.pack(fill="x", pady=4)

    def create_directory_page(self):
        title = ttk.Label(self.container, text="בחירת תיקיית התקנה", style="Header.TLabel")
        title.pack(anchor="w", pady=(0, 6))

        sub = ttk.Label(self.container, text="בחר את המיקום שבו יותקן SBpy במחשב שלך:", style="SubHeader.TLabel")
        sub.pack(anchor="w", pady=(0, 20))

        dir_frame = tk.Frame(self.container, bg="#181824")
        dir_frame.pack(fill="x", pady=10)

        entry = tk.Entry(
            dir_frame,
            textvariable=self.install_dir_var,
            font=("Segoe UI", 10),
            bg="#0d1117",
            fg="#FFFFFF",
            insertbackground="#FFFFFF",
            relief="solid",
            bd=1
        )
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 10))

        btn_browse = ttk.Button(dir_frame, text="עיון... / Browse", style="Secondary.TButton", command=self.browse_dir)
        btn_browse.pack(side="right")

        info_box = tk.Label(
            self.container,
            text="💡 שטח דיסק נדרש: כ-25 MB.\nההתקנה כוללת את הבינארי, כלי ה-CLI, והממשק הגרפי.",
            bg="#181824",
            fg="#8B949E",
            font=("Segoe UI", 9),
            justify="right",
            anchor="e"
        )
        info_box.pack(anchor="w", pady=15)

    def browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.install_dir_var.get(), title="בחר תיקיית התקנה")
        if chosen:
            self.install_dir_var.set(chosen)

    def create_options_page(self):
        title = ttk.Label(self.container, text="אפשרויות התקנה נוספות", style="Header.TLabel")
        title.pack(anchor="w", pady=(0, 6))

        sub = ttk.Label(self.container, text="בחר את הפעולות שברצונך לבצע במהלך ההתקנה:", style="SubHeader.TLabel")
        sub.pack(anchor="w", pady=(0, 20))

        opts_frame = tk.Frame(self.container, bg="#21262d", padx=16, pady=16)
        opts_frame.pack(fill="both", expand=True, pady=10)

        cb1 = ttk.Checkbutton(
            opts_frame,
            text="צור קיצור דרך במסך הבית (Desktop Shortcut)",
            variable=self.create_desktop_var,
            style="TCheckbutton"
        )
        cb1.pack(anchor="w", pady=8)

        cb2 = ttk.Checkbutton(
            opts_frame,
            text="צור קיצור דרך בתפריט התחלה (Start Menu Shortcut)",
            variable=self.create_start_var,
            style="TCheckbutton"
        )
        cb2.pack(anchor="w", pady=8)

        cb3 = ttk.Checkbutton(
            opts_frame,
            text="הוסף את SBpy למשתנה הסביבה PATH (זמין מכל טרמינל)",
            variable=self.add_path_var,
            style="TCheckbutton"
        )
        cb3.pack(anchor="w", pady=8)

    def create_install_page(self):
        title = ttk.Label(self.container, text="מתקין את SBpy...", style="Header.TLabel")
        title.pack(anchor="w", pady=(0, 6))

        self.status_label = ttk.Label(self.container, text="מתחיל בהתקנה...", style="Desc.TLabel")
        self.status_label.pack(anchor="w", pady=(0, 15))

        self.progress = ttk.Progressbar(self.container, style="TProgressbar", mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=10)

        self.log_text = tk.Text(
            self.container,
            height=10,
            bg="#0d1117",
            fg="#7EE787",
            font=("Consolas", 9),
            relief="solid",
            bd=1
        )
        self.log_text.pack(fill="both", expand=True, pady=10)

        # Run installation thread
        threading.Thread(target=self.run_installation, daemon=True).start()

    def run_installation(self):
        try:
            target_dir = Path(self.install_dir_var.get().strip())
            target_dir.mkdir(parents=True, exist_ok=True)

            def log(msg: str, progress_val: int):
                self.log_text.insert("end", f"> {msg}\n")
                self.log_text.see("end")
                self.status_label.config(text=msg)
                self.progress["value"] = progress_val
                self.update_idletasks()
                time.sleep(0.3)

            log("יוצר תיקיות יעד...", 10)
            assets_dir = target_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)

            # Copy sbpy.exe
            log("מעתיק קובץ בינארי ראשי sbpy.exe...", 30)
            src_exe = self.base_dir / "dist" / "sbpy.exe"
            if not src_exe.exists():
                src_exe = self.base_dir / "sbpy.exe"

            target_exe = target_dir / "sbpy.exe"
            if src_exe.exists():
                shutil.copy2(src_exe, target_exe)
            else:
                raise FileNotFoundError(f"Source executable not found: {src_exe}")

            # Copy assets
            log("מעתיק קובצי גרפיקה ואייקונים...", 50)
            src_assets = self.base_dir / "assets"
            if src_assets.exists():
                for f in src_assets.iterdir():
                    if f.is_file():
                        shutil.copy2(f, assets_dir / f.name)

            target_ico = assets_dir / "icon.ico"

            # Create uninstaller script
            log("מייצר קובץ הסרה...", 65)
            uninstall_bat = target_dir / "uninstall.bat"
            uninstall_content = f"""@echo off
chcp 65001 >nul
echo מסיר את SBpy מהמחשב...
powershell -NoProfile -Command "Remove-Item -Path '{str(target_dir)}' -Recurse -Force -ErrorAction SilentlyContinue"
powershell -NoProfile -Command "Remove-Item -Path '$env:USERPROFILE\\Desktop\\SBpy.lnk' -Force -ErrorAction SilentlyContinue"
powershell -NoProfile -Command "Remove-Item -Path '$env:USERPROFILE\\OneDrive - PCMASTER\\Desktop\\SBpy.lnk' -Force -ErrorAction SilentlyContinue"
echo SBpy הוסר בהצלחה.
pause
"""
            uninstall_bat.write_text(uninstall_content, encoding="utf-8")

            # Register in Windows Add/Remove
            register_uninstaller(target_dir, target_exe, target_ico)

            # Shortcuts
            if self.create_desktop_var.get():
                log("יוצר קיצור דרך במסך הבית...", 80)
                desktop = get_desktop_dir()
                ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{str(desktop / "SBpy.lnk")}')
$Shortcut.TargetPath = '{str(target_exe)}'
$Shortcut.WorkingDirectory = '{str(target_dir)}'
$Shortcut.IconLocation = '{str(target_ico if target_ico.exists() else target_exe)}'
$Shortcut.Description = 'SBpy - Python AI Debugger, Error Fixer & Optimizer'
$Shortcut.Save()
"""
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True)

            if self.create_start_var.get():
                log("יוצר קיצור דרך בתפריט התחלה...", 90)
                start_dir = get_start_menu_dir()
                ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{str(start_dir / "SBpy.lnk")}')
$Shortcut.TargetPath = '{str(target_exe)}'
$Shortcut.WorkingDirectory = '{str(target_dir)}'
$Shortcut.IconLocation = '{str(target_ico if target_ico.exists() else target_exe)}'
$Shortcut.Description = 'SBpy - Python AI Debugger & Optimizer'
$Shortcut.Save()
"""
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True)

            if self.add_path_var.get():
                log("מוסיף את SBpy למשתנה הסביבה PATH...", 95)
                add_to_user_path(str(target_dir))

            log("ההתקנה הושלמה בהצלחה!", 100)
            time.sleep(0.5)
            self.after(500, lambda: self.show_step(4))

        except Exception as e:
            self.log_text.insert("end", f"\n[ERROR] ההתקנה נכשלה: {e}\n")
            messagebox.showerror("שגיאה בהתקנה", f"אירעה שגיאה במהלך ההתקנה:\n{e}")
            self.btn_cancel.config(state="normal")

    def create_finish_page(self):
        title = ttk.Label(self.container, text="🎉 ההתקנה הושלמה בהצלחה!", style="Header.TLabel")
        title.pack(anchor="w", pady=(0, 6))

        sub = ttk.Label(self.container, text="SBpy הותקן בהצלחה ומוכן לפעולה במחשב שלך.", style="SubHeader.TLabel")
        sub.pack(anchor="w", pady=(0, 20))

        finish_frame = tk.Frame(self.container, bg="#21262d", padx=16, pady=16)
        finish_frame.pack(fill="both", expand=True, pady=10)

        target_dir = Path(self.install_dir_var.get().strip())
        info_txt = f"""מיקום ההתקנה: {target_dir}

כעת תוכל:
  • להפעיל את SBpy ישירות משולחן העבודה בלחיצה על האייקון.
  • לפתוח טרמינל ולהריץ את הפקודה: sbpy
  • להפעיל את ממשק הדשבורד הגרפי עם: sbpy ui
"""
        lbl = tk.Label(finish_frame, text=info_txt, bg="#21262d", fg="#C9D1D9", font=("Segoe UI", 10), justify="right", anchor="e")
        lbl.pack(fill="both", expand=True)

        cb_launch = ttk.Checkbutton(
            self.container,
            text="הפעל את SBpy כעת (Launch SBpy)",
            variable=self.launch_after_var,
            style="TCheckbutton"
        )
        cb_launch.pack(anchor="w", pady=10)


def main():
    app = SBpyInstallerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
