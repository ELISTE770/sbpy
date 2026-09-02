"""SBpy Windows Setup Installer GUI Wizard.
A modern, sleek, English-only graphical installer for SBpy built by Smart Binary.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Fix UTF-8 encoding
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "SBpy - Python AI Debugger & Optimizer")
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Smart Binary")
        winreg.SetValueEx(key, "URLInfoAbout", 0, winreg.REG_SZ, "https://smartbinary.org")
        winreg.SetValueEx(key, "HelpLink", 0, winreg.REG_SZ, "https://github.com/ELISTE770/sbpy")
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
    # Professional GitHub Dark Palette
    BG_DARK = "#0d1117"
    BG_CARD = "#161b22"
    BG_CARD_HOVER = "#1c2128"
    BORDER_COLOR = "#30363d"
    TEXT_PRIMARY = "#f0f6fc"
    TEXT_SECONDARY = "#8b949e"
    TEXT_MUTED = "#6e7681"
    ACCENT_BLUE = "#58a6ff"
    ACCENT_GREEN = "#238636"
    ACCENT_GREEN_HOVER = "#2ea043"

    def __init__(self):
        super().__init__()
        self.title("SBpy Setup Wizard")
        self.geometry("680x520")
        self.resizable(False, False)
        
        # Center on screen
        self.update_idletasks()
        w = 680
        h = 520
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
        self.configure(bg=self.BG_DARK)
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.style.configure(
            "TProgressbar",
            thickness=14,
            troughcolor=self.BG_CARD,
            background=self.ACCENT_BLUE,
            borderwidth=0
        )

    def create_layout(self):
        # Top banner frame
        self.banner_frame = tk.Frame(self, bg=self.BG_CARD, height=88, highlightthickness=1, highlightbackground=self.BORDER_COLOR)
        self.banner_frame.pack(fill="x", side="top")
        self.banner_frame.pack_propagate(False)

        # Header titles
        header_left = tk.Frame(self.banner_frame, bg=self.BG_CARD)
        header_left.pack(side="left", padx=24, pady=10)

        title_lbl = tk.Label(
            header_left,
            text="SBpy Setup Wizard",
            font=("Segoe UI", 14, "bold"),
            bg=self.BG_CARD,
            fg=self.TEXT_PRIMARY
        )
        title_lbl.pack(anchor="w")

        # Version & Smart Binary Signature
        sub_frame = tk.Frame(header_left, bg=self.BG_CARD)
        sub_frame.pack(anchor="w", pady=(2, 0))

        v_lbl = tk.Label(
            sub_frame,
            text="v0.1.0  •  ",
            font=("Segoe UI", 9),
            bg=self.BG_CARD,
            fg=self.TEXT_MUTED
        )
        v_lbl.pack(side="left")

        by_lbl = tk.Label(
            sub_frame,
            text="Built by Smart Binary",
            font=("Segoe UI", 9, "bold"),
            bg=self.BG_CARD,
            fg=self.ACCENT_BLUE,
            cursor="hand2"
        )
        by_lbl.pack(side="left")
        by_lbl.bind("<Button-1>", lambda e: webbrowser.open("https://smartbinary.org"))
        by_lbl.bind("<Enter>", lambda e: by_lbl.config(font=("Segoe UI", 9, "underline", "bold"), fg="#79b8ff"))
        by_lbl.bind("<Leave>", lambda e: by_lbl.config(font=("Segoe UI", 9, "bold"), fg=self.ACCENT_BLUE))

        # GitHub Repo Link
        gh_frame = tk.Frame(self.banner_frame, bg=self.BG_CARD)
        gh_frame.pack(side="right", padx=24, pady=10)

        gh_btn = tk.Label(
            gh_frame,
            text="GitHub Repository ↗",
            font=("Segoe UI", 9),
            bg=self.BG_CARD,
            fg=self.TEXT_SECONDARY,
            cursor="hand2",
            padx=8,
            pady=4,
            relief="solid",
            bd=1
        )
        gh_btn.config(highlightbackground=self.BORDER_COLOR)
        gh_btn.pack(side="right")
        gh_btn.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/ELISTE770/sbpy"))
        gh_btn.bind("<Enter>", lambda e: gh_btn.config(fg=self.TEXT_PRIMARY, bg="#21262d"))
        gh_btn.bind("<Leave>", lambda e: gh_btn.config(fg=self.TEXT_SECONDARY, bg=self.BG_CARD))

        # Main content area
        self.container = tk.Frame(self, bg=self.BG_DARK, padx=28, pady=24)
        self.container.pack(fill="both", expand=True)

        # Bottom navigation bar
        self.bottom_bar = tk.Frame(self, bg=self.BG_CARD, height=60, padx=24, pady=12, highlightthickness=1, highlightbackground=self.BORDER_COLOR)
        self.bottom_bar.pack(fill="x", side="bottom")
        self.bottom_bar.pack_propagate(False)

        # Bottom footer links
        footer_links = tk.Frame(self.bottom_bar, bg=self.BG_CARD)
        footer_links.pack(side="left")

        site_link = tk.Label(
            footer_links,
            text="smartbinary.org",
            font=("Segoe UI", 9),
            bg=self.BG_CARD,
            fg=self.TEXT_MUTED,
            cursor="hand2"
        )
        site_link.pack(side="left")
        site_link.bind("<Button-1>", lambda e: webbrowser.open("https://smartbinary.org"))
        site_link.bind("<Enter>", lambda e: site_link.config(fg=self.ACCENT_BLUE, font=("Segoe UI", 9, "underline")))
        site_link.bind("<Leave>", lambda e: site_link.config(fg=self.TEXT_MUTED, font=("Segoe UI", 9)))

        sep_lbl = tk.Label(footer_links, text="  |  ", bg=self.BG_CARD, fg=self.TEXT_MUTED, font=("Segoe UI", 9))
        sep_lbl.pack(side="left")

        gh_link = tk.Label(
            footer_links,
            text="ELISTE770/sbpy",
            font=("Segoe UI", 9),
            bg=self.BG_CARD,
            fg=self.TEXT_MUTED,
            cursor="hand2"
        )
        gh_link.pack(side="left")
        gh_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/ELISTE770/sbpy"))
        gh_link.bind("<Enter>", lambda e: gh_link.config(fg=self.ACCENT_BLUE, font=("Segoe UI", 9, "underline")))
        gh_link.bind("<Leave>", lambda e: gh_link.config(fg=self.TEXT_MUTED, font=("Segoe UI", 9)))

        # Action Buttons
        self.btn_next = tk.Button(
            self.bottom_bar,
            text="Next >",
            font=("Segoe UI", 10, "bold"),
            bg=self.ACCENT_GREEN,
            fg="#FFFFFF",
            activebackground=self.ACCENT_GREEN_HOVER,
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            padx=18,
            pady=5,
            cursor="hand2",
            command=self.on_next
        )
        self.btn_next.pack(side="right", padx=(8, 0))

        self.btn_back = tk.Button(
            self.bottom_bar,
            text="< Back",
            font=("Segoe UI", 10),
            bg="#21262d",
            fg=self.TEXT_PRIMARY,
            activebackground="#30363d",
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self.on_back
        )
        self.btn_back.pack(side="right", padx=(8, 0))

        self.btn_cancel = tk.Button(
            self.bottom_bar,
            text="Cancel",
            font=("Segoe UI", 10),
            bg="#21262d",
            fg=self.TEXT_SECONDARY,
            activebackground="#30363d",
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self.on_cancel
        )
        self.btn_cancel.pack(side="right")

    def show_step(self, step_idx: int):
        self.current_step = step_idx
        for widget in self.container.winfo_children():
            widget.destroy()
        
        self.steps[step_idx]()

        # Button states
        if step_idx == 0:
            self.btn_back.config(state="disabled", bg="#161b22", fg=self.TEXT_MUTED, cursor="arrow")
            self.btn_next.config(text="Next >", state="normal", bg=self.ACCENT_GREEN, fg="#FFFFFF", cursor="hand2")
            self.btn_cancel.config(state="normal", bg="#21262d", fg=self.TEXT_SECONDARY, cursor="hand2")
        elif step_idx == 1:
            self.btn_back.config(state="normal", bg="#21262d", fg=self.TEXT_PRIMARY, cursor="hand2")
            self.btn_next.config(text="Next >", state="normal", bg=self.ACCENT_GREEN, fg="#FFFFFF", cursor="hand2")
            self.btn_cancel.config(state="normal", bg="#21262d", fg=self.TEXT_SECONDARY, cursor="hand2")
        elif step_idx == 2:
            self.btn_back.config(state="normal", bg="#21262d", fg=self.TEXT_PRIMARY, cursor="hand2")
            self.btn_next.config(text="Install", state="normal", bg=self.ACCENT_GREEN, fg="#FFFFFF", cursor="hand2")
            self.btn_cancel.config(state="normal", bg="#21262d", fg=self.TEXT_SECONDARY, cursor="hand2")
        elif step_idx == 3:
            self.btn_back.config(state="disabled", bg="#161b22", fg=self.TEXT_MUTED, cursor="arrow")
            self.btn_next.config(state="disabled", bg="#161b22", fg=self.TEXT_MUTED, cursor="arrow")
            self.btn_cancel.config(state="disabled", bg="#161b22", fg=self.TEXT_MUTED, cursor="arrow")
        elif step_idx == 4:
            self.btn_back.config(state="disabled", bg="#161b22", fg=self.TEXT_MUTED, cursor="arrow")
            self.btn_cancel.pack_forget()
            self.btn_next.config(text="Finish", state="normal", bg=self.ACCENT_GREEN, fg="#FFFFFF", cursor="hand2", command=self.on_finish)

    def on_next(self):
        if self.current_step == 1:
            dest = self.install_dir_var.get().strip()
            if not dest:
                messagebox.showerror("Error", "Please select a valid installation directory.")
                return
        if self.current_step < len(self.steps) - 1:
            self.show_step(self.current_step + 1)

    def on_back(self):
        if self.current_step > 0:
            self.show_step(self.current_step - 1)

    def on_cancel(self):
        if messagebox.askyesno("Cancel Setup", "Are you sure you want to exit SBpy Setup?"):
            self.destroy()

    def on_finish(self):
        if self.launch_after_var.get():
            install_dir = Path(self.install_dir_var.get().strip())
            exe_path = install_dir / "sbpy.exe"
            if exe_path.exists():
                try:
                    if sys.platform == "win32":
                        subprocess.Popen(f'start "" "{str(exe_path)}"', cwd=str(install_dir), shell=True)
                    else:
                        subprocess.Popen([str(exe_path)], cwd=str(install_dir))
                except Exception as e:
                    print(f"Error launching: {e}", file=sys.stderr)
        self.destroy()

    # --- Custom Sleek Checkbox Widget (Never glitches to white background) ---
    def create_checkbox(self, parent, text: str, variable: tk.BooleanVar, subtext: str = ""):
        frame = tk.Frame(parent, bg=self.BG_CARD, cursor="hand2", pady=4)
        frame.pack(fill="x", pady=4)

        cb = tk.Checkbutton(
            frame,
            variable=variable,
            bg=self.BG_CARD,
            activebackground=self.BG_CARD,
            selectcolor="#0d1117",
            fg=self.TEXT_PRIMARY,
            activeforeground=self.TEXT_PRIMARY,
            highlightthickness=0,
            bd=0,
            cursor="hand2"
        )
        cb.pack(side="left", padx=(0, 10))

        text_container = tk.Frame(frame, bg=self.BG_CARD, cursor="hand2")
        text_container.pack(side="left", fill="x", expand=True)

        lbl = tk.Label(
            text_container,
            text=text,
            font=("Segoe UI", 10, "bold"),
            bg=self.BG_CARD,
            fg=self.TEXT_PRIMARY,
            cursor="hand2",
            anchor="w"
        )
        lbl.pack(anchor="w")

        if subtext:
            sub_lbl = tk.Label(
                text_container,
                text=subtext,
                font=("Segoe UI", 9),
                bg=self.BG_CARD,
                fg=self.TEXT_SECONDARY,
                cursor="hand2",
                anchor="w"
            )
            sub_lbl.pack(anchor="w")

        def toggle(e=None):
            variable.set(not variable.get())

        frame.bind("<Button-1>", toggle)
        lbl.bind("<Button-1>", toggle)
        text_container.bind("<Button-1>", toggle)
        if subtext:
            sub_lbl.bind("<Button-1>", toggle)

        return frame

    # --- Step 1: Welcome ---
    def create_welcome_page(self):
        h1 = tk.Label(
            self.container,
            text="Welcome to SBpy Setup",
            font=("Segoe UI", 16, "bold"),
            bg=self.BG_DARK,
            fg=self.TEXT_PRIMARY
        )
        h1.pack(anchor="w", pady=(0, 4))

        sub = tk.Label(
            self.container,
            text="Local-first Python error fixing & AI diagnostics, with Gemini as the last resort.",
            font=("Segoe UI", 10),
            bg=self.BG_DARK,
            fg=self.TEXT_SECONDARY
        )
        sub.pack(anchor="w", pady=(0, 16))

        card = tk.Frame(self.container, bg=self.BG_CARD, padx=20, pady=18, highlightthickness=1, highlightbackground=self.BORDER_COLOR)
        card.pack(fill="both", expand=True)

        features = [
            ("⚡ Local-First Engine", "Instant zero-dependency AST static checks and automatic fixes."),
            ("🤖 Smart AI Escalation", "Connects to Google Gemini API seamlessly when complex reasoning is needed."),
            ("🌐 Interactive Web Dashboard", "Live visual code inspector, AI pair programmer, and dependency graphs."),
            ("💻 Professional CLI & REPL", "Powerful developer terminal suite with real-time crash diagnostics.")
        ]

        for title, desc in features:
            f_row = tk.Frame(card, bg=self.BG_CARD)
            f_row.pack(fill="x", pady=6)

            t_lbl = tk.Label(f_row, text=title, font=("Segoe UI", 10, "bold"), bg=self.BG_CARD, fg=self.TEXT_PRIMARY)
            t_lbl.pack(anchor="w")

            d_lbl = tk.Label(f_row, text=desc, font=("Segoe UI", 9), bg=self.BG_CARD, fg=self.TEXT_SECONDARY)
            d_lbl.pack(anchor="w")

    # --- Step 2: Choose Destination ---
    def create_directory_page(self):
        h1 = tk.Label(
            self.container,
            text="Select Installation Location",
            font=("Segoe UI", 16, "bold"),
            bg=self.BG_DARK,
            fg=self.TEXT_PRIMARY
        )
        h1.pack(anchor="w", pady=(0, 4))

        sub = tk.Label(
            self.container,
            text="Setup will install SBpy into the following folder. Click Browse to select a different folder.",
            font=("Segoe UI", 10),
            bg=self.BG_DARK,
            fg=self.TEXT_SECONDARY
        )
        sub.pack(anchor="w", pady=(0, 16))

        card = tk.Frame(self.container, bg=self.BG_CARD, padx=20, pady=20, highlightthickness=1, highlightbackground=self.BORDER_COLOR)
        card.pack(fill="x", pady=(0, 16))

        tk.Label(card, text="Destination Folder:", font=("Segoe UI", 9, "bold"), bg=self.BG_CARD, fg=self.TEXT_PRIMARY).pack(anchor="w", pady=(0, 8))

        row = tk.Frame(card, bg=self.BG_CARD)
        row.pack(fill="x")

        entry = tk.Entry(
            row,
            textvariable=self.install_dir_var,
            font=("Segoe UI", 10),
            bg="#0d1117",
            fg=self.TEXT_PRIMARY,
            insertbackground=self.TEXT_PRIMARY,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=self.BORDER_COLOR
        )
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 10))

        btn_browse = tk.Button(
            row,
            text="Browse...",
            font=("Segoe UI", 9),
            bg="#21262d",
            fg=self.TEXT_PRIMARY,
            activebackground="#30363d",
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self.browse_dir
        )
        btn_browse.pack(side="right")

        info_card = tk.Frame(self.container, bg=self.BG_CARD, padx=16, pady=12, highlightthickness=1, highlightbackground=self.BORDER_COLOR)
        info_card.pack(fill="x")

        tk.Label(
            info_card,
            text="Space required: ~25.0 MB\nSpace available on drive: Adequate",
            font=("Segoe UI", 9),
            bg=self.BG_CARD,
            fg=self.TEXT_MUTED,
            justify="left"
        ).pack(anchor="w")

    def browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.install_dir_var.get(), title="Select Installation Folder")
        if chosen:
            self.install_dir_var.set(chosen)

    # --- Step 3: Options ---
    def create_options_page(self):
        h1 = tk.Label(
            self.container,
            text="Select Additional Tasks",
            font=("Segoe UI", 16, "bold"),
            bg=self.BG_DARK,
            fg=self.TEXT_PRIMARY
        )
        h1.pack(anchor="w", pady=(0, 4))

        sub = tk.Label(
            self.container,
            text="Select the additional tasks you would like Setup to perform while installing SBpy:",
            font=("Segoe UI", 10),
            bg=self.BG_DARK,
            fg=self.TEXT_SECONDARY
        )
        sub.pack(anchor="w", pady=(0, 16))

        card = tk.Frame(self.container, bg=self.BG_CARD, padx=20, pady=16, highlightthickness=1, highlightbackground=self.BORDER_COLOR)
        card.pack(fill="both", expand=True)

        self.create_checkbox(
            card,
            "Create a Desktop Shortcut",
            self.create_desktop_var,
            "Places an SBpy launch icon directly onto your desktop."
        )

        self.create_checkbox(
            card,
            "Create a Start Menu Shortcut",
            self.create_start_var,
            "Adds SBpy to the Windows Start Menu applications list."
        )

        self.create_checkbox(
            card,
            "Add SBpy to system PATH (Recommended)",
            self.add_path_var,
            "Allows running `sbpy` directly from any terminal, PowerShell, or command prompt."
        )

    # --- Step 4: Installing Progress ---
    def create_install_page(self):
        h1 = tk.Label(
            self.container,
            text="Installing SBpy",
            font=("Segoe UI", 16, "bold"),
            bg=self.BG_DARK,
            fg=self.TEXT_PRIMARY
        )
        h1.pack(anchor="w", pady=(0, 4))

        self.status_label = tk.Label(
            self.container,
            text="Preparing installation...",
            font=("Segoe UI", 10),
            bg=self.BG_DARK,
            fg=self.TEXT_SECONDARY
        )
        self.status_label.pack(anchor="w", pady=(0, 12))

        self.progress = ttk.Progressbar(self.container, style="TProgressbar", mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 14))

        card = tk.Frame(self.container, bg="#0d1117", highlightthickness=1, highlightbackground=self.BORDER_COLOR)
        card.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            card,
            bg="#0d1117",
            fg="#7ee787",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
            padx=12,
            pady=10
        )
        self.log_text.pack(fill="both", expand=True)

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

            log("Creating destination directories...", 10)
            assets_dir = target_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)

            # Copy sbpy.exe
            log("Extracting main executable: sbpy.exe...", 30)
            src_exe = self.base_dir / "dist" / "sbpy.exe"
            if not src_exe.exists():
                src_exe = self.base_dir / "sbpy.exe"

            target_exe = target_dir / "sbpy.exe"
            if src_exe.exists():
                shutil.copy2(src_exe, target_exe)
            else:
                raise FileNotFoundError(f"Source executable not found: {src_exe}")

            # Copy assets
            log("Installing graphical assets and icons...", 50)
            src_assets = self.base_dir / "assets"
            if src_assets.exists():
                for f in src_assets.iterdir():
                    if f.is_file():
                        shutil.copy2(f, assets_dir / f.name)

            target_ico = assets_dir / "icon.ico"

            # Create uninstaller
            log("Generating uninstaller...", 65)
            uninstall_bat = target_dir / "uninstall.bat"
            uninstall_content = f"""@echo off
