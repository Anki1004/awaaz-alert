"""
Hinglish fraud-script lexicon for Indian cybercrime calls (1930 helpline context).

Each pattern is a regex matched case-insensitively against the transcript (Devanagari or
romanised). Categories map to how Indian scam scripts are actually built:
  impersonation  -> "main CBI/ED/police/bank se bol raha hoon"
  threat         -> arrest, case, warrant, account block
  payment        -> OTP, UPI, transfer, gift card
  urgency        -> abhi, turant, 2 ghante mein
  secrecy        -> kisi ko mat batana, phone mat kaatna
  victim_loss    -> paisa kat gaya, account khali   (victim-side distress words)
Weights are per category hit (capped), so a long call cannot inflate the score by repetition.
"""
import re

PATTERNS = {
    "impersonation": [
        (r"\b(cbi|c\.b\.i|ed\b|enforcement|narcotics|ncb|trai|rbi|sebi|customs|income tax|police|crime branch|cyber cell|interpol)\b", 1.0),
        (r"(सीबीआई|पुलिस|क्राइम ब्रांच|कस्टम|आरबीआई|ट्राई|नारकोटिक्स|इनकम टैक्स)", 1.0),
        (r"\b(bank (se|manager|officer)|sbi|hdfc|icici|axis|pnb|kotak)\b", 0.7),
        (r"\b(fedex|dhl|blue ?dart|courier|parcel|package)\b", 0.8),
        (r"(कूरियर|पार्सल|पैकेज)", 0.8),
        (r"\b(digital arrest|video call (par|pe|me|mein)|skype|arrest)\b", 1.0),
        (r"(डिजिटल अरेस्ट|गिरफ्तार|वीडियो कॉल)", 1.0),
    ],
    "threat": [
        (r"\b(arrest|warrant|case (darj|register|file)|fir\b|jail|court|summon|non[- ]?bailable)\b", 1.0),
        (r"(गिरफ्तार|वारंट|केस|जेल|कोर्ट|समन|एफआईआर)", 1.0),
        (r"\b(account|sim|aadhaar|aadhar|card) (block|suspend|band|freeze)", 0.9),
        (r"(ब्लॉक|सस्पेंड|बंद हो जाएगा|फ्रीज)", 0.9),
        (r"\b(drugs|narcotics|money laundering|illegal|terror|hawala)\b", 0.9),
        (r"(ड्रग्स|मनी लॉन्ड्रिंग|गैरकानूनी|हवाला)", 0.9),
    ],
    "payment": [
        (r"\b(otp|one time password|pin\b|cvv|password)\b", 1.0),
        (r"(ओटीपी|पासवर्ड|पिन)", 1.0),
        (r"\b(upi|paytm|phonepe|google ?pay|gpay|transfer|rtgs|neft|imps)\b", 0.8),
        (r"(ट्रांसफर|यूपीआई|पेटीएम|फोनपे)", 0.8),
        (r"\b(gift ?card|crypto|bitcoin|usdt|wallet|verification (fee|amount)|processing fee|security deposit|refundable)\b", 0.9),
        (r"(गिफ्ट कार्ड|क्रिप्टो|वॉलेट|वेरिफिकेशन फीस|प्रोसेसिंग फीस|सिक्योरिटी डिपॉजिट|रिफंड)", 0.9),
        (r"\b(anydesk|teamviewer|quick ?support|screen share|app (install|download) kar)\b", 1.0),
        (r"(एनीडेस्क|स्क्रीन शेयर|ऐप डाउनलोड)", 1.0),
        (r"\b(lottery|lucky draw|prize|kbc|jackpot|task|part[- ]time job|investment|trading tips|double)\b", 0.7),
        (r"(लॉटरी|लकी ड्रॉ|इनाम|केबीसी|टास्क|पार्ट टाइम|निवेश|डबल)", 0.7),
    ],
    "urgency": [
        (r"\b(abhi|turant|jaldi|immediately|urgent|right now|within|2 ghante|10 minute|aaj hi|last chance|deadline)\b", 0.8),
        (r"(अभी|तुरंत|जल्दी|अर्जेंट|दो घंटे|दस मिनट|आज ही|आखिरी मौका)", 0.8),
    ],
    "secrecy": [
        (r"\b(kisi ko (mat|nahi) bata|phone (mat|nahi) (kaat|rakh)|line (par|pe) (raho|rahiye)|confidential|secret|gupt)\b", 1.0),
        (r"(किसी को मत बता|फोन मत काट|लाइन पर रह|गोपनीय|गुप्त)", 1.0),
    ],
    "victim_loss": [
        (r"\b(paise? (kat|chale|nikal|gaye|gaya|cut)|account (khali|empty)|loot|fraud ho gaya|thag|dhokha|scam ho gaya)\b", 1.0),
        (r"(पैसे कट|पैसे निकल|पैसे चले गए|अकाउंट खाली|लूट|ठग|धोखा|फ्रॉड हो गया)", 1.0),
        (r"\b(bacha ?lo|help (karo|kijiye)|please|madad|kya karu|kya karoon|ro (raha|rahi))\b", 0.6),
        (r"(बचा लो|मदद|क्या करूं|क्या करूँ|रो रह)", 0.6),
    ],
}

