# AwaazAlert — distress + fraud-script radar for 1930 cybercrime helpline calls

**VecnaVerse 2026 · Problem statement 2 (Cybersecurity): Real-Time Speech Emotion Analysis for Cybercrime Investigation**

Cybercrime helpline operators juggle many calls: terrified victims mid-"digital arrest", fraudsters
being baited, routine status queries. AwaazAlert listens alongside the operator and gives one honest,
explainable number per call — **urgency 0–100** — built from three independent signals, so the queue can
be prioritised and the operator sees *why* a call lit up. It never claims to know who is lying.

> Indicative signal only. Scores help prioritise calls; they are not evidence of anyone's intent,
> honesty or guilt. Audio is analysed in memory and never stored. (Shown permanently in the UI.)

**▶ Try it:** [awaaz-alert.pages.dev](https://awaaz-alert.pages.dev) · **🎬 90-second video:** [AwaazAlert-demo-90s.mp4](https://awaaz-alert.pages.dev/AwaazAlert-demo-90s.mp4)

The hosted page is a **recorded demo**: it replays outputs the real pipeline produced on an RTX 4060 (`web/public/demo/`,
captured from `/ws/replay` and `/analyze`) in step with the call audio, so judges can click through without a GPU. Live
microphone analysis and uploads need the server below. Build it yourself with `cd web && VITE_STATIC_DEMO=1 npx vite build`.

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

| sample (synthetic, edge-tts) | kind | urgency | level | named script | fraud | avg latency / 3 s window | RTF |
|---|---|---|---|---|---|---|---|
| Digital arrest — scammer side | fraudster | **64** | high | Digital arrest | 0.56 | 760 ms | 0.26 |
| Victim calling 1930 after loss | victim | **67** | high | Digital arrest (described by victim) | 0.79 | 570 ms | 0.20 |
| Bank KYC / OTP scam | fraudster | **54** | medium | Remote-access takeover | 0.79 | 518 ms | 0.19 |
| Part-time task / investment scam (English) | fraudster | **50** | medium | Task / investment scam | 0.65 | 471 ms | 0.16 |
| Routine status query (control) | normal | **16** | low | — | 0.07 | 570 ms | 0.21 |

`python server/eval.py` → **control lowest: PASS**. RTX 4060 laptop GPU, faster-whisper large-v3-turbo fp16 + emotion2vec+ base.
Stage profile on one 3 s window: whisper ≈ 400 ms, emotion2vec ≈ 70 ms, prosody ≈ 5 ms.

What this table proves: the pipeline runs in real time (RTF < 0.3) and the **script path separates scam calls from a
calm control by 3–4×**. What it does not prove: emotion accuracy — the TTS voices are flat (distress 0.0–0.11 on every
clip), so the acoustic branch contributes almost nothing here. That branch needs consented real recordings.

## Stress test: does the score beat a plain keyword alarm?

The five demo calls above are a showcase, not a benchmark. To find out where the fused score is weak, we added 20
more synthetic calls aimed at the failure modes that matter for triage — a **calm** caller reporting a real loss, a
frightened caller who uses none of the scam vocabulary, **legitimate** calls full of scary words (OTP, police, parcel,
customs, KYC, SIM block), and scam scripts outside the demo set — and scored them against a naive baseline
(*alert if the Hinglish scam lexicon matches anything*). "Alert" = AwaazAlert level medium or above.

| set | how it was used | AwaazAlert: scams caught / false alerts | keyword-only: scams caught / false alerts |
|---|---|---|---|
| `samples/hard` (11 calls) | **dev set** — labels written first, then used to fix lexicon gaps (see `results-run1-before-fixes.json`: 3/6 and 1/5 before the fixes) | 5/6 · 1/5 | 5/6 · 2/5 |
| `samples/heldout` (9 calls) | written *after* those fixes, scored **once**, lexicon not touched afterwards | **2/5 · 1/4** | **5/5 · 2/4** |

Reproduce: `python server/make_hard_cases.py && python server/eval_hard.py` and `make_heldout.py` / `eval_heldout.py`.
The WAVs are git-ignored (regenerated by the `make_*.py` scripts with edge-tts); the labelled texts, expectations and the recorded `results.json` files are committed.

What we take from it, plainly:

- **On held-out calls the fused score caught fewer scams (2/5) than a keyword alarm (5/5)**, with fewer false alerts
  (1/4 vs 2/4). It under-ranks scams that light only one or two lexicon categories (electricity-bill, SIM/TRAI,
  family-emergency scripts). A keyword alarm is noisier but does not miss them.
- Legitimate calls and scam calls use the same words: a genuine "SIM block" question scores 0.375 on the lexicon, a real
  electricity scam 0.23. **No threshold on keyword evidence separates them** — we did not tune one, because on 20
  synthetic calls that would be overfitting. Separating them needs context (who is asking for what), i.e. real labelled
  calls, not more regexes.
- Whisper is **confidently wrong** on Hinglish: segment confidence stays 0.77–0.9 on garbled transcripts, even with
  added noise. We tried an "unclear transcript" state driven by that confidence; it never fired, so we removed it
  rather than ship a safety net that does not catch anything.
- Two changes survived because they are design decisions, not tuning: a first-person **loss report** (past-tense "paise
  nikal gaye", "OTP bata diya") floors a call at *medium* so a calm victim is not ranked as routine, and the call
  language is now pinned from the audio (needs 5 s of speech, Hindi preferred unless English is clearly ahead) instead
  of from the first 3 s window's auto-detect (a Hindi "Namaste" opener used to pin English and decode the whole call
  as translated English).

So the claim we make is narrow: AwaazAlert is a **ranking aid for a human operator** — explainable, real-time, private by
design — and its accuracy on real helpline calls is **unmeasured**. The synthetic voices are flat, so the acoustic
branch is untested too. The next step is not another model; it is consented, expert-labelled calls and a human-only vs
human-plus-AwaazAlert triage comparison.

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
