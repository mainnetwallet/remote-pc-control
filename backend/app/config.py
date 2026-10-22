import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    token = os.getenv("REMOTE_PC_TOKEN", "")
    host = os.getenv("REMOTE_PC_HOST", "127.0.0.1")
    port = int(os.getenv("REMOTE_PC_PORT", "8888"))
    fps = max(1, min(30, int(os.getenv("REMOTE_PC_FPS", "10"))))
    jpeg_quality = max(25, min(85, int(os.getenv("REMOTE_PC_JPEG_QUALITY", "55"))))
    # Frames wider than this are downscaled before sending (0 = send full resolution).
    max_width = max(0, int(os.getenv("REMOTE_PC_MAX_WIDTH", "1280")))
    # Draw a small pointer on the stream so touch users can see where the mouse is.
    show_cursor = os.getenv("REMOTE_PC_SHOW_CURSOR", "1") not in ("0", "false", "False")

settings = Settings()
def validate_settings():
    if len(settings.token.encode()) < 32 or settings.token.startswith("replace-"):
        raise RuntimeError("Set a unique REMOTE_PC_TOKEN (32+ bytes) in .env")
