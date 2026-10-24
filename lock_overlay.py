"""
PIN lock screen for this PC.

Runs on its own, independent of the Remote PC Control server (backend/app/main.py). Every
second it reads the canonical lock_state.json (via app.pinlock) and shows or hides a
full-screen PIN screen to match it. Because it reads that file directly instead of asking the
server, it works even if the server is not running, and it works again the moment Windows
signs you back in after a restart -- if the PC was locked when it last shut down, it is still
locked.

The PC-side lock only ever changes because:
  - someone enters the correct PIN here, or
  - the phone app calls POST /api/v1/lock/unlock (protected by the app's own access token), or
  - the phone app calls POST /api/v1/lock/lock to lock it.
Nothing in this file locks or auto-locks on a timer.

Install to start automatically at sign-in:  .\\scripts\\install-lock-overlay.ps1
Run it directly to test:                    .\\.venv\\Scripts\\pythonw.exe lock_overlay.py
Diagnostics are written to lock_overlay.log (see log_path()). Secrets are never logged.

Only one overlay runs per Windows session (named mutex; a second launch logs and exits), so the
Scheduled Task and a manual launch cannot fight over keyboard focus.

Limits, stated plainly: this is a normal desktop window, not a Windows login screen. While it
is open it blocks the Windows key, Alt+Tab, Alt+Esc and Ctrl+Esc / Ctrl+Shift+Esc, but
Ctrl+Alt+Delete cannot be intercepted by any ordinary application -- Windows sends that
combination straight to the secure desktop by design.
"""
from __future__ import annotations

import atexit
import logging
import logging.handlers
import os
import platform
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from app import pinlock  # noqa: E402

POLL_MS = 1000
FOCUS_RETRY_MS = (0, 120, 400, 1000)   # bounded retries right after the window appears
MIN_REFOCUS_INTERVAL_S = 0.5           # never re-grab focus more often than this
IS_WINDOWS = platform.system() == "Windows"
MUTEX_NAME = "Local\\RemotePCControlLockOverlay"   # Local\ = one overlay per Windows session

log = logging.getLogger("remote_pc_control.overlay")


# ---- logging -------------------------------------------------------------------------------
def log_path() -> Path:
    base = os.getenv("LOCALAPPDATA")
    d = Path(base) / "RemotePCControl" if base else Path(__file__).resolve().parent
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = Path(__file__).resolve().parent
    return d / "lock_overlay.log"


def setup_logging() -> None:
    root = logging.getLogger()
    if any(getattr(h, "_rpc_overlay", False) for h in root.handlers):
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    try:
        h: logging.Handler = logging.handlers.RotatingFileHandler(
            log_path(), maxBytes=512_000, backupCount=2, encoding="utf-8")
    except OSError:
        h = logging.StreamHandler()
    h.setFormatter(fmt)
    h._rpc_overlay = True  # type: ignore[attr-defined]
    root.addHandler(h)
    if sys.stderr is not None:     # pythonw.exe has no stderr
        s = logging.StreamHandler()
        s.setFormatter(fmt)
        s._rpc_overlay = True  # type: ignore[attr-defined]
        root.addHandler(s)


