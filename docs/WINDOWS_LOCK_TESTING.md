<div align="center">

# PIN Lock Screen: Manual Test Checklist

Windows 11 · run on a real signed-in desktop and record the result.

[← Project README](../README.md#-pin-lock) · [Architecture: PIN lock design](ARCHITECTURE.md#pin-lock-design)

</div>

---

## What the automated tests do and do not prove

The automated tests (`backend/tests/test_lock_overlay.py`) cover the overlay's logic and Tk event handling. They run on Linux/Xvfb and on the Windows CI runner.

They do **not** prove:

- physical keyboard input,
- focus stealing by other apps,
- the low-level keyboard hook,
- the named mutex,
- the Scheduled Task on a real signed-in desktop.

Run this checklist on a real Windows 11 PC for those.

## Setup

```powershell
.\scripts\setup.ps1
.\scripts\set-pin.ps1
.\scripts\install-lock-overlay.ps1
Start-ScheduledTask RemotePCControlLock
```

Log file: `%LOCALAPPDATA%\RemotePCControl\lock_overlay.log`. The PIN is 4-12 digits; five wrong PINs trigger a 60-second cool-down.

## Checklist

Fill in the **Result** column (✅ / ❌ and a note).

### Entering the PIN

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

### Keyboard blocking and focus

| # | Step | Expected | Result |
|---|------|----------|--------|
| 10 | Lock; open another app with Alt+Tab / Win key / Ctrl+Esc / Ctrl+Shift+Esc | Blocked while locked; keys work normally after unlock | |
| 11 | Lock; launch a program that grabs focus, or click the desktop edge | Typing returns to the PIN field (one refocus, no flicker loop) | |
| 23 | Press Ctrl+Alt+Delete while locked | Windows' secure screen opens (cannot be blocked; expected) | |
| 24 | After a session with the lock shown, press Win | Start menu opens (hook removed) | |

### Single instance and scheduled task

| # | Step | Expected | Result |
|---|------|----------|--------|
| 12 | Lock; run `pythonw.exe lock_overlay.py` by hand while the task is running | No second window; log says "already running" | |
| 13 | `Get-Process pythonw` after step 12 | Exactly one overlay process | |
| 14 | End the overlay in Task Manager while locked | Overlay returns within ~1 min, still locked | |
| 15 | Run `install-lock-overlay.ps1` twice; `Get-ScheduledTask RemotePCControlLock*` | Exactly one task | |

### Server and app interaction

| # | Step | Expected | Result |
|---|------|----------|--------|
| 16 | Lock from the app, stop the Remote PC Control server | Overlay still shown; PIN still unlocks | |
| 17 | Lock from the app, then Unlock from the app | Overlay closes within ~1 s | |
| 22 | Close the app / lose the connection while unlocked | PC does not lock by itself | |
| 25 | With a PIN set, tap **Lock** in the app's power buttons | PIN screen appears (not the Windows sign-in screen); response mode is `pin` | |
| 26 | Add `REMOTE_PC_LOCK_BUTTON=windows` to `.env`, restart the server, tap **Lock** | Windows lock screen appears; remove the setting afterwards | |

### Restart and shutdown persistence

| # | Step | Expected | Result |
|---|------|----------|--------|
| 18 | Lock, **restart** Windows, sign in | Locked screen appears after sign-in | |
| 19 | Unlock, **restart** Windows, sign in | No lock screen | |
| 20 | Lock, **shut down**, power on, sign in | Locked screen appears | |
| 21 | Unlock, shut down, power on, sign in | No lock screen | |

## Known limitation

> [!NOTE]
> This is an ordinary desktop window, not the Windows sign-in screen. It cannot block Ctrl+Alt+Delete and does not replace the Windows account password.