CATEGORY_WEIGHT = {
    "impersonation": 0.25,
    "threat": 0.25,
    "payment": 0.25,
    "urgency": 0.10,
    "secrecy": 0.10,
    "victim_loss": 0.20,
}

_COMPILED = {
    cat: [(re.compile(p, re.IGNORECASE), w) for p, w in pats]
    for cat, pats in PATTERNS.items()
}

# Well-known composite scripts; matching ≥2 categories of one pattern names the scam for the operator.
SCAM_SIGNATURES = [
    ("Digital arrest", {"impersonation", "threat"}, r"digital arrest|डिजिटल अरेस्ट|video call|cbi|police|parcel|courier|कूरियर|पार्सल"),
    ("Bank/KYC block", {"impersonation", "payment"}, r"kyc|block|otp|ओटीपी|ब्लॉक|bank|बैंक"),
    ("Task / investment scam", {"payment"}, r"task|investment|trading|double|टास्क|निवेश|डबल|telegram"),
    ("Lottery / prize", {"payment"}, r"lottery|kbc|prize|lucky|लॉटरी|केबीसी|इनाम"),
    ("Remote-access takeover", {"payment"}, r"anydesk|teamviewer|screen share|एनीडेस्क|स्क्रीन शेयर"),
]


def scan(text: str) -> dict:
    """Return per-category scores (0..1), matched terms, and a named scam signature if any."""
    if not text:
        return {"score": 0.0, "categories": {}, "matches": [], "signature": None}
    cats, matches = {}, []
    for cat, pats in _COMPILED.items():
        total = 0.0
        for rx, w in pats:
            for m in rx.finditer(text):
                total += w
                matches.append({"category": cat, "term": m.group(0), "start": m.start(), "end": m.end()})
        cats[cat] = min(1.0, total / 2.0)  # two strong hits saturate a category
    score = min(1.0, sum(cats[c] * CATEGORY_WEIGHT[c] for c in cats) / 0.6)  # ~3 categories lit = 1.0
    signature = None
    hit_cats = {c for c, v in cats.items() if v >= 0.4}
    for name, needed, rx in SCAM_SIGNATURES:
        if needed.issubset(hit_cats) and re.search(rx, text, re.IGNORECASE):
            signature = name
            break
    return {"score": round(score, 3), "categories": {k: round(v, 3) for k, v in cats.items()}, "matches": matches, "signature": signature}


# PII redaction — operator can toggle; the raw transcript never leaves the process when on.
_PII = [
    (re.compile(r"(\+91[\s-]?)?\b[6-9]\d{9}\b"), "[PHONE]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[AADHAAR]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[CARD]"),
    (re.compile(r"\b[\w.\-]{2,}@[a-z]{2,}\b", re.IGNORECASE), "[UPI]"),
    (re.compile(r"\b(otp|ओटीपी)\D{0,12}(\d{4,6})\b", re.IGNORECASE), r"\1 [OTP]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN]"),
]


def redact(text: str) -> str:
    for rx, rep in _PII:
        text = rx.sub(rep, text)
    return text
