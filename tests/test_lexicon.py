"""Lexicon regression tests. These pin behaviour we decided on; they are not accuracy claims (see README stress test)."""
import pytest

import fraud_lexicon as L


def cats(text, floor=0.4):
    r = L.scan(text)
    return {c for c, v in r["categories"].items() if v >= floor}, r


@pytest.mark.parametrize("text,name", [
    ("CBI officer bol raha hoon, aapke naam se parcel mein drugs mile hain, digital arrest hai, video call par rahiye", "Digital arrest"),
    ("SBI bank manager bol raha hoon, KYC pending hai, account block ho jayega, OTP bata dijiye", "Bank/KYC block"),
    ("AnyDesk download karke screen share kijiye, hum UPI transfer kar denge", "Remote-access takeover"),
])
def test_named_scam_signatures(text, name):
    assert L.scan(text)["signature"] == name


@pytest.mark.parametrize("text", [
    "Namaste, online complaint ka status kaise check karte hain",
    "Mujhe passport verification ke liye police station ka address chahiye",
    "Hello, I wanted to know the working hours of the cyber crime helpline",
])
def test_ordinary_calls_have_no_signature_and_low_score(text):
    r = L.scan(text)
    assert r["signature"] is None and r["score"] < 0.25


@pytest.mark.parametrize("text", [
    "mere account se do lakh rupaye nikal gaye",
    "kisi ne mere paise transfer kar liye",
    "maine OTP bata diya aur paisa kat gaya",
    "मेरे अकाउंट से पचास हजार रुपए निकल गए",
])
def test_past_tense_loss_reports_count_as_victim_loss(text):
    assert L.scan(text)["categories"]["victim_loss"] >= 0.5


@pytest.mark.parametrize("text", [
    "aapko paisa transfer karna hoga abhi",
    "OTP bata dijiye turant",
    "apne account ka paisa RBI ke safe account mein transfer karo",
    "आपको पैसे ट्रांसफर करने होंगे",
])
def test_scammer_demands_are_not_loss_reports(text):
    """A demand ('transfer karna hoga', 'bata dijiye') is the scammer talking, not a victim reporting a loss."""
    assert L.scan(text)["categories"]["victim_loss"] < 0.5


def test_redaction_masks_phone_aadhaar_and_otp_digits():
    out = L.redact("mera number 9876543210 hai, aadhaar 1234 5678 9012, otp 482915 hai")
    for digits in ("9876543210", "1234 5678 9012", "482915"):
        assert digits not in out
