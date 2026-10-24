"""
AwaazAlert analysis pipeline.

One 3-second window of 16 kHz mono audio goes through three independent signals that are then
fused into one urgency score with an explanation:

  1. acoustic emotion  — emotion2vec+ (FunASR) if available, else a wav2vec2 SER model (HF).
                          Language-agnostic-ish paralinguistics: fear / sad / angry / neutral ...
  2. prosody           — pitch variability, energy, voiced ratio, speaking rate (librosa).
                          Cheap, fully language-independent arousal cues.
  3. transcript        — faster-whisper (Hindi/English) -> Hinglish fraud-script lexicon.

Design rules:
  * Audio is processed in memory and discarded. Nothing is written to disk.
  * Every number in the explanation comes from a measured feature, never a guess.
  * Output is an INDICATIVE signal for call prioritisation, never a judgement of a person.
"""
from __future__ import annotations

import io
import logging
import math
import os
import subprocess
import time
from dataclasses import dataclass, field, asdict

import numpy as np

from fraud_lexicon import scan as fraud_scan, redact

log = logging.getLogger("awaaz")
SR = 16000

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
    status = {"device": _device, "whisper": None, "emotion": None}

    size = whisper_size or os.environ.get("AWAAZ_WHISPER", "small")
    try:
        from faster_whisper import WhisperModel
        compute = "float16" if _device == "cuda" else "int8"
        _whisper = WhisperModel(size, device=_device, compute_type=compute)
        status["whisper"] = f"faster-whisper {size} ({compute})"
    except Exception as e:  # noqa: BLE001
        log.exception("whisper load failed")
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
    """Return a probability dict over EMO_KEYS (sums ~1)."""
    probs = {k: 0.0 for k in EMO_KEYS}
    if _emotion is None or len(audio) < SR // 2:
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


def prosody(audio: np.ndarray) -> dict:
    """Pitch / energy / voicing statistics. All values measured, none assumed."""
    import librosa
    if len(audio) < SR // 4:
        return {"f0_mean": 0, "f0_std": 0, "rms_mean": 0, "rms_peak": 0, "voiced_ratio": 0, "arousal": 0.0}
    f0 = librosa.yin(audio, fmin=70, fmax=400, sr=SR, frame_length=1024, hop_length=256)
    rms = librosa.feature.rms(y=audio, frame_length=1024, hop_length=256)[0]
    voiced = rms > max(0.01, float(np.percentile(rms, 30)))
    f0v = f0[voiced] if voiced.any() else f0
    f0_mean = float(np.median(f0v)) if len(f0v) else 0.0
    f0_std = float(np.std(f0v)) if len(f0v) else 0.0
    rms_mean = float(rms.mean())
    rms_peak = float(rms.max())
    voiced_ratio = float(voiced.mean())
    # arousal: high pitch variability + high energy + dense voicing -> agitated speech. Each term 0..1.
    arousal = min(1.0, 0.45 * min(1.0, f0_std / 60.0) + 0.35 * min(1.0, rms_mean / 0.12) + 0.20 * voiced_ratio)
    return {"f0_mean": round(f0_mean, 1), "f0_std": round(f0_std, 1), "rms_mean": round(rms_mean, 4),
            "rms_peak": round(rms_peak, 4), "voiced_ratio": round(voiced_ratio, 3), "arousal": round(arousal, 3)}


