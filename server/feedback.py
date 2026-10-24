"""
Operator feedback store: this is how a deployment earns its own evaluation set. For every window or call the
operator can say agree / too_high / too_low / missed_scam / false_alarm. Rows hold NUMBERS and the verdict, never
audio; the redacted transcript line is kept only when AWAAZ_STORE_TEXT=1.

  python export_feedback.py data/feedback.db > feedback.csv     # input for the evaluation in docs/PILOT.md
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

VERDICTS = ("agree", "too_high", "too_low", "missed_scam", "false_alarm")
SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, operator TEXT NOT NULL,
  session_id TEXT, line_id TEXT, scope TEXT NOT NULL CHECK(scope IN ('window','call')),
  t_start REAL, urgency INTEGER, level TEXT, signature TEXT, language TEXT,
  verdict TEXT NOT NULL, note TEXT, text_redacted TEXT
);
"""


class FeedbackStore:
    def __init__(self, path: Path, store_text: bool = False):
        self.path, self.store_text = Path(path), store_text
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path, timeout=10)

    def add(self, operator: str, verdict: str, scope: str = "call", session_id=None, line_id=None, t_start=None,
            urgency=None, level=None, signature=None, language=None, note=None, text_redacted=None) -> int:
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}")
        if scope not in ("window", "call"):
            raise ValueError("scope must be 'window' or 'call'")
        note = (note or "")[:500] or None
        text = (text_redacted or "")[:2000] if self.store_text else None
        with self.lock, self._conn() as c:
            cur = c.execute(
                "INSERT INTO feedback(ts,operator,session_id,line_id,scope,t_start,urgency,level,signature,language,verdict,note,text_redacted)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), operator, session_id, line_id, scope, t_start, urgency, level, signature, language, verdict, note, text))
            return cur.lastrowid

    def summary(self) -> dict:
        with self._conn() as c:
            rows = c.execute("SELECT verdict, COUNT(*) FROM feedback GROUP BY verdict").fetchall()
            by_level = c.execute("SELECT level, verdict, COUNT(*) FROM feedback WHERE scope='call' GROUP BY level, verdict").fetchall()
        total = sum(n for _, n in rows)
        return {"total": total, "by_verdict": dict(rows),
                "agree_rate": round(dict(rows).get("agree", 0) / total, 3) if total else None,
                "by_level": [{"level": lv, "verdict": v, "n": n} for lv, v, n in by_level]}
