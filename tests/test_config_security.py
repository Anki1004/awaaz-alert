import config
import security
from conftest import KEY_A, KEY_B


def test_parse_keys():
    assert config.parse_keys("a:op1, b:op2 ,c") == {"a": "op1", "b": "op2", "c": "operator"}
    assert config.parse_keys("") == {}


def test_production_refuses_unsafe_config(monkeypatch):
    monkeypatch.setattr(config, "PRODUCTION", True)
    monkeypatch.setattr(config, "API_KEYS", {})
    monkeypatch.setattr(config, "ORIGINS", ["*"])
    problems = config.validate()
    assert any("API_KEYS" in p for p in problems)
    assert any("ORIGINS" in p for p in problems)
    monkeypatch.setattr(config, "API_KEYS", {"short": "op"})
    assert any("24 characters" in p for p in config.validate())


def test_demo_mode_never_fails_validation(monkeypatch):
    monkeypatch.setattr(config, "PRODUCTION", False)
    monkeypatch.setattr(config, "API_KEYS", {})
    assert config.validate() == []


def test_operator_lookup():
    assert security.operator_for(KEY_A) == "op-alice"
    assert security.operator_for(KEY_B) == "op-bob"
    assert security.operator_for("nope") is None
    assert security.operator_for(None) is None
    assert security.operator_for("") is None


def test_bearer_parsing():
    assert security.bearer("Bearer abc") == "abc"
    assert security.bearer("bearer  abc ") == "abc"
    assert security.bearer("Basic abc") is None
    assert security.bearer(None) is None


def test_rate_limiter_blocks_after_quota():
    rl = security.RateLimiter(3)
    assert [rl.allow("alice") for _ in range(5)] == [True, True, True, False, False]
    assert rl.allow("bob")                                          # per-operator buckets
