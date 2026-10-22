import asyncio, hmac, io, json, platform
from fastapi import WebSocket, WebSocketDisconnect
from PIL import Image
from .config import settings

async def screen_socket(ws: WebSocket):
    await ws.accept()
    try:
        auth = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=8))
        if not hmac.compare_digest(str(auth.get("token", "")).encode(), settings.token.encode()): await ws.close(code=4401); return
        await ws.send_json({"type":"ready"})
        if platform.system() != "Windows": await ws.send_json({"type":"error","message":"Windows required"}); return
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            while True:
                shot=sct.grab(monitor); image=Image.frombytes("RGB",shot.size,shot.rgb); buf=io.BytesIO()
                image.save(buf,"JPEG",quality=settings.jpeg_quality,optimize=True)
                await ws.send_bytes(buf.getvalue()); await asyncio.sleep(1/settings.fps)
    except WebSocketDisconnect: return
    except asyncio.TimeoutError: await ws.close(code=4401,reason="Authentication timeout")
    except Exception as exc:
        try: await ws.send_json({"type":"error","message":type(exc).__name__}); await ws.close(code=1011)
        except Exception: pass

async def input_socket(ws: WebSocket):
    await ws.accept()
    try:
        auth=json.loads(await asyncio.wait_for(ws.receive_text(),timeout=8))
        if not hmac.compare_digest(str(auth.get("token","")).encode(),settings.token.encode()): await ws.close(code=4401); return
        from pynput import keyboard, mouse
        m,k=mouse.Controller(),keyboard.Controller()
        keys={"ENTER":keyboard.Key.enter,"TAB":keyboard.Key.tab,"BACKSPACE":keyboard.Key.backspace,"ESC":keyboard.Key.esc,"SPACE":keyboard.Key.space,"UP":keyboard.Key.up,"DOWN":keyboard.Key.down,"LEFT":keyboard.Key.left,"RIGHT":keyboard.Key.right,"CTRL":keyboard.Key.ctrl,"ALT":keyboard.Key.alt,"SHIFT":keyboard.Key.shift}
        await ws.send_json({"type":"ready"})
        while True:
            d=json.loads(await ws.receive_text()); kind=d.get("type")
            if kind=="move": m.position=(max(0,int(d["x"])),max(0,int(d["y"])))
            elif kind=="click": m.click(mouse.Button.right if d.get("button")=="right" else mouse.Button.left)
            elif kind=="scroll": m.scroll(0,max(-5,min(5,int(d.get("dy",0)))))
            elif kind=="key":
                key=str(d.get("key",""))
                if len(key)==1 and key.isprintable(): k.press(key); k.release(key)
                elif key.upper() in keys: k.press(keys[key.upper()]); k.release(keys[key.upper()])
            elif kind=="type": k.type(str(d.get("text",""))[:500])
    except WebSocketDisconnect: return
    except asyncio.TimeoutError: await ws.close(code=4401,reason="Authentication timeout")
    except Exception:
        try: await ws.close(code=1008,reason="Invalid input")
        except Exception: pass
