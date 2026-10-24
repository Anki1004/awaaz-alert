"""
AwaazAlert analysis pipeline.

Audio arrives as 16 kHz mono float32. Every WINDOW (3 s) we emit one result, but the signals are
computed with context, because 3 s in isolation is too little for speech:

  1. acoustic emotion  — emotion2vec+ (FunASR) on the current window; wav2vec2 SER as fallback.
  2. prosody           — pitch σ, energy, voicing on the current window, then expressed RELATIVE to the
                          caller's own running baseline (speaker normalisation). "Louder/shakier than this
                          person has been so far" is the distress cue; absolute loudness is just the mic.
  3. transcript        — faster-whisper on the last CONTEXT seconds (default 9 s) with word timestamps;
                          the words that fall inside the current window are shown, the whole context is
                          scanned by the Hinglish fraud lexicon so multi-category scripts register.

Design rules:
  * Audio is processed in memory and discarded. Nothing is written to disk.
  * Every number in the explanation comes from a measured feature, never a guess.
  * Output is an INDICATIVE signal for call prioritisation, never a judgement of a person.
"""
from __future__ import annotations

import logging
import math
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field, asdict
from statistics import median

import numpy as np

from fraud_lexicon import scan as fraud_scan, redact

log = logging.getLogger("awaaz")
SR = 16000
# One GPU, one stream of inference: concurrent whisper/emotion2vec calls from several lines corrupt each
# other's outputs (seen as hallucinated cues on a calm call while another call was being scored).
_INFER_LOCK = threading.Lock()
CONTEXT_S = float(os.environ.get("AWAAZ_CONTEXT", "9"))

# Vocabulary the ASR should expect. Whisper conditions on this prompt, which stops "CBI" turning into
# "नेज्ट बी" and "OTP" into "अदिपी". One prompt per language: feeding Devanagari to an English call makes
# whisper hallucinate Hindi words from the prompt (seen: "पार्सल, वारंट" injected into an English task-scam call).
ASR_PROMPT = {
    "hi": ("1930 साइबर हेल्पलाइन कॉल. CBI, ED, पुलिस, साइबर सेल, डिजिटल अरेस्ट, पार्सल, कूरियर, FedEx, आधार, KYC, OTP, "
           "UPI, Paytm, PhonePe, AnyDesk, स्क्रीन शेयर, अकाउंट ब्लॉक, मनी लॉन्ड्रिंग, ड्रग्स, गिरफ्तार, वारंट, RBI, SBI, HDFC, "
           "पैसे कट गए, फ्रॉड हो गया, मदद कीजिए."),
    "en": ("1930 cyber helpline call. CBI, ED, police, cyber cell, digital arrest, parcel, courier, FedEx, Aadhaar, KYC, OTP, "
           "UPI, Paytm, PhonePe, AnyDesk, TeamViewer, screen share, account block, money laundering, drugs, arrest warrant, "
           "RBI, SBI, HDFC, part time job, Telegram task, investment, security deposit, refundable, lottery."),
}
ASR_PROMPT["default"] = ASR_PROMPT["hi"]
# Off by default: large-v3-turbo no longer needs it, and a prompt makes whisper copy its words into calm calls.
USE_PROMPT = os.environ.get("AWAAZ_PROMPT", "0") == "1"

# ----------------------------------------------------------------------------- models (lazy)
_whisper = None
_emotion = None          # ("e2v", model) | ("hf", pipeline)
_device = "cpu"


def _torch_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def load_models(whisper_size: str | None = None) -> dict:
    """Load once. Returns a status dict for /health."""
    global _whisper, _emotion, _device
    _device = _torch_device()
    status = {"device": _device, "whisper": None, "emotion": None, "context_s": CONTEXT_S}

    size = whisper_size or os.environ.get("AWAAZ_WHISPER", "large-v3-turbo" if _device == "cuda" else "small")
    for candidate in [size, "small"]:
        try:
            from faster_whisper import WhisperModel
            compute = "float16" if _device == "cuda" else "int8"
            _whisper = WhisperModel(candidate, device=_device, compute_type=compute)
            status["whisper"] = f"faster-whisper {candidate} ({compute})"
            break
        except Exception as e:  # noqa: BLE001
            log.warning("whisper %s failed: %s", candidate, e)
            status["whisper"] = f"unavailable: {e}"

    try:
        from funasr import AutoModel
        m = AutoModel(model=os.environ.get("AWAAZ_E2V", "iic/emotion2vec_plus_base"), hub="ms",
                      device=_device, disable_update=True, disable_pbar=True, log_level="ERROR")
        _emotion = ("e2v", m)
        status["emotion"] = "emotion2vec+ base (FunASR)"
    except Exception as e:  # noqa: BLE001
        log.warning("emotion2vec unavailable (%s); falling back to wav2vec2 SER", e)
        try:
            from transformers import pipeline
            p = pipeline("audio-classification",
                         model="ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition",
                         device=0 if _device == "cuda" else -1)
            _emotion = ("hf", p)
            status["emotion"] = "wav2vec2-xlsr SER (HF fallback)"
        except Exception as e2:  # noqa: BLE001
            log.exception("no emotion model")
            status["emotion"] = f"unavailable: {e2}"
    return status


