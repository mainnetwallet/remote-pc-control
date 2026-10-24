import sys
from app import firstrun
firstrun.prepare()   # packaged exe: create .env on first start; must run before app.config is imported
import uvicorn
from app.config import settings
if __name__ == "__main__":
    if firstrun.already_running(settings.port): sys.exit(0)
    firstrun.announce(settings.port)
    uvicorn.run("app.main:app",host=settings.host,port=settings.port,reload=False,ws_per_message_deflate=False)
