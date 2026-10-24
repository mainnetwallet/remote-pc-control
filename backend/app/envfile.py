"""Read and edit the .env file from the control panel, keeping comments and unknown lines untouched."""
import os, re, tempfile
from pathlib import Path

# What the control panel may change. kind: choice | int | bool. "live" settings need no restart.
FIELDS = [
    {"key": "REMOTE_PC_RTC_FPS", "group": "video", "kind": "choice", "default": "auto",
     "options": ["auto", "30", "45", "60", "90", "120"]},
    {"key": "REMOTE_PC_FPS", "group": "video", "kind": "choice", "default": "auto",
     "options": ["auto", "15", "20", "30", "45", "60"]},
    {"key": "REMOTE_PC_RTC_BITRATE", "group": "video", "kind": "int", "default": "4000", "min": 300, "max": 30000},
    {"key": "REMOTE_PC_JPEG_QUALITY", "group": "video", "kind": "int", "default": "55", "min": 25, "max": 85},
    {"key": "REMOTE_PC_MAX_WIDTH", "group": "video", "kind": "int", "default": "1280", "min": 0, "max": 7680},
    {"key": "REMOTE_PC_RTC_ENCODER", "group": "video", "kind": "choice", "default": "auto",
     "options": ["auto", "nvenc", "qsv", "amf", "x264"]},
    {"key": "REMOTE_PC_CAPTURE", "group": "video", "kind": "choice", "default": "auto", "options": ["auto", "mss"]},
    {"key": "REMOTE_PC_WEBRTC", "group": "video", "kind": "bool", "default": "1"},
    {"key": "REMOTE_PC_SHOW_CURSOR", "group": "video", "kind": "bool", "default": "1"},
]
_BY_KEY = {f["key"]: f for f in FIELDS}
_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def parse(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"): continue
        m = _LINE.match(line)
        if m: out[m.group(1)] = m.group(2).strip("\"'")
    return out


def read(path: Path) -> dict:
    try: return parse(Path(path).read_text(encoding="utf-8"))
    except OSError: return {}


def validate_setting(key: str, value) -> str:
    f = _BY_KEY.get(key)
    if not f: raise ValueError(f"Unknown setting {key}")
    v = str(value).strip().lower()
    if f["kind"] == "choice":
        if v not in f["options"]: raise ValueError(f"{key}: choose one of {', '.join(f['options'])}")
        return v
    if f["kind"] == "bool":
        if v in ("1", "true", "yes", "on"): return "1"
        if v in ("0", "false", "no", "off"): return "0"
        raise ValueError(f"{key}: must be on or off")
    try: n = int(v)
    except ValueError: raise ValueError(f"{key}: must be a number") from None
    if not f["min"] <= n <= f["max"]: raise ValueError(f"{key}: must be between {f['min']} and {f['max']}")
    return str(n)


def validate_token(token) -> str:
    t = str(token or "")
    if len(t) < 4: raise ValueError("Password must be at least 4 characters")
    if len(t) > 200: raise ValueError("Password is too long (200 characters at most)")
    if any(c.isspace() for c in t): raise ValueError("Password must not contain spaces")
    if not t.isprintable() or any(c in "\"'\\$#" for c in t):
        raise ValueError("Password must not contain quotes, backslash, $ or # (use letters, digits and - _ . ! @ etc.)")
    return t


def update(path: Path, updates: dict) -> None:
    """Set KEY=value lines (replace if present, append otherwise); everything else stays as it was."""
    path = Path(path)
    for k, v in updates.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) or "\n" in str(v) or "\r" in str(v):
            raise ValueError("Invalid .env entry")
    try: lines = path.read_text(encoding="utf-8").splitlines()
    except OSError: lines = []
    pending = dict(updates)
    for i, line in enumerate(lines):
        m = _LINE.match(line)
        if m and not line.lstrip().startswith("#") and m.group(1) in pending:
            lines[i] = f"{m.group(1)}={pending.pop(m.group(1))}"
    for k, v in pending.items(): lines.append(f"{k}={v}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh: fh.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise
