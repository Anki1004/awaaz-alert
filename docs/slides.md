# AwaazAlert — 5 slides (mandatory format)

## 1 · Problem statement and understanding
- 1930 cybercrime helpline operators handle many simultaneous calls: victims mid-"digital arrest", fraudsters, informants, routine queries. Distress and urgency are hard to hear when you are on your 40th call.
- PS2 asks for real-time speech emotion signals to prioritise calls — **as indicative signals, not evidence**.
- Our reading: emotion alone is weak on Indian call audio (no Hindi SER benchmark exists; published call-centre accuracy is 55–65%). What *is* reliable is the **script**: Indian scams follow fixed scripts (impersonation → threat → secrecy → payment). So we fuse voice + words.

## 2 · Technical approach
- 16 kHz audio → 3 s windows with a 9 s rolling context.
- **Voice:** emotion2vec+ (FunASR) → fear/sad/anger probabilities. **Prosody:** librosa pitch σ, energy, voicing, expressed relative to *this caller's own baseline*. **Words:** faster-whisper large-v3-turbo (hi/en, language pinned, domain vocabulary prompt) → **Hinglish fraud-script lexicon** (6 categories, Devanagari + romanised) → named scam signature.
- urgency = 0.40·distress + 0.20·arousal + 0.30·fraud + 0.10·speech-rate; call level = max(peak-weighted windows, whole-transcript scan); named script ⇒ at least *medium*.
- FastAPI + WebSocket streaming; React dashboard. Audio stays in memory; transcript PII-redacted by default.

## 3 · Feasibility and viability
| sample (synthetic, edge-tts) | urgency | level | named script | latency / 3 s window |
|---|---|---|---|---|
| Digital arrest (scammer) | 65 | high | Digital arrest | ~1.1 s |
| Bank KYC / OTP (scammer) | 65 | high | Remote-access takeover | ~0.9 s |
| Victim calling after loss | 59 | medium | — (victim side) | ~1.3 s |
| Part-time task scam (English) | 50 | medium | Task / investment scam | ~0.4 s |
| Routine query (control) | 17 | low | — | ~1.3 s |
- Runs on one laptop GPU (RTX 4060): real-time factor ≈ 0.45. CPU-only works with whisper-small.
- Honest limits: demo calls are synthetic (flat affect) — they prove the pipeline and the script path, not emotion accuracy; no speaker diarisation yet; whisper mishears some Hinglish.

## 4 · Impact and benefit
- Operator sees *why* a line lit up (measured cues), not a black-box number → faster triage of real victims, fewer missed "money still in transit" calls where minutes matter (freeze requests to banks).
- Named script = instant playbook (Digital arrest → tell the victim to hang up, no transfer, file NCRP).
- Privacy by design: nothing stored, PII redacted, indicative-only framing — deployable on-prem at a state cyber cell.

## 5 · Comparison with existing platforms — our unique feature
- Call-centre emotion analytics (Uniphore, Cogito, Nemesysco): English, enterprise, black-box, no fraud-script awareness.
- 1930 today: Goa Police AI voice assistant does complaint *intake*; MHA ordered an AI upgrade (Jun 2026) — no distress/priority layer exists.
- Typical hackathon SER: upload a clip → one emotion label.
- **Unique:** fusion of voice + prosody-vs-baseline + **Hinglish scam-script detection with named patterns**, live streaming queue across lines, explanation built only from measured features, redaction and indicative-only banner baked into the UI.
