"""
AwaazAlert API — real-time distress + fraud-script signal for cybercrime helpline operators.

  GET  /health                      model status
  POST /analyze  (multipart file)   full-file analysis -> timeline + overall  (demo / recorded calls)
  GET  /samples                     bundled demo calls
  WS   /ws/live                     browser sends 16 kHz int16 PCM chunks; server streams window results
  WS   /ws/replay?sample=<id>       replays a bundled sample as if live (for demos)

Privacy: audio stays in memory for the duration of one window and is then dropped. Nothing is
persisted. Transcripts are redacted by default; the operator can reveal PII with an explicit toggle.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import pipeline as P

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("awaaz.api")

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
WINDOW_S = float(os.environ.get("AWAAZ_WINDOW", "3.0"))

app = FastAPI(title="AwaazAlert", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
STATUS: dict = {"ready": False}


@app.on_event("startup")
async def _startup():
    loop = asyncio.get_event_loop()
    st = await loop.run_in_executor(None, P.load_models)
    STATUS.update(st)
    STATUS["ready"] = True
    log.info("models ready: %s", st)


@app.get("/health")
async def health():
    return STATUS


@app.get("/samples")
async def samples():
    meta = SAMPLES / "samples.json"
    if not meta.exists():
        return []
    return json.loads(meta.read_text(encoding="utf-8"))


@app.get("/samples/{name}")
async def sample_file(name: str):
    p = (SAMPLES / name).resolve()
    if not p.is_file() or SAMPLES.resolve() not in p.parents:
        return {"error": "not found"}
    return FileResponse(p)


@app.post("/analyze")
async def analyze(file: UploadFile = File(...), language: str | None = None):
    data = await file.read()
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, P.analyze_file, data, WINDOW_S, language)
    except ValueError as e:
        return {"error": str(e)}
    return result


async def _send(ws: WebSocket, obj: dict):
    await ws.send_text(json.dumps(obj, ensure_ascii=False))


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    """Client protocol: binary frames = int16 PCM @16 kHz mono (any length, we re-chunk to WINDOW_S);
    text frame {"cmd":"flush"} forces analysis of what is buffered; {"cmd":"lang","value":"hi"} pins language."""
    await ws.accept()
    await _send(ws, {"type": "hello", "window_s": WINDOW_S, "status": STATUS})
    buf = np.zeros(0, dtype=np.float32)
    session = P.Session(None, WINDOW_S)
    loop = asyncio.get_event_loop()
    need = int(WINDOW_S * P.SR)
    try:
        while True:
            msg = await ws.receive()
            if msg.get("bytes") is not None:
                buf = np.concatenate([buf, P.pcm16_bytes_to_float(msg["bytes"])])
            elif msg.get("text"):
                try:
                    cmd = json.loads(msg["text"])
                except json.JSONDecodeError:
                    cmd = {}
                if cmd.get("cmd") == "lang":
                    session.language = cmd.get("value") or None
                elif cmd.get("cmd") == "flush" and len(buf) >= P.SR * 0.6:
                    chunk, buf = buf, np.zeros(0, dtype=np.float32)
                    res = await loop.run_in_executor(None, session.feed, chunk)
                    await _send(ws, {"type": "window", "data": res.to_dict(), "overall": session.overall()["overall"]})
                elif cmd.get("cmd") == "reset":
                    buf = np.zeros(0, dtype=np.float32); session = P.Session(session.language, WINDOW_S)
                    await _send(ws, {"type": "reset"})
            while len(buf) >= need:
                chunk, buf = buf[:need], buf[need:]
                res = await loop.run_in_executor(None, session.feed, chunk)
                await _send(ws, {"type": "window", "data": res.to_dict(), "overall": session.overall()["overall"]})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("ws_live error")
        try:
            await _send(ws, {"type": "error", "message": "analysis error"})
        except Exception:  # noqa: BLE001
            pass


@app.websocket("/ws/replay")
async def ws_replay(ws: WebSocket, sample: str = Query(...), speed: float = Query(1.0)):
    """Replay a bundled sample window-by-window with real-time pacing (speed=2 -> twice as fast)."""
    await ws.accept()
    p = (SAMPLES / sample).resolve()
    if not p.is_file() or SAMPLES.resolve() not in p.parents:
        await _send(ws, {"type": "error", "message": "unknown sample"}); await ws.close(); return
    loop = asyncio.get_event_loop()
    audio = await loop.run_in_executor(None, P.decode_to_pcm16k, p.read_bytes())
    await _send(ws, {"type": "hello", "window_s": WINDOW_S, "duration": len(audio) / P.SR, "status": STATUS})
    need = int(WINDOW_S * P.SR)
    session = P.Session(None, WINDOW_S)
    try:
        for i in range(0, len(audio), need):
            chunk = audio[i:i + need]
            if len(chunk) < P.SR * 0.6:
                break
            t0 = loop.time()
            res = await loop.run_in_executor(None, session.feed, chunk)
            await _send(ws, {"type": "window", "data": res.to_dict(), "overall": session.overall()["overall"]})
            # pace to real time minus the time already spent analysing
            wait = (len(chunk) / P.SR) / max(0.1, speed) - (loop.time() - t0)
            if wait > 0:
                await asyncio.sleep(wait)
        await _send(ws, {"type": "done", "overall": session.overall()["overall"]})
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8765")), reload=False)
