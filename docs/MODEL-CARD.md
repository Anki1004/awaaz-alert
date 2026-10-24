# AwaazAlert model card

## Intended use
A **ranking aid** for human operators at a cybercrime helpline: it orders live calls by an explainable priority score and
shows which cues produced it. A person decides what to do. It is not evidence, not a verdict on anyone's honesty or
intent, and not a lie detector.

## Out of scope
Automated decisions about individuals; use as evidence or for enforcement action; languages other than Hindi/English;
mixed-speaker audio (no diarisation); non-telephone audio quality not tested.

## What is inside
| part | component | role |
|---|---|---|
| speech to text | faster-whisper `large-v3-turbo` (fp16, GPU), language pinned from >= 5 s of audio (Hindi preferred unless English is clearly ahead) | transcript used by the lexicon |
| voice emotion | emotion2vec+ base (FunASR) | fear / sad / angry / surprised / neutral / happy probabilities |
| prosody | librosa pitch / energy, expressed relative to *this caller's own* rolling baseline | arousal |
| script cues | hand-written Hinglish lexicon: impersonation, threat, payment, urgency, secrecy, victim-loss; named scam signatures | fraud-script score |
| fusion | fixed weights (distress 0.40, arousal 0.20, script 0.30, speech rate 0.10); named script floors at medium; first-person loss report floors at medium | priority 0-100, level low/medium/high/critical |

No model was trained or fine-tuned by this project. The weights are hand-set, not learned or calibrated.

## Evidence (all synthetic unless stated; see README "Evaluation" and "Stress test")
* 5 demo calls ordered as designed; control lowest.
* 20 further synthetic stress calls: on 5 never-seen scams a plain keyword alarm caught 5, AwaazAlert 2, with fewer false alerts (1/4 vs 2/4).
* 8 kHz G.711 mu-law (telephone codec) on 25 clean synthetic calls: scams caught 10/15 vs 11/15 at 16 kHz, false alerts 0/10 vs 2/10, mean urgency drift 3.8 points.
* Real-time factor 0.13-0.26 per stream on an RTX 4060 laptop GPU; concurrent capacity in `docs/DEPLOYMENT.md`.
* **No evaluation on real helpline calls. Accuracy in deployment is unknown.**

## Known failure modes
1. Scam and legitimate calls share vocabulary (OTP, police, parcel, customs, KYC, SIM block). A keyword score cannot tell
   "bank asked for my OTP" from "I received an OTP". Legitimate calls full of these words get scored up.
2. Scam scripts that light only one or two cue categories (electricity bill, SIM / TRAI, family emergency) are under-ranked.
3. Whisper is confidently wrong on Hinglish and noise; transcripts feed everything downstream. Its own confidence score does not flag this.
4. A calm victim with no scam vocabulary and no panic can score low unless they state a loss in past tense.
5. Emotion models were trained on acted English corpora; their behaviour on real distressed Hindi speech is untested here.
6. Pitch baselines may behave differently by speaker sex, age and accent. Not tested.
7. Redaction misses digits spoken as words and misheard digits (docs/SECURITY.md).

## Human oversight and updates
Operators can record agree / too high / too low / missed scam / false alarm on every call; these verdicts are the raw
material for the evaluation in `docs/PILOT.md`. Lexicon or weight changes must be re-run through `server/eval*.py`
and the held-out set, and recorded in the changelog; never tune against the held-out set (add new cases instead).
