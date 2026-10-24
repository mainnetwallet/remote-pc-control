import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    token = os.getenv("REMOTE_PC_TOKEN", "")
    host = os.getenv("REMOTE_PC_HOST", "127.0.0.1")
    port = int(os.getenv("REMOTE_PC_PORT", "8888"))
    fps = max(1, min(30, int(os.getenv("REMOTE_PC_FPS", "20"))))
    jpeg_quality = max(25, min(85, int(os.getenv("REMOTE_PC_JPEG_QUALITY", "55"))))
    # Frames wider than this are downscaled before sending (0 = send full resolution).
    max_width = max(0, int(os.getenv("REMOTE_PC_MAX_WIDTH", "1280")))
    # While the picture is changing fast (scrolling, animations) frames are sent at this percent of the JPEG quality
    # so they arrive sooner; one full-quality frame follows when the picture stops (100 = off, 40-100).
    motion_quality = max(40, min(100, int(os.getenv("REMOTE_PC_MOTION_QUALITY", "100"))))
    # Same moments: frames are also scaled to this percent of their width (50-100; 100 = keep the width).
    motion_width = max(50, min(100, int(os.getenv("REMOTE_PC_MOTION_WIDTH", "100"))))
    # Latency first: on a slow link the picture is made smaller at once (and grows back slowly, in steps) so a
    # click shows up without waiting behind big frames. 0 = always send exactly the configured quality and width.
    latency_first = os.getenv("REMOTE_PC_LATENCY_FIRST", "1").strip() not in ("0", "false", "no", "off")
    # Screen capture: "auto" uses fast DXGI capture when the optional dxcam package works and mss otherwise; "mss" forces mss.
    capture = os.getenv("REMOTE_PC_CAPTURE", "auto").strip().lower()
    # Draw a small pointer on the stream so touch users can see where the mouse is.
    show_cursor = os.getenv("REMOTE_PC_SHOW_CURSOR", "1") not in ("0", "false", "False")

    # --- WebRTC transport (/ws/rtc). The WebSocket JPEG stream stays available as the fallback. ---
    # 1 (default) = offer WebRTC; 0 = /ws/rtc answers "unavailable" and clients use the WebSocket stream.
    webrtc = os.getenv("REMOTE_PC_WEBRTC", "1").strip().lower() not in ("0", "false", "no", "off")
    # Max frames per second of the WebRTC video (1-30).
    rtc_fps = max(1, min(30, int(os.getenv("REMOTE_PC_RTC_FPS", "30") or "30")))
    # Upper limit of the video bitrate in kbit/s (the link's own estimate can only lower it). 300-30000.
    rtc_bitrate = max(300, min(30000, int(os.getenv("REMOTE_PC_RTC_BITRATE", "4000") or "4000")))
    # H.264 encoder: auto (try nvenc, qsv, amf, then libx264) or force one of nvenc / qsv / amf / x264.
    rtc_encoder = os.getenv("REMOTE_PC_RTC_ENCODER", "auto").strip().lower()
    # ICE servers. STUN finds the public address (comma separated list). TURN relays the video when a direct
    # connection is impossible (CGNAT, strict firewalls); it is only used when REMOTE_PC_TURN_URL is set.
    stun_urls = [u.strip() for u in os.getenv("REMOTE_PC_STUN_URL", "stun:stun.l.google.com:19302").split(",") if u.strip()]
    turn_url = os.getenv("REMOTE_PC_TURN_URL", "").strip()
    turn_user = os.getenv("REMOTE_PC_TURN_USER", "").strip()
    turn_pass = os.getenv("REMOTE_PC_TURN_PASS", "")

    # --- Secure Windows unlock (disabled by default; needs the native Credential Provider, see docs/UNLOCK.md) ---
    unlock_enabled = os.getenv("REMOTE_PC_UNLOCK", "0").strip().lower() in ("1", "true", "yes", "on")
    # The one local Windows account this agent may unlock (e.g. "alice"). Required when unlock is enabled.
    unlock_account = os.getenv("REMOTE_PC_UNLOCK_ACCOUNT", "").strip()
    # 1 = the plain Windows PIN/password action is refused; only phone-biometric + credential is accepted.
    unlock_require_biometric = os.getenv("REMOTE_PC_UNLOCK_REQUIRE_BIOMETRIC", "0").strip().lower() in ("1", "true", "yes", "on")
    # Folder for the enrolled device public keys (never holds Windows credentials).
    unlock_data_dir = os.getenv("REMOTE_PC_UNLOCK_DATA", "").strip()
    # Optional stable PC identifier that challenges are bound to (default: derived from the machine GUID/hostname).
    pc_id = os.getenv("REMOTE_PC_ID", "").strip()

settings = Settings()
MIN_TOKEN_LEN = 4   # short passwords are allowed; longer is safer (12+ recommended, setup.ps1 generates 64 chars)

def validate_settings():
    if len(settings.token) < MIN_TOKEN_LEN or settings.token.startswith("replace-"):
        raise RuntimeError(f"Set REMOTE_PC_TOKEN in .env (at least {MIN_TOKEN_LEN} characters)")
    if len(settings.token) < 12:
        print("WARNING: REMOTE_PC_TOKEN is short. Anyone who finds the link could guess it; use 12+ characters if the PC is reachable from the internet.")
