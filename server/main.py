"""
AwaazAlert API: real-time distress + fraud-script signal for cybercrime helpline operators.

  GET  /health                      liveness + model status (minimal in production)
  GET  /ready                       200 only when models are loaded (load-balancer probe)
  GET  /metrics                     Prometheus text (auth in production)
  POST /analyze  (multipart file)   full-file analysis -> timeline + overall                      [auth, size-capped]
  WS   /ws/live                     browser sends 16 kHz int16 PCM; server streams window results   [auth, admission]
  WS   /ws/ingest                   telephony gateway: G.711/PCM frames + {"line_id","codec","rate"} [auth, admission]
  POST /feedback                    operator verdict on a window/call (builds the evaluation set)    [auth]
  GET  /feedback/summary            agreement counts                                                 [auth]
  GET  /samples, /samples/{f}, WS /ws/replay   bundled demo calls                                    [demo mode only]

Privacy: audio stays in memory for one window, then is dropped. Nothing audio- or transcript-shaped is persisted:
the audit log and feedback store hold ids, operators, numbers and verdicts only. See docs/SECURITY.md.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

import config
import pipeline as P
import security
import telephony
from audit import AuditLog
from fraud_lexicon import redact
from feedback import VERDICTS, FeedbackStore
from metrics import METRICS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("awaaz.api")

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
WINDOW_S = config.WINDOW_S
STATUS: dict = {"ready": False}
AUDIT: AuditLog | None = None
FEEDBACK: FeedbackStore | None = None
ACTIVE = {"n": 0}
IDLE_TIMEOUT_S = float(os.environ.get("AWAAZ_IDLE_TIMEOUT", "120"))
MAX_BUFFER_S = 20.0           # if analysis falls this far behind real time, drop the oldest audio and say so
MAX_FRAME_BYTES = 1 << 20
_LINE_RE = re.compile(r"[^A-Za-z0-9_.:-]")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global AUDIT, FEEDBACK
    problems = config.validate()
    if problems:
        for p in problems:
            log.error("config: %s", p)
        sys.exit("refusing to start in production mode with an unsafe configuration")
    if config.PRODUCTION or config.API_KEYS:
        AUDIT = AuditLog(config.DATA_DIR / "audit.jsonl")
        FEEDBACK = FeedbackStore(config.DATA_DIR / "feedback.db", config.STORE_TEXT)
    else:
        log.warning("DEMO MODE: API is open, no audit log. Do not expose this to a network.")
        FEEDBACK = FeedbackStore(config.DATA_DIR / "feedback-demo.db", False)
    loop = asyncio.get_event_loop()
    st = await loop.run_in_executor(None, P.load_models)
    STATUS.update(st)
    STATUS["ready"] = True
    METRICS.gauge("ready", 1)
    log.info("models ready (%s mode): %s", config.MODE, st)
    _audit("service_start", "system", mode=config.MODE, device=st.get("device"))
    yield


app = FastAPI(title="AwaazAlert", version="0.2.0", lifespan=lifespan,
              docs_url=None if config.PRODUCTION else "/docs", redoc_url=None,
              openapi_url=None if config.PRODUCTION else "/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ORIGINS if config.PRODUCTION else ["*"],
    allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"],
)


def _can_reveal(operator: str) -> bool:
    return (not config.PRODUCTION) or operator in config.REVEAL_OPERATORS


def _scrub_window(w: dict) -> dict:
    w["transcript"] = w.get("transcript_redacted", "")
    for m in w.get("fraud", {}).get("matches", []):
        m["term"] = redact(m["term"])
    w["explain"] = [redact(e) for e in w.get("explain", [])]
    return w


def _scrub_overall(o: dict) -> dict:
    if "transcript_redacted" in o:
        o["transcript"] = o["transcript_redacted"]
    o["explain"] = [redact(e) for e in o.get("explain", [])]
    return o


def scrub_message(msg: dict, operator: str) -> dict:
    """Server-side redaction: for operators without reveal permission the raw transcript is replaced by the redacted
    one BEFORE it is serialised, so it never crosses the network. (The UI toggle is only a convenience on top.)"""
    if _can_reveal(operator):
        return msg
    if isinstance(msg.get("data"), dict):
        _scrub_window(msg["data"])
    for w in msg.get("windows", []) or []:
        _scrub_window(w)
    if isinstance(msg.get("overall"), dict):
        _scrub_overall(msg["overall"])
    return msg


def _audit(event: str, operator: str, **fields):
    if AUDIT:
        try:
            AUDIT.append(event, operator, **fields)
        except Exception:  # noqa: BLE001  an audit failure must be loud, never silent
            log.exception("AUDIT WRITE FAILED for event %s", event)
            METRICS.inc("audit_write_failures_total")


@app.get("/health")
async def health():
    if config.PRODUCTION:
        return {"ready": STATUS["ready"]}
    return {**STATUS, "mode": config.MODE}


@app.get("/ready")
async def ready():
    if not STATUS["ready"]:
        raise HTTPException(status_code=503, detail="models loading")
    return {"ready": True}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics(operator: str = Depends(security.require_operator)):
    METRICS.gauge("sessions_active", ACTIVE["n"])
    METRICS.gauge("sessions_max", config.MAX_SESSIONS)
    return METRICS.render()


@app.get("/samples")
async def samples():
    if config.PRODUCTION:
        raise HTTPException(status_code=404)
    meta = SAMPLES / "samples.json"
    return json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else []


@app.get("/samples/{name}")
async def sample_file(name: str):
    if config.PRODUCTION:
        raise HTTPException(status_code=404)
    p = (SAMPLES / name).resolve()
    if not p.is_file() or SAMPLES.resolve() not in p.parents:
        raise HTTPException(status_code=404)
    return FileResponse(p)


@app.post("/analyze")
async def analyze(request: Request, file: UploadFile = File(...), language: str | None = None,
                  operator: str = Depends(security.require_operator)):
    if language not in (None, "hi", "en"):
        raise HTTPException(status_code=422, detail="language must be 'hi' or 'en'")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > config.MAX_UPLOAD_BYTES + 4096:
        raise HTTPException(status_code=413, detail="recording too large")
    chunks, total = [], 0
    while True:
        part = await file.read(1 << 20)
        if not part:
            break
        total += len(part)
        if total > config.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="recording too large")
        chunks.append(part)
    data = b"".join(chunks)
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, P.analyze_file, data, WINDOW_S, language)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    METRICS.inc("analyze_total")
    o = result["overall"]
    summary = (o["urgency"], o["level"], o.get("signature"))
    _audit("analyze_upload", operator, duration_s=result.get("duration"), urgency=summary[0], level=summary[1], signature=summary[2])
    return scrub_message(result, operator)


async def _send(ws: WebSocket, obj: dict):
    await ws.send_text(json.dumps(obj, ensure_ascii=False))


async def _admit(ws: WebSocket) -> str | None:
    """Authenticate and apply admission control BEFORE accepting. Returns the operator id or None (socket closed)."""
    op = security.ws_operator(ws)
    if op is None:
        METRICS.inc("auth_failures_total")
        await ws.close(code=1008)
        return None
    if not STATUS["ready"] or ACTIVE["n"] >= config.MAX_SESSIONS:
        METRICS.inc("busy_rejections_total")
        await ws.close(code=1013)   # "try again later": the console shows "all analysis slots busy"
        return None
    return op


async def _stream(ws: WebSocket, operator: str, kind: str, line_id: str | None, convert):
    """Shared analysis loop. `convert(bytes) -> float32 16 kHz array | None` (None = need more bytes)."""
    sid = uuid.uuid4().hex[:12]
    session = P.Session(None, WINDOW_S)
    loop = asyncio.get_event_loop()
    need = int(WINDOW_S * P.SR)
    buf = np.zeros(0, dtype=np.float32)
    windows = 0
    ACTIVE["n"] += 1
    METRICS.inc("sessions_total")
    _audit("session_start", operator, session=sid, kind=kind, line=line_id)
    try:
        await _send(ws, {"type": "hello", "session": sid, "window_s": WINDOW_S, "status": {"ready": True}})
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=IDLE_TIMEOUT_S)
            except asyncio.TimeoutError:
                await _send(ws, {"type": "error", "message": "idle timeout"})
                break
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                if len(msg["bytes"]) > MAX_FRAME_BYTES:
                    await _send(ws, {"type": "error", "message": "frame too large"})
                    break
                arr = convert(msg["bytes"])
                if arr is not None:
                    buf = np.concatenate([buf, arr])
                if len(buf) > MAX_BUFFER_S * P.SR:
                    dropped = len(buf) - int(MAX_BUFFER_S * P.SR)
                    buf = buf[dropped:]
                    METRICS.inc("audio_dropped_seconds_total", dropped / P.SR)
                    await _send(ws, {"type": "lag", "dropped_s": round(dropped / P.SR, 1)})
            elif msg.get("text"):
                try:
                    cmd = json.loads(msg["text"])
                except json.JSONDecodeError:
                    cmd = {}
                if cmd.get("cmd") == "lang" and cmd.get("value") in ("hi", "en", None, ""):
                    session.language = cmd.get("value") or None
                elif cmd.get("cmd") == "flush" and len(buf) >= P.SR * 0.6:
                    chunk, buf = buf, np.zeros(0, dtype=np.float32)
                    res = await loop.run_in_executor(None, session.feed, chunk)
                    windows += 1
                    METRICS.inc("windows_total")
                    METRICS.observe_latency(res.latency_ms / 1000)
                    await _send(ws, scrub_message({"type": "window", "data": res.to_dict(), "overall": session.overall()["overall"]}, operator))
                elif cmd.get("cmd") == "reset":
                    buf = np.zeros(0, dtype=np.float32)
                    session = P.Session(session.language, WINDOW_S)
                    await _send(ws, {"type": "reset"})
            while len(buf) >= need:
                chunk, buf = buf[:need], buf[need:]
                res = await loop.run_in_executor(None, session.feed, chunk)
                windows += 1
                METRICS.inc("windows_total")
                METRICS.observe_latency(res.latency_ms / 1000)
                await _send(ws, scrub_message({"type": "window", "data": res.to_dict(), "overall": session.overall()["overall"]}, operator))
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("stream error (session %s)", sid)
        METRICS.inc("stream_errors_total")
        try:
            await _send(ws, {"type": "error", "message": "analysis error"})
        except Exception:  # noqa: BLE001
            pass
    finally:
        ACTIVE["n"] -= 1
        o = session.overall()["overall"] if session.windows else {}
        _audit("session_end", operator, session=sid, kind=kind, line=line_id, windows=windows,
               duration_s=round(session.t, 1), peak_urgency=max((w["urgency"] for w in session.windows), default=0),
               final_urgency=o.get("urgency"), level=o.get("level"), signature=o.get("signature"),
               language=session.language)


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    """Browser microphone: binary frames = int16 PCM @16 kHz mono (any length, re-chunked to WINDOW_S)."""
    op = await _admit(ws)
    if op is None:
        return
    await ws.accept(subprotocol=security.ws_subprotocol(ws))
    await _stream(ws, op, "browser", None, lambda b: P.pcm16_bytes_to_float(b))


@app.websocket("/ws/ingest")
async def ws_ingest(ws: WebSocket):
    """Telephony gateway. First TEXT frame: {"line_id": "L-12", "codec": "pcmu|pcma|pcm16", "rate": 8000}.
    Then binary media frames (one speaker channel). The server answers hello, then a window result every WINDOW_S."""
    op = await _admit(ws)
    if op is None:
        return
    await ws.accept(subprotocol=security.ws_subprotocol(ws))
    try:
        first = await asyncio.wait_for(ws.receive_text(), timeout=15)
        hello = json.loads(first)
        codec, rate = hello.get("codec"), int(hello.get("rate", 0))
        if codec not in telephony.CODECS or rate not in telephony.RATES:
            raise ValueError(f"codec must be one of {telephony.CODECS} and rate one of {telephony.RATES}")
        line_id = _LINE_RE.sub("", str(hello.get("line_id", "")))[:64] or None
    except (ValueError, json.JSONDecodeError, asyncio.TimeoutError, WebSocketDisconnect, TypeError) as e:
        try:
            await _send(ws, {"type": "error", "message": f"bad ingest hello: {e}"})
            await ws.close(code=1003)
        except Exception:  # noqa: BLE001
            pass
        return
    sb = telephony.StreamBuffer(codec, rate)
    await _stream(ws, op, f"ingest:{codec}@{rate}", line_id, sb.push)


@app.websocket("/ws/replay")
async def ws_replay(ws: WebSocket, sample: str = Query(...), speed: float = Query(1.0)):
    """Demo only: replay a bundled sample window-by-window with real-time pacing."""
    if config.PRODUCTION:
        await ws.close(code=1008)
        return
    await ws.accept()
    p = (SAMPLES / sample).resolve()
    if not p.is_file() or SAMPLES.resolve() not in p.parents:
        await _send(ws, {"type": "error", "message": "unknown sample"})
        await ws.close()
        return
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
            wait = (len(chunk) / P.SR) / max(0.1, speed) - (loop.time() - t0)
            if wait > 0:
                await asyncio.sleep(wait)
        await _send(ws, {"type": "done", "overall": session.overall()["overall"]})
    except WebSocketDisconnect:
        pass


class FeedbackIn(BaseModel):
    verdict: str
    scope: str = "call"
    session_id: str | None = Field(default=None, max_length=64)
    line_id: str | None = Field(default=None, max_length=64)
    t_start: float | None = None
    urgency: int | None = Field(default=None, ge=0, le=100)
    level: str | None = Field(default=None, max_length=16)
    signature: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=8)
    note: str | None = Field(default=None, max_length=500)
    text_redacted: str | None = Field(default=None, max_length=2000)


@app.post("/feedback")
async def post_feedback(body: FeedbackIn, operator: str = Depends(security.require_operator)):
    if body.verdict not in VERDICTS:
        raise HTTPException(status_code=422, detail=f"verdict must be one of {VERDICTS}")
    if body.scope not in ("window", "call"):
        raise HTTPException(status_code=422, detail="scope must be 'window' or 'call'")
    fid = FEEDBACK.add(operator, **body.model_dump())
    METRICS.inc("feedback_total")
    _audit("feedback", operator, id=fid, verdict=body.verdict, scope=body.scope, session=body.session_id, level=body.level)
    return {"id": fid}


@app.get("/feedback/summary")
async def feedback_summary(operator: str = Depends(security.require_operator)):
    return FEEDBACK.summary()


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0" if config.PRODUCTION else "127.0.0.1")
    uvicorn.run("main:app", host=host, port=int(os.environ.get("PORT", "8765")), reload=False)