# ---- single instance -----------------------------------------------------------------------
class SingleInstance:
    """Windows: named mutex (kernel releases it when the process dies, so a crash or forced
    kill never leaves a stale marker). Elsewhere (dev/tests): an flock'ed file, same property."""

    def __init__(self, name: str = MUTEX_NAME, lock_file: Path | None = None):
        self.name = name
        self.lock_file = lock_file
        self._handle = None
        self._fh = None

    def acquire(self) -> bool:
        if IS_WINDOWS:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            k32.CreateMutexW.restype = wintypes.HANDLE
            handle = k32.CreateMutexW(None, True, self.name)
            err = ctypes.get_last_error()
            if not handle:
                log.error("CreateMutexW failed (error %s); continuing without single-instance guard", err)
                return True
            if err == 183:    # ERROR_ALREADY_EXISTS
                k32.CloseHandle.argtypes = [wintypes.HANDLE]
                k32.CloseHandle(handle)
                return False
            self._handle = handle
            return True
        import fcntl
        path = self.lock_file or Path(os.getenv("TMPDIR", "/tmp")) / "remote-pc-control-overlay.lock"
        fh = open(path, "a+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self._fh = fh
        return True

    def release(self) -> None:
        if self._handle:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32")
            k32.ReleaseMutex.argtypes = [wintypes.HANDLE]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            k32.ReleaseMutex(self._handle)
            k32.CloseHandle(self._handle)
            self._handle = None
        if self._fh:
            self._fh.close()      # closing drops the flock
            self._fh = None


# ---- keyboard hook policy (pure, testable anywhere) ----------------------------------------
VK_TAB, VK_ESCAPE = 0x09, 0x1B
VK_LWIN, VK_RWIN = 0x5B, 0x5C


def should_block_key(vk: int, down: bool, alt: bool, ctrl: bool) -> bool:
    """True only for the explicitly intended shortcuts. Digits (0x30-0x39), numpad digits
    (0x60-0x69), Backspace (0x08), Enter (0x0D), arrows, Delete etc. are NEVER blocked."""
    if vk in (VK_LWIN, VK_RWIN):
        return True                                   # block both press and release
    if down and vk == VK_TAB and alt:
        return True                                   # Alt+Tab
    if down and vk == VK_ESCAPE and (alt or ctrl):
        return True                                   # Alt+Esc, Ctrl+Esc, Ctrl+Shift+Esc
    return False


class KeyboardHook:
    """Low-level keyboard hook on its own thread with its own message loop.
    start()/stop() are idempotent; the hook is always removed in a finally block, on stop(),
    and at interpreter exit. (If the process is killed outright Windows removes the hook with
    the process.) Windows only; elsewhere start() is a no-op."""

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self.installed = False
        atexit.register(self.stop)

    def start(self) -> bool:
        if not IS_WINDOWS or (self._thread and self._thread.is_alive()):
            return self.installed
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="lock-kbd-hook", daemon=True)
        self._thread.start()
        self._ready.wait(2.0)
        return self.installed

    def stop(self) -> None:
        t = self._thread
        if not t or not t.is_alive():
            return
        if self._thread_id:
            import ctypes
            from ctypes import wintypes
            u = ctypes.WinDLL("user32")
            u.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            u.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)    # WM_QUIT ends the message loop
        t.join(2.0)
        self._thread = None

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes
        hook = None
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        try:
            LRESULT = ctypes.c_ssize_t        # pointer-sized: correct on 64-bit Windows
            ULONG_PTR = ctypes.c_size_t

            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                            ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                            ("dwExtraInfo", ULONG_PTR)]

            HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
            user32.SetWindowsHookExW.restype = wintypes.HHOOK
            user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
            user32.CallNextHookEx.restype = LRESULT
            user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
            user32.UnhookWindowsHookEx.restype = wintypes.BOOL
            user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
            user32.GetAsyncKeyState.restype = ctypes.c_short
            user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

            WH_KEYBOARD_LL, HC_ACTION = 13, 0
            DOWN_MSGS = (0x0100, 0x0104)       # WM_KEYDOWN, WM_SYSKEYDOWN  (0x0101/0x0105 = key up)
            VK_MENU, VK_CONTROL = 0x12, 0x11

            def proc(nCode, wParam, lParam):
                try:
                    if nCode == HC_ACTION and lParam:
                        info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        down = wParam in DOWN_MSGS
                        # Real modifier state from Windows, so press/release (and a modifier that
                        # was already held when the hook was installed) are always correct.
                        alt = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
                        ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                        if should_block_key(info.vkCode, down, alt, ctrl):
                            return 1
                except Exception:      # never let an exception escape into the hook chain
                    log.exception("keyboard hook callback error")
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            keep_alive = HOOKPROC(proc)        # local reference lives until this function ends,
            hmod = kernel32.GetModuleHandleW(None)     # i.e. for the whole life of the hook
            hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, keep_alive, hmod, 0)
            if not hook:
                log.error("SetWindowsHookExW failed (error %s); the lock screen still works but "
                          "Win/Alt+Tab are not blocked", ctypes.get_last_error())
                return
            self._thread_id = kernel32.GetCurrentThreadId()
            self.installed = True
            log.info("keyboard hook installed")
            self._ready.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:   # blocks; WM_QUIT -> 0
                pass
        except Exception:
            log.exception("keyboard hook thread failed")
        finally:
            if hook:
                user32.UnhookWindowsHookEx(hook)
                log.info("keyboard hook removed")
            self.installed = False
            self._thread_id = 0
            self._ready.set()


