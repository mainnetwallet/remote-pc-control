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
    # Draw a small pointer on the stream so touch users can see where the mouse is.
    show_cursor = os.getenv("REMOTE_PC_SHOW_CURSOR", "1") not in ("0", "false", "False")

settings = Settings()
MIN_TOKEN_LEN = 4   # short passwords are allowed; longer is safer (12+ recommended, setup.ps1 generates 64 chars)

def validate_settings():
    if len(settings.token) < MIN_TOKEN_LEN or settings.token.startswith("replace-"):
        raise RuntimeError(f"Set REMOTE_PC_TOKEN in .env (at least {MIN_TOKEN_LEN} characters)")
    if len(settings.token) < 12:
        print("WARNING: REMOTE_PC_TOKEN is short. Anyone who finds the link could guess it; use 12+ characters if the PC is reachable from the internet.")
