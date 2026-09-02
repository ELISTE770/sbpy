"""Terminal and Shell Aliases for accidental foreign keyboard typing.

Installs דנפט and טפנד wrappers in Windows PATH, Python Scripts directories,
and PowerShell profiles so typing דנפט in CMD or PowerShell instantly launches SBpy.
"""

from __future__ import annotations

import sys
import sysconfig
from pathlib import Path

_CMD_CONTENT = """@echo off
py -m sbpy %*
"""

_PS1_CONTENT = """& py -m sbpy @args
"""

_SH_CONTENT = """#!/usr/bin/env sh
py -m sbpy "$@"
"""

ALIASES = ["דנפט", "טפנד"]


def get_target_script_dirs() -> list[Path]:
    """Finds all candidate directories in PATH / Python Scripts where CLI wrappers can be placed."""
    dirs: list[Path] = []

    try:
        p = Path(sysconfig.get_path("scripts"))
        if p.exists() and p not in dirs:
            dirs.append(p)
    except Exception:  # sbpy: ignore=silent-except
        pass

    try:
        p = Path(sysconfig.get_path("scripts", "nt_user"))
        if p.exists() and p not in dirs:
            dirs.append(p)
    except Exception:  # sbpy: ignore=silent-except
        pass

    p = Path(sys.prefix) / "Scripts"
    if p.exists() and p not in dirs:
        dirs.append(p)

    cwd = Path.cwd()
    if cwd not in dirs:
        dirs.append(cwd)

    return dirs


def get_powershell_profile_paths() -> list[Path]:
    """Returns potential PowerShell profile paths across Windows PowerShell and PowerShell 7."""
    profiles: list[Path] = []
    user_home = Path.home()
    documents = user_home / "Documents"
    onedrive_docs = user_home / "OneDrive" / "Documents"

    for doc_dir in (documents, onedrive_docs):
        for ps_dir in ("WindowsPowerShell", "PowerShell"):
            profile_file = doc_dir / ps_dir / "Microsoft.PowerShell_profile.ps1"
            profiles.append(profile_file)
            profile_all = doc_dir / ps_dir / "profile.ps1"
            profiles.append(profile_all)

    return profiles


def install_terminal_aliases() -> list[str]:
    """Writes wrapper scripts (cmd, bat, ps1, sh) and configures PowerShell profiles."""
    created: list[str] = []
    target_dirs = get_target_script_dirs()

    # 1. Write wrapper scripts to Scripts / PATH directories
    for target_dir in target_dirs:
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception:  # sbpy: ignore=silent-except
            continue

        for alias in ALIASES:
            cmd_file = target_dir / f"{alias}.cmd"
            try:
                cmd_file.write_text(_CMD_CONTENT, encoding="utf-8")
                created.append(str(cmd_file))
            except Exception:  # sbpy: ignore=silent-except
                pass

            bat_file = target_dir / f"{alias}.bat"
            try:
                bat_file.write_text(_CMD_CONTENT, encoding="utf-8")
                created.append(str(bat_file))
            except Exception:  # sbpy: ignore=silent-except
                pass

            ps1_file = target_dir / f"{alias}.ps1"
            try:
                ps1_file.write_text(_PS1_CONTENT, encoding="utf-8")
                created.append(str(ps1_file))
            except Exception:  # sbpy: ignore=silent-except
                pass

            sh_file = target_dir / alias
            try:
                sh_file.write_text(_SH_CONTENT, encoding="utf-8")
                try:
                    sh_file.chmod(0o755)
                except Exception:  # sbpy: ignore=silent-except
                    pass
                created.append(str(sh_file))
            except Exception:  # sbpy: ignore=silent-except
                pass

    # 2. Add aliases to PowerShell profiles
    ps_snippet = "\n# SBpy Hebrew keyboard aliases\nfunction דנפט { py -m sbpy @args }\nfunction טפנד { py -m sbpy @args }\n"
    for profile_path in get_powershell_profile_paths():
        try:
            if profile_path.parent.exists():
                existing = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
                if "function דנפט" not in existing:
                    profile_path.write_text(existing + ps_snippet, encoding="utf-8")
                    created.append(str(profile_path))
        except Exception:  # sbpy: ignore=silent-except
            pass

    return created
