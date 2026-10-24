"""
Tamper-evident audit trail: one JSON line per event, each carrying the SHA-256 of the previous line, so an edited,
deleted or reordered line breaks the chain (`python audit.py verify data/audit.jsonl`).

What is logged: who (operator id), what (session start/end, upload analysed, feedback given), when, and aggregate
numbers (duration, peak priority, level, named script, language). What is NEVER logged: audio, transcripts, phone
numbers, caller identity. An audit log that contained call content would itself be the breach.

Limit, stated plainly: a hash chain detects edits, it does not prevent them. Someone with write access can rewrite
the whole file consistently. For real assurance ship the lines to an append-only external store (WORM bucket / SIEM)
and anchor the latest hash somewhere the operator account cannot write.
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from pathlib import Path

GENESIS = "0" * 64


def _canon(rec: dict) -> str:
    return json.dumps(rec, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.seq, self.prev = 0, GENESIS
        if self.path.exists() and self.path.stat().st_size:
            ok, n, last = verify(self.path)
            if not ok:
                raise RuntimeError(f"audit log {self.path} fails verification at line {n}; refusing to append")
            self.seq, self.prev = n, last

    def append(self, event: str, operator: str, **fields) -> dict:
        with self.lock:
            rec = {"seq": self.seq + 1, "ts": round(time.time(), 3), "event": event, "operator": operator, "data": fields, "prev": self.prev}
            rec["hash"] = hashlib.sha256(_canon(rec).encode("utf-8")).hexdigest()
            with self.path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(_canon(rec) + "\n")
            self.seq, self.prev = rec["seq"], rec["hash"]
            return rec


def verify(path: Path) -> tuple[bool, int, str]:
    """-> (ok, lines_checked_or_first_bad_line, last_hash)."""
    prev, n = GENESIS, 0
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            n += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                return False, n, prev
            h = rec.pop("hash", None)
            if rec.get("prev") != prev or rec.get("seq") != n:
                return False, n, prev
            if hashlib.sha256(_canon(rec).encode("utf-8")).hexdigest() != h:
                return False, n, prev
            prev = h
    return True, n, prev


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "verify":
        ok, n, _ = verify(Path(sys.argv[2]))
        print(("OK" if ok else "TAMPERED"), f"- {n} line(s) checked")
        sys.exit(0 if ok else 1)
    print("usage: python audit.py verify <audit.jsonl>")
    sys.exit(2)
