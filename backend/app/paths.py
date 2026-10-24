import os, sys
from pathlib import Path

APP_NAME = "RemotePCControl"


def frozen() -> bool:
    """True inside the packaged RemotePCControl.exe (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    """Folder that holds .env and the agent log.
    Run from source: the current folder, exactly as before.
    Packaged exe: the exe's own folder if it already has a .env (older installs), otherwise
    %LOCALAPPDATA%\\RemotePCControl. That folder is private to the user; Program Files is readable by every PC user."""
    if not frozen():
        return Path.cwd()
    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir / ".env").exists():
        return exe_dir
    return Path(os.getenv("LOCALAPPDATA") or exe_dir) / APP_NAME
