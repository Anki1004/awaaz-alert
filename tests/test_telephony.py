import numpy as np
import pytest

import telephony as T


def _sine(freq=440, secs=1.0, rate=8000, amp=12000):
    t = np.arange(int(secs * rate)) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.int16)


def _snr_db(ref, got):
    n = min(len(ref), len(got))
    ref, got = ref[:n].astype(np.float64), got[:n].astype(np.float64)
    return 10 * np.log10((ref ** 2).sum() / max(1e-9, ((ref - got) ** 2).sum()))


def test_ulaw_known_values():
    assert T.decode_g711(bytes([0xFF]), "pcmu")[0] == 0
    assert T.decode_g711(bytes([0x7F]), "pcmu")[0] == 0              # negative zero
    assert T.decode_g711(bytes([0x00]), "pcmu")[0] == -32124
    assert T.decode_g711(bytes([0x80]), "pcmu")[0] == 32124


def test_ulaw_roundtrip_quality():
    x = _sine()
    y = T.decode_g711(T.encode_ulaw(x), "pcmu")
    assert _snr_db(x, y) > 30                                       # G.711 is ~38 dB for a full-scale tone


def test_alaw_is_antisymmetric_and_monotonic():
    tbl = T.decode_g711(bytes(range(256)), "pcma").astype(int)
    # A-law bytes 0x80..0xFF are the positive half, 0x00..0x7F the negative half; magnitudes must match pairwise
    assert (tbl[0x80:] == -tbl[0x00:0x80]).all()
    assert (np.diff(tbl[0x80:0x100][np.argsort(tbl[0x80:0x100])]) >= 0).all()


def test_resample_8k_to_16k_length_and_level():
    x = _sine(rate=8000)
    out = T.to_float16k(T.encode_ulaw(x), "pcmu", 8000)
    assert out.dtype == np.float32 and abs(len(out) - 16000) <= 2
    assert 0.3 < np.abs(out).max() < 0.5                           # 12000/32768 = 0.366 survives resampling


def test_pcm16_odd_byte_is_tolerated():
    out = T.to_float16k(b"\x00\x10" * 160 + b"\x01", "pcm16", 16000)
    assert len(out) == 160


def test_rejects_unknown_codec_and_rate():
    with pytest.raises(ValueError):
        T.to_float16k(b"\x00", "opus", 8000)
    with pytest.raises(ValueError):
        T.to_float16k(b"\x00", "pcmu", 11025)


def test_stream_buffer_waits_for_minimum_audio():
    sb = T.StreamBuffer("pcmu", 8000, min_ms=200)
    frame = T.encode_ulaw(_sine(secs=0.02))                        # one 20 ms RTP frame = 160 bytes
    assert sb.push(frame) is None
    got = None
    for _ in range(12):
        out = sb.push(frame)
        got = out if out is not None else got
    assert got is not None and len(got) >= 3200                    # >= 200 ms at 16 kHz
