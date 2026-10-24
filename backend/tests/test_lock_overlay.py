"""
Automated tests for lock_overlay.py and the hardened pinlock state handling.

Tk tests need a display; on headless Linux run under Xvfb:  xvfb-run -a python -m pytest ...
They are skipped (not failed) when no display/Tk is available.

What these tests are -- and are not: they exercise the overlay's logic and Tk event handling
on whatever platform runs them (Linux/Xvfb here, Windows in CI). Win32-only code (the keyboard
hook, SetForegroundWindow, the named mutex) is NOT executed on Linux; its pure policy
(should_block_key) is tested and the Win32 calls are covered by docs/WINDOWS_LOCK_TESTING.md,
which must be run by a person on a real Windows 11 PC.
"""
import gc
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import lock_overlay  # noqa: E402
from app import pinlock  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(pinlock, "STATE_PATH", tmp_path / "lock_state.json")


# ---------------------------------------------------------------- pure policy / state tests
def test_should_block_only_intended_shortcuts():
    blk = lock_overlay.should_block_key
    assert blk(0x5B, True, False, False) and blk(0x5C, False, False, False)      # Win keys
    assert blk(0x09, True, True, False)                                           # Alt+Tab
    assert blk(0x1B, True, True, False) and blk(0x1B, True, False, True)          # Alt+Esc, Ctrl+Esc
    assert not blk(0x09, True, False, False)                                      # plain Tab
    assert not blk(0x1B, True, False, False)                                      # plain Esc
    assert not blk(0x09, False, True, False)                                      # Alt+Tab key *up*
    for vk in list(range(0x30, 0x3A)) + list(range(0x60, 0x6A)) + [0x08, 0x0D, 0x2E, 0x25, 0x27, 0x10, 0x11, 0x12]:
        for alt in (False, True):
            for ctrl in (False, True):
                assert not blk(vk, True, alt, ctrl), hex(vk)      # digits, keypad, Backspace, Enter, Del, arrows, modifiers


def test_hook_is_noop_off_windows():
    if lock_overlay.IS_WINDOWS:
        pytest.skip("Windows-only behaviour is covered by the manual checklist")
    h = lock_overlay.KeyboardHook()
    assert h.start() is False and h.installed is False
    h.stop(); h.stop()        # idempotent


def test_state_path_is_absolute_and_cwd_independent(monkeypatch, tmp_path):
    monkeypatch.delenv("REMOTE_PC_LOCK_STATE", raising=False)
    a = pinlock.resolve_state_path()
    monkeypatch.chdir(tmp_path)
    b = pinlock.resolve_state_path()
    assert a == b and a.is_absolute() and a.name == "lock_state.json"


def test_relative_override_is_relative_to_project_not_cwd(monkeypatch, tmp_path):
    monkeypatch.setenv("REMOTE_PC_LOCK_STATE", "custom_state.json")
    monkeypatch.chdir(tmp_path)
    assert pinlock.resolve_state_path() == (pinlock._project_root() / "custom_state.json").resolve()


def test_corrupt_state_is_never_read_as_unlocked(tmp_path):
    (tmp_path / "lock_state.json").write_text("{not json")
    with pytest.raises(pinlock.StateFileError):
        pinlock.status()
    ok, msg = pinlock.unlock_with_pin("1234")
    assert ok is False and "1234" not in msg


def test_failed_attempts_do_not_log_pin(caplog):
    pinlock.set_pin("482915")
    pinlock.lock()
    with caplog.at_level("DEBUG"):
        pinlock.unlock_with_pin("000000")
        pinlock.unlock_with_pin("482915")
    text = caplog.text
    assert "482915" not in text and "000000" not in text
    assert json.loads(pinlock.STATE_PATH.read_text())["pin_hash"] not in text