# ----------------------------------------------------------------------------- audio helpers
def decode_to_pcm16k(data: bytes) -> np.ndarray:
    """Any container (webm/ogg/mp3/wav/m4a) -> float32 mono 16 kHz, via ffmpeg in memory."""
    cmd = ["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(SR), "pipe:1"]
    out = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if out.returncode != 0 or not out.stdout:
        raise ValueError(f"ffmpeg could not decode audio: {out.stderr.decode(errors='ignore')[:200]}")
    return np.frombuffer(out.stdout, dtype=np.float32).copy()


def pcm16_bytes_to_float(data: bytes) -> np.ndarray:
    return (np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0).copy()


def has_speech(audio: np.ndarray) -> bool:
    """Cheap energy gate so silence never reaches whisper (which hallucinates on it, slowly)."""
    if len(audio) < SR // 4:
        return False
    frame = 400
    n = len(audio) // frame
    if n == 0:
        return False
    rms = np.sqrt((audio[: n * frame].reshape(n, frame) ** 2).mean(axis=1))
    return float((rms > 0.01).mean()) > 0.08 and float(rms.max()) > 0.02



import re as _re


def clean_text(text: str) -> str:
    """Strip whisper hallucinations: runs of the same token/bigram, and windows that are mostly repeats.
    Returns "" when the text is not credible speech."""
    if not text:
        return ""
    toks = text.replace("�", " ").split()
    if not toks:
        return ""
    out = []
    for t in toks:  # collapse 3+ identical consecutive tokens to one
        if len(out) >= 2 and out[-1] == t and out[-2] == t:
            continue
        out.append(t)
    # collapse repeated bigrams: "का पार्सल, का पार्सल, का पार्सल"
    i = 0; res = []
    while i < len(out):
        if i + 3 < len(out) and out[i] == out[i + 2] and out[i + 1] == out[i + 3]:
            j = i
            while j + 1 < len(out) and out[j] == out[i] and out[j + 1] == out[i + 1]:
                j += 2
            res += out[i:i + 2]; i = j
        else:
            res.append(out[i]); i += 1
    uniq_ratio = len(set(res)) / max(1, len(res))
    if len(res) >= 6 and uniq_ratio < 0.45:
        return ""  # a real sentence is not 55% repeats
    return _re.sub(r"\s+", " ", " ".join(res)).strip()

# ----------------------------------------------------------------------------- features
EMO_KEYS = ["angry", "disgusted", "fearful", "happy", "neutral", "sad", "surprised", "other"]


def _norm_label(label: str) -> str:
    l = label.lower()
    if "/" in l:
        l = l.split("/")[-1]
    l = l.strip()
    aliases = {"anger": "angry", "fear": "fearful", "disgust": "disgusted", "sadness": "sad", "calm": "neutral",
               "surprise": "surprised", "<unk>": "other", "unknown": "other", "unk": "other"}
    return aliases.get(l, l)


def emotion_probs(audio: np.ndarray) -> dict[str, float]:
    probs = {k: 0.0 for k in EMO_KEYS}
    if _emotion is None or len(audio) < SR // 2 or not has_speech(audio):
        probs["other"] = 1.0
        return probs
    kind, model = _emotion
    try:
        if kind == "e2v":
            res = model.generate(audio, granularity="utterance", extract_embedding=False)
            r = res[0]
            for lab, sc in zip(r["labels"], r["scores"]):
                k = _norm_label(lab)
                probs[k if k in probs else "other"] += float(sc)
        else:
            res = model({"array": audio, "sampling_rate": SR}, top_k=None)
            for item in res:
                k = _norm_label(item["label"])
                probs[k if k in probs else "other"] += float(item["score"])
    except Exception:  # noqa: BLE001
        log.exception("emotion inference failed")
        probs["other"] = 1.0
    s = sum(probs.values()) or 1.0
    return {k: round(v / s, 4) for k, v in probs.items()}


def prosody_raw(audio: np.ndarray) -> dict:
    import librosa
    if len(audio) < SR // 4 or not has_speech(audio):
        return {"f0_mean": 0.0, "f0_std": 0.0, "rms_mean": 0.0, "rms_peak": 0.0, "voiced_ratio": 0.0, "speech": False}
    f0 = librosa.yin(audio, fmin=70, fmax=400, sr=SR, frame_length=1024, hop_length=256)
    rms = librosa.feature.rms(y=audio, frame_length=1024, hop_length=256)[0]
    voiced = rms > max(0.01, float(np.percentile(rms, 30)))
    f0v = f0[voiced] if voiced.any() else f0
    return {"f0_mean": float(np.median(f0v)) if len(f0v) else 0.0, "f0_std": float(np.std(f0v)) if len(f0v) else 0.0,
            "rms_mean": float(rms.mean()), "rms_peak": float(rms.max()), "voiced_ratio": float(voiced.mean()), "speech": True}


class SpeakerBaseline:
    """Running median of this caller's pitch σ and energy. Arousal is deviation from it, not an absolute."""

    def __init__(self):
        self.f0_std: list[float] = []
        self.rms: list[float] = []

    def arousal(self, p: dict) -> float:
        if not p.get("speech"):
            return 0.0
        if len(self.f0_std) >= 2:
            b_f0 = max(5.0, median(self.f0_std))
            b_rms = max(0.005, median(self.rms))
            dev_f0 = (p["f0_std"] - b_f0) / b_f0          # +1.0 = twice as variable as usual
            dev_rms = (p["rms_mean"] - b_rms) / b_rms
            a = 0.5 + 0.30 * np.tanh(dev_f0) + 0.25 * np.tanh(dev_rms) + 0.15 * (p["voiced_ratio"] - 0.5)
        else:  # first windows: absolute but conservative
            a = 0.25 + 0.25 * min(1.0, p["f0_std"] / 80.0) + 0.15 * min(1.0, p["rms_mean"] / 0.15)
        self.f0_std.append(p["f0_std"]); self.rms.append(p["rms_mean"])
        if len(self.f0_std) > 40:
            self.f0_std.pop(0); self.rms.pop(0)
        return float(min(1.0, max(0.0, a)))


def detect_call_language(context: np.ndarray) -> str | None:
    """Pin the call language from the audio itself, before any text is decoded. Letting transcribe() auto-detect on the
    first 3 s window pinned a Hindi opener to "en" and decoded the whole call as translated English. Only hi/en are
    candidates; Hinglish helpline callers lean Hindi, so Hindi wins unless English is clearly ahead."""
    if _whisper is None or len(context) < SR * 5 or not has_speech(context):
        return None  # a 3 s opener ("Namaste") is too little to tell Hinglish from English
    try:
        _, _, probs = _whisper.detect_language(audio=context[: 12 * SR])
        d = dict(probs)
        p_hi, p_en = d.get("hi", 0.0), d.get("en", 0.0)
        if p_hi + p_en < 0.5:
            return None
        return "hi" if p_hi >= 0.5 * p_en else "en"
    except Exception:  # noqa: BLE001
        log.exception("language detection failed")
        return None


def transcribe_context(context: np.ndarray, window_start_in_context: float, language: str | None = None) -> dict:
    """Transcribe the context; return words inside the current window + the full context text."""
    if _whisper is None or len(context) < SR // 2 or not has_speech(context):
        return {"window_text": "", "context_text": "", "language": None, "words_per_sec": 0.0}
    try:
        segments, info = _whisper.transcribe(
            context, language=language, beam_size=1, best_of=1, temperature=[0.0, 0.2], vad_filter=True,
            repetition_penalty=1.15, no_repeat_ngram_size=3,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200},
            word_timestamps=True, condition_on_previous_text=False,
            initial_prompt=(ASR_PROMPT.get(language or "default", ASR_PROMPT["default"]) if USE_PROMPT else None),
            no_speech_threshold=0.6, log_prob_threshold=-1.0, compression_ratio_threshold=2.4,
        )
        words, texts, confs = [], [], []
        for s in segments:
            texts.append(s.text.strip())
            if getattr(s, "avg_logprob", None) is not None:
                confs.append(math.exp(min(0.0, s.avg_logprob)))
            for w in (s.words or []):
                words.append((w.start, w.end, w.word))
        context_text = clean_text(" ".join(t for t in texts if t).strip())
        win_words = [w for (st, en, w) in words if en > window_start_in_context]
        window_text = clean_text("".join(win_words).strip()) if win_words else ""
        if not window_text and context_text and window_start_in_context <= 0.5:
            window_text = context_text
        dur = max(0.5, len(context) / SR - window_start_in_context)
        wps = len(window_text.split()) / dur if window_text else 0.0
        if wps > 7.0:  # faster than any human speaker: decoder loop, not speech
            window_text, wps = "", 0.0
        return {"window_text": window_text, "context_text": context_text, "language": getattr(info, "language", None), "words_per_sec": round(wps, 2),
                "asr_conf": round(sum(confs) / len(confs), 3) if confs else None}
    except Exception:  # noqa: BLE001
        log.exception("transcription failed")
        return {"window_text": "", "context_text": "", "language": None, "words_per_sec": 0.0}


