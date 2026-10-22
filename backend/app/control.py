import ctypes, platform, subprocess
from fastapi import HTTPException

def lock_workstation():
    if platform.system() != "Windows": raise HTTPException(501, "Windows only")
    if not ctypes.windll.user32.LockWorkStation(): raise HTTPException(500, "Lock request failed")

def sleep_pc():
    if platform.system() != "Windows": raise HTTPException(501, "Windows only")
    if not ctypes.windll.powrprof.SetSuspendState(False, False, False): raise HTTPException(500, "Sleep request failed")

def power_action(action: str, confirm: bool):
    if not confirm: raise HTTPException(400, "Explicit confirmation required")
    if platform.system() != "Windows": raise HTTPException(501, "Windows only")
    cmds = {"restart": ["shutdown.exe", "/r", "/t", "5"], "shutdown": ["shutdown.exe", "/s", "/t", "5"]}
    if action not in cmds: raise HTTPException(400, "Unsupported action")
    subprocess.Popen(cmds[action], shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