def test_concurrent_processes_never_corrupt_state(tmp_path):
    pinlock.set_pin("1234")
    code = ("import sys; sys.path.insert(0, r'%s'); from app import pinlock; from pathlib import Path;"
            "pinlock.STATE_PATH = Path(r'%s')\n"
            "for _ in range(25):\n    pinlock.lock(); pinlock.unlock()") % (ROOT / "backend", pinlock.STATE_PATH)
    ps = [subprocess.Popen([sys.executable, "-c", code], stderr=subprocess.PIPE, text=True) for _ in range(3)]
    for _ in range(100):                      # reader hammers the file meanwhile
        pinlock.status()
    errs = [p.communicate(timeout=60)[1] for p in ps]
    assert all(p.returncode == 0 for p in ps), errs
    assert pinlock.status()["pin_set"] is True


def test_lock_state_persists_across_process_restarts(tmp_path):
    pinlock.set_pin("1234"); pinlock.lock()
    code = ("import sys; sys.path.insert(0, r'%s'); from app import pinlock; from pathlib import Path;"
            "pinlock.STATE_PATH = Path(r'%s'); print(pinlock.status()['locked'])") % (ROOT / "backend", pinlock.STATE_PATH)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "True", out.stderr
    pinlock.unlock()
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "False", out.stderr


# ---------------------------------------------------------------- single instance
@pytest.mark.skipif(lock_overlay.IS_WINDOWS, reason="uses the POSIX flock fallback; Windows mutex is in the manual checklist")
def test_only_one_overlay_instance(tmp_path):
    f = tmp_path / "inst.lock"
    a, b = lock_overlay.SingleInstance(lock_file=f), lock_overlay.SingleInstance(lock_file=f)
    assert a.acquire() is True
    assert b.acquire() is False
    a.release()
    assert b.acquire() is True        # released cleanly -> next one may run
    b.release()


@pytest.mark.skipif(lock_overlay.IS_WINDOWS, reason="POSIX flock fallback")
def test_stale_instance_marker_after_crash_is_safe(tmp_path):
    f = tmp_path / "inst.lock"
    code = ("import sys,time; sys.path.insert(0, r'%s'); import lock_overlay; from pathlib import Path;"
            "g=lock_overlay.SingleInstance(lock_file=Path(r'%s')); assert g.acquire(); print('held', flush=True); time.sleep(60)") % (ROOT, f)
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "held"
        assert lock_overlay.SingleInstance(lock_file=f).acquire() is False     # live instance blocks us
        p.kill(); p.wait()                                                      # crash / forced kill
        again = lock_overlay.SingleInstance(lock_file=f)
        assert again.acquire() is True                                          # marker file remains but is not stale-locked
        again.release()
    finally:
        p.kill()


# ---------------------------------------------------------------- Tk behaviour
@pytest.fixture
def tkroot():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no display available: {e}")
    root.withdraw()
    root._test_screens = []
    yield root
    # Deterministic teardown ON THE MAIN THREAD. A leftover Tk object that is garbage-collected
    # later by some other test's thread aborts the whole pytest process with
    # "Tcl_AsyncDelete: async handler deleted by the wrong thread" (seen on the Windows CI run).
    for screen in root._test_screens:
        screen.close()
    root._test_screens.clear()
    try:
        root.destroy()
    except tk.TclError:
        pass
    del root
    for _ in range(3):
        gc.collect()


class FakeHook:
    installed = False
    def __init__(self): self.started = 0; self.stopped = 0
    def start(self): self.started += 1; return False
    def stop(self): self.stopped += 1


def pump(root, ms=250):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update(); time.sleep(0.01)


def make(root, **kw):
    screen = lock_overlay.LockScreen(root, hook=FakeHook(), poll_ms=50, **kw)
    root._test_screens.append(screen)
    return screen


def type_keys(screen, *keysyms):
    for k in keysyms:
        # state=16 is Mod2 = NumLock on, which is what makes X11 report keypad keys as digits
        # (on Windows with NumLock on, Tk reports them as digits natively).
        screen.entry.event_generate(f"<{k}>", state=16 if k.startswith("KP_") else 0)
        screen.root.update()


