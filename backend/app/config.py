import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    token = os.getenv("REMOTE_PC_TOKEN", "")
    host = os.getenv("REMOTE_PC_HOST", "127.0.0.1")
    port = int(os.getenv("REMOTE_PC_PORT", "8788"))
    fps = max(1, min(12, int(os.getenv("REMOTE_PC_FPS", "5"))))
    jpeg_quality = max(25, min(85, int(os.getenv("REMOTE_PC_JPEG_QUALITY", "55"))))

settings = Settings()
def validate_settings():
    if len(settings.token.encode()) < 32 or settings.token.startswith("replace-"):
        raise RuntimeError("Set a unique REMOTE_PC_TOKEN (32+ bytes) in .env")
