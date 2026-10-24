"""
Telephony ingest helpers. A helpline's media arrives as 8 kHz G.711 (mu-law in India's carriers' SBCs is common, A-law
in some trunks), forked from the call by an SBC / FreeSWITCH / Asterisk (mod_audio_fork, AudioSocket, ExternalMedia)
and sent to /ws/ingest as binary frames. This module turns those frames into the 16 kHz float32 the pipeline wants.

Supported codecs:  pcmu (G.711 mu-law) · pcma (G.711 A-law) · pcm16 (signed 16-bit little-endian)
Supported rates:   any of 8000 / 16000 / 24000 / 48000 (resampled to 16 kHz)

One stream = ONE speaker channel. Do not mix caller and operator into one channel; if the gateway can fork the legs
separately, send the caller leg only (and open a second ingest for the operator leg only if you want it at all).
"""
from __future__ import annotations

from math import gcd

import numpy as np
from scipy.signal import resample_poly

TARGET_SR = 16000
CODECS = ("pcmu", "pcma", "pcm16")
RATES = (8000, 16000, 24000, 48000)


def _build_ulaw_table() -> np.ndarray:
    t = np.empty(256, dtype=np.int16)
    for i in range(256):
        u = ~i & 0xFF
        sign, exp, mant = u & 0x80, (u >> 4) & 0x07, u & 0x0F
        val = (((mant << 3) + 0x84) << exp) - 0x84
        t[i] = -val if sign else val
    return t


def _build_alaw_table() -> np.ndarray:
    t = np.empty(256, dtype=np.int16)
    for i in range(256):
        a = i ^ 0x55
        sign, exp, mant = a & 0x80, (a >> 4) & 0x07, a & 0x0F
        val = (mant << 4) + 8 if exp == 0 else ((mant << 4) + 0x108) << (exp - 1)
        t[i] = val if sign else -val
    return t


_ULAW = _build_ulaw_table()
_ALAW = _build_alaw_table()


def decode_g711(data: bytes, codec: str) -> np.ndarray:
    """G.711 bytes -> int16 samples (8 kHz)."""
    tbl = _ULAW if codec == "pcmu" else _ALAW
    return tbl[np.frombuffer(data, dtype=np.uint8)]


def encode_ulaw(pcm: np.ndarray) -> bytes:
    """int16 -> mu-law bytes. Used by tests and the capacity benchmark to build realistic telephone frames."""
    x = np.clip(pcm.astype(np.int32), -32635, 32635)
    sign = np.where(x < 0, 0x80, 0)
    mag = np.abs(x) + 0x84
    exp = np.clip(np.floor(np.log2(np.maximum(mag, 1))).astype(np.int32) - 7, 0, 7)
    mant = (mag >> (exp + 3)) & 0x0F
    return (~(sign | (exp << 4) | mant) & 0xFF).astype(np.uint8).tobytes()


def to_float16k(frame: bytes, codec: str, rate: int) -> np.ndarray:
    """Decode one binary frame and return float32 mono at 16 kHz in [-1, 1]. Stateless per frame: a polyphase
    resampler's edge ripple on 20 ms frames is why the caller should buffer >= 100 ms before calling this."""
    if codec not in CODECS:
        raise ValueError(f"unsupported codec {codec!r}; use one of {CODECS}")
    if rate not in RATES:
        raise ValueError(f"unsupported sample rate {rate}; use one of {RATES}")
    if codec == "pcm16":
        if len(frame) % 2:
            frame = frame[:-1]
        pcm = np.frombuffer(frame, dtype="<i2")
    else:
        pcm = decode_g711(frame, codec)
    x = pcm.astype(np.float32) / 32768.0
    if rate != TARGET_SR:
        g = gcd(TARGET_SR, rate)
        x = resample_poly(x, TARGET_SR // g, rate // g).astype(np.float32)
    return x


class StreamBuffer:
    """Accumulates frames until >= min_ms of audio is available, so resampling edges are not inserted every 20 ms."""

    def __init__(self, codec: str, rate: int, min_ms: int = 200):
        self.codec, self.rate = codec, rate
        self.bytes_per_ms = (rate / 1000.0) * (2 if codec == "pcm16" else 1)
        self.min_bytes = int(self.bytes_per_ms * min_ms)
        self.pending = b""

    def push(self, frame: bytes) -> np.ndarray | None:
        self.pending += frame
        if len(self.pending) < self.min_bytes:
            return None
        if self.codec == "pcm16" and len(self.pending) % 2:
            data, self.pending = self.pending[:-1], self.pending[-1:]
        else:
            data, self.pending = self.pending, b""
        return to_float16k(data, self.codec, self.rate)