def test_overlay_starts_without_window_when_unlocked(tkroot):
    s = make(tkroot); pump(tkroot, 150)
    assert s.win is None


def test_locked_state_shows_overlay_and_unlocked_dismisses(tkroot):
    pinlock.set_pin("1234"); pinlock.lock()
    s = make(tkroot); pump(tkroot)
    assert s.win is not None and s.hook.started == 1
    pinlock.unlock(); pump(tkroot)
    assert s.win is None and s.hook.stopped >= 1


def test_android_unlock_api_dismisses_overlay(tkroot):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import settings
    h = {"Authorization": "Bearer " + settings.token}
    with TestClient(app) as c:
        assert c.post("/api/v1/lock/pin", json={"pin": "5678"}, headers=h).status_code == 200
        assert c.post("/api/v1/lock/lock", headers=h).status_code == 200
        s = make(tkroot); pump(tkroot)
        assert s.win is not None
        assert c.post("/api/v1/lock/unlock", headers=h).status_code == 200
        pump(tkroot)
        assert s.win is None
        assert c.post("/api/v1/lock/lock", headers=h).status_code == 200      # Android Lock again
        pump(tkroot)
        assert s.win is not None


def test_pin_entry_gets_focus_and_keeps_it(tkroot):
    pinlock.set_pin("1234"); pinlock.lock()
    s = make(tkroot); pump(tkroot, 600)
    assert tkroot.focus_get() is s.entry                    # the field itself, not just the toplevel
    calls = []
    orig = lock_overlay.force_foreground
    lock_overlay.force_foreground = lambda w: calls.append(1)
    try:
        type_keys(s, "Key-1", "Key-2"); pump(tkroot, 400)   # several poll cycles while typing
    finally:
        lock_overlay.force_foreground = orig
    assert calls == []                                      # no focus re-grab while the field has focus
    assert s.entry_var.get() == "12"                        # typing was not disturbed


def test_numeric_keypad_backspace_and_filtering(tkroot):
    pinlock.set_pin("1234"); pinlock.lock()
    s = make(tkroot); pump(tkroot, 600)
    type_keys(s, "Key-1", "KP_2", "KP_3", "Key-x", "Key-a", "KP_4")
    assert s.entry_var.get() == "1234"                      # digits + keypad accepted, letters ignored
    type_keys(s, "BackSpace")
    assert s.entry_var.get() == "123"
    type_keys(s, *["Key-9"] * 20)
    assert len(s.entry_var.get()) <= pinlock.MAX_PIN_LEN


def test_enter_and_button_unlock_with_correct_pin(tkroot):
    pinlock.set_pin("2468"); pinlock.lock()
    s = make(tkroot); pump(tkroot, 600)
    type_keys(s, "Key-2", "Key-4", "Key-6", "Key-8", "Return"); pump(tkroot)
    assert pinlock.status()["locked"] is False and s.win is None
    pinlock.lock(); pump(tkroot, 400)                       # lock again; this time use the mouse button
    assert s.win is not None
    type_keys(s, "KP_2", "KP_4", "KP_6", "KP_8")
    s.button.invoke(); pump(tkroot)
    assert pinlock.status()["locked"] is False and s.win is None


def test_keypad_enter_submits(tkroot):
    pinlock.set_pin("2468"); pinlock.lock()
    s = make(tkroot); pump(tkroot, 600)
    type_keys(s, "Key-2", "Key-4", "Key-6", "Key-8", "KP_Enter"); pump(tkroot)
    assert pinlock.status()["locked"] is False