# ---- Win32 focus helper --------------------------------------------------------------------
def force_foreground(tk_toplevel) -> None:
    """Make the lock window the foreground window so it receives physical keyboard input.
    Windows refuses SetForegroundWindow from a background process unless our thread is
    attached to the foreground thread's input queue first; this is the standard workaround."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.WinDLL("user32", use_last_error=True)
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        u.GetParent.argtypes = [wintypes.HWND]; u.GetParent.restype = wintypes.HWND
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.BringWindowToTop.argtypes = [wintypes.HWND]
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        k.GetCurrentThreadId.restype = wintypes.DWORD
        hwnd = u.GetParent(tk_toplevel.winfo_id()) or tk_toplevel.winfo_id()   # Tk's wrapper window
        fg = u.GetForegroundWindow()
        fg_thread = u.GetWindowThreadProcessId(fg, None) if fg else 0
        me = k.GetCurrentThreadId()
        attached = bool(fg_thread and fg_thread != me and u.AttachThreadInput(me, fg_thread, True))
        try:
            u.ShowWindow(hwnd, 5)          # SW_SHOW
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
        finally:
            if attached:
                u.AttachThreadInput(me, fg_thread, False)
    except Exception:
        log.exception("force_foreground failed")


# ---- UI ------------------------------------------------------------------------------------
class LockScreen:
    """`pin_api` is the pinlock module (injectable for tests)."""

    def __init__(self, root, pin_api=pinlock, hook: KeyboardHook | None = None, poll_ms: int = POLL_MS):
        import tkinter as tk
        self.tk = tk
        self.root = root
        self.pin_api = pin_api
        self.hook = hook if hook is not None else KeyboardHook()
        self.poll_ms = poll_ms
        self.win = None
        self.entry = None
        self.entry_var = tk.StringVar()
        self.msg_var = tk.StringVar()
        self._busy = False
        self._last_focus_grab = 0.0
        self._focus_job = None
        self._last_state_error = None
        self._poll()

    # -- state polling --
    def _poll(self):
        try:
            self.apply_state(self.pin_api.status()["locked"])
            self._last_state_error = None
        except pinlock.StateFileError as e:
            if str(e) != self._last_state_error:          # log each distinct problem once
                log.error("cannot read lock state: %s (keeping current screen state)", e)
                self._last_state_error = str(e)
        except Exception:
            log.exception("poll failed")
        self.root.after(self.poll_ms, self._poll)

    def apply_state(self, locked: bool):
        if locked and self.win is None:
            self._show()
        elif not locked and self.win is not None:
            self._hide()
        elif self.win is not None:
            self.ensure_focus()           # no-op while the PIN field already has focus

    # -- window --
    def _show(self):
        tk = self.tk
        log.info("state is locked: showing lock screen")
        self.entry_var.set("")
        self.msg_var.set("")
        self._busy = False
        w = tk.Toplevel(self.root)
        self.win = w
        w.configure(bg="#0b0f1a")
        # A regular borderless full-screen window (NOT overrideredirect): Windows will not
        # activate override-redirect windows, which is why keystrokes used to go to whatever
        # window was active before.
        w.attributes("-topmost", True)
        try:
            w.attributes("-fullscreen", True)
        except tk.TclError:
            w.geometry(f"{w.winfo_screenwidth()}x{w.winfo_screenheight()}+0+0")
        w.protocol("WM_DELETE_WINDOW", lambda: None)     # Alt+F4 does nothing

        frame = tk.Frame(w, bg="#0b0f1a")
        frame.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(frame, text="\U0001F512  PC Locked", font=("Segoe UI", 28, "bold"),
                 fg="#e8ecf6", bg="#0b0f1a").pack(pady=(0, 18))
        tk.Label(frame, text="Enter PIN to unlock", font=("Segoe UI", 13),
                 fg="#9aa4bd", bg="#0b0f1a").pack(pady=(0, 14))

        vcmd = (w.register(self._validate_pin_text), "%P")
        entry = tk.Entry(frame, textvariable=self.entry_var, show="\u2022", justify="center",
                         font=("Segoe UI", 22), width=10, bg="#161c2c", fg="#e8ecf6",
                         insertbackground="#e8ecf6", relief="flat", bd=10,
                         validate="key", validatecommand=vcmd)
        entry.pack(pady=(0, 10))
        self.entry = entry
        entry.bind("<Return>", self._on_enter)
        entry.bind("<KP_Enter>", self._on_enter)
        for d in range(10):      # numeric keypad (NumLock on): insert the digit exactly once
            entry.bind(f"<KP_{d}>", lambda e, d=d: self._on_keypad_digit(d))

        tk.Label(frame, textvariable=self.msg_var, font=("Segoe UI", 11), fg="#ff6b6b",
                 bg="#0b0f1a").pack(pady=(0, 10))
        self.button = tk.Button(frame, text="Unlock", font=("Segoe UI", 12, "bold"),
                                command=self._try_unlock, bg="#4f7cff", fg="white",
                                activebackground="#3d63d9", relief="flat", padx=24, pady=6,
                                cursor="hand2", takefocus=0)
        self.button.pack()

        # Click anywhere that isn't the button -> keep the cursor in the PIN field.
        w.bind("<Button-1>", self._on_click)
        # Focus lost to another window: ONE debounced refocus (see ensure_focus).
        entry.bind("<FocusOut>", self._on_entry_focus_out)

        w.update_idletasks()
        w.deiconify()
        for delay in FOCUS_RETRY_MS:        # a few bounded attempts; stops as soon as it works
            w.after(delay, self._initial_focus)
        if self.hook.start() is False and IS_WINDOWS:
            log.warning("keyboard shortcuts are not blocked (hook not installed)")

    def _initial_focus(self):
        if self.win is not None and not self._entry_has_focus():
            self.ensure_focus(force=True)

    def _hide(self):
        log.info("state is unlocked: hiding lock screen")
        self.hook.stop()
        if self._focus_job is not None:
            try:
                self.root.after_cancel(self._focus_job)
            except Exception:
                pass
            self._focus_job = None
        if self.win is not None:
            self.win.destroy()
            self.win = None
            self.entry = None

    # -- focus --
    def _validate_pin_text(self, proposed: str) -> bool:
        return proposed == "" or (proposed.isascii() and proposed.isdigit()
                                  and len(proposed) <= pinlock.MAX_PIN_LEN)

    def _on_keypad_digit(self, d: int):
        e = self.entry
        if e is None:
            return "break"
        try:
            if e.selection_present():
                e.delete("sel.first", "sel.last")
            e.insert("insert", str(d))          # the validatecommand still enforces digits/length
        except self.tk.TclError:
            pass
        return "break"          # stops Tk's own class binding from inserting it a second time

    def _entry_has_focus(self) -> bool:
        try:
            return self.entry is not None and self.root.focus_get() is self.entry
        except KeyError:
            return False

    def _window_has_focus(self) -> bool:
        try:
            f = self.root.focus_get()
        except KeyError:
            return False
        return f is not None and self.win is not None and f.winfo_toplevel() is self.win

    def ensure_focus(self, force: bool = False):
        """Give keyboard focus to the PIN entry -- but only when it is not already there, and
        at most every MIN_REFOCUS_INTERVAL_S, so typing/selecting/deleting is never disturbed
        and there is no focus-stealing loop."""
        if self.win is None or self.entry is None or self._entry_has_focus():
            return
        import time
        now = time.monotonic()
        if not force and now - self._last_focus_grab < MIN_REFOCUS_INTERVAL_S:
            return
        self._last_focus_grab = now
        try:
            if not self._window_has_focus():       # OS-level focus is elsewhere
                self.win.attributes("-topmost", True)
                self.win.lift()
                force_foreground(self.win)
            self.entry.focus_force()              # the field itself, not just the toplevel
        except self.tk.TclError:
            log.exception("focus attempt failed")

    def _on_entry_focus_out(self, _e):
        if self._focus_job is None and self.win is not None:
            self._focus_job = self.root.after(100, self._deferred_focus)

    def _deferred_focus(self):
        self._focus_job = None
        self.ensure_focus()

    def _on_click(self, e):
        if e.widget is not getattr(self, "button", None) and self.entry is not None:
            self.entry.focus_set()

    # -- unlocking --
    def _on_enter(self, _e=None):
        self._try_unlock()
        return "break"          # swallow the key so it can't also trigger anything else

    def _try_unlock(self):
        if self._busy or self.win is None:        # Enter + button / key-repeat can't double-submit
            return
        pin = self.entry_var.get().strip()
        if not pin:
            self.msg_var.set("Enter your PIN")
            return                                # an empty submit never counts as a failed try
        if len(pin) < pinlock.MIN_PIN_LEN:
            self.msg_var.set(f"PIN is at least {pinlock.MIN_PIN_LEN} digits")
            return
        self._busy = True
        try:
            ok, message = self.pin_api.unlock_with_pin(pin)
        except Exception:
            log.exception("PIN verification raised")
            ok, message = False, "Could not check the PIN - see lock_overlay.log"
        finally:
            self._busy = False
        self.entry_var.set("")
        if ok:
            self._hide()
        else:
            self.msg_var.set(message)
            if self.entry is not None:
                self.entry.focus_set()


def main() -> int:
    setup_logging()
    sys.excepthook = lambda t, v, tb: log.critical("uncaught exception", exc_info=(t, v, tb))
    guard = SingleInstance()
    if not guard.acquire():
        log.info("another lock overlay is already running in this session; exiting")
        return 0
    hook = KeyboardHook()
    try:
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            log.exception("Tkinter could not start (no display?)")
            return 2
        root.withdraw()     # no visible window of its own; LockScreen creates/destroys the real one
        root.report_callback_exception = lambda t, v, tb: log.error("Tk callback error", exc_info=(t, v, tb))
        log.info("lock overlay started (state file: %s)", pinlock.STATE_PATH)
        LockScreen(root, hook=hook)
        root.mainloop()
        return 0
    except Exception:
        log.exception("lock overlay crashed")
        return 1
    finally:
        hook.stop()
        guard.release()


if __name__ == "__main__":
    sys.exit(main())