# ----------------------------------------------------------------------------- fusion
@dataclass
class WindowResult:
    t_start: float
    t_end: float
    emotion: dict
    prosody: dict
    transcript: str
    transcript_redacted: str
    language: str | None
    fraud: dict            # scanned over the CONTEXT text (multi-category scripts need > 3 s)
    distress: float
    urgency: int
    level: str
    explain: list = field(default_factory=list)
    latency_ms: int = 0
    asr_conf: float | None = None   # mean exp(avg_logprob) of the decoded segments: how sure Whisper was

    def to_dict(self) -> dict:
        return asdict(self)


def level_for(urgency: int) -> str:
    if urgency >= 80:
        return "critical"
    if urgency >= 60:
        return "high"
    if urgency >= 35:
        return "medium"
    return "low"


class Session:
    """One call. Holds the rolling audio context and the speaker baseline. Never persisted."""

    def __init__(self, language: str | None = None, window_s: float = 3.0):
        self.language = language
        self.window_s = window_s
        self.context = np.zeros(0, dtype=np.float32)
        self.baseline = SpeakerBaseline()
        self.windows: list[dict] = []
        self.t = 0.0
        self.full_text: list[str] = []

    def feed(self, window: np.ndarray) -> WindowResult:
        t0 = time.perf_counter()
        self.context = np.concatenate([self.context, window])[-int(CONTEXT_S * SR):]
        win_start_in_ctx = max(0.0, len(self.context) / SR - len(window) / SR)

        pro = prosody_raw(window)
        arousal = self.baseline.arousal(pro)
        with _INFER_LOCK:
            emo = emotion_probs(window)
            if self.language is None:
                self.language = detect_call_language(self.context)
            tr = transcribe_context(self.context, win_start_in_ctx, self.language)
        if tr["window_text"]:
            self.full_text.append(tr["window_text"])
        fraud = fraud_scan(tr["context_text"])
        # local matches for highlighting: scan the window text itself
        local = fraud_scan(tr["window_text"])
        fraud["matches"] = local["matches"]

        distress = min(1.0, emo["fearful"] * 1.0 + emo["sad"] * 0.8 + emo["angry"] * 0.6 + emo["surprised"] * 0.1)
        rate_term = min(1.0, max(0.0, (tr["words_per_sec"] - 2.2) / 2.5))
        fused = 0.40 * distress + 0.20 * arousal + 0.30 * fraud["score"] + 0.10 * rate_term
        urgency = int(round(100 * fused))
        if fraud["signature"]:
            urgency = max(urgency, 40)  # a named scam script is actionable on its own, whatever the affect

        explain = []
        top_emo = max(emo, key=emo.get)
        if emo[top_emo] >= 0.35 and top_emo not in ("neutral", "other", "happy"):
            explain.append(f"voice sounds {top_emo} ({int(emo[top_emo] * 100)}%)")
        if arousal >= 0.65 and pro.get("speech"):
            explain.append(f"more agitated than this caller's baseline: pitch σ {pro['f0_std']:.0f} Hz, energy {pro['rms_mean']:.3f}")
        if fraud["signature"]:
            explain.append(f"script pattern: {fraud['signature']}")
        lit = [c for c, v in fraud["categories"].items() if v >= 0.4]
        if lit:
            terms = sorted({m['term'].lower() for m in fraud_scan(tr["context_text"])['matches']})[:6]
            explain.append(f"fraud cues ({', '.join(lit)}): {', '.join(terms)}")
        if rate_term >= 0.4:
            explain.append(f"hurried speech: {tr['words_per_sec']} words/s")
        if not explain:
            explain.append("no distress or fraud cues in this window")

        res = WindowResult(
            t_start=round(self.t, 2), t_end=round(self.t + len(window) / SR, 2),
            emotion=emo, prosody={**{k: (round(v, 4) if isinstance(v, float) else v) for k, v in pro.items()}, "arousal": round(arousal, 3)},
            transcript=tr["window_text"], transcript_redacted=redact(tr["window_text"]), language=tr["language"],
            fraud=fraud, distress=round(distress, 3), urgency=urgency, level=level_for(urgency), explain=explain,
            latency_ms=int((time.perf_counter() - t0) * 1000), asr_conf=tr.get("asr_conf"),
        )
        self.t += len(window) / SR
        self.windows.append(res.to_dict())
        return res

    def overall(self) -> dict:
        return summarize(self.windows, self.t, " ".join(self.full_text))


