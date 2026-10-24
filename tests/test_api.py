"""HTTP + WebSocket behaviour of the production server with models stubbed out."""
import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import config
import pipeline as P
import telephony
from conftest import KEY_A, KEY_B

AUTH = {"Authorization": f"Bearer {KEY_A}"}


@pytest.fixture(scope="module")
def client():
    P.load_models = lambda *a, **k: {"device": "test", "whisper": "stub", "emotion": "stub"}
    import main
    with TestClient(main.app) as c:
        yield c


def test_startup_refuses_unsafe_production_config(monkeypatch):
    import main
    import asyncio
    monkeypatch.setattr(config, "API_KEYS", {})

    async def boot():
        async with main.lifespan(main.app):
            pass

    with pytest.raises(SystemExit):
        asyncio.run(boot())


def test_health_is_minimal_in_production(client):
    assert client.get("/health").json() == {"ready": True}
    assert client.get("/ready").status_code == 200


def test_docs_and_samples_are_off_in_production(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/samples").status_code == 404


def test_metrics_needs_a_key(client):
    assert client.get("/metrics").status_code == 401
    r = client.get("/metrics", headers=AUTH)
    assert r.status_code == 200 and "awaaz_sessions_max 2" in r.text


def test_analyze_rejects_missing_wrong_key_and_oversize(client):
    f = {"file": ("a.wav", io.BytesIO(b"x" * 100), "audio/wav")}
    assert client.post("/analyze", files=f).status_code == 401
    f = {"file": ("a.wav", io.BytesIO(b"x" * 100), "audio/wav")}
    assert client.post("/analyze", files=f, headers={"Authorization": "Bearer wrong"}).status_code == 401
    big = {"file": ("a.wav", io.BytesIO(b"\0" * (config.MAX_UPLOAD_BYTES + 10)), "audio/wav")}
    assert client.post("/analyze", files=big, headers=AUTH).status_code == 413


def test_analyze_validates_language(client):
    f = {"file": ("a.wav", io.BytesIO(b"x" * 100), "audio/wav")}
    assert client.post("/analyze?language=fr", files=f, headers=AUTH).status_code == 422


def test_feedback_roundtrip_and_validation(client):
    ok = client.post("/feedback", headers=AUTH, json={"verdict": "too_high", "level": "high", "urgency": 67, "session_id": "s1"})
    assert ok.status_code == 200 and ok.json()["id"] >= 1
    assert client.post("/feedback", headers=AUTH, json={"verdict": "nonsense"}).status_code == 422
    assert client.post("/feedback", headers=AUTH, json={"verdict": "agree", "urgency": 500}).status_code == 422
    assert client.post("/feedback", json={"verdict": "agree"}).status_code == 401
    s = client.get("/feedback/summary", headers=AUTH).json()
    assert s["total"] >= 1 and s["by_verdict"]["too_high"] >= 1


def test_audit_trail_records_feedback_and_verifies(client):
    from audit import verify
    ok, n, _ = verify(config.DATA_DIR / "audit.jsonl")
    assert ok and n >= 2
    text = (config.DATA_DIR / "audit.jsonl").read_text(encoding="utf-8")
    assert '"event":"feedback"' in text and "op-alice" in text


def test_ws_requires_key(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/ingest"):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/live", subprotocols=["bearer.wrong"]):
            pass


def test_ws_replay_is_disabled(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/replay?sample=x.wav"):
            pass


def test_ingest_rejects_bad_hello(client):
    with client.websocket_connect("/ws/ingest", subprotocols=[f"bearer.{KEY_A}"]) as ws:
        ws.send_text(json.dumps({"line_id": "L1", "codec": "opus", "rate": 8000}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error" and "codec" in msg["message"]


def test_ingest_streams_g711_and_returns_windows(client):
    t = np.arange(8000 * 4) / 8000
    pcm = (6000 * np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t))).astype(np.int16)
    frames = telephony.encode_ulaw(pcm)
    with client.websocket_connect("/ws/ingest", subprotocols=[f"bearer.{KEY_A}"]) as ws:
        ws.send_text(json.dumps({"line_id": "L-12 <script>", "codec": "pcmu", "rate": 8000}))
        hello = json.loads(ws.receive_text())
        assert hello["type"] == "hello" and hello["session"]
        for i in range(0, len(frames), 160):
            ws.send_bytes(frames[i:i + 160])
        win = json.loads(ws.receive_text())
        assert win["type"] == "window" and "urgency" in win["data"] and "overall" in win


def test_admission_control_returns_busy(client):
    import main
    main.ACTIVE["n"] = config.MAX_SESSIONS
    try:
        with pytest.raises(WebSocketDisconnect) as e:
            with client.websocket_connect("/ws/ingest", subprotocols=[f"bearer.{KEY_A}"]):
                pass
        assert e.value.code == 1013
    finally:
        main.ACTIVE["n"] = 0


def _msg():
    return {"type": "window",
            "data": {"transcript": "mera otp 482915 hai, number 9876543210", "transcript_redacted": "mera otp [redacted] hai, number [redacted]",
                     "fraud": {"matches": [{"term": "otp 482915"}]}, "explain": ["fraud cues: otp 482915"]},
            "overall": {"transcript": "raw 9876543210", "transcript_redacted": "raw [redacted]", "explain": ["x 9876543210"]}}


def test_server_side_redaction_for_operators_without_reveal():
    import main
    blob = json.dumps(main.scrub_message(_msg(), "op-alice"), ensure_ascii=False)
    assert "482915" not in blob and "9876543210" not in blob


def test_reveal_permission_returns_raw(monkeypatch):
    import main
    monkeypatch.setattr(config, "REVEAL_OPERATORS", {"op-alice"})
    assert "482915" in json.dumps(main.scrub_message(_msg(), "op-alice"))
    assert "482915" not in json.dumps(main.scrub_message(_msg(), "op-bob"))