chcp 65001 >nul
echo Uninstalling SBpy...
powershell -NoProfile -Command "Remove-Item -Path '{str(target_dir)}' -Recurse -Force -ErrorAction SilentlyContinue"
powershell -NoProfile -Command "Remove-Item -Path '$env:USERPROFILE\\Desktop\\SBpy.lnk' -Force -ErrorAction SilentlyContinue"
powershell -NoProfile -Command "Remove-Item -Path '$env:USERPROFILE\\OneDrive - PCMASTER\\Desktop\\SBpy.lnk' -Force -ErrorAction SilentlyContinue"
powershell -NoProfile -Command "Remove-Item -Path '$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\SBpy.lnk' -Force -ErrorAction SilentlyContinue"
powershell -NoProfile -Command "Remove-Item -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SBpy' -Recurse -Force -ErrorAction SilentlyContinue"
echo SBpy was uninstalled successfully.
pause
"""
            uninstall_bat.write_text(uninstall_content, encoding="utf-8")

            # Register in Windows Add/Remove
            register_uninstaller(target_dir, target_exe, target_ico)

            # Shortcuts
            if self.create_desktop_var.get():
                log("Creating Desktop shortcut...", 80)
                desktop = get_desktop_dir()
                ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{str(desktop / "SBpy.lnk")}')
$Shortcut.TargetPath = '{str(target_exe)}'
$Shortcut.WorkingDirectory = '{str(target_dir)}'
$Shortcut.IconLocation = '{str(target_ico if target_ico.exists() else target_exe)}'
$Shortcut.Description = 'SBpy - Python AI Debugger & Optimizer'
$Shortcut.Save()
"""
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True)

            if self.create_start_var.get():
                log("Creating Start Menu shortcut...", 90)
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
                log("Configuring User PATH environment variable...", 95)
                add_to_user_path(str(target_dir))

            log("Installation completed successfully!", 100)
            time.sleep(0.5)
            self.after(500, lambda: self.show_step(4))

        except Exception as e:
            self.log_text.insert("end", f"\n[ERROR] Installation failed: {e}\n")
            messagebox.showerror("Installation Error", f"An error occurred during installation:\n{e}")
            self.btn_cancel.config(state="normal")

    # --- Step 5: Finished ---
    def create_finish_page(self):
        h1 = tk.Label(
            self.container,
            text="Completing SBpy Setup",
            font=("Segoe UI", 16, "bold"),
            bg=self.BG_DARK,
            fg=self.TEXT_PRIMARY
        )
        h1.pack(anchor="w", pady=(0, 4))

        sub = tk.Label(
            self.container,
            text="SBpy has been successfully installed on your computer.",
            font=("Segoe UI", 10),
            bg=self.BG_DARK,
            fg=self.TEXT_SECONDARY
        )
        sub.pack(anchor="w", pady=(0, 16))

        card = tk.Frame(self.container, bg=self.BG_CARD, padx=20, pady=18, highlightthickness=1, highlightbackground=self.BORDER_COLOR)
        card.pack(fill="both", expand=True)

        target_dir = Path(self.install_dir_var.get().strip())
        info_txt = f"""Installation Folder:
{target_dir}

Quick Start Options:
  • Launch directly via the Desktop shortcut or Start Menu.
  • Open any terminal and run: sbpy
  • Open the graphical web dashboard with: sbpy ui
"""
        lbl = tk.Label(
            card,
            text=info_txt,
            font=("Segoe UI", 10),
            bg=self.BG_CARD,
            fg=self.TEXT_PRIMARY,
            justify="left",
            anchor="w"
        )
        lbl.pack(fill="both", expand=True)

        self.create_checkbox(
            self.container,
            "Launch SBpy now",
            self.launch_after_var
        )


def main():
    app = SBpyInstallerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
