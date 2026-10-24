# PIN lock screen: manual test checklist (Windows 11)

The automated tests (`backend/tests/test_lock_overlay.py`) cover the overlay's logic and Tk
event handling, run on Linux/Xvfb and on the Windows CI runner. They do **not** prove physical
keyboard input, focus stealing by other apps, the low-level keyboard hook, the named mutex or the
Scheduled Task on a real signed-in desktop. Run this on a real Windows 11 PC and record the result.

Setup: `.\scripts\setup.ps1`, `.\scripts\set-pin.ps1`, `.\scripts\install-lock-overlay.ps1`,
`Start-ScheduledTask RemotePCControlLock`. Log file: `%LOCALAPPDATA%\RemotePCControl\lock_overlay.log`.

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Lock from the Android app | Full-screen, topmost PIN screen appears within ~1 s | |
| 2 | Without clicking, type digits on the main keyboard | Dots appear in the PIN field immediately | |
| 3 | Type digits on the numeric keypad (NumLock on) | Dots appear, once per key press | |
| 4 | Backspace, then retype; select all (Ctrl+A) and overwrite | Digits delete/replace; focus never jumps while typing | |
| 5 | Type letters / symbols | Ignored | |
| 6 | Wrong PIN + Enter | "Wrong PIN (n attempts left)", field cleared, can retry | |
| 7 | 5 wrong PINs | Cool-down message; correct PIN rejected until it ends | |
| 8 | Correct PIN + Enter (try both Enter and keypad Enter) | Unlocks once, screen closes | |
| 9 | Lock again; correct PIN via mouse + Unlock button | Unlocks | |
| 10 | Lock; open another app with Alt+Tab / Win key / Ctrl+Esc / Ctrl+Shift+Esc | Blocked while locked; keys work normally after unlock | |
| 11 | Lock; launch a program that grabs focus, or click the desktop edge | Typing returns to the PIN field (one refocus, no flicker loop) | |
| 12 | Lock; run `pythonw.exe lock_overlay.py` by hand while the task is running | No second window; log says "already running" | |
| 13 | `Get-Process pythonw` after step 12 | Exactly one overlay process | |
| 14 | End the overlay in Task Manager while locked | Overlay returns within ~1 min, still locked | |
| 15 | Run `install-lock-overlay.ps1` twice; `Get-ScheduledTask RemotePCControlLock*` | Exactly one task | |
| 16 | Lock from the app, stop the Remote PC Control server | Overlay still shown; PIN still unlocks | |
| 17 | Lock from the app, then Unlock from the app | Overlay closes within ~1 s | |
| 18 | Lock, **restart** Windows, sign in | Locked screen appears after sign-in | |
| 19 | Unlock, **restart** Windows, sign in | No lock screen | |
| 20 | Lock, **shut down**, power on, sign in | Locked screen appears | |
| 21 | Unlock, shut down, power on, sign in | No lock screen | |
| 22 | Close the app / lose the connection while unlocked | PC does not lock by itself | |
| 23 | Press Ctrl+Alt+Delete while locked | Windows' secure screen opens (cannot be blocked; expected) | |
| 24 | After a session with the lock shown, press Win | Start menu opens (hook removed) | |

Known limitation: this is an ordinary desktop window, not the Windows sign-in screen. It cannot
block Ctrl+Alt+Delete and does not replace the Windows account password.
