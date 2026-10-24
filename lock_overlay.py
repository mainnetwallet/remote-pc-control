"""
PIN lock screen for this PC.

Runs on its own, independent of the Remote PC Control server (backend/app/main.py). Every
second it checks lock_state.json (via app.pinlock) and shows or hides a full-screen PIN
screen to match it. Because it reads that file directly instead of asking the server, it
works even if the server is not running, and it works again the moment Windows signs you
back in after a restart -- if the PC was locked when it last shut down, it is still locked.

The PC-side lock only ever changes because:
  - someone enters the correct PIN here, or
  - the phone app calls POST /api/v1/lock/unlock (already protected by the app's own
    access token), or
  - the phone app calls POST /api/v1/lock/lock to lock it.
Nothing in this file locks or auto-locks on a timer.

Install to start automatically at sign-in:  .\\scripts\\install-lock-overlay.ps1
Run it directly to test:                    .\\.venv\\Scripts\\pythonw.exe lock_overlay.py

Limits, stated plainly: this is a normal desktop window, not a Windows login screen. It
blocks the keyboard shortcuts listed below while it is open, but Ctrl+Alt+Delete cannot be
intercepted by any ordinary application -- Windows sends that combination straight to the
secure desktop by design, and pressing it on this screen still opens Windows' own
Task Manager / lock / sign-out menu. Someone who gets there can still switch user or sign
out, same as on any Windows PC.
"""
import platform
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from app import pinlock  # noqa: E402

POLL_MS = 1000
IS_WINDOWS = platform.system() == "Windows"

# ---- best-effort low-level keyboard hook (Windows only) -----------------------------------
# Swallows Win, Alt+Tab, Alt+Esc, Ctrl+Esc while locked so the desktop/taskbar underneath
# can't be reached. See the module docstring for what this cannot block (Ctrl+Alt+Delete).
_hook_active = threading.Event()

def _run_keyboard_hook():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    WH_KEYBOARD_LL = 13
    WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
    VK_LWIN, VK_RWIN, VK_TAB, VK_ESCAPE = 0x5B, 0x5C, 0x09, 0x1B
    VK_LMENU, VK_RMENU, VK_LCONTROL, VK_RCONTROL = 0xA4, 0xA5, 0xA2, 0xA3

    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    held = {"alt": False, "ctrl": False}

    def proc(nCode, wParam, lParam):
        if nCode == 0 and _hook_active.is_set():
            vk = ctypes.cast(lParam, ctypes.POINTER(ctypes.c_long))[0] & 0xFFFFFFFF
            down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
            if vk in (VK_LMENU, VK_RMENU): held["alt"] = down
            if vk in (VK_LCONTROL, VK_RCONTROL): held["ctrl"] = down
            block = (
                vk in (VK_LWIN, VK_RWIN)
                or (down and vk == VK_TAB and held["alt"])
                or (down and vk == VK_ESCAPE and (held["alt"] or held["ctrl"]))
            )
            if block:
                return 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    keep_alive = HOOKPROC(proc)   # must outlive the hook
    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, keep_alive, None, 0)
    if not hook:
        return
    msg = wintypes.MSG()
    while _hook_active.is_set():
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)
        time.sleep(0.02)
    user32.UnhookWindowsHookEx(hook)


def _start_hook():
    if not IS_WINDOWS or _hook_active.is_set():
        return
    _hook_active.set()
    threading.Thread(target=_run_keyboard_hook, daemon=True).start()


def _stop_hook():
    _hook_active.clear()


# ---- UI -------------------------------------------------------------------------------------
class LockScreen:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.win: tk.Toplevel | None = None
        self.entry_var = tk.StringVar()
        self.msg_var = tk.StringVar()
        self._poll()

    def _poll(self):
        s = pinlock.status()
        if s["locked"] and self.win is None:
            self._show()
        elif not s["locked"] and self.win is not None:
            self._hide()
        elif self.win is not None:
            self.win.attributes("-topmost", True)
            self.win.lift()
            self.win.focus_force()
        self.root.after(POLL_MS, self._poll)

    def _show(self):
        self.entry_var.set("")
        self.msg_var.set("")
        w = tk.Toplevel(self.root)
        self.win = w
        w.overrideredirect(True)   # no title bar / border; also means no close button
        w.attributes("-topmost", True)
        try:
            w.attributes("-fullscreen", True)
        except tk.TclError:
            w.geometry(f"{w.winfo_screenwidth()}x{w.winfo_screenheight()}+0+0")
        w.configure(bg="#0b0f1a")
        w.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = tk.Frame(w, bg="#0b0f1a")
        frame.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(frame, text="\U0001F512  PC Locked", font=("Segoe UI", 28, "bold"),
                  fg="#e8ecf6", bg="#0b0f1a").pack(pady=(0, 18))
        tk.Label(frame, text="Enter PIN to unlock", font=("Segoe UI", 13),
                  fg="#9aa4bd", bg="#0b0f1a").pack(pady=(0, 14))

        entry = tk.Entry(frame, textvariable=self.entry_var, show="\u2022", justify="center",
                          font=("Segoe UI", 22), width=10, bg="#161c2c", fg="#e8ecf6",
                          insertbackground="#e8ecf6", relief="flat", bd=10)
        entry.pack(pady=(0, 10))
        entry.bind("<Return>", lambda e: self._try_unlock())
        entry.focus_set()

        tk.Label(frame, textvariable=self.msg_var, font=("Segoe UI", 11), fg="#ff6b6b",
                  bg="#0b0f1a").pack(pady=(0, 10))
        tk.Button(frame, text="Unlock", font=("Segoe UI", 12, "bold"), command=self._try_unlock,
                  bg="#4f7cff", fg="white", activebackground="#3d63d9", relief="flat",
                  padx=24, pady=6, cursor="hand2").pack()

        # Keep this window on top and keyboard-focused no matter what the user tries.
        w.bind("<FocusOut>", lambda e: w.after(50, lambda: (w.lift(), w.focus_force())))
        _start_hook()

    def _hide(self):
        _stop_hook()
        if self.win is not None:
            self.win.destroy()
            self.win = None

    def _try_unlock(self):
        ok, message = pinlock.unlock_with_pin(self.entry_var.get())
        self.entry_var.set("")
        if ok:
            self._hide()
        else:
            self.msg_var.set(message)


def main():
    root = tk.Tk()
    root.withdraw()   # no visible window of its own; LockScreen creates/destroys the real one
    LockScreen(root)
    root.mainloop()


if __name__ == "__main__":
    main()
