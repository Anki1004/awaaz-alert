"""Test harness. Production-mode environment is set BEFORE the server modules are imported; model loading is stubbed
so the suite runs in seconds on a machine with no GPU (real-model behaviour is covered by server/eval*.py)."""
import os
import sys
import tempfile
from pathlib import Path

DATA = tempfile.mkdtemp(prefix="awaaz-test-")
os.environ.update({
    "AWAAZ_MODE": "production",
    "AWAAZ_API_KEYS": "test-key-aaaaaaaaaaaaaaaaaaaaaaaa:op-alice,test-key-bbbbbbbbbbbbbbbbbbbbbbbb:op-bob",
    "AWAAZ_ORIGINS": "https://console.example.gov.in",
    "AWAAZ_DATA_DIR": DATA,
    "AWAAZ_MAX_SESSIONS": "2",
    "AWAAZ_RATE_PER_MIN": "1000",
    "AWAAZ_MAX_UPLOAD_MB": "1",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

KEY_A = "test-key-aaaaaaaaaaaaaaaaaaaaaaaa"
KEY_B = "test-key-bbbbbbbbbbbbbbbbbbbbbbbb"