def analyze_file(data: bytes, window_s: float = 3.0, language: str | None = None) -> dict:
    audio = decode_to_pcm16k(data)
    n = int(window_s * SR)
    s = Session(language, window_s)
    for i in range(0, max(1, len(audio)), n):
        chunk = audio[i:i + n]
        if len(chunk) < SR * 0.6:
            break
        s.feed(chunk)
    out = s.overall()
    out["duration"] = round(len(audio) / SR, 2)
    return out


def summarize(windows: list[dict], duration: float, full_text: str = "") -> dict:
    if not windows:
        return {"duration": duration, "windows": [], "overall": {"urgency": 0, "level": "low", "signature": None, "explain": ["no speech"]}}
    urg = [w["urgency"] for w in windows]
    peak_mean = 0.6 * max(urg) + 0.4 * (sum(urg) / len(urg))
    # whole-call script scan: a scam unfolds over a minute, not inside one window
    full = full_text or " ".join(w["transcript"] for w in windows if w["transcript"]).strip()
    fr = fraud_scan(full)
    max_distress = max(w["distress"] for w in windows)
    max_arousal = max(w["prosody"].get("arousal", 0) for w in windows)
    call_level = 100 * (0.30 * max_distress + 0.15 * max_arousal + 0.45 * fr["score"] + 0.10 * min(1.0, len(fr["matches"]) / 8))
    sig = fr["signature"] or next((w["fraud"]["signature"] for w in windows if w["fraud"]["signature"]), None)
    # A calm caller reporting a real loss has flat affect and no scam script, so neither of the other two signals
    # fires. A first-person loss report is itself a reason for a human to pick up soon: floor it at "medium".
    loss_report = fr["categories"].get("victim_loss", 0) >= 0.5
    overall_u = int(round(max(peak_mean, call_level, 45 if sig else 0, 35 if loss_report else 0)))
    confs = [w["asr_conf"] for w in windows if w.get("asr_conf") is not None]
    asr_conf = round(sum(confs) / len(confs), 2) if confs else None
    explain = []
    if sig:
        explain.append(f"script pattern: {sig}")
    lit = [c for c, v in fr["categories"].items() if v >= 0.4]
    if lit:
        terms = sorted({m['term'].lower() for m in fr['matches']})[:8]
        explain.append(f"fraud cues across the call ({', '.join(lit)}): {', '.join(terms)}")
    if loss_report:
        explain.append("caller reports a loss in their own words: held at medium or above for a human to pick up")
    seen = set(explain)
    for w in sorted(windows, key=lambda x: -x["urgency"])[:3]:
        for e in w["explain"]:
            if e not in seen and not e.startswith("no distress") and not e.startswith("script pattern") and not e.startswith("fraud cues"):
                seen.add(e)
                explain.append(f"[{int(w['t_start'])}s] {e}")
    return {
        "duration": round(duration, 2),
        "windows": windows,
        "overall": {"urgency": overall_u, "level": level_for(overall_u), "signature": sig,
                    "explain": explain or ["no distress or fraud cues detected"],
                    "asr_confidence": asr_conf, "loss_report": loss_report,
                    "fraud": {"score": fr["score"], "categories": fr["categories"]},
                    "transcript": full, "transcript_redacted": redact(full),
                    "avg_latency_ms": int(sum(w["latency_ms"] for w in windows) / len(windows))},
    }
