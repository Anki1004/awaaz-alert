"""
Runtime configuration, all from environment variables so one image serves demo and production.

  AWAAZ_MODE=demo         (default) open API, bundled samples, any origin. Never expose this to a network.
  AWAAZ_MODE=production   refuses to start without API keys; samples/replay/docs disabled; CORS limited;
                          audit log + feedback store required to be writable.

  AWAAZ_API_KEYS      "key1:operatorA,key2:operatorB"   (each key maps to an accountable operator id)
  AWAAZ_ORIGINS       comma list of allowed browser origins (production)
  AWAAZ_MAX_SESSIONS  concurrent live streams admitted (default 2 = what one RTX 4060 laptop GPU sustained; measure with bench_capacity.py on YOUR GPU)
  AWAAZ_MAX_UPLOAD_MB largest recording /analyze accepts (default 25)
  AWAAZ_RATE_PER_MIN  /analyze + /feedback calls per key per minute (default 30)
  AWAAZ_DATA_DIR      where audit.jsonl and feedback.db live (default ./data). Audio and transcripts are never written.
  AWAAZ_STORE_TEXT=1  also keep the REDACTED transcript line in feedback rows (default off)
  AWAAZ_REVEAL_OPERATORS  comma list of operator ids allowed to receive the UNREDACTED transcript (production default:
                      nobody). Everyone else is sent redacted text only; the raw text never leaves the server for them.
"""
from __future__ import annotations

import os
from pathlib import Path

MODE = os.environ.get("AWAAZ_MODE", "demo").strip().lower()
PRODUCTION = MODE == "production"
WINDOW_S = float(os.environ.get("AWAAZ_WINDOW", "3.0"))
MAX_SESSIONS = int(os.environ.get("AWAAZ_MAX_SESSIONS", "2"))
MAX_UPLOAD_BYTES = int(float(os.environ.get("AWAAZ_MAX_UPLOAD_MB", "25")) * 1024 * 1024)
RATE_PER_MIN = int(os.environ.get("AWAAZ_RATE_PER_MIN", "30"))
STORE_TEXT = os.environ.get("AWAAZ_STORE_TEXT", "0") == "1"
DATA_DIR = Path(os.environ.get("AWAAZ_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))
REVEAL_OPERATORS = {o.strip() for o in os.environ.get("AWAAZ_REVEAL_OPERATORS", "").split(",") if o.strip()}
ORIGINS = [o.strip() for o in os.environ.get("AWAAZ_ORIGINS", "").split(",") if o.strip()]


def parse_keys(raw: str | None = None) -> dict[str, str]:
    """'k1:opA,k2:opB' -> {'k1': 'opA', 'k2': 'opB'}. A key with no ':' maps to the operator id 'operator'."""
    raw = os.environ.get("AWAAZ_API_KEYS", "") if raw is None else raw
    out: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        key, _, op = part.partition(":")
        out[key.strip()] = (op.strip() or "operator")
    return out


API_KEYS = parse_keys()


def validate() -> list[str]:
    """Problems that must stop a production start. Demo mode never fails."""
    problems = []
    if not PRODUCTION:
        return problems
    if not API_KEYS:
        problems.append("AWAAZ_API_KEYS is empty: production mode needs at least one operator key")
    if any(len(k) < 24 for k in API_KEYS):
        problems.append("API keys must be at least 24 characters (python -c \"import secrets;print(secrets.token_urlsafe(32))\")")
    if "*" in ORIGINS or not ORIGINS:
        problems.append("AWAAZ_ORIGINS must list the exact browser origin(s) of the operator console, not '*' or empty")
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = DATA_DIR / ".write-test"
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        problems.append(f"AWAAZ_DATA_DIR {DATA_DIR} is not writable: {e}")
    return problems
