import json

import pytest

from audit import AuditLog, verify


def test_chain_verifies_and_survives_restart(tmp_path):
    p = tmp_path / "audit.jsonl"
    a = AuditLog(p)
    a.append("session_start", "alice", session="s1")
    a.append("session_end", "alice", session="s1", peak_urgency=64)
    assert verify(p)[:2] == (True, 2)
    b = AuditLog(p)                       # restart continues the same chain
    b.append("feedback", "bob", verdict="agree")
    ok, n, _ = verify(p)
    assert ok and n == 3


def test_edited_line_is_detected(tmp_path):
    p = tmp_path / "audit.jsonl"
    a = AuditLog(p)
    for i in range(4):
        a.append("e", "alice", i=i)
    lines = p.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1]); rec["data"]["i"] = 99
    lines[1] = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, n, _ = verify(p)
    assert not ok and n == 2


def test_deleted_line_is_detected(tmp_path):
    p = tmp_path / "audit.jsonl"
    a = AuditLog(p)
    for i in range(4):
        a.append("e", "alice", i=i)
    lines = p.read_text(encoding="utf-8").splitlines()
    del lines[1]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not verify(p)[0]


def test_refuses_to_append_to_a_tampered_log(tmp_path):
    p = tmp_path / "audit.jsonl"
    a = AuditLog(p)
    a.append("e", "alice")
    a.append("e", "alice")
    p.write_text(p.read_text(encoding="utf-8").replace("alice", "mallory", 1), encoding="utf-8")
    with pytest.raises(RuntimeError):
        AuditLog(p)


def test_audit_never_carries_call_content_fields():
    """Guard against someone later passing transcript text into the audit trail."""
    import main
    src = open(main.__file__, encoding="utf-8").read()
    for line in src.splitlines():
        if "_audit(" in line and "def _audit" not in line:
            assert "transcript" not in line and "text" not in line.replace("text_redacted", "")