def test_wrong_pin_stays_locked_shows_error_and_allows_retry(tkroot):
    pinlock.set_pin("2468"); pinlock.lock()
    s = make(tkroot); pump(tkroot, 600)
    type_keys(s, "Key-0", "Key-0", "Key-0", "Key-0", "Return")
    assert pinlock.status()["locked"] is True and s.win is not None
    assert "wrong pin" in s.msg_var.get().lower() and s.entry_var.get() == ""
    type_keys(s, "Key-2", "Key-4", "Key-6", "Key-8", "Return"); pump(tkroot)     # second attempt works
    assert pinlock.status()["locked"] is False


def test_enter_submits_exactly_once_and_empty_enter_is_free(tkroot):
    pinlock.set_pin("2468"); pinlock.lock()
    calls = []
    class Spy:
        StateFileError = pinlock.StateFileError
        MIN_PIN_LEN = pinlock.MIN_PIN_LEN; MAX_PIN_LEN = pinlock.MAX_PIN_LEN
        status = staticmethod(pinlock.status)
        @staticmethod
        def unlock_with_pin(p): calls.append(1); return pinlock.unlock_with_pin(p)
    s = make(tkroot, pin_api=Spy); pump(tkroot, 600)
    type_keys(s, "Return", "Return")                        # empty Enter: no verification, no failed attempt
    assert calls == [] and json.loads(pinlock.STATE_PATH.read_text())["fail_count"] == 0
    type_keys(s, "Key-0", "Key-0", "Key-0", "Key-0", "Return")
    assert calls == [1]                                     # one Enter = one submission


def test_rate_limit_still_enforced_through_overlay(tkroot):
    pinlock.set_pin("2468"); pinlock.lock()
    s = make(tkroot); pump(tkroot, 600)
    for _ in range(pinlock.MAX_PIN_FAILS):
        type_keys(s, "Key-0", "Key-0", "Key-0", "Key-0", "Return")
    type_keys(s, "Key-2", "Key-4", "Key-6", "Key-8", "Return")      # correct, but in cooldown
    assert pinlock.status()["locked"] is True
    assert "too many" in s.msg_var.get().lower()


def test_state_file_error_keeps_current_screen(tkroot):
    pinlock.set_pin("1234"); pinlock.lock()
    s = make(tkroot); pump(tkroot, 300)
    assert s.win is not None
    pinlock.STATE_PATH.write_text("garbage")                # unreadable -> must NOT unlock
    pump(tkroot, 300)
    assert s.win is not None


def test_lock_survives_overlay_restart(tkroot):
    pinlock.set_pin("1234"); pinlock.lock()
    first = make(tkroot); pump(tkroot, 300)
    assert first.win is not None
    first._hide()                                           # simulate the overlay process dying
    second = make(tkroot); pump(tkroot, 300)
    assert second.win is not None                           # new process sees the persisted lock


def test_overlay_runs_without_api_server(tkroot):
    pinlock.set_pin("1234"); pinlock.lock()                 # no TestClient/server anywhere in this test
    s = make(tkroot); pump(tkroot, 600)
    type_keys(s, "Key-1", "Key-2", "Key-3", "Key-4", "Return"); pump(tkroot)
    assert pinlock.status()["locked"] is False


# ---------------------------------------------------------------- installer script (static)
def test_installer_script_is_idempotent_by_construction():
    t = (ROOT / "scripts" / "install-lock-overlay.ps1").read_text(encoding="utf-8")
    assert t.count("Register-ScheduledTask") == 1 and "-Force" in t       # same name replaced, never added
    assert '$name = "RemotePCControlLock"' in t
    assert "lock_overlay.py" in t and "Unregister-ScheduledTask" in t     # stale/duplicate tasks removed
    assert "-LogonType Interactive" in t                                  # runs in the signed-in desktop session
    assert "-MultipleInstances IgnoreNew" in t
    assert "-RestartCount" in t and "-RestartInterval" in t               # restarts if it exits
    assert "-AtLogOn" in t and "-RepetitionInterval" in t                 # and is re-launched if it died
    assert "Stop-Process" not in t and "taskkill" not in t.lower()        # never kills unrelated processes
