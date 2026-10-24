# Deployment guide

AwaazAlert runs as one GPU analysis service plus a static web console. This guide covers the production shape, sizing from
**measured** numbers, telephony hookup and operations. Read "What is untested" first.

## What is untested (be honest with your own reviewers)

* The **Dockerfile, docker-compose.yml and nginx template were never built or run**: the author's machine has no Docker.
  Treat the first build as part of acceptance testing.
* Telephony ingest is tested with synthetic G.711 frames and a paced 8 kHz stream (`bench_capacity.py`), **not** against
  a real SBC / FreeSWITCH / Asterisk, real RTP jitter, packet loss, or real PSTN noise.
* No real helpline audio has ever been processed.
* Capacity was measured on one RTX 4060 **laptop** GPU sharing the machine with the load generator.

## Shape

```
 SBC / FreeSWITCH / Asterisk  --(WSS, G.711 frames, one caller channel per call)-->  nginx (TLS, SSO)  -->  awaaz (GPU)
 operator console (static web/dist) <--(WSS window results, redacted text)---------  nginx  <------------   awaaz
                                                                                              |-> data/audit.jsonl  (ship to WORM)
                                                                                              |-> data/feedback.db  (operator verdicts)
```

## 1. Configure

```
cp .env.example .env     # then edit: keys, origins, reveal list
python -c "import secrets;print(secrets.token_urlsafe(32))"      # one key per operator / gateway
```

Production mode (`AWAAZ_MODE=production`) **refuses to start** without keys of at least 24 characters, an explicit
`AWAAZ_ORIGINS`, and a writable data dir. It also disables `/docs`, `/openapi.json`, `/samples` and `/ws/replay`.

## 2. Run

```
docker compose up -d --build                  # or: docker build --build-arg PREFETCH=1 ... for air-gapped hosts
curl -s localhost:8765/ready                  # 200 when models are loaded (first start downloads ~1.6 GB unless prefetched)
curl -s -H "Authorization: Bearer <key>" localhost:8765/metrics | head
python server/audit.py verify data/audit.jsonl   # OK - N line(s) checked
```

Without Docker: `pip install -r server/requirements.txt`, set the env vars, `python server/main.py` (binds 0.0.0.0 in
production, 127.0.0.1 in demo). Build the console with `cd web && npm ci && npm run build`, serve `web/dist` and
proxy `/api/` as in `deploy/nginx.conf`.

## 3. Hook up telephony

Fork the **caller leg only**, one stream per call, to `wss://<host>/api/ws/ingest` (or directly `/ws/ingest`).

1. Open the WebSocket with `Authorization: Bearer <gateway key>` (or subprotocol `bearer.<key>`).
2. First TEXT frame: `{"line_id": "L-1042", "codec": "pcmu", "rate": 8000}`  (`pcmu` / `pcma` / `pcm16`; 8000/16000/24000/48000 Hz).
3. Then BINARY frames of raw media (a 20 ms G.711 frame is 160 bytes). The server answers `hello`, then one `window`
   message every 3 s with the priority, level, cues and (redacted) transcript. `lag` events mean analysis fell behind and
   audio was dropped; `error` ends the session; close code **1013** = all slots busy (retry / route elsewhere).
4. `{"cmd":"lang","value":"hi"}` pins the language if the gateway knows it; `{"cmd":"flush"}` scores buffered audio at end of call.

Reference client: `server/bench_capacity.py` (`one_stream`). FreeSWITCH `mod_audio_fork` and Asterisk AudioSocket /
ExternalMedia can both feed this with a thin adapter; the adapter is yours to write and test.

## 4. Sizing (measured, then extrapolated carefully)

`python server/bench_capacity.py 1 2 3 4` streams N copies of a 42 s call as real-time 8 kHz mu-law through `/ws/ingest`
and measures how far behind real time each window result arrives.

| concurrent streams on one RTX 4060 laptop GPU | lag p50 / p95 | end-of-call lag | verdict |
|---|---|---|---|
| 1 | 1.5 s / 1.7 s | 1.5 s | keeps up |
| 2 | 1.7 s / 2.8 s | 2.6 s | keeps up (stable, not growing) |
| 3 | 7.8 s / 13.4 s | 13.4 s | falls behind (lag grows through the call) |
| 4 | 17 s / 26 s | 26 s | falls behind |

So **one such GPU sustains about 2 simultaneous calls** at the default 9 s context window with `large-v3-turbo`
(`AWAAZ_MAX_SESSIONS=2` is the default for that reason). Each stream costs ~0.2 real-time factor of GPU, but inference is
serialised behind one lock and Python/CPU work (prosody, resampling, JSON) competes, so measured capacity is far below
the naive 1/RTF.

Options tried, and rejected on the evidence (same evals as the README):

| setting | capacity | quality |
|---|---|---|
| `AWAAZ_CONTEXT=6` | 2 stay fine, 3 degrade less (lag ~6 s) | worse: the Digital-arrest victim call loses its scam name (65 high -> 50 medium) |
| `AWAAZ_WHISPER=medium` | not usable in the test | much worse: demo recall 3/6, scam names lost |

**Sizing rule of thumb: GPUs = ceil(peak concurrent lines / 2) on hardware like the test machine.** A data-centre GPU
(L4 / A10 / L40S) should do several times better, but that is unmeasured; run `bench_capacity.py` on the real host and set
`AWAAZ_MAX_SESSIONS` from it. Scale out by running one container per GPU behind a load balancer that health-checks
`/ready` and retries on close code 1013 (rate limits and admission counters are per process).

Real engineering levers not yet pulled: batching windows across calls on one GPU, a smaller/quantised ASR for the
non-urgent path, transcribing only the new window plus overlap instead of the full 9 s context each time.

## 5. Operate

| signal | meaning | action |
|---|---|---|
| `/ready` != 200 | models not loaded | do not route calls; check disk space / model cache |
| `awaaz_sessions_active` == `awaaz_sessions_max` | full | add a GPU host or accept 1013 rejections |
| `awaaz_busy_rejections_total` rising | demand above capacity | scale out |
| `awaaz_audio_dropped_seconds_total` > 0 | analysis behind real time | lower `AWAAZ_MAX_SESSIONS` |
| `awaaz_audit_write_failures_total` > 0 | **audit trail broken** | page someone; treat as an incident |
| `awaaz_auth_failures_total` spike | key guessing / misconfigured gateway | check source IPs at the proxy |
| `awaaz_window_latency_seconds` p95 | per-window analysis time | compare with `bench_capacity.py` baseline |

Back up `data/feedback.db`; verify and ship `data/audit.jsonl` (`python server/audit.py verify`). Rotate keys by editing
`.env` and restarting (sessions in flight end; gateways reconnect).

## 6. Tests

`python -m pytest tests` (48 tests, ~15 s, no GPU: models are stubbed) covers auth, rate limiting, size caps, admission
control, G.711 decoding, ingest protocol, audit chain tamper detection, server-side redaction and lexicon behaviour.
Model-level behaviour is covered by `server/eval.py`, `eval_hard.py`, `eval_heldout.py`, `eval_narrowband.py`.
