# server

FastAPI service. See the root README for the pipeline description.

- `main.py` — API + WebSocket endpoints (`/health`, `/analyze`, `/samples`, `/ws/live`, `/ws/replay`)
- `pipeline.py` — window analysis: emotion2vec+ → prosody → whisper → fraud lexicon → fused urgency + explanation
- `fraud_lexicon.py` — Hinglish scam-script patterns, scam signatures, PII redaction
- `make_samples.py` — synthetic demo calls (edge-tts)
- `eval.py` — prints the evaluation table used in the slides

Env: `AWAAZ_WHISPER` (default `small`), `AWAAZ_E2V` (default `iic/emotion2vec_plus_base`), `AWAAZ_WINDOW` (seconds, default 3), `PORT` (8765).
