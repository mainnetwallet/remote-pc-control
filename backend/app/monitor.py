import platform
import psutil, socket, time
_previous = None
_previous_at = None

def is_elevated():
    """True when this process runs as Administrator. Windows (UIPI) blocks mouse/keyboard input from a normal
    process into elevated windows such as Task Manager or an admin terminal, so remote input does nothing there."""
    if platform.system()!="Windows": return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception: return False
def snapshot():
    global _previous, _previous_at
    now = time.monotonic(); counters = psutil.net_io_counters()
    net = {"sent_bytes_per_sec": 0, "recv_bytes_per_sec": 0}
    if _previous is not None and _previous_at is not None and now > _previous_at:
        dt = now - _previous_at
        net = {"sent_bytes_per_sec": max(0, int((counters.bytes_sent-_previous.bytes_sent)/dt)), "recv_bytes_per_sec": max(0, int((counters.bytes_recv-_previous.bytes_recv)/dt))}
    _previous, _previous_at = counters, now
    vm, disk = psutil.virtual_memory(), psutil.disk_usage("/")
    return {"online": True, "hostname": socket.gethostname(), "uptime_seconds": int(time.time()-psutil.boot_time()), "cpu_percent": psutil.cpu_percent(interval=None), "memory": {"total": vm.total, "used": vm.used, "percent": vm.percent}, "disk": {"total": disk.total, "used": disk.used, "percent": disk.percent}, "network": net, "timestamp": time.time(), "elevated": is_elevated()}
