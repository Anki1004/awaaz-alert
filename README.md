# AwaazAlert — distress + fraud-script radar for 1930 cybercrime helpline calls

**VecnaVerse 2026 · Problem statement 2 (Cybersecurity): Real-Time Speech Emotion Analysis for Cybercrime Investigation**

Cybercrime helpline operators juggle many calls: terrified victims mid-"digital arrest", fraudsters
being baited, routine status queries. AwaazAlert listens alongside the operator and gives one honest,
explainable number per call — **urgency 0–100** — built from three independent signals, so the queue can
be prioritised and the operator sees *why* a call lit up. It never claims to know who is lying.

> Indicative signal only. Scores help prioritise calls; they are not evidence of anyone's intent,
> honesty or guilt. Audio is analysed in memory and never stored. (Shown permanently in the UI.)

## What makes it different from "upload audio → emotion label"

| | Typical SER demo | AwaazAlert |
|---|---|---|
| Input | one uploaded clip | **live mic / call stream**, 3-second rolling windows, plus upload and replay |
| Signal | one emotion classifier | **fusion**: acoustic emotion (emotion2vec+) + prosody (pitch σ, energy, voicing) + **Hinglish fraud-script detection** on the live transcript |
| Language | English benchmark clips | Hindi / Hinglish / Indian English transcript (faster-whisper); lexicon in Devanagari *and* romanised Hindi |
| Output | "angry 0.71" | urgency + level + **named scam pattern** ("Digital arrest", "Bank/KYC block", "Task scam"…) + **explanation built only from measured features** |
| Operator view | single screen | **priority queue** across calls, timeline, highlighted cues, PII redaction (on by default) |
| Responsible AI | a sentence | banner in the UI, no storage, indicative-only framing, redaction, explainability — the PS objective verbatim |

## How it works

```
mic / file ──► 16 kHz PCM ──► 3 s window ──┬─► emotion2vec+ (FunASR)  → fearful/sad/angry/… probs ─┐
                                           ├─► librosa prosody         → pitch σ, RMS, voiced ratio → arousal
                                           └─► faster-whisper (hi/en)  → transcript → fraud lexicon → categories + signature
                                                                                                         │
             urgency = 100 × (0.40·distress + 0.20·arousal + 0.30·fraud + 0.10·speech-rate)  ◄──────────┘
             distress = P(fear) + 0.8·P(sad) + 0.6·P(angry) + 0.2·P(surprised)
             level: <35 low · 35–59 medium · 60–79 high · ≥80 critical
             overall (per call) = 0.6·max(window) + 0.4·mean(window)   — one critical moment outweighs a calm average
```

Every line in the "Why this score" panel is generated from a measured value (`pitch σ 71 Hz`, `fraud cues
(impersonation, threat): cbi, arrest, parcel`), never from a template guess.

### Fraud-script lexicon (`server/fraud_lexicon.py`)
Six categories mirror how Indian scam calls are actually scripted: **impersonation** (CBI/ED/police/bank/courier),
**threat** (arrest, warrant, account block, drugs), **payment** (OTP, UPI, AnyDesk, gift card, deposit),
**urgency** (abhi, turant, 2 ghante), **secrecy** (kisi ko mat batana, phone mat kaatna), **victim_loss**
(paise kat gaye, madad kijiye). Two strong hits saturate a category; ≥2 categories plus a signature regex names
the scam. Patterns exist in Devanagari and romanised Hindi because Whisper emits both.

### Privacy
Audio never touches disk. Transcripts are PII-redacted (phone, Aadhaar, card, UPI id, OTP digits, PAN) before
display; the operator can reveal with an explicit toggle. No accounts, no logs of call content.

## Run

```bash
# server (Python 3.11, ffmpeg on PATH; GPU optional — RTX 4060 used in the demo)
pip install -r server/requirements.txt
python server/make_samples.py        # 5 synthetic Hinglish demo calls via edge-tts (optional)
python server/main.py                # http://127.0.0.1:8765  (first run downloads whisper-small + emotion2vec+ ≈ 1.6 GB)

# dashboard
cd web && npm install && npm run dev # http://127.0.0.1:5173  (proxies /api and /ws to the server)

# evaluation table used in the slides
python server/eval.py
```

## Evaluation

_Filled from `python server/eval.py` on the bundled samples — see "Results" below after a run._

## Honest limitations

- Open SER models are trained on English acted corpora (IEMOCAP etc.); published accuracy is ~70–80% there
  and 55–65% on real call audio. **Hindi has no public benchmark**, which is exactly why emotion is only 40%
  of the score and the transcript/script path carries the rest.
- The bundled demo calls are **synthetic (edge-tts)**: flat affect, scripted words. They prove the pipeline and
  the fraud path, not emotion accuracy. Real, consented recordings are needed for any accuracy claim.
- Whisper-small mishears Hinglish at times; lexicon matching is tolerant but not perfect.
- One speaker per stream; no diarisation (victim vs. fraudster) yet.

## Roadmap (what we would ship next)
Speaker diarisation (victim/caller split) · fine-tune emotion2vec+ on consented Hindi helpline audio ·
SIP/telephony tap for real 1930 lines · operator feedback loop ("was this flagged correctly?") to calibrate
thresholds · on-prem deployment package.

## Stack
FastAPI · faster-whisper · FunASR emotion2vec+ · librosa · React + Vite + Tailwind v4 · WebSocket streaming.