def transcribe(audio: np.ndarray, language: str | None = None) -> dict:
    if _whisper is None or len(audio) < SR // 2:
        return {"text": "", "language": None, "words_per_sec": 0.0}
    try:
        segments, info = _whisper.transcribe(audio, language=language, beam_size=1, vad_filter=True,
                                             condition_on_previous_text=False, without_timestamps=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        dur = max(0.5, len(audio) / SR)
        wps = len(text.split()) / dur if text else 0.0
        return {"text": text, "language": getattr(info, "language", None), "words_per_sec": round(wps, 2)}
    except Exception:  # noqa: BLE001
        log.exception("transcription failed")
        return {"text": "", "language": None, "words_per_sec": 0.0}


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
    fraud: dict
    distress: float
    urgency: int
    level: str
    explain: list = field(default_factory=list)
    latency_ms: int = 0

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


def analyze_window(audio: np.ndarray, t_start: float = 0.0, language: str | None = None) -> WindowResult:
    t0 = time.perf_counter()
    emo = emotion_probs(audio)
    pro = prosody(audio)
    tr = transcribe(audio, language)
    fraud = fraud_scan(tr["text"])

    # distress = negative, high-stakes affect on the victim side
    distress = min(1.0, emo["fearful"] * 1.0 + emo["sad"] * 0.8 + emo["angry"] * 0.6 + emo["surprised"] * 0.2)
    rate_term = min(1.0, max(0.0, (tr["words_per_sec"] - 2.0) / 2.5))  # > 2 w/s starts to count as hurried
    fused = 0.40 * distress + 0.20 * pro["arousal"] + 0.30 * fraud["score"] + 0.10 * rate_term
    urgency = int(round(100 * fused))

    explain = []
    top_emo = max(emo, key=emo.get)
    if emo[top_emo] >= 0.35 and top_emo not in ("neutral", "other", "happy"):
        explain.append(f"voice sounds {top_emo} ({int(emo[top_emo]*100)}%)")
    if pro["arousal"] >= 0.55:
        explain.append(f"agitated prosody: pitch σ {pro['f0_std']} Hz, energy {pro['rms_mean']}")
    if fraud["signature"]:
        explain.append(f"script pattern: {fraud['signature']}")
    lit = [c for c, v in fraud["categories"].items() if v >= 0.4]
    if lit:
        terms = sorted({m['term'] for m in fraud['matches']})[:5]
        explain.append(f"fraud cues ({', '.join(lit)}): {', '.join(terms)}")
    if rate_term >= 0.4:
        explain.append(f"hurried speech: {tr['words_per_sec']} words/s")
    if not explain:
        explain.append("no distress or fraud cues in this window")

    return WindowResult(
        t_start=round(t_start, 2), t_end=round(t_start + len(audio) / SR, 2),
        emotion=emo, prosody=pro, transcript=tr["text"], transcript_redacted=redact(tr["text"]),
        language=tr["language"], fraud=fraud, distress=round(distress, 3), urgency=urgency,
        level=level_for(urgency), explain=explain, latency_ms=int((time.perf_counter() - t0) * 1000),
    )


def analyze_file(data: bytes, window_s: float = 3.0, language: str | None = None) -> dict:
    audio = decode_to_pcm16k(data)
    n = int(window_s * SR)
    windows = []
    for i in range(0, max(1, len(audio)), n):
        chunk = audio[i:i + n]
        if len(chunk) < SR * 0.6:  # ignore a sub-0.6 s tail
            break
        windows.append(analyze_window(chunk, t_start=i / SR, language=language).to_dict())
    return summarize(windows, duration=len(audio) / SR)


def summarize(windows: list[dict], duration: float) -> dict:
    if not windows:
        return {"duration": duration, "windows": [], "overall": {"urgency": 0, "level": "low", "signature": None, "explain": ["no speech"]}}
    # peak-weighted: a single critical window matters more than the average
    urg = [w["urgency"] for w in windows]
    overall_u = int(round(0.6 * max(urg) + 0.4 * (sum(urg) / len(urg))))
    sigs = [w["fraud"]["signature"] for w in windows if w["fraud"]["signature"]]
    sig = max(set(sigs), key=sigs.count) if sigs else None
    explain = []
    seen = set()
    for w in sorted(windows, key=lambda x: -x["urgency"])[:3]:
        for e in w["explain"]:
            if e not in seen and not e.startswith("no distress"):
                seen.add(e)
                explain.append(f"[{int(w['t_start'])}s] {e}")
    full = " ".join(w["transcript"] for w in windows if w["transcript"]).strip()
    return {
        "duration": round(duration, 2),
        "windows": windows,
        "overall": {"urgency": overall_u, "level": level_for(overall_u), "signature": sig,
                    "explain": explain or ["no distress or fraud cues detected"],
                    "transcript": full, "transcript_redacted": redact(full),
                    "avg_latency_ms": int(sum(w["latency_ms"] for w in windows) / len(windows))},
    }
